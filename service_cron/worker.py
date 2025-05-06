#!/usr/bin/env python3
"""
BlinkScoring ML Cron Worker

This worker runs on a schedule (every 5 minutes by default) to:
1. Fetch users with new financial data
2. Generate features for each user
3. Score each user using the ML model
4. Store the scores in the database
"""
import os
import json
import time
import logging
import traceback
import requests
from datetime import datetime, timedelta
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.db import execute_query, get_postgres_connection

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
SCORING_URL = os.getenv("SCORING_URL", "http://localhost:8000")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "200"))
SCORING_INTERVAL_MINUTES = int(os.getenv("SCORING_INTERVAL_MINUTES", "5"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
SLEEP_AFTER_USER = float(os.getenv("SLEEP_AFTER_USER", "0.1"))  # Sleep for 100ms after each user

def get_active_users(batch_size=BATCH_SIZE):
    """
    Get users who need to be scored. This is a simplified version that will
    retrieve any users with Plaid connections, regardless of transaction history.
    
    In production: Make this query actually check for new transaction data since the last score.
    """
    # DEBUG VERSION: Just get any 5 users with Plaid connections
    query = """
    SELECT 
        u.id as user_id, 
        u.email,
        u.first_name
    FROM users u
    WHERE EXISTS (
        SELECT 1 FROM plaid_items pi WHERE pi.user_id = u.id
    )
    LIMIT %(batch_size)s
    """
    
    params = {
        "batch_size": 5  # Get a small number of users for debugging
    }
    
    try:
        return execute_query(query, params)
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        # Return empty list as fallback
        return []

def generate_features_for_user(user_id):
    """
    Generate feature values for a user based on their financial data.
    
    For now, this returns dummy features. In production, this would pull real data.
    """
    # Dummy features for testing
    features = {
        "metric_median_paycheck": 1200 + hash(user_id) % 1000,  # Random-ish paycheck amount
        "metric_overdraft_count90": hash(user_id) % 5,           # Random-ish overdraft count
        "metric_total_balance": 5000 + hash(user_id) % 10000,
        "metric_transaction_count90": 50 + hash(user_id) % 100,
        "metric_income_expense_ratio": 1.2 + (hash(user_id) % 10) / 10,
    }
    
    return features

def score_user(user_id, features):
    """Score a user using the ML scoring service"""
    try:
        payload = {
            "user_id": user_id,
            "features": features,
            "persist_score": not DRY_RUN
        }
        
        # Try batch API endpoint first
        try:
            response = requests.post(
                f"{SCORING_URL}/score",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
        except Exception as e:
            logger.error(f"Error calling scoring API: {e}")
            # Return dummy score on failure
            return {
                "score": 0.5,
                "user_id": user_id,
                "model_version": "dummy-fallback",
                "top_features": []
            }
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error scoring user {user_id}: {response.status_code} {response.text}")
            # Return dummy score on failure
            return {
                "score": 0.5,
                "user_id": user_id,
                "model_version": "dummy-fallback",
                "top_features": []
            }
    except Exception as e:
        logger.error(f"Exception when scoring user {user_id}: {e}")
        traceback.print_exc()
        return {
            "score": 0.5,
            "user_id": user_id,
            "model_version": "dummy-fallback",
            "top_features": []
        }

def store_feature_snapshot(user_id, features):
    """Store a snapshot of the user's features in the feature store"""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would store feature snapshot for user {user_id}")
        return "dummy-snapshot-id"
        
    query = """
    INSERT INTO feature_store_snapshots 
    (user_id, decision_ts, json_features)
    VALUES (%(user_id)s, NOW(), %(json_features)s)
    RETURNING snapshot_id
    """
    
    params = {
        "user_id": user_id,
        "json_features": json.dumps(features)
    }
    
    try:
        result = execute_query(query, params)
        return result[0]["snapshot_id"] if result else None
    except Exception as e:
        logger.error(f"Error storing feature snapshot: {e}")
        return None

def store_risk_score_directly(user_id, score_result):
    """Store a risk score directly in the database (backup if persist_score doesn't work)"""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would store risk score for user {user_id}: {score_result['score']}")
        return True
    
    # Extract the top features from the result
    try:
        top_features = score_result.get("top_features", [])
        shap_json = json.dumps([
            {"feature": f["feature"], "impact": f["impact"]} 
            for f in top_features
        ])
        
        query = """
        INSERT INTO risk_score_audits 
        (user_id, blink_ml_score, blink_ml_version, shap_top5, snapshot_timestamp)
        VALUES (%(user_id)s, %(score)s, %(model_version)s, %(shap_top5)s, NOW())
        """
        
        params = {
            "user_id": user_id,
            "score": score_result["score"],
            "model_version": score_result.get("model_version", "unknown"),
            "shap_top5": shap_json
        }
        
        execute_query(query, params)
        return True
    except Exception as e:
        logger.error(f"Error storing risk score: {e}")
        return False

def process_batch():
    """Process a batch of users"""
    start_time = time.time()
    logger.info(f"Starting batch processing with batch size {BATCH_SIZE}")
    
    # Get users to process
    users = get_active_users(BATCH_SIZE)
    logger.info(f"Found {len(users)} users to process")
    
    if not users:
        logger.info("No users to process, exiting")
        return 0
    
    processed = 0
    errors = 0
    
    # Process users in smaller batches to avoid overwhelming the API
    batch_size = min(50, len(users))
    for i in range(0, len(users), batch_size):
        batch = users[i:i+batch_size]
        batch_items = []
        
        for user in batch:
            user_id = user["user_id"]
            try:
                # Generate features
                logger.info(f"Generating features for user {user_id}")
                features = generate_features_for_user(user_id)
                
                if features:
                    # Store feature snapshot
                    snapshot_id = store_feature_snapshot(user_id, features)
                    logger.info(f"Stored feature snapshot {snapshot_id} for user {user_id}")
                    
                    # Prepare item for batch scoring
                    batch_items.append({
                        "user_id": user_id,
                        "features": features,
                        "persist_score": not DRY_RUN
                    })
                else:
                    logger.warning(f"No features generated for user {user_id}")
                    errors += 1
            except Exception as e:
                logger.error(f"Error preparing user {user_id}: {e}")
                traceback.print_exc()
                errors += 1
        
        # Score the batch if we have items
        if batch_items:
            try:
                # Try batch endpoint if available
                try:
                    batch_payload = {
                        "items": batch_items,
                        "persist_scores": not DRY_RUN
                    }
                    logger.info(f"Scoring batch of {len(batch_items)} users")
                    response = requests.post(
                        f"{SCORING_URL}/score-batch",
                        json=batch_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        batch_result = response.json()
                        logger.info(f"Batch scored successfully: {len(batch_result.get('results', []))} results")
                        processed += len(batch_result.get('results', []))
                        
                        # If needed, store scores directly if persist_scores didn't work
                        for result in batch_result.get('results', []):
                            user_id = result["user_id"]
                            
                            # For demonstration, always store scores directly
                            # In production, would only do this as fallback
                            store_risk_score_directly(user_id, result)
                    else:
                        logger.error(f"Batch scoring failed: {response.status_code} {response.text}")
                        raise Exception(f"Batch scoring failed: {response.status_code}")
                except Exception as e:
                    logger.error(f"Error with batch scoring, falling back to individual scoring: {e}")
                    
                    # Fall back to individual scoring
                    for item in batch_items:
                        user_id = item["user_id"]
                        features = item["features"]
                        
                        # Score individual user
                        score_result = score_user(user_id, features)
                        
                        if score_result:
                            logger.info(f"User {user_id} scored: {score_result.get('score', 'unknown')}")
                            processed += 1
                            
                            # Store score directly
                            store_risk_score_directly(user_id, score_result)
                        else:
                            logger.error(f"Failed to score user {user_id}")
                            errors += 1
                        
                        # Sleep briefly to avoid overwhelming the scoring service
                        time.sleep(SLEEP_AFTER_USER)
            except Exception as e:
                logger.error(f"Error processing batch: {e}")
                traceback.print_exc()
                errors += len(batch_items)
    
    end_time = time.time()
    duration = end_time - start_time
    
    logger.info(f"Batch processing completed in {duration:.2f} seconds")
    logger.info(f"Processed: {processed}, Errors: {errors}")
    
    return processed

def main():
    """Main entry point for the worker"""
    logger.info("BlinkScoring ML Cron Worker starting")
    
    if DRY_RUN:
        logger.info("Running in DRY RUN mode - no scores will be persisted")
    
    try:
        # Process one batch
        processed = process_batch()
        logger.info(f"Processed {processed} users")
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        traceback.print_exc()
    
    logger.info("BlinkScoring ML Cron Worker completed")

if __name__ == "__main__":
    main() 