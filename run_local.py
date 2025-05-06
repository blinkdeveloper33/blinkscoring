#!/usr/bin/env python3
"""
Helper script for local development that sets up a basic environment
and starts the FastAPI scoring service.
"""
import os
import sys
import argparse
import uvicorn
from pathlib import Path

def ensure_models_directory():
    """Create models directory structure for local development"""
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    # Create a latest symlink if it doesn't exist
    latest_dir = models_dir / "latest"
    latest_dir.mkdir(exist_ok=True)

def run_scoring_service():
    """Start the FastAPI scoring service"""
    ensure_models_directory()
    
    # Set up default environment variables for local development
    os.environ.setdefault("MODEL_PATH", str(Path("models/latest/model.tl").absolute()))
    os.environ.setdefault("EXPLAINER_PATH", str(Path("models/latest/shap_explainer.pkl").absolute()))
    os.environ.setdefault("MODEL_VERSION", "local-dev")
    
    print("Starting BlinkScoring ML API server...")
    print(f"MODEL_PATH: {os.environ['MODEL_PATH']}")
    print(f"EXPLAINER_PATH: {os.environ['EXPLAINER_PATH']}")
    
    # Start uvicorn server
    uvicorn.run(
        "service-scoring.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

def run_cron_worker():
    """Run the cron worker once"""
    ensure_models_directory()
    
    # Set up default environment variables for local development
    os.environ.setdefault("SCORING_URL", "http://localhost:8000")
    os.environ.setdefault("MODEL_VERSION", "local-dev")
    
    print("Running cron worker...")
    print(f"SCORING_URL: {os.environ['SCORING_URL']}")
    
    # Import and run the worker
    try:
        sys.path.insert(0, os.getcwd())
        from service_cron.worker import main
        main()
    except Exception as e:
        print(f"Error running cron worker: {str(e)}")

def run_trainer():
    """Run the model trainer once"""
    ensure_models_directory()
    
    # Set up default environment variables for local development
    os.environ.setdefault("MODEL_DIR", str(Path("models").absolute()))
    
    print("Running model trainer...")
    print(f"MODEL_DIR: {os.environ['MODEL_DIR']}")
    
    # Import and run the trainer
    try:
        sys.path.insert(0, os.getcwd())
        from service_trainer.train import main
        main()
    except Exception as e:
        print(f"Error running model trainer: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BlinkScoring ML local development helper")
    parser.add_argument(
        "service",
        choices=["scoring", "cron", "trainer"],
        help="Which service to run"
    )
    
    args = parser.parse_args()
    
    if args.service == "scoring":
        run_scoring_service()
    elif args.service == "cron":
        run_cron_worker()
    elif args.service == "trainer":
        run_trainer()
    else:
        print(f"Unknown service: {args.service}")
        parser.print_help()
        sys.exit(1) 