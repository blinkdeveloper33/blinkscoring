"""
Prediction module for loading trained model and making predictions.
Supports both native LightGBM and optimized Treelite models.
"""
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Union, Optional, Any

import numpy as np
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default paths
DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "models", "latest")
METADATA_FILE = "model_metadata.json"
LGB_MODEL_FILE = "model.txt"
TREELITE_MODEL_FILE = "model.so"

class ModelLoader:
    """
    Loads and manages ML models for prediction.
    Supports both LightGBM and optimized Treelite models.
    """
    
    def __init__(self, model_dir: str = DEFAULT_MODEL_DIR):
        """
        Initialize the model loader.
        
        Args:
            model_dir: Directory containing model files
        """
        self.model_dir = model_dir
        self.model = None
        self.predictor = None
        self.metadata = None
        self.feature_names = []
        self.using_treelite = False
        
        # Load model
        self._load_model()
    
    def _load_model(self) -> None:
        """Load the appropriate model based on what's available."""
        # First load metadata to get feature information
        metadata_path = os.path.join(self.model_dir, METADATA_FILE)
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                self.metadata = json.load(f)
                
                if "feature_names" in self.metadata:
                    self.feature_names = self.metadata["feature_names"]
                    logger.info(f"Loaded {len(self.feature_names)} feature names from metadata")
                    
        # Try to load Treelite model first (faster inference)
        treelite_path = os.path.join(self.model_dir, TREELITE_MODEL_FILE)
        if os.path.exists(treelite_path):
            try:
                import treelite.runtime
                self.predictor = treelite.runtime.Predictor(treelite_path)
                self.using_treelite = True
                logger.info(f"Loaded Treelite model from {treelite_path}")
                return
            except Exception as e:
                logger.warning(f"Failed to load Treelite model: {e}")
        
        # Fall back to LightGBM model
        lgb_path = os.path.join(self.model_dir, LGB_MODEL_FILE)
        if os.path.exists(lgb_path):
            try:
                import lightgbm as lgb
                self.model = lgb.Booster(model_file=lgb_path)
                
                # If no feature names in metadata, try to get from model
                if not self.feature_names:
                    self.feature_names = self.model.feature_name()
                    
                logger.info(f"Loaded LightGBM model from {lgb_path}")
                return
            except Exception as e:
                logger.error(f"Failed to load LightGBM model: {e}")
                
        # No model found
        logger.error(f"No valid model found in {self.model_dir}")
        raise FileNotFoundError(f"No model files found in {self.model_dir}")
    
    def predict(self, features: Union[pd.DataFrame, Dict[str, Any]]) -> float:
        """
        Make a prediction for a single user.
        
        Args:
            features: Features as DataFrame or dictionary
            
        Returns:
            Risk score (0-100)
        """
        # Convert dict to DataFrame if needed
        if isinstance(features, dict):
            features = pd.DataFrame([features])
        
        # Ensure all required features are present
        missing_features = set(self.feature_names) - set(features.columns)
        if missing_features:
            logger.warning(f"Missing features: {missing_features}")
            # Add missing features with default values (0)
            for feat in missing_features:
                features[feat] = 0
        
        # Select and order features according to model requirements
        features = features[self.feature_names]
        
        # Make prediction
        raw_score = self._predict_raw(features)
        
        # Convert to score range (0-100)
        score = self._scale_prediction(raw_score)
        
        return score
    
    def predict_batch(self, features_batch: pd.DataFrame) -> List[float]:
        """
        Make predictions for multiple users.
        
        Args:
            features_batch: DataFrame with features for multiple users
            
        Returns:
            List of risk scores
        """
        # Ensure all required features are present
        missing_features = set(self.feature_names) - set(features_batch.columns)
        if missing_features:
            logger.warning(f"Missing features: {missing_features}")
            # Add missing features with default values
            for feat in missing_features:
                features_batch[feat] = 0
        
        # Select and order features according to model requirements
        features_batch = features_batch[self.feature_names]
        
        # Make predictions
        raw_scores = self._predict_raw(features_batch)
        
        # Convert to score range (0-100)
        scores = [self._scale_prediction(score) for score in raw_scores]
        
        return scores
    
    def _predict_raw(self, features: pd.DataFrame) -> Union[float, List[float]]:
        """Internal method to get raw prediction from model."""
        if self.using_treelite:
            # For Treelite
            batch = treelite.runtime.Batch.from_pandas(features, nthread=1)
            out_pred = np.zeros(features.shape[0], dtype=np.float32)
            self.predictor.predict(batch, out_pred)
            return out_pred if len(out_pred) > 1 else out_pred[0]
        else:
            # For LightGBM
            return self.model.predict(features)
    
    def _scale_prediction(self, raw_score: float) -> float:
        """
        Scale raw prediction to a 0-100 score.
        
        Args:
            raw_score: Raw model output (log-odds for binary classification)
            
        Returns:
            Scaled score between 0-100
        """
        # Convert log-odds to probability
        prob = 1 / (1 + np.exp(-raw_score))
        
        # Scale probability to 0-100 range
        score = int(round(prob * 100))
        
        # Clip to valid range
        return max(0, min(100, score))
    
    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get feature importance from the model.
        
        Returns:
            Dictionary mapping feature names to importance values
        """
        if self.using_treelite:
            # Treelite doesn't have feature importance
            if self.metadata and "top_features" in self.metadata:
                # Use saved importance from metadata
                top_features = self.metadata["top_features"]
                return {item["Feature"]: item["Importance"] for item in top_features}
            return {}
        else:
            # Get from LightGBM model
            importance = self.model.feature_importance(importance_type='gain')
            return dict(zip(self.feature_names, importance))


# Singleton instance for reuse
_model_instance = None

def get_model() -> ModelLoader:
    """
    Get (or create) the model loader instance.
    
    Returns:
        ModelLoader instance
    """
    global _model_instance
    if _model_instance is None:
        _model_instance = ModelLoader()
    return _model_instance


def score_user(features: Dict[str, Any]) -> int:
    """
    Score a user based on their features.
    
    Args:
        features: Dictionary of user features
        
    Returns:
        Risk score (0-100)
    """
    model = get_model()
    return int(model.predict(features))


def score_batch(features_batch: List[Dict[str, Any]]) -> List[int]:
    """
    Score multiple users based on their features.
    
    Args:
        features_batch: List of feature dictionaries
        
    Returns:
        List of risk scores (0-100)
    """
    if not features_batch:
        return []
        
    model = get_model()
    df = pd.DataFrame(features_batch)
    scores = model.predict_batch(df)
    return [int(score) for score in scores] 