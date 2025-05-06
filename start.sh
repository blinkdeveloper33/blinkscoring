#!/bin/bash
set -e
# Activate virtual environment
source /opt/venv/bin/activate
# Debug information
echo "Current directory: $(pwd)"
echo "Directory contents:"
ls -la
# Go to service directory and run app
cd service-scoring
echo "Service directory contents:"
ls -la
# Start the app
exec uvicorn main:app --host 0.0.0.0 --port $PORT
