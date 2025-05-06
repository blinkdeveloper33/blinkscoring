#!/bin/bash
set -e
set -x
# Show environment
echo "Environment:"
echo "PWD: $PWD"
echo "PATH: $PATH"
echo "Directory contents:"
ls -la
# Activate virtual environment
source /opt/venv/bin/activate || echo "Failed to activate venv"
# Create Python-friendly symlink
ln -sf service-scoring service_scoring
ls -la
# Update Python path
export PYTHONPATH=$PWD:$PYTHONPATH
echo "PYTHONPATH: $PYTHONPATH"
# Change to app directory and run
cd service_scoring
echo "App directory contents:"
ls -la
# Run app
echo "Starting uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port $PORT
