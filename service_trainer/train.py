#!/usr/bin/env python3
"""
LightGBM training script for risk scoring model.
Extracts features from database, trains a model, and exports to both
native LightGBM and optimized Treelite formats.
"""
import os
import sys
import json
import uuid
import logging
import traceback
from pathlib import Path
import datetime as dt
from typing import Tuple
import pickle
import numpy as np
import pandas as pd
import lightgbm as lgb
import treelite
import sqlalchemy as sa
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, f1_score
from sklearn.model_selection import train_test_split

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

# Connection settings
DB_URL = os.getenv("DATABASE_URL")

# Feature columns based on risk_score_audits table
FEATURE_COLS = [
    'metric_observed_history_days',
    'metric_median_paycheck',
    'metric_paycheck_regularity', 
    'metric_days_since_last_paycheck',
    'metric_overdraft_count90',
    'metric_net_cash30',
    'metric_debt_load30',
    'metric_volatility90',
    'metric_clean_buffer7',
    'metric_buffer_volatility',
    'metric_deposit_multiplicity30',
]

# Target and time column for temporal splitting
TARGET = 'target_label'
TIME_COL = 'snapshot_timestamp'

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

def load_data() -> pd.DataFrame:
    """Extract training data from the database."""
    logger.info("Loading data from database")
    
    eng = sa.create_engine(DB_URL)
    
    # Query that extracts features and creates a binary target label
    # indicating whether a user has ever defaulted/been delinquent
    query = """
    SELECT
        r.user_id,
        r.snapshot_timestamp,
        r.metric_observed_history_days,
        r.metric_median_paycheck,
        r.metric_paycheck_regularity,
        r.metric_days_since_last_paycheck,
        r.metric_overdraft_count90,
        r.metric_net_cash30,
        r.metric_debt_load30,
        r.metric_volatility90,
        r.metric_clean_buffer7,
        r.metric_buffer_volatility,
        r.metric_deposit_multiplicity30,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM repayments rep
                WHERE rep.user_id = r.user_id
                  AND rep.status IN ('defaulted','delinquent','escalated')
                  AND rep.created_at > r.snapshot_timestamp
            )
            OR EXISTS (
                SELECT 1
                FROM cash_advances ca
                WHERE ca.user_id = r.user_id
                  AND ca.status = 'overdue'
                  AND ca.created_at > r.snapshot_timestamp
            )
            THEN 1 ELSE 0
        END AS target_label
    FROM risk_score_audits r
    """
    
    try:
        with eng.connect() as conn:
            df = pd.read_sql(query, conn)
        
        logger.info(f"Loaded {len(df)} rows of data")
        
        # Drop rows with missing values
        orig_len = len(df)
        df = df.dropna(subset=FEATURE_COLS + [TARGET])
        if len(df) < orig_len:
            logger.warning(f"Dropped {orig_len - len(df)} rows with missing values")
        
        return df
    
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        raise

