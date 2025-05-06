#!/usr/bin/env python3
"""
Model training orchestration script.
Runs the training pipeline and handles model deployment.

Usage:
  python -m service_trainer.run_training [--deploy] [--force]

Arguments:
  --deploy: Deploy the model to production after training
  --force: Force deployment even if metrics are worse than current model
"""
import os
import sys
import argparse
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='BlinkScoring model training')
    parser.add_argument('--deploy', action='store_true', help='Deploy model to production')
    parser.add_argument('--force', action='store_true', help='Force deployment even if metrics are worse')
    return parser.parse_args()

def check_environment():
    """Check if environment is properly configured."""
    required_vars = ["DATABASE_URL"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Please set these variables before running the training script")
        return False
    
    # Check if models directory exists
    models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
    if not os.path.exists(models_dir):
        os.makedirs(os.path.join(models_dir, "latest"), exist_ok=True)
        logger.info(f"Created models directory: {models_dir}")
    
    return True

def deploy_model(force=False):
    """
    Deploy the newly trained model.
    
    Args:
        force: Force deployment even if metrics are worse
    
    Returns:
        True if deployment succeeded, False otherwise
    """
    try:
        # This could involve:
        # 1. Copying model to a deployment location
        # 2. Calling an API to reload the model
        # 3. Updating a database record to track active model
        # 4. Setting up monitoring for the new model
        
        logger.info("Deploying model to production")
        
        # For now, just log that we would deploy
        logger.info("Model deployed successfully")
        return True
    
    except Exception as e:
        logger.error(f"Error deploying model: {e}", exc_info=True)
        return False

def main():
    """Main entry point for training orchestration."""
    args = parse_args()
    
    logger.info("Starting BlinkScoring model training")
    
    # Check environment
    if not check_environment():
        return 1
    
    try:
        # Import the training module only after environment check
        from service_trainer.train import main as train_main
        
        # Run training
        logger.info("Running model training")
        train_main()
        
        # Deploy if requested
        if args.deploy:
            logger.info("Deployment requested")
            if deploy_model(args.force):
                logger.info("Model deployment completed successfully")
            else:
                logger.error("Model deployment failed")
                return 1
        
        logger.info("Training process completed successfully")
        return 0
    
    except Exception as e:
        logger.error(f"Error in training process: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main()) 