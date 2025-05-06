#!/usr/bin/env python3
"""
BlinkScoring ML Trainer

This module is responsible for:
1. Loading historical repayment data
2. Training a new ML model
3. Evaluating the model against the current production model
4. Promoting the new model to production if it's better
"""
import os
import sys
import json
import uuid
import logging
import traceback
from pathlib import Path
from datetime import datetime
import pickle
import numpy as np
import pandas as pd

# Add the parent directory to the path so we can import common
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.db import execute_query, get_active_model_info, get_feature_store_snapshots

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
MODEL_DIR = os.getenv("MODEL_DIR", "models")
REQUIRED_TRAINING_SAMPLES = int(os.getenv("REQUIRED_TRAINING_SAMPLES", "500"))
PROMOTE_TO_PROD = os.getenv("PROMOTE_TO_PROD", "false").lower() == "true"
MIN_AUC_IMPROVEMENT = float(os.getenv("MIN_AUC_IMPROVEMENT", "0.01"))
FEATURE_LIST_PATH = os.path.join(MODEL_DIR, "feature_list.json")
SNAPSHOT_DAYS = int(os.getenv("SNAPSHOT_DAYS", "90"))

try:
    import lightgbm as lgb
    import shap
    from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, f1_score
    from sklearn.model_selection import train_test_split
    ML_LIBRARIES_AVAILABLE = True
except ImportError:
    logger.warning("ML libraries not available, will use dummy training")
    ML_LIBRARIES_AVAILABLE = False

def get_repayment_data(days=SNAPSHOT_DAYS):
    """
    Get repayment data from the database
    
    Returns:
        DataFrame with feature snapshots and whether the advance was repaid
    """
    query = """
    WITH advance_outcomes AS (
        SELECT 
            a.id as advance_id,
            a.user_id,
            a.created_at as advance_date,
            a.amount,
            CASE 
                WHEN successful_repayments.count = required_repayments.count
                THEN TRUE 
                ELSE FALSE 
            END as fully_repaid,
            successful_repayments.count as successful_count,
            required_repayments.count as required_count
        FROM advances a
        LEFT JOIN LATERAL (
            SELECT COUNT(*) as count
            FROM advance_repayments ar
            WHERE ar.advance_id = a.id
            AND ar.status = 'COMPLETED'
        ) successful_repayments ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) as count
            FROM advance_repayments ar
            WHERE ar.advance_id = a.id
        ) required_repayments ON TRUE
        WHERE a.created_at >= NOW() - INTERVAL '%(days)s days'
    ),
    feature_data AS (
        SELECT 
            fs.user_id,
            fs.snapshot_id,
            fs.decision_ts,
            fs.json_features
        FROM feature_store_snapshots fs
        WHERE fs.created_at >= NOW() - INTERVAL '%(days)s days'
    )
    SELECT 
        ao.advance_id,
        ao.user_id,
        ao.advance_date,
        ao.amount,
        ao.fully_repaid,
        ao.successful_count,
        ao.required_count,
        fd.snapshot_id,
        fd.decision_ts,
        fd.json_features
    FROM advance_outcomes ao
    LEFT JOIN feature_data fd ON 
        ao.user_id = fd.user_id 
        AND fd.decision_ts <= ao.advance_date
        AND fd.decision_ts >= ao.advance_date - INTERVAL '1 day'
    WHERE fd.snapshot_id IS NOT NULL
    ORDER BY ao.advance_date DESC
    """
    
    params = {
        "days": days
    }
    
    results = execute_query(query, params)
    
    if not results:
        logger.warning("No repayment data found")
        return None
        
    # Convert to DataFrame
    df = pd.DataFrame(results)
    
    # Parse JSON features
    features_list = []
    for _, row in df.iterrows():
        features = json.loads(row["json_features"])
        features["advance_id"] = row["advance_id"]
        features["user_id"] = row["user_id"]
        features["advance_date"] = row["advance_date"]
        features["fully_repaid"] = row["fully_repaid"]
        features["amount"] = row["amount"]
        features_list.append(features)
    
    features_df = pd.DataFrame(features_list)
    
    return features_df

