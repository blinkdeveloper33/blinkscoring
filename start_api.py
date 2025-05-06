#!/usr/bin/env python3
"""
Simple script to start the BlinkScoring ML API locally.
"""
import uvicorn

if __name__ == "__main__":
    print("Starting BlinkScoring ML API server...")
    uvicorn.run("service_scoring.main:app", host="0.0.0.0", port=8000, reload=True) 