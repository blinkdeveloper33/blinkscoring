#!/usr/bin/env python3
"""
Scoring service API for BlinkScoring ML
"""

import os
import time
import logging
from typing import Dict, List, Optional, Union
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import our ML scoring endpoints
from service_scoring.endpoints import router as ml_router

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="BlinkScoring ML API",
    description="API for risk scoring based on financial data",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
START_TIME = time.time()

# Health check route
@app.get("/health")
async def health_check():
    """Health check endpoint for the scoring API"""
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME)
    }

# Include the ML scoring router
app.include_router(ml_router)

# Main entry point
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("service_scoring.main:app", host="0.0.0.0", port=port, reload=True) 