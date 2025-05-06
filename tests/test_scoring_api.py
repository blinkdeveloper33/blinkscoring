#!/usr/bin/env python3
"""
Tests for the scoring API
"""
import unittest
import os
import sys
import json
from unittest.mock import patch, MagicMock

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestScoringAPI(unittest.TestCase):
    """Test cases for the scoring API"""
    
    def setUp(self):
        """Set up the test client"""
        from fastapi.testclient import TestClient
        from service_scoring.main import app
        self.client = TestClient(app)
    
    def test_health_endpoint(self):
        """Test the health endpoint"""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("uptime_seconds", data)
    
    def test_score_endpoint(self):
        """Test the score endpoint"""
        payload = {
            "user_id": "test-user",
            "features": {
                "metric_median_paycheck": 1200,
                "metric_overdraft_count90": 0
            },
            "persist_score": False
        }
        
        response = self.client.post("/score", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("score", data)
        self.assertEqual(data["user_id"], "test-user")
        self.assertIn("top_features", data)
    
    def test_batch_score_endpoint(self):
        """Test the batch score endpoint"""
        payload = {
            "items": [
                {
                    "user_id": "test-user-1",
                    "features": {
                        "metric_median_paycheck": 1200,
                        "metric_overdraft_count90": 0
                    },
                    "persist_score": False
                },
                {
                    "user_id": "test-user-2",
                    "features": {
                        "metric_median_paycheck": 800,
                        "metric_overdraft_count90": 2
                    },
                    "persist_score": False
                }
            ],
            "persist_scores": False
        }
        
        response = self.client.post("/score-batch", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 2)
        self.assertIn("processing_time_ms", data)
        self.assertEqual(data["batch_size"], 2)

if __name__ == "__main__":
    unittest.main() 