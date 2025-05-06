#!/usr/bin/env python3
"""
WSGI config for BlinkScoring project.
This helps some deployment platforms find our app.
"""

import os
import sys

# Set PYTHONPATH environment variable
os.environ["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Print debug information
print(f"WSGI Starting in {os.getcwd()}")
print(f"Files in current directory: {os.listdir('.')}")
print(f"Python path: {sys.path}")
print(f"PYTHONPATH env: {os.environ.get('PYTHONPATH', 'Not set')}")

# Import the FastAPI app
from service_scoring.main import app as application

# For direct running of this file
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("wsgi:application", host="0.0.0.0", port=int(os.environ.get("PORT", 8000))) 