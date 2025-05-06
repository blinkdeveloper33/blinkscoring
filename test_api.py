#!/usr/bin/env python3
"""
Test script for BlinkScoring API endpoints.
Validates health check, individual scoring, and batch scoring functionality.
"""
import os
import sys
import json
import logging
import requests
import argparse
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Default API URL (can be overridden with command line args)
DEFAULT_API_URL = "http://localhost:8080"

def test_health_endpoint(base_url: str) -> bool:
    """Test the health check endpoint."""
    url = f"{base_url}/health"
    
    try:
        logger.info(f"Testing health endpoint: {url}")
        response = requests.get(url)
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"Health check response: {data}")
        
        # Verify expected fields
        assert "status" in data, "Missing 'status' field in response"
        assert data["status"] == "ok", f"Expected status 'ok', got '{data['status']}'"
        assert "uptime_seconds" in data, "Missing 'uptime_seconds' field in response"
        
        logger.info("✅ Health check test passed")
        return True
    
    except Exception as e:
        logger.error(f"❌ Health check test failed: {e}")
        return False

def generate_test_features() -> Dict[str, float]:
    """Generate a set of test features for scoring."""
    return {
        'metric_observed_history_days': 180,
        'metric_median_paycheck': 3000,
        'metric_paycheck_regularity': 0.8, 
        'metric_days_since_last_paycheck': 5,
        'metric_overdraft_count90': 2,
        'metric_net_cash30': 1500,
        'metric_debt_load30': 0.3,
        'metric_volatility90': 0.2,
        'metric_clean_buffer7': 0.9,
        'metric_buffer_volatility': 0.1,
        'metric_deposit_multiplicity30': 3,
    }

def generate_challenging_features() -> Dict[str, float]:
    """Generate features for a high-risk user."""
    return {
        'metric_observed_history_days': 45,  # Short history
        'metric_median_paycheck': 800,       # Low income
        'metric_paycheck_regularity': 0.3,   # Irregular pay
        'metric_days_since_last_paycheck': 20, # Long time since last pay
        'metric_overdraft_count90': 8,       # Many overdrafts
        'metric_net_cash30': -500,           # Negative cash flow
        'metric_debt_load30': 0.7,           # High debt
        'metric_volatility90': 0.8,          # High volatility
        'metric_clean_buffer7': 0.1,         # Low buffer
        'metric_buffer_volatility': 0.9,     # Unstable buffer
        'metric_deposit_multiplicity30': 1,   # Single income source
    }

def test_score_endpoint(base_url: str) -> bool:
    """Test the individual score endpoint."""
    url = f"{base_url}/score"
    
    try:
        # Test with normal user
        features = generate_test_features()
        payload = {
            "user_id": "test_user_123",
            "features": features,
            "persist_score": False
        }
        
        logger.info(f"Testing score endpoint with normal user: {url}")
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"Score response: {data}")
        
        # Verify expected fields
        assert "score" in data, "Missing 'score' field in response"
        assert "user_id" in data, "Missing 'user_id' field in response"
        assert data["user_id"] == "test_user_123", "User ID mismatch"
        
        normal_score = data["score"]
        logger.info(f"Normal user score: {normal_score}")
        
        # Test with high-risk user
        risky_features = generate_challenging_features()
        risky_payload = {
            "user_id": "risky_user_456",
            "features": risky_features,
            "persist_score": False
        }
        
        logger.info(f"Testing score endpoint with high-risk user")
        risky_response = requests.post(url, json=risky_payload)
        risky_response.raise_for_status()
        
        risky_data = risky_response.json()
        risky_score = risky_data["score"]
        logger.info(f"High-risk user score: {risky_score}")
        
        # In a well-functioning model, high-risk users should have lower scores
        # (or higher scores if higher means riskier, depending on the model)
        # Let's assume lower is better/less risky
        if normal_score != risky_score:
            logger.info("✅ Model correctly differentiated between normal and high-risk users")
        else:
            logger.warning("⚠️ Model gave same score to normal and high-risk users")
        
        logger.info("✅ Score endpoint test passed")
        return True
    
    except Exception as e:
        logger.error(f"❌ Score endpoint test failed: {e}")
        return False

