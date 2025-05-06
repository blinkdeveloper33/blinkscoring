#!/usr/bin/env python3
"""
Cron job to score all users with available data using the ML model.
This script periodically runs to keep risk scores up-to-date in the database.
"""
import os
import sys
import logging
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
import time
import json

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from service_scoring.predict import get_model, score_user

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"/tmp/blink_scoring_cron_{datetime.now().strftime('%Y%m%d')}.log")
    ]
)
logger = logging.getLogger(__name__)

# Database connection string from environment
DB_URL = os.getenv("DATABASE_URL")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

def get_db_connection():
    """Create a database connection."""
    return psycopg2.connect(DB_URL)

def get_users_with_available_data(conn, limit=None):
    """
    Get users who have sufficient data for scoring.
    
    Args:
        conn: Database connection
        limit: Optional limit on number of users to process
        
    Returns:
        List of user_ids with available data
    """
    with conn.cursor() as cur:
        # Query users who have sufficient data (all 11 metrics available)
        # This query can be optimized based on database structure
        query = """
        WITH latest_asset_reports AS (
            SELECT user_id, MAX(created_at) as latest_date
            FROM asset_reports
            GROUP BY user_id
        )
        SELECT DISTINCT ar.user_id
        FROM asset_reports ar
        JOIN latest_asset_reports lar ON ar.user_id = lar.user_id AND ar.created_at = lar.latest_date
        JOIN asset_report_items ari ON ar.id = ari.asset_report_id
        JOIN asset_report_accounts ara ON ari.id = ara.asset_report_item_id
        JOIN asset_report_transactions art ON ara.id = art.asset_report_account_id
        WHERE
            -- Must have transactions spanning at least 90 days
            (EXTRACT(EPOCH FROM (MAX(art.date) - MIN(art.date))) / 86400) >= 90
        GROUP BY ar.user_id
        """
        
        # Add limit if specified
        if limit:
            query += f" LIMIT {limit}"
            
        cur.execute(query)
        users = [row[0] for row in cur.fetchall()]
        
        logger.info(f"Found {len(users)} users with available data for scoring")
        return users

