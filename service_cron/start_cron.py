#!/usr/bin/env python3
"""
Cron job scheduler for BlinkScoring.
Sets up and runs periodic tasks including risk score updates.
"""
import os
import sys
import time
import logging
import schedule
import importlib
from datetime import datetime

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"/tmp/blink_cron_scheduler_{datetime.now().strftime('%Y%m%d')}.log")
    ]
)
logger = logging.getLogger(__name__)

# Import cron job modules
try:
    from service_cron.score_users import main as run_scoring
    scoring_available = True
except ImportError as e:
    logger.error(f"Could not import scoring module: {e}")
    scoring_available = False

def job_wrapper(job_name, job_func):
    """Wrapper to handle exceptions in scheduled jobs."""
    try:
        logger.info(f"Starting job: {job_name}")
        start_time = time.time()
        job_func()
        duration = time.time() - start_time
        logger.info(f"Completed job: {job_name} in {duration:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in job {job_name}: {e}", exc_info=True)

def schedule_tasks():
    """Set up scheduled tasks."""
    logger.info("Setting up scheduled tasks")
    
    # Schedule risk scoring job to run every hour
    if scoring_available:
        schedule.every(1).hours.do(
            job_wrapper, 
            "risk_score_update", 
            run_scoring
        )
        logger.info("Scheduled risk score update job to run every hour")
    
    # Add other scheduled tasks here as needed
    
    logger.info("All tasks scheduled")

def run_scheduler():
    """Run the scheduler loop."""
    logger.info("Starting scheduler")
    
    schedule_tasks()
    
    # Run the scoring job immediately on startup
    if scoring_available:
        logger.info("Running initial risk score update")
        job_wrapper("risk_score_update_initial", run_scoring)
    
    # Main loop
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            # Don't break, try to continue
            time.sleep(300)  # Wait 5 minutes before retrying after an error

if __name__ == "__main__":
    logger.info("BlinkScoring cron scheduler starting")
    run_scheduler() 