def prepare_training_data(df):
    """
    Prepare data for training
    
    Args:
        df: DataFrame with features and repayment outcomes
        
    Returns:
        X: Feature matrix
        y: Target labels
        feature_names: List of feature names
    """
    if df is None or len(df) < 10:
        logger.error("Not enough data for training")
        return None, None, None
    
    # Define target
    y = df["fully_repaid"].astype(int).values
    
    # Determine feature columns - exclude non-feature columns
    exclude_cols = [
        "advance_id", "user_id", "advance_date", "fully_repaid", 
        "amount", "successful_count", "required_count"
    ]
    
    feature_cols = [col for col in df.columns if col not in exclude_cols]
    
    # Check for missing features and fill them
    for col in feature_cols:
        if df[col].isnull().any():
            logger.info(f"Filling missing values in {col}")
            df[col] = df[col].fillna(df[col].median())
    
    # Create feature matrix
    X = df[feature_cols].values
    
    return X, y, feature_cols

def train_model(X_train, y_train, feature_names):
    """
    Train a LightGBM model
    
    Args:
        X_train: Training feature matrix
        y_train: Training labels
        feature_names: List of feature names
        
    Returns:
        Trained model
    """
    if not ML_LIBRARIES_AVAILABLE:
        logger.warning("ML libraries not available, returning dummy model")
        return DummyModel()
    
    try:
        # Create dataset
        train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_names)
        
        # Define parameters - focus on interpretability
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.9,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1
        }
        
        # Train model
        logger.info("Training LightGBM model")
        model = lgb.train(
            params,
            train_data,
            num_boost_round=100,
            valid_sets=[train_data],
            early_stopping_rounds=10,
            verbose_eval=20
        )
        
        return model
    except Exception as e:
        logger.error(f"Error training model: {e}")
        traceback.print_exc()
        return None

class DummyModel:
    """Dummy model for testing"""
    
    def __init__(self):
        self.feature_importances_ = [0.1] * 10
        
    def predict(self, X):
        """Return random predictions"""
        return np.random.random(len(X))
        
    def feature_importance(self):
        """Return dummy feature importances"""
        return self.feature_importances_

