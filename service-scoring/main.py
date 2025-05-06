#!/usr/bin/env python3
"""
Scoring service API for BlinkScoring ML
"""

import os
import time
import logging
from typing import Dict, List, Optional, Union
from datetime import datetime
import json

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
import uvicorn

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="BlinkScoring ML API",
    description="API for risk scoring based on financial data",
    version="0.1.0",
)

# Global variables
START_TIME = time.time()

# Data models
class ScoringRequest(BaseModel):
    user_id: str
    features: Dict[str, float]
    persist_score: bool = True

class ScoringBatchItem(BaseModel):
    user_id: str
    features: Dict[str, float]
    persist_score: bool = True

class ScoringBatchRequest(BaseModel):
    items: List[ScoringBatchItem]
    persist_scores: bool = True

class ScoringResponse(BaseModel):
    user_id: str
    score: float
    score_timestamp: datetime = Field(default_factory=datetime.now)
    model_version: str = "0.1.0"
    top_features: List[Dict[str, Union[str, float]]] = []

class BatchScoringResponse(BaseModel):
    results: List[ScoringResponse]
    batch_size: int
    processing_time_ms: float

# Routes
@app.get("/health")
async def health_check():
    """Health check endpoint for the scoring API"""
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME)
    }

@app.post("/score", response_model=ScoringResponse)
async def score_user(request: ScoringRequest):
    """Score a single user based on their features"""
    try:
        # In a real implementation, we'd load the model and score the user
        # For now, we'll just return a dummy score
        user_id = request.user_id
        features = request.features
        
        # Dummy scoring logic
        score = 0.5  # Default score
        
        # Simple rule-based score adjustment based on available features
        if "metric_median_paycheck" in features:
            if features["metric_median_paycheck"] > 1000:
                score += 0.2
        
        if "metric_overdraft_count90" in features:
            if features["metric_overdraft_count90"] > 0:
                score -= 0.1 * features["metric_overdraft_count90"]
        
        # Ensure score is between 0 and 1
        score = max(0, min(1, score))
        
        # Generate dummy top features
        top_features = []
        for feature_name, feature_value in features.items():
            top_features.append({
                "feature_name": feature_name,
                "feature_value": feature_value,
                "importance": 0.1  # Dummy importance value
            })
        
        # Return response
        return ScoringResponse(
            user_id=user_id,
            score=score,
            top_features=top_features[:5]  # Return top 5 features
        )
    
    except Exception as e:
        logger.error(f"Error processing score request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/score-batch", response_model=BatchScoringResponse)
async def score_batch(request: ScoringBatchRequest):
    """Score a batch of users"""
    try:
        start_time = time.time()
        
        results = []
        for item in request.items:
            # Process each user (simplified version)
            score_request = ScoringRequest(
                user_id=item.user_id,
                features=item.features,
                persist_score=item.persist_score
            )
            result = await score_user(score_request)
            results.append(result)
        
        processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        return BatchScoringResponse(
            results=results,
            batch_size=len(results),
            processing_time_ms=processing_time
        )
    
    except Exception as e:
        logger.error(f"Error processing batch score request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Main entry point
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 