def temporal_split(df: pd.DataFrame, train_ratio: float = 0.8) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split data temporally to avoid look-ahead bias.
    
    Args:
        df: DataFrame with features and target
        train_ratio: Portion of data (by time) to use for training
        
    Returns:
        Training and validation DataFrames
    """
    logger.info(f"Performing temporal split with {train_ratio:.0%} train, {1-train_ratio:.0%} validation")
    
    # Sort by timestamp
    df = df.sort_values(by=TIME_COL)
    
    # Find the cutoff timestamp
    cutoff_idx = int(len(df) * train_ratio)
    cutoff_time = df.iloc[cutoff_idx][TIME_COL]
    
    # Split the data
    train_df = df[df[TIME_COL] <= cutoff_time].copy()
    valid_df = df[df[TIME_COL] > cutoff_time].copy()
    
    logger.info(f"Train set: {len(train_df)} rows, Validation set: {len(valid_df)} rows")
    logger.info(f"Cutoff time: {cutoff_time}")
    
    # Check class balance
    train_pos = train_df[TARGET].mean()
    valid_pos = valid_df[TARGET].mean()
    logger.info(f"Train positive rate: {train_pos:.2%}, Validation positive rate: {valid_pos:.2%}")
    
    return train_df, valid_df

def feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """Apply feature engineering transformations."""
    logger.info("Applying feature engineering")
    
    # Create a copy to avoid modifying the original
    df = df.copy()
    
    # Log transform for highly skewed numeric features
    for col in ['metric_median_paycheck', 'metric_net_cash30']:
        if col in df.columns:
            # Handle negative values by adding minimum + 1
            min_val = df[col].min()
            if min_val < 0:
                df[f'{col}_log'] = np.log(df[col] - min_val + 1)
            else:
                df[f'{col}_log'] = np.log(df[col] + 1)
    
    # Ratio features
    if 'metric_net_cash30' in df.columns and 'metric_median_paycheck' in df.columns:
        df['cash_to_income_ratio'] = df['metric_net_cash30'] / df['metric_median_paycheck'].clip(lower=1)
    
    # Interaction terms for strong predictors
    if 'metric_debt_load30' in df.columns and 'metric_overdraft_count90' in df.columns:
        df['debt_overdraft_interaction'] = df['metric_debt_load30'] * df['metric_overdraft_count90']
    
    # Add derived columns to feature list
    global FEATURE_COLS
    new_cols = [col for col in df.columns if col not in FEATURE_COLS 
                and col not in [TARGET, TIME_COL, 'user_id']
                and not pd.isna(df[col]).all()]
    
    FEATURE_COLS = FEATURE_COLS + new_cols
    logger.info(f"Added {len(new_cols)} engineered features. Total features: {len(FEATURE_COLS)}")
    
    return df

def train_model(train_df: pd.DataFrame, valid_df: pd.DataFrame):
    """
    Train a LightGBM model for risk scoring.
    
    Args:
        train_df: Training data
        valid_df: Validation data
        
    Returns:
        Trained LightGBM model
    """
    logger.info("Training LightGBM model")
    
    # Create datasets
    train_set = lgb.Dataset(
        train_df[FEATURE_COLS], 
        label=train_df[TARGET],
        feature_name=FEATURE_COLS
    )
    
    valid_set = lgb.Dataset(
        valid_df[FEATURE_COLS], 
        label=valid_df[TARGET],
        feature_name=FEATURE_COLS,
        reference=train_set
    )
    
    # Model parameters - focused on preventing overfitting
    params = {
        "objective": "binary",
        "metric": ["auc", "binary_logloss"],
        "boosting_type": "gbdt",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "min_data_in_leaf": 50,
        "min_sum_hessian_in_leaf": 10.0,
        "max_depth": 6,
        "seed": 42,
        "verbose": -1
    }
    
    # Train with early stopping
    model = lgb.train(
        params,
        train_set,
        num_boost_round=10000,
        valid_sets=[valid_set, train_set],
        valid_names=["valid", "train"],
        early_stopping_rounds=100,
        verbose_eval=100,
    )
    
    # Evaluate on validation set
    y_pred = model.predict(valid_df[FEATURE_COLS])
    auc_score = roc_auc_score(valid_df[TARGET], y_pred)
    
    # Calculate PR AUC as well
    precision, recall, _ = precision_recall_curve(valid_df[TARGET], y_pred)
    pr_auc = auc(recall, precision)
    
    logger.info(f"Validation ROC-AUC: {auc_score:.4f}")
    logger.info(f"Validation PR-AUC: {pr_auc:.4f}")
    
    # Feature importance
    importance = model.feature_importance(importance_type='gain')
    feature_importance = pd.DataFrame({
        'Feature': FEATURE_COLS,
        'Importance': importance
    }).sort_values(by='Importance', ascending=False)
    
    logger.info("Top 10 features by importance:")
    for i, (feature, importance) in enumerate(zip(feature_importance['Feature'].values[:10], 
                                                feature_importance['Importance'].values[:10])):
        logger.info(f"{i+1}. {feature}: {importance:.2f}")
    
    return model, auc_score, pr_auc, feature_importance

def export_model(model, metrics=None):
    """
    Export the trained model to disk in multiple formats.
    
    Args:
        model: Trained LightGBM model
        metrics: Dictionary of evaluation metrics
    """
    # Create models directory if it doesn't exist
    models_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                              "models", "latest")
    os.makedirs(models_path, exist_ok=True)
    
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. Save native LightGBM model
    lgb_path = os.path.join(models_path, f"model_{timestamp}.txt")
    model.save_model(lgb_path)
    logger.info(f"Saved LightGBM model to {lgb_path}")
    
    # 2. Save as Treelite model for faster inference
    try:
        tl_model = treelite.Model.from_lightgbm(model)
        tl_path = os.path.join(models_path, f"model_{timestamp}.so")
        tl_model.export_lib(toolchain="gcc", libpath=tl_path, verbose=True, params={})
        logger.info(f"Exported Treelite optimized model to {tl_path}")
    except Exception as e:
        logger.error(f"Failed to export Treelite model: {e}")
    
    # Also create symlinks to the latest models
    latest_lgb = os.path.join(models_path, "model.txt")
    latest_tl = os.path.join(models_path, "model.so")
    
    try:
        if os.path.exists(latest_lgb):
            os.remove(latest_lgb)
        if os.path.exists(latest_tl):
            os.remove(latest_tl)
            
        os.symlink(os.path.basename(lgb_path), latest_lgb)
        os.symlink(os.path.basename(tl_path), latest_tl)
        
        logger.info("Created symlinks to latest models")
    except Exception as e:
        logger.error(f"Failed to create symlinks: {e}")
    
    # Save model metadata and evaluation metrics
    if metrics:
        metadata = {
            "timestamp": timestamp,
            "model_path": lgb_path,
            "treelite_path": tl_path,
            "num_features": len(FEATURE_COLS),
            "feature_names": FEATURE_COLS,
            **metrics
        }
        
        metadata_path = os.path.join(models_path, f"model_metadata_{timestamp}.json")
        import json
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Symlink to latest metadata
        latest_metadata = os.path.join(models_path, "model_metadata.json")
        if os.path.exists(latest_metadata):
            os.remove(latest_metadata)
        os.symlink(os.path.basename(metadata_path), latest_metadata)
        
        logger.info(f"Saved model metadata to {metadata_path}")

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
    """Main training pipeline"""
    logger.info("Starting model training pipeline")
    
    try:
        # Load data
        df = load_data()
        
        # Feature engineering
        df = feature_engineering(df)
        
        # Split data
        train_df, valid_df = temporal_split(df)
        
        # Train model
        model, roc_auc, pr_auc, feature_importance = train_model(train_df, valid_df)
        
        # Export model
        metrics = {
            "validation_roc_auc": float(roc_auc),
            "validation_pr_auc": float(pr_auc),
            "train_samples": len(train_df),
            "validation_samples": len(valid_df),
            "positive_rate_train": float(train_df[TARGET].mean()),
            "positive_rate_validation": float(valid_df[TARGET].mean()),
            "top_features": feature_importance.head(10).to_dict(orient='records')
        }
        
        export_model(model, metrics)
        
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
            
        logger.info("Model training pipeline completed successfully")
        
    except Exception as e:
        logger.error(f"Model training failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main() 