def get_user_features(conn, user_id):
    """
    Extract features for a specific user from the database.
    
    Args:
        conn: Database connection
        user_id: User ID to extract features for
        
    Returns:
        Dictionary of features or None if insufficient data
    """
    features = {}
    try:
        with conn.cursor() as cur:
            # Get the latest asset report for this user
            cur.execute("""
                SELECT id, created_at 
                FROM asset_reports 
                WHERE user_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (user_id,))
            asset_report = cur.fetchone()
            
            if not asset_report:
                logger.warning(f"No asset report found for user {user_id}")
                return None
                
            asset_report_id, report_date = asset_report
            
            # Find the associated account
            cur.execute("""
                SELECT ara.id, ara.balance_current 
                FROM asset_report_accounts ara
                JOIN asset_report_items ari ON ara.asset_report_item_id = ari.id
                WHERE ari.asset_report_id = %s
                LIMIT 1
            """, (asset_report_id,))
            account = cur.fetchone()
            
            if not account:
                logger.warning(f"No account found for asset report {asset_report_id}")
                return None
                
            account_id, current_balance = account
            
            # Get transactions
            cur.execute("""
                SELECT * 
                FROM asset_report_transactions 
                WHERE asset_report_account_id = %s
                ORDER BY date ASC
            """, (account_id,))
            transactions = cur.fetchall()
            
            if not transactions:
                logger.warning(f"No transactions found for account {account_id}")
                return None
                
            # Get historical balances
            cur.execute("""
                SELECT balance_date, balance_current 
                FROM asset_report_account_historical_balances 
                WHERE asset_report_account_id = %s 
                ORDER BY balance_date ASC
            """, (account_id,))
            balances = cur.fetchall()
            
            # Process data and calculate all 11 risk metrics
            # This implementation uses a simplified approach - in production you'd want
            # to leverage the existing riskScoringService.js logic to ensure consistency
            
            # For now, we'll calculate some basic metrics
            first_transaction_date = transactions[0][3]  # Assuming date is at index 3
            latest_transaction_date = transactions[-1][3]
            
            if isinstance(first_transaction_date, str):
                first_transaction_date = datetime.strptime(first_transaction_date, "%Y-%m-%d")
            if isinstance(latest_transaction_date, str):
                latest_transaction_date = datetime.strptime(latest_transaction_date, "%Y-%m-%d")
            
            # Calculate observed history days
            if isinstance(report_date, str):
                report_date = datetime.strptime(report_date, "%Y-%m-%d %H:%M:%S")
            observed_days = (report_date - first_transaction_date).days + 1
            
            if observed_days < 90:
                logger.warning(f"Insufficient history for user {user_id}: {observed_days} days")
                return None
                
            # Initialize features with the core 11 metrics
            features = {
                'metric_observed_history_days': float(observed_days),
                'metric_median_paycheck': 0.0,
                'metric_paycheck_regularity': 0.0,
                'metric_days_since_last_paycheck': 30.0,
                'metric_overdraft_count90': 0.0,
                'metric_net_cash30': 0.0,
                'metric_debt_load30': 0.0,
                'metric_volatility90': 0.0,
                'metric_clean_buffer7': 0.0,
                'metric_buffer_volatility': 0.0,
                'metric_deposit_multiplicity30': 1.0
            }
            
            # Pull the actual metrics from the most recent risk_score_audit if available
            # This is a shortcut - ideally we'd calculate these metrics directly
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
            
            audit_metrics = cur.fetchone()
            if audit_metrics:
                # Update features with database metrics
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
                
                for i, name in enumerate(metrics_names):
                    if audit_metrics[i] is not None:
                        features[name] = float(audit_metrics[i])
            
            return features
            
    except Exception as e:
        logger.error(f"Error extracting features for user {user_id}: {str(e)}")
        return None

def update_risk_score_audit(conn, user_id, features, ml_score, top5_features=None):
    """
    Update the risk_score_audits table with the ML model score.
    
    Args:
        conn: Database connection
        user_id: User ID 
        features: Dictionary of features used for scoring
        ml_score: Score generated by the ML model (0-100)
        top5_features: Optional list of top 5 influential features
        
    Returns:
        ID of the audit record or None on failure
    """
    try:
        now = datetime.now()
        
        # Get existing audit or create new one
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
            
            if existing_audit and not DRY_RUN:
                # Update existing audit with ML score
                audit_id = existing_audit[0]
                cur.execute("""
                    UPDATE risk_score_audits 
                    SET 
                        blink_ml_score = %s,
                        blink_ml_version = %s,
                        shap_top5 = %s
                    WHERE id = %s
                """, (ml_score, "1.0.0", json.dumps(top5_features) if top5_features else None, audit_id))
                
                logger.info(f"Updated existing audit {audit_id} for user {user_id} with ML score {ml_score}")
                
            elif not DRY_RUN:
                # Create new audit entry with all metrics and ML score
                query = """
                    INSERT INTO risk_score_audits (
                        user_id, snapshot_timestamp, asset_report_id,
                        metric_observed_history_days, metric_median_paycheck, metric_paycheck_regularity,
                        metric_days_since_last_paycheck, metric_overdraft_count90, metric_net_cash30,
                        metric_debt_load30, metric_volatility90, metric_clean_buffer7,
                        metric_buffer_volatility, metric_deposit_multiplicity30,
                        blink_ml_score, blink_ml_version, shap_top5, calculation_engine_version
                    ) VALUES (
                        %s, %s, NULL,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s
                    ) RETURNING id
                """
                
                params = [
                    user_id, now,
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
                    json.dumps(top5_features) if top5_features else None,
                    "LightGBM-1.0"
                ]
                
                cur.execute(query, params)
                audit_id = cur.fetchone()[0]
                
                logger.info(f"Created new audit {audit_id} for user {user_id} with ML score {ml_score}")
            
            else:
                audit_id = "dry-run"
                logger.info(f"DRY RUN: Would update/create audit for user {user_id} with ML score {ml_score}")
            
            if not DRY_RUN:
                conn.commit()
                
            return audit_id
            
    except Exception as e:
        logger.error(f"Error updating risk score audit for user {user_id}: {str(e)}")
        conn.rollback()
        return None

def process_users(conn, users):
    """
    Process a batch of users to update their risk scores.
    
    Args:
        conn: Database connection
        users: List of user IDs to process
        
    Returns:
        Dictionary with processing statistics
    """
    stats = {
        'processed': 0,
        'succeeded': 0,
        'failed': 0,
        'skipped': 0
    }
    
    # Load the ML model
    model = get_model()
    
    for user_id in users:
        stats['processed'] += 1
        
        try:
            # Get features for this user
            features = get_user_features(conn, user_id)
            
            if not features:
                logger.warning(f"Skipping user {user_id} - insufficient data")
                stats['skipped'] += 1
                continue
                
            # Score using ML model
            ml_score = score_user(features)
            
            # Generate mock top 5 features (in production this would come from SHAP)
            top5_features = [
                {"feature": "metric_debt_load30", "importance": 0.3},
                {"feature": "metric_overdraft_count90", "importance": 0.25},
                {"feature": "metric_median_paycheck", "importance": 0.2},
                {"feature": "metric_volatility90", "importance": 0.15},
                {"feature": "metric_clean_buffer7", "importance": 0.1}
            ]
            
            # Update database
            audit_id = update_risk_score_audit(conn, user_id, features, ml_score, top5_features)
            
            if audit_id:
                stats['succeeded'] += 1
            else:
                stats['failed'] += 1
                
        except Exception as e:
            logger.error(f"Error processing user {user_id}: {str(e)}")
            stats['failed'] += 1
            
        # Add a small delay to avoid overloading the database
        time.sleep(0.1)
        
    return stats

def main():
    """Main entry point for the cron job."""
    start_time = time.time()
    logger.info("Starting risk score update cron job")
    
    if DRY_RUN:
        logger.info("DRY RUN MODE - no database changes will be made")
    
    try:
        conn = get_db_connection()
        
        # Get list of users with available data
        users = get_users_with_available_data(conn, limit=BATCH_SIZE)
        
        if not users:
            logger.info("No users found with available data")
            return
            
        # Process users in batches
        stats = process_users(conn, users)
        
        # Log results
        duration = time.time() - start_time
        logger.info(f"Completed risk score updates in {duration:.2f} seconds")
        logger.info(f"Processed {stats['processed']} users: {stats['succeeded']} succeeded, {stats['failed']} failed, {stats['skipped']} skipped")
        
    except Exception as e:
        logger.error(f"Error in risk score update job: {str(e)}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    main() 