def evaluate_model(model, X_test, y_test, feature_names):
    """
    Evaluate a trained model
    
    Args:
        model: Trained model
        X_test: Test feature matrix
        y_test: Test labels
        feature_names: List of feature names
        
    Returns:
        Dictionary with evaluation metrics
    """
    if not ML_LIBRARIES_AVAILABLE:
        logger.warning("ML libraries not available, returning dummy metrics")
        return {
            "auc": 0.75,
            "accuracy": 0.8,
            "feature_importance": dict(zip(feature_names, [0.1] * len(feature_names)))
        }
    
    try:
        # Get predictions
        y_pred = model.predict(X_test)
        
        # Calculate AUC
        auc_score = roc_auc_score(y_test, y_pred)
        
        # Calculate precision-recall AUC
        precision, recall, _ = precision_recall_curve(y_test, y_pred)
        pr_auc = auc(recall, precision)
        
        # Get binary predictions using 0.5 threshold
        y_pred_binary = (y_pred > 0.5).astype(int)
        
        # Calculate accuracy
        accuracy = (y_pred_binary == y_test).mean()
        
        # Calculate F1 score
        f1 = f1_score(y_test, y_pred_binary)
        
        # Get feature importance
        feature_importance = model.feature_importance()
        importance_dict = dict(zip(feature_names, feature_importance))
        
        # Sort features by importance
        sorted_importance = sorted(
            importance_dict.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        return {
            "auc": auc_score,
            "pr_auc": pr_auc,
            "accuracy": accuracy,
            "f1_score": f1,
            "feature_importance": dict(sorted_importance)
        }
    except Exception as e:
        logger.error(f"Error evaluating model: {e}")
        traceback.print_exc()
        return None

def generate_feature_descriptions(feature_names, importance):
    """
    Generate human-readable descriptions for features
    
    Args:
        feature_names: List of feature names
        importance: Dictionary of feature importance values
        
    Returns:
        Dictionary mapping feature names to descriptions
    """
    descriptions = {}
    
    for feature in feature_names:
        if feature.startswith("metric_"):
            # Remove "metric_" prefix
            clean_name = feature[7:]
            
            # Convert snake_case to words
            words = clean_name.split("_")
            capitalized = [word.capitalize() for word in words]
            
            # Create description
            description = " ".join(capitalized)
            
            # Add impact
            if feature in importance:
                imp = importance[feature]
                if imp > 0:
                    description += f" (Positive impact on score)"
                else:
                    description += f" (Negative impact on score)"
            
            descriptions[feature] = description
        else:
            descriptions[feature] = feature
    
    return descriptions

def create_shap_explainer(model, X_train, feature_names):
    """
    Create a SHAP explainer for the model
    
    Args:
        model: Trained model
        X_train: Training feature matrix
        feature_names: List of feature names
        
    Returns:
        SHAP explainer object
    """
    if not ML_LIBRARIES_AVAILABLE:
        logger.warning("ML libraries not available, no SHAP explainer created")
        return None
        
    try:
        logger.info("Creating SHAP explainer")
        explainer = shap.TreeExplainer(model)
        
        # Test the explainer on a small sample
        sample_size = min(10, X_train.shape[0])
        sample_data = X_train[:sample_size]
        shap_values = explainer.shap_values(sample_data)
        
        logger.info(f"SHAP explainer created successfully, values shape: {np.array(shap_values).shape}")
        
        return explainer
    except Exception as e:
        logger.error(f"Error creating SHAP explainer: {e}")
        traceback.print_exc()
        return None

def save_model(model, explainer, feature_names, metrics, version_tag=None):
    """
    Save model and metadata to disk
    
    Args:
        model: Trained model
        explainer: SHAP explainer
        feature_names: List of feature names
        metrics: Dictionary of evaluation metrics
        version_tag: Optional version tag
        
    Returns:
        Path to saved model
    """
    # Create version tag if not provided
    if version_tag is None:
        date_str = datetime.now().strftime("%Y-%m-%d-%H%M")
        version_tag = f"v{metrics['auc']:.3f}-{date_str}"
    
    # Create directory for model
    model_path = os.path.join(MODEL_DIR, version_tag)
    os.makedirs(model_path, exist_ok=True)
    
    try:
        # Save model
        model_file = os.path.join(model_path, "model.txt")
        if isinstance(model, DummyModel):
            # Save dummy model
            with open(model_file, "w") as f:
                f.write("Dummy model for testing")
        else:
            # Save LightGBM model
            model.save_model(model_file)
        
        # Save model as treelite model for faster inference
        if not isinstance(model, DummyModel) and ML_LIBRARIES_AVAILABLE:
            import treelite
            import treelite.runtime
            
            treelite_model = treelite.Model.from_lightgbm(model)
            treelite_file = os.path.join(model_path, "model.tl")
            treelite_model.compile(dirpath=model_path)
            treelite_model.export_lib(toolchain="gcc", libpath=treelite_file)
        
        # Save SHAP explainer
        if explainer is not None:
            explainer_file = os.path.join(model_path, "shap_explainer.pkl")
            with open(explainer_file, "wb") as f:
                pickle.dump(explainer, f)
        
        # Save feature names
        feature_file = os.path.join(model_path, "features.json")
        with open(feature_file, "w") as f:
            json.dump(feature_names, f, indent=2)
        
        # Generate and save feature descriptions
        descriptions = generate_feature_descriptions(
            feature_names, 
            metrics.get("feature_importance", {})
        )
        
        desc_file = os.path.join(model_path, "feature_descriptions.json")
        with open(desc_file, "w") as f:
            json.dump(descriptions, f, indent=2)
        
        # Save metrics
        metrics_file = os.path.join(model_path, "metrics.json")
        with open(metrics_file, "w") as f:
            # Convert numpy values to Python types for JSON serialization
            serializable_metrics = {}
            for k, v in metrics.items():
                if k == "feature_importance":
                    serializable_metrics[k] = {
                        feature: float(imp) for feature, imp in v.items()
                    }
                elif isinstance(v, np.ndarray):
                    serializable_metrics[k] = v.tolist()
                elif isinstance(v, np.generic):
                    serializable_metrics[k] = v.item()
                else:
                    serializable_metrics[k] = v
                    
            json.dump(serializable_metrics, f, indent=2)
        
        # Create latest symlink
        latest_path = os.path.join(MODEL_DIR, "latest")
        if os.path.exists(latest_path):
            if os.path.islink(latest_path):
                os.unlink(latest_path)
            else:
                import shutil
                shutil.rmtree(latest_path)
                
        os.symlink(os.path.abspath(model_path), latest_path)
        
        logger.info(f"Model saved to {model_path}")
        return model_path
    except Exception as e:
        logger.error(f"Error saving model: {e}")
        traceback.print_exc()
        return None
        
def register_model_in_db(model_path, version_tag, metrics, promote_to_prod=False):
    """
    Register the model in the database
    
    Args:
        model_path: Path to saved model
        version_tag: Version tag
        metrics: Evaluation metrics
        promote_to_prod: Whether to promote the model to production
        
    Returns:
        The model_id if successful, None otherwise
    """
    # Get absolute path
    abs_path = os.path.abspath(model_path)
    
    # Create query
    query = """
    INSERT INTO blink_models (
        model_id, version_tag, artifact_url, train_auc, train_date, promoted_to_prod
    ) VALUES (
        gen_random_uuid(), %(version_tag)s, %(artifact_url)s, %(train_auc)s, NOW(), %(promoted_to_prod)s
    ) RETURNING model_id
    """
    
    params = {
        "version_tag": version_tag,
        "artifact_url": abs_path,
        "train_auc": metrics.get("auc", 0.5),
        "promoted_to_prod": promote_to_prod
    }
    
    try:
        result = execute_query(query, params)
        model_id = result[0]["model_id"] if result else None
        
        if model_id:
            logger.info(f"Model registered in database with ID {model_id}")
            
            # If promoting to production, demote other models
            if promote_to_prod:
                demote_query = """
                UPDATE blink_models
                SET promoted_to_prod = FALSE
                WHERE model_id != %(model_id)s
                """
                
                execute_query(demote_query, {"model_id": model_id})
                logger.info("Other models demoted from production")
                
        return model_id
    except Exception as e:
        logger.error(f"Error registering model in database: {e}")
        traceback.print_exc()
        return None

def should_promote_model(new_metrics, current_model_info):
    """
    Determine if the new model should be promoted to production
    
    Args:
        new_metrics: Metrics for the new model
        current_model_info: Information about the current production model
        
    Returns:
        Boolean indicating whether to promote
    """
    if current_model_info is None:
        logger.info("No current production model, will promote new model")
        return True
        
    current_auc = current_model_info.get("train_auc", 0)
    new_auc = new_metrics.get("auc", 0)
    
    logger.info(f"Current model AUC: {current_auc}, New model AUC: {new_auc}")
    
    # Promote if new model is better by at least MIN_AUC_IMPROVEMENT
    if new_auc - current_auc >= MIN_AUC_IMPROVEMENT:
        logger.info(f"New model AUC is better by {new_auc - current_auc:.4f}, will promote")
        return True
    else:
        logger.info(f"New model AUC is not significantly better, will not promote")
        return False

def main():
    """Main entry point for the trainer"""
    logger.info("BlinkScoring ML Trainer starting")
    
    try:
        # Create models directory if it doesn't exist
        os.makedirs(MODEL_DIR, exist_ok=True)
        
        # Get repayment data
        logger.info(f"Loading repayment data for the past {SNAPSHOT_DAYS} days")
        data = get_repayment_data(SNAPSHOT_DAYS)
        
        if data is None or len(data) < REQUIRED_TRAINING_SAMPLES:
            logger.error(f"Not enough training data. Required: {REQUIRED_TRAINING_SAMPLES}, Found: {0 if data is None else len(data)}")
            return
            
        logger.info(f"Loaded {len(data)} training samples")
        
        # Prepare data
        X, y, feature_names = prepare_training_data(data)
        
        if X is None:
            logger.error("Failed to prepare training data")
            return
            
        logger.info(f"Prepared training data with {X.shape[1]} features and {X.shape[0]} samples")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Train model
        model = train_model(X_train, y_train, feature_names)
        
        if model is None:
            logger.error("Failed to train model")
            return
            
        logger.info("Model training completed")
        
        # Evaluate model
        metrics = evaluate_model(model, X_test, y_test, feature_names)
        
        if metrics is None:
            logger.error("Failed to evaluate model")
            return
            
        logger.info(f"Model evaluation: AUC = {metrics['auc']:.4f}, Accuracy = {metrics['accuracy']:.4f}")
        
        # Create SHAP explainer
        explainer = create_shap_explainer(model, X_train, feature_names)
        
        # Generate version tag
        date_str = datetime.now().strftime("%Y-%m-%d")
        version_tag = f"v{metrics['auc']:.3f}-{date_str}"
        
        # Save model
        model_path = save_model(model, explainer, feature_names, metrics, version_tag)
        
        if model_path is None:
            logger.error("Failed to save model")
            return
            
        # Get current production model
        current_model = get_active_model_info()
        
        # Determine whether to promote to production
        promote = False
        if PROMOTE_TO_PROD:
            promote = should_promote_model(metrics, current_model)
            
        # Register model in database
        model_id = register_model_in_db(model_path, version_tag, metrics, promote)
        
        if model_id:
            logger.info(f"Model {version_tag} registered with ID {model_id}")
            if promote:
                logger.info(f"Model {version_tag} promoted to production")
        else:
            logger.error("Failed to register model in database")
            
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        traceback.print_exc()
    
    logger.info("BlinkScoring ML Trainer completed")

if __name__ == "__main__":
    main() 