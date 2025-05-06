#!/usr/bin/env python3
"""
Test script for the BlinkScoring model training pipeline.
This runs a small-scale version of the training to validate the entire process.
"""
import os
import sys
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def create_synthetic_data() -> pd.DataFrame:
    """
    Create synthetic data for testing when no real data is available.
    This mimics the structure of the risk_score_audits table.
    """
    logger.info("Creating synthetic training data...")
    
    # Number of samples
    n_samples = 100
    
    # Create user IDs and timestamps
    np.random.seed(42)
    user_ids = [f"user_{i}" for i in range(n_samples)]
    timestamps = pd.date_range(start='2023-01-01', periods=n_samples, freq='D')
    
    # Generate synthetic features
    data: Dict[str, Any] = {
        'user_id': user_ids,
        'snapshot_timestamp': timestamps,
        'metric_observed_history_days': np.random.randint(30, 365, n_samples),
        'metric_median_paycheck': np.random.uniform(1000, 5000, n_samples),
        'metric_paycheck_regularity': np.random.uniform(0, 1, n_samples),
        'metric_days_since_last_paycheck': np.random.randint(1, 30, n_samples),
        'metric_overdraft_count90': np.random.randint(0, 10, n_samples),
        'metric_net_cash30': np.random.uniform(-1000, 5000, n_samples),
        'metric_debt_load30': np.random.uniform(0, 0.8, n_samples),
        'metric_volatility90': np.random.uniform(0, 1, n_samples),
        'metric_clean_buffer7': np.random.uniform(0, 1, n_samples),
        'metric_buffer_volatility': np.random.uniform(0, 1, n_samples),
        'metric_deposit_multiplicity30': np.random.randint(1, 10, n_samples),
    }
    
    # Create target based on features (higher risk for higher debt and overdrafts)
    debt_impact = data['metric_debt_load30'] * 2
    overdraft_impact = data['metric_overdraft_count90'] * 0.3
    income_impact = -1 * (data['metric_median_paycheck'] / 5000)
    
    # Probability of default based on features
    probs = 0.3 + debt_impact + overdraft_impact + income_impact
    probs = np.clip(probs, 0, 1)
    
    # Generate binary targets
    data['target_label'] = (np.random.random(n_samples) < probs).astype(int)
    
    return pd.DataFrame(data)

def test_feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """Test the feature engineering function with synthetic data."""
    logger.info("Testing feature engineering...")
    
    try:
        from service_trainer.train import feature_engineering
        
        # Apply feature engineering
        engineered_df = feature_engineering(df)
        
        logger.info(f"Original columns: {df.columns.tolist()}")
        logger.info(f"Engineered columns: {engineered_df.columns.tolist()}")
        logger.info(f"Added {len(engineered_df.columns) - len(df.columns)} new features")
        
        return engineered_df
    except Exception as e:
        logger.error(f"Feature engineering test failed: {e}")
        raise

def test_model_training(df: pd.DataFrame) -> None:
    """Test model training with synthetic data."""
    logger.info("Testing model training...")
    
    try:
        from service_trainer.train import temporal_split, train_model
        
        # Perform temporal split
        train_df, valid_df = temporal_split(df, train_ratio=0.8)
        
        logger.info(f"Training set: {len(train_df)} samples, Validation set: {len(valid_df)} samples")
        
        # Train model
        model, auc, pr_auc, feature_imp = train_model(train_df, valid_df)
        
        logger.info(f"Model training successful")
        logger.info(f"Validation AUC: {auc:.4f}, PR-AUC: {pr_auc:.4f}")
        logger.info(f"Top 5 features: {feature_imp.head(5)['Feature'].tolist()}")
        
        return model
    except Exception as e:
        logger.error(f"Model training test failed: {e}")
        raise

def test_model_export(model) -> None:
    """Test model export functionality."""
    logger.info("Testing model export...")
    
    try:
        from service_trainer.train import export_model
        
        # Create metrics for export
        metrics = {
            "validation_roc_auc": 0.85,
            "validation_pr_auc": 0.75,
            "train_samples": 80,
            "validation_samples": 20,
        }
        
        # Export model
        export_model(model, metrics)
        
        logger.info("Model export successful")
    except Exception as e:
        logger.error(f"Model export test failed: {e}")
        raise

def test_prediction_module() -> None:
    """Test prediction module with exported model."""
    logger.info("Testing prediction module...")
    
    try:
        from service_scoring.predict import get_model, score_user, score_batch
        
        # Create test features
        test_features = {
            'metric_observed_history_days': 180,
            'metric_median_paycheck': 3000,
            'metric_paycheck_regularity': 0.8, 
            'metric_days_since_last_paycheck': 5,
            'metric_overdraft_count90': 2,
            'metric_net_cash30': 1500,
            'metric_debt_load30': 0.3,
            'metric_volatility90': 0.2,
            'metric_clean_buffer7': 0.9,
            'metric_buffer_volatility': 0.1,
            'metric_deposit_multiplicity30': 3,
        }
        
        # Test single prediction
        score = score_user(test_features)
        logger.info(f"Single user score: {score}")
        
        # Test batch prediction
        batch_features = [test_features] * 3
        batch_scores = score_batch(batch_features)
        logger.info(f"Batch scores: {batch_scores}")
        
        logger.info("Prediction module test successful")
    except Exception as e:
        logger.error(f"Prediction module test failed: {e}")
        raise

def main():
    """Run tests for all components of the training pipeline."""
    try:
        # Create synthetic data (use if no real data available)
        df = create_synthetic_data()
        
        # Test feature engineering
        df = test_feature_engineering(df)
        
        # Test model training
        model = test_model_training(df)
        
        # Test model export
        test_model_export(model)
        
        # Test prediction module
        test_prediction_module()
        
        logger.info("All tests completed successfully!")
        return 0
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 