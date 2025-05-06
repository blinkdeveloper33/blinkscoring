#!/usr/bin/env python3
"""
Verify that the module imports work correctly locally.
This helps diagnose any PYTHONPATH or module structure issues.
"""

import os
import sys
import importlib
from pathlib import Path

def main():
    print(f"Current working directory: {os.getcwd()}")
    print(f"Files in current directory: {os.listdir('.')}")
    print(f"Python path: {sys.path}")
    
    # Try to import the module
    print("\nAttempting to import service_scoring.main...")
    try:
        # Add the current directory to the path if not already there
        if '.' not in sys.path:
            sys.path.insert(0, '.')
        
        # Try importing the module
        import service_scoring.main
        print(f"✅ Successfully imported service_scoring.main")
        print(f"Module located at: {service_scoring.main.__file__}")
        print(f"App defined: {'app' in dir(service_scoring.main)}")
        
        # Check for FastAPI app instance
        if hasattr(service_scoring.main, 'app'):
            print(f"FastAPI app routes: {[route.path for route in service_scoring.main.app.routes]}")
    except ImportError as e:
        print(f"❌ Import error: {e}")
    
    print("\nVerifying directory structure:")
    # Check if service_scoring exists
    if os.path.exists('service_scoring'):
        print(f"✅ service_scoring directory exists")
        print(f"Contents: {os.listdir('service_scoring')}")
    else:
        print(f"❌ service_scoring directory does not exist")
    
    # Print the Git tracked files to see what's actually in version control
    print("\nFiles tracked by Git:")
    import subprocess
    try:
        result = subprocess.run(['git', 'ls-files'], capture_output=True, text=True)
        if result.returncode == 0:
            service_files = [f for f in result.stdout.splitlines() if f.startswith('service_')]
            print(f"Service files in Git: {service_files}")
        else:
            print(f"Error running git ls-files: {result.stderr}")
    except Exception as e:
        print(f"Error checking Git files: {e}")

if __name__ == "__main__":
    main() 