def test_batch_score_endpoint(base_url: str) -> bool:
    """Test the batch scoring endpoint."""
    url = f"{base_url}/score-batch"
    
    try:
        # Create a batch of 3 users with varying risk profiles
        items = [
            {
                "user_id": "user_normal_1",
                "features": generate_test_features(),
                "persist_score": False
            },
            {
                "user_id": "user_normal_2",
                "features": generate_test_features(),
                "persist_score": False
            },
            {
                "user_id": "user_risky_1",
                "features": generate_challenging_features(),
                "persist_score": False
            }
        ]
        
        payload = {
            "items": items,
            "persist_scores": False
        }
        
        logger.info(f"Testing batch score endpoint: {url}")
        logger.info(f"Batch size: {len(items)} users")
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        # Verify expected fields
        assert "results" in data, "Missing 'results' field in response"
        assert "batch_size" in data, "Missing 'batch_size' field in response"
        assert data["batch_size"] == len(items), f"Expected batch_size {len(items)}, got {data['batch_size']}"
        
        # Check individual results
        scores = []
        for i, result in enumerate(data["results"]):
            assert "score" in result, f"Missing 'score' in result {i}"
            assert "user_id" in result, f"Missing 'user_id' in result {i}"
            assert result["user_id"] == items[i]["user_id"], f"User ID mismatch for result {i}"
            scores.append((result["user_id"], result["score"]))
        
        logger.info(f"Batch scores: {scores}")
        
        # Check processing time if available
        if "processing_time_ms" in data:
            logger.info(f"Batch processing time: {data['processing_time_ms']} ms")
        
        logger.info("✅ Batch score endpoint test passed")
        return True
    
    except Exception as e:
        logger.error(f"❌ Batch score endpoint test failed: {e}")
        return False

def test_missing_features(base_url: str) -> bool:
    """Test how the API handles missing features."""
    url = f"{base_url}/score"
    
    try:
        # Incomplete feature set
        incomplete_features = {
            'metric_median_paycheck': 2500,
            'metric_overdraft_count90': 1,
            # Other features missing
        }
        
        payload = {
            "user_id": "missing_features_user",
            "features": incomplete_features,
            "persist_score": False
        }
        
        logger.info(f"Testing score endpoint with missing features")
        response = requests.post(url, json=payload)
        
        # We expect this to either:
        # 1. Return a valid response (if the API handles missing features gracefully)
        # 2. Return an error (if the API requires all features)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"API handled missing features - returned score: {data['score']}")
            logger.info("✅ Missing features test passed (API handled gracefully)")
        else:
            logger.info(f"API rejected missing features with status {response.status_code}")
            logger.info(f"Response: {response.text}")
            logger.info("✅ Missing features test passed (API rejected incomplete request)")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Missing features test failed: {e}")
        return False

def run_all_tests(base_url: str) -> bool:
    """Run all API tests."""
    logger.info(f"Running all tests against API at {base_url}")
    
    tests = [
        test_health_endpoint,
        test_score_endpoint,
        test_batch_score_endpoint,
        test_missing_features
    ]
    
    results = []
    for test in tests:
        results.append(test(base_url))
    
    success_count = sum(results)
    total_count = len(results)
    
    logger.info(f"Test Results: {success_count} of {total_count} tests passed")
    
    return all(results)

def get_cli_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Test BlinkScoring API endpoints")
    parser.add_argument("--url", default=DEFAULT_API_URL, help="Base URL of the API (default: %(default)s)")
    parser.add_argument("--test", choices=["health", "score", "batch", "missing", "all"], 
                        default="all", help="Specific test to run (default: all)")
    return parser.parse_args()

def main():
    """Main entry point."""
    args = get_cli_args()
    
    try:
        if args.test == "health":
            success = test_health_endpoint(args.url)
        elif args.test == "score":
            success = test_score_endpoint(args.url)
        elif args.test == "batch":
            success = test_batch_score_endpoint(args.url)
        elif args.test == "missing":
            success = test_missing_features(args.url)
        else:  # "all"
            success = run_all_tests(args.url)
        
        return 0 if success else 1
    
    except Exception as e:
        logger.error(f"Error running tests: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 