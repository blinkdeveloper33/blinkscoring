#!/usr/bin/env python3
"""
Test script to validate SQL query for risk scoring model.
This will check if the modified query runs without errors.
"""
import os
import sys
import logging
import sqlalchemy as sa
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Database connection
DB_URL = os.getenv("DATABASE_URL")

def test_risk_score_query():
    """Test if the risk score query runs correctly."""
    if not DB_URL:
        logger.error("DATABASE_URL environment variable not set")
        return False
    
    try:
        logger.info("Connecting to database...")
        engine = sa.create_engine(DB_URL)
        
        # Query that was causing issues but is now fixed
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
        LIMIT 10
        """
        
        with engine.connect() as conn:
            logger.info("Executing query...")
            result = pd.read_sql(query, conn)
            
            logger.info(f"Query successful, retrieved {len(result)} rows")
            logger.info(f"Columns: {result.columns.tolist()}")
            
            # Show first row as sample
            if not result.empty:
                logger.info(f"Sample row: {result.iloc[0].to_dict()}")
            
            return True
            
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return False

if __name__ == "__main__":
    success = test_risk_score_query()
    sys.exit(0 if success else 1) 