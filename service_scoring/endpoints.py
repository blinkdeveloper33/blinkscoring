#!/usr/bin/env python3
"""
API endpoints for BlinkScoring ML model.
"""
import os
import sys
import time
import logging
import traceback
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
import psycopg2
import json

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from service_scoring.predict import get_model, score_user, score_batch

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/ml",
    tags=["ML Scoring"]
)

# Database connection string from environment
DB_URL = os.getenv("DATABASE_URL")

# Models
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

class UserIds(BaseModel):
    user_ids: List[str]

class ScoringResponse(BaseModel):
    user_id: str
    score: float
    top_features: List[Dict[str, Any]] = []

class BatchScoringResponse(BaseModel):
    results: List[ScoringResponse]
    batch_size: int
    processing_time_ms: float

# Database helper
def get_db_connection():
    """Create a database connection."""
    return psycopg2.connect(DB_URL)

# Helper function for updating risk_score_audits
def update_risk_score_audit(user_id: str, ml_score: float, features: Dict[str, float], top_features: List[Dict[str, Any]]):
    """Update the risk_score_audits table with ML score"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Check if there's a recent audit we can update (last 24 hours)
            cur.execute("""
                SELECT id FROM risk_score_audits 
                WHERE user_id = %s 
                AND created_at > NOW() - INTERVAL '24 hours'
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            
            existing_audit = cur.fetchone()
            
            if existing_audit:
                # Update existing audit with ML score
                audit_id = existing_audit[0]
                cur.execute("""
                    UPDATE risk_score_audits 
                    SET 
                        blink_ml_score = %s,
                        blink_ml_version = %s,
                        shap_top5 = %s
                    WHERE id = %s
                """, (ml_score, "1.0.0", json.dumps(top_features) if top_features else None, audit_id))
                
                logger.info(f"Updated existing audit {audit_id} for user {user_id} with ML score {ml_score}")
                
            else:
                # Create new audit entry with all metrics and ML score
                query = """
                    INSERT INTO risk_score_audits (
                        user_id, snapshot_timestamp, 
                        metric_observed_history_days, metric_median_paycheck, metric_paycheck_regularity,
                        metric_days_since_last_paycheck, metric_overdraft_count90, metric_net_cash30,
                        metric_debt_load30, metric_volatility90, metric_clean_buffer7,
                        metric_buffer_volatility, metric_deposit_multiplicity30,
                        blink_ml_score, blink_ml_version, shap_top5, calculation_engine_version
                    ) VALUES (
                        %s, NOW(),
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s
                    ) RETURNING id
                """
                
                params = [
                    user_id,
                    features.get('metric_observed_history_days'),
                    features.get('metric_median_paycheck'),
                    features.get('metric_paycheck_regularity'),
                    features.get('metric_days_since_last_paycheck'),
                    features.get('metric_overdraft_count90'),
                    features.get('metric_net_cash30'),
                    features.get('metric_debt_load30'),
                    features.get('metric_volatility90'),
                    features.get('metric_clean_buffer7'),
                    features.get('metric_buffer_volatility'),
                    features.get('metric_deposit_multiplicity30'),
                    ml_score, "1.0.0", 
                    json.dumps(top_features) if top_features else None,
                    "LightGBM-1.0"
                ]
                
                cur.execute(query, params)
                audit_id = cur.fetchone()[0]
                
                logger.info(f"Created new audit {audit_id} for user {user_id} with ML score {ml_score}")
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error updating risk score audit for user {user_id}: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def run_batch_scoring_job(user_ids: List[str]):
    """
    Background task to process a batch of user IDs.
    Simpler implementation of what service_cron.score_users does.
    """
    try:
        # Load model
        model = get_model()
        
        conn = get_db_connection()
        
        for user_id in user_ids:
            try:
                # Get user features from DB
                with conn.cursor() as cur:
                    # Query most recent audit record to get features
                    cur.execute("""
                        SELECT 
                            metric_observed_history_days,
                            metric_median_paycheck,
                            metric_paycheck_regularity,
                            metric_days_since_last_paycheck,
                            metric_overdraft_count90,
                            metric_net_cash30,
                            metric_debt_load30,
                            metric_volatility90,
                            metric_clean_buffer7,
                            metric_buffer_volatility,
                            metric_deposit_multiplicity30
                        FROM risk_score_audits
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (user_id,))
                    
                    metrics = cur.fetchone()
                    
                    if not metrics:
                        logger.warning(f"No existing metrics found for user {user_id}")
                        continue
                        
                    # Build features dictionary
                    metrics_names = [
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
                        'metric_deposit_multiplicity30'
                    ]
                    
                    features = {}
                    for i, name in enumerate(metrics_names):
                        if metrics[i] is not None:
                            features[name] = float(metrics[i])
                
                # Skip if insufficient features
                if len(features) < 5:  # Arbitrary threshold
                    logger.warning(f"Insufficient features for user {user_id}")
                    continue
                
                # Score with ML model
                ml_score = score_user(features)
                
                # Use static top features for now
                top_features = [
                    {"feature": "metric_debt_load30", "importance": 0.3},
                    {"feature": "metric_overdraft_count90", "importance": 0.25},
                    {"feature": "metric_median_paycheck", "importance": 0.2},
                    {"feature": "metric_volatility90", "importance": 0.15},
                    {"feature": "metric_clean_buffer7", "importance": 0.1}
                ]
                
                # Update database
                update_risk_score_audit(user_id, ml_score, features, top_features)
                
                logger.info(f"Successfully updated score for user {user_id}")
                
            except Exception as e:
                logger.error(f"Error processing user {user_id}: {str(e)}")
                # Continue to next user
    
    except Exception as e:
        logger.error(f"Error in batch scoring job: {str(e)}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# Endpoints
@router.post("/score", response_model=ScoringResponse)
async def ml_score_user(request: ScoringRequest):
    """Score a user with the ML model and optionally persist to database."""
    try:
        # Get score from ML model
        start_time = time.time()
        score_result = score_user(request.features)
        
        # Create response
        response = ScoringResponse(
            user_id=request.user_id,
            score=score_result,
            # Use static top features for now
            top_features=[
                {"feature": "metric_debt_load30", "importance": 0.3},
                {"feature": "metric_overdraft_count90", "importance": 0.25},
                {"feature": "metric_median_paycheck", "importance": 0.2},
                {"feature": "metric_volatility90", "importance": 0.15},
                {"feature": "metric_clean_buffer7", "importance": 0.1}
            ]
        )
        
        # Optionally persist to database
        if request.persist_score:
            update_risk_score_audit(
                request.user_id, 
                score_result, 
                request.features, 
                response.top_features
            )
        
        return response
    
    except Exception as e:
        logger.error(f"Error scoring user {request.user_id}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error scoring user: {str(e)}")

@router.post("/score-batch", response_model=BatchScoringResponse)
async def ml_score_batch(request: ScoringBatchRequest):
    """Score a batch of users with the ML model."""
    try:
        start_time = time.time()
        
        # Prepare batch for scoring
        features_batch = [item.features for item in request.items]
        user_ids = [item.user_id for item in request.items]
        
        # Get scores from ML model
        scores = score_batch(features_batch)
        
        # Prepare responses
        results = []
        for i, (user_id, score) in enumerate(zip(user_ids, scores)):
            # Use static top features for now
            top_features = [
                {"feature": "metric_debt_load30", "importance": 0.3},
                {"feature": "metric_overdraft_count90", "importance": 0.25},
                {"feature": "metric_median_paycheck", "importance": 0.2},
                {"feature": "metric_volatility90", "importance": 0.15},
                {"feature": "metric_clean_buffer7", "importance": 0.1}
            ]
            
            result = ScoringResponse(
                user_id=user_id,
                score=score,
                top_features=top_features
            )
            results.append(result)
            
            # Optionally persist to database
            if request.persist_scores and request.items[i].persist_score:
                update_risk_score_audit(
                    user_id, 
                    score, 
                    request.items[i].features, 
                    top_features
                )
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000  # ms
        
        return BatchScoringResponse(
            results=results,
            batch_size=len(results),
            processing_time_ms=processing_time
        )
    
    except Exception as e:
        logger.error(f"Error processing batch scoring: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error scoring batch: {str(e)}")

@router.post("/update-scores", status_code=202)
async def update_user_scores(request: UserIds, background_tasks: BackgroundTasks):
    """Trigger score updates for specific users (admin feature)."""
    if not request.user_ids:
        raise HTTPException(status_code=400, detail="No user IDs provided")
    
    # Run processing in background
    background_tasks.add_task(run_batch_scoring_job, request.user_ids)
    
    return {"message": f"Score update job initiated for {len(request.user_ids)} users"}

@router.get("/health")
async def health_check():
    """Health check endpoint for the ML API."""
    # Try to load model to verify it's working
    try:
        model = get_model()
        return {
            "status": "ok",
            "model_loaded": True,
            "uptime": os.getenv("UPTIME", "unknown")
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "error",
            "model_loaded": False,
            "error": str(e)
        } 