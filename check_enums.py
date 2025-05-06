#!/usr/bin/env python3
"""
Script to check valid enum values in the database.
This helps identify the correct values to use in SQL queries.
"""
import os
import sys
import logging
import sqlalchemy as sa

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Database connection
DB_URL = os.getenv("DATABASE_URL")

def check_enum_values():
    """Check the valid values for enums in the database."""
    if not DB_URL:
        logger.error("DATABASE_URL environment variable not set")
        return False
    
    try:
        logger.info("Connecting to database...")
        engine = sa.create_engine(DB_URL)
        
        # Query to check enum type values for cash_advance_status_enum
        query_ca_status = """
        SELECT
            n.nspname AS schema,
            t.typname AS type_name,
            e.enumlabel AS enum_value
        FROM pg_type t
        JOIN pg_enum e ON e.enumtypid = t.oid
        JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'cash_advance_status_enum'
        ORDER BY e.enumsortorder;
        """
        
        # Query to check enum type values for repayment_status_enum
        query_rep_status = """
        SELECT
            n.nspname AS schema,
            t.typname AS type_name,
            e.enumlabel AS enum_value
        FROM pg_type t
        JOIN pg_enum e ON e.enumtypid = t.oid
        JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'repayment_status_enum'
        ORDER BY e.enumsortorder;
        """
        
        # Check distinct actual values in tables
        query_ca_values = """
        SELECT DISTINCT status FROM cash_advances;
        """
        
        query_rep_values = """
        SELECT DISTINCT status FROM repayments;
        """
        
        with engine.connect() as conn:
            logger.info("Checking cash_advance_status_enum values:")
            try:
                result = conn.execute(sa.text(query_ca_status))
                for row in result:
                    logger.info(f"  - {row['enum_value']}")
            except Exception as e:
                logger.error(f"Error getting cash_advance_status_enum: {e}")
            
            logger.info("\nChecking repayment_status_enum values:")
            try:
                result = conn.execute(sa.text(query_rep_status))
                for row in result:
                    logger.info(f"  - {row['enum_value']}")
            except Exception as e:
                logger.error(f"Error getting repayment_status_enum: {e}")
            
            logger.info("\nActual values in cash_advances table:")
            try:
                result = conn.execute(sa.text(query_ca_values))
                for row in result:
                    logger.info(f"  - {row['status']}")
            except Exception as e:
                logger.error(f"Error getting cash_advances values: {e}")
            
            logger.info("\nActual values in repayments table:")
            try:
                result = conn.execute(sa.text(query_rep_values))
                for row in result:
                    logger.info(f"  - {row['status']}")
            except Exception as e:
                logger.error(f"Error getting repayments values: {e}")
                
        return True
            
    except Exception as e:
        logger.error(f"Error checking enum values: {e}")
        return False

if __name__ == "__main__":
    success = check_enum_values()
    sys.exit(0 if success else 1) 