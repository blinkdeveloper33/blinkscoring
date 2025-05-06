#!/usr/bin/env python3
"""
Debugging script to help diagnose Python module import issues in the container.
Will be run as part of the startup process.
"""
import os
import sys
import glob
import importlib

print("=" * 60)
print("PYTHON IMPORT PATH DEBUGGER")
print("=" * 60)

print(f"Current working directory: {os.getcwd()}")
print(f"Files in current directory: {os.listdir('.')}")
print(f"Python path: {sys.path}")
print(f"Environment PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")

# Try to import service_scoring.main
print("\nTrying to import 'service_scoring.main'...")
try:
    # First try direct import
    import service_scoring.main
    print("✅ Successfully imported service_scoring.main")
    print(f"Module located at: {service_scoring.main.__file__}")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    
    # Try searching for it
    print("\nSearching for service_scoring directories...")
    for path in ["/app", "/", "/usr", "/opt", "/home", "/root", "."]:
        if os.path.exists(path):
            print(f"Searching in {path}...")
            for root, dirs, files in os.walk(path, topdown=True, followlinks=False):
                if "service_scoring" in dirs:
                    print(f"Found service_scoring in {root}")
                    service_path = os.path.join(root, "service_scoring")
                    print(f"Contents: {os.listdir(service_path)}")
                    
                # Don't go into deep system directories
                if root.count('/') > 5:
                    dirs[:] = []
                    
                # Skip common system directories to speed up search    
                dirs[:] = [d for d in dirs if d not in [".git", "proc", "sys", "dev", "tmp", "var", "run"]]
    
    # Try adding current directory to PYTHONPATH
    print("\nAdding current directory to sys.path and retrying import...")
    if "." not in sys.path:
        sys.path.insert(0, ".")
    try:
        import service_scoring.main
        print("✅ Successfully imported after adding '.' to sys.path")
    except ImportError as e:
        print(f"❌ Still failed: {e}")

print("\nChecking nearby directories for module files...")
for pattern in ["./service_*", "/app/service_*", "../service_*"]:
    matches = glob.glob(pattern)
    if matches:
        print(f"Found matches for {pattern}: {matches}")
        for match in matches:
            if os.path.isdir(match):
                print(f"Contents of {match}: {os.listdir(match)}")

print("=" * 60)
print("END DEBUGGING OUTPUT")
print("=" * 60) 