"""
Database utilities for BlinkScoring ML
"""
import os
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, text
from contextlib import contextmanager
import json

logger = logging.getLogger(__name__)

# Default connection URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
CONNECTION_POOL = None
CONNECTION_POOL_CREATED_AT = 0
POOL_MAX_AGE_SECONDS = 3600  # Refresh connections after 1 hour

def get_sqlalchemy_engine():
    """
    Get a SQLAlchemy engine with the appropriate connection settings.
    
    Returns:
        SQLAlchemy engine
    """
    return create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800
    )

def _get_connection_pool():
    """
    Create or retrieve a psycopg2 connection pool with refresh functionality.
    """
    global CONNECTION_POOL, CONNECTION_POOL_CREATED_AT
    
    current_time = time.time()
    if CONNECTION_POOL is None or (current_time - CONNECTION_POOL_CREATED_AT) > POOL_MAX_AGE_SECONDS:
        if CONNECTION_POOL is not None:
            logger.info("Refreshing connection pool due to age")
        
        # SimpleConnectionPool(minconn, maxconn, dsn)
        CONNECTION_POOL = psycopg2.pool.SimpleConnectionPool(
            1, 20, DATABASE_URL
        )
        CONNECTION_POOL_CREATED_AT = current_time
        
    return CONNECTION_POOL

@contextmanager
def get_postgres_connection(dictcursor=True):
    """
    Get a PostgreSQL connection with the appropriate settings.
    
    Args:
        dictcursor: Whether to use a RealDictCursor (default: True)
        
    Returns:
        psycopg2 connection object
    """
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        if dictcursor:
            conn.cursor_factory = psycopg2.extras.RealDictCursor
        
        conn.autocommit = True
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        pool.putconn(conn)

def execute_query(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Execute a SQL query and return the results.
    
    Args:
        query: The SQL query to execute
        params: Optional parameters for the query
        
    Returns:
        List of dictionaries with the query results
    """
    with get_postgres_connection(dictcursor=True) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(query, params or {})
                if cur.description:
                    return cur.fetchall()
                return []
            except Exception as e:
                logger.error(f"Error executing query: {e}")
                logger.error(f"Query: {query}")
                logger.error(f"Params: {params}")
                raise

def get_active_model_info() -> Dict[str, Any]:
    """
    Get information about the currently active model.
    
    Returns:
        Dictionary with model information
    """
    query = """
    SELECT model_id, version_tag, artifact_url, train_auc, train_date
    FROM blink_models
    WHERE promoted_to_prod = TRUE
    ORDER BY train_date DESC
    LIMIT 1;
    """
    
    results = execute_query(query)
    
    if results:
        return results[0]
    
    # Return default model info if no model is found
    return {
        "model_id": "default",
        "version_tag": "v0.1.0-default",
        "artifact_url": os.getenv("MODEL_PATH", "models/latest/model.tl"),
        "train_auc": 0.5,
        "train_date": None
    }

def store_risk_score(
    user_id: str, 
    score: float, 
    model_version: str, 
    explanations: List[Tuple[str, float]],
    raw_features: Dict[str, Any] = None
):
    """
    Store a risk score and its explanations in the database.
    
    Args:
        user_id: The user ID
        score: The risk score (0-1)
        model_version: The model version tag
        explanations: List of (feature_name, shap_value) tuples
        raw_features: Optional raw features used to generate the score
    """
    shap_json = json.dumps([
        {"feature": feature, "impact": float(value)} 
        for feature, value in explanations
    ])
    
    query = """
    INSERT INTO risk_score_audits 
    (user_id, blink_ml_score, blink_ml_version, shap_top5, raw_features)
    VALUES (%(user_id)s, %(score)s, %(model_version)s, %(shap_top5)s, %(raw_features)s)
    """
    
    params = {
        "user_id": user_id,
        "score": score,
        "model_version": model_version,
        "shap_top5": shap_json,
        "raw_features": json.dumps(raw_features) if raw_features else None
    }
    
    execute_query(query, params)
    return True

def get_feature_store_snapshots(limit=1000, since_days=30):
    """
    Get feature snapshots from the feature store.
    
    Args:
        limit: Maximum number of records to return
        since_days: Only return features from the past N days
        
    Returns:
        List of feature snapshots
    """
    query = """
    SELECT snapshot_id, user_id, decision_ts, json_features
    FROM feature_store_snapshots
    WHERE decision_ts > NOW() - INTERVAL '%(since_days)s days'
    ORDER BY decision_ts DESC
    LIMIT %(limit)s
    """
    
    params = {
        "limit": limit,
        "since_days": since_days
    }
    
    return execute_query(query, params) 