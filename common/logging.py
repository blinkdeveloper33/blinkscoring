"""
Centralized logging configuration for BlinkScoring ML
Includes Sentry integration for error tracking
"""

import os
import logging
import sys
from typing import Optional

# Try to import sentry_sdk, gracefully handle if not available
try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

# Get environment variables
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
SENTRY_DSN = os.getenv("SENTRY_DSN")
SERVICE_NAME = os.getenv("SERVICE_NAME", "blinkscoring-ml")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

def configure_logging(service_name: Optional[str] = None):
    """
    Configure standard Python logging
    
    Args:
        service_name: Optional service name to include in logs
    """
    name = service_name or SERVICE_NAME
    
    # Set up structured logging format
    log_format = f"%(asctime)s - {name} - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=log_format,
        stream=sys.stdout
    )
    
    # Make third-party loggers less verbose
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    logger = logging.getLogger(name)
    logger.info(f"Logging configured for {name} at level {LOG_LEVEL}")
    return logger

def init_sentry():
    """
    Initialize Sentry for error tracking
    """
    if not SENTRY_AVAILABLE:
        logging.warning("Sentry SDK not available, skipping initialization")
        return False
    
    if not SENTRY_DSN:
        logging.info("No SENTRY_DSN provided, skipping Sentry initialization")
        return False
    
    try:
        # Configure Sentry with integrations
        sentry_logging = LoggingIntegration(
            level=logging.INFO,        # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        )
        
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            integrations=[
                sentry_logging,
                SqlalchemyIntegration(),
                FastApiIntegration()
            ],
            
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            # We recommend adjusting this value in production.
            traces_sample_rate=0.2,
            
            # Set profiles_sample_rate to 1.0 to profile 100%
            # of sampled transactions.
            # We recommend adjusting this value in production.
            profiles_sample_rate=0.1,
        )
        
        logging.info(f"Sentry initialized for environment: {ENVIRONMENT}")
        return True
    except Exception as e:
        logging.error(f"Failed to initialize Sentry: {e}")
        return False 