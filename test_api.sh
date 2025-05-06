#!/bin/bash
# Simple script to test BlinkScoring API using curl

# Default to localhost if API_URL not set
API_URL=${API_URL:-"http://localhost:8080"}
echo "Testing API at: $API_URL"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Test health endpoint
echo -e "\n${YELLOW}Testing health endpoint...${NC}"
curl -s $API_URL/health | jq .

# Test score endpoint with normal user
echo -e "\n${YELLOW}Testing score endpoint with normal user...${NC}"
curl -s -X POST $API_URL/score \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_123",
    "features": {
      "metric_observed_history_days": 180,
      "metric_median_paycheck": 3000,
      "metric_paycheck_regularity": 0.8,
      "metric_days_since_last_paycheck": 5,
      "metric_overdraft_count90": 2,
      "metric_net_cash30": 1500,
      "metric_debt_load30": 0.3,
      "metric_volatility90": 0.2,
      "metric_clean_buffer7": 0.9,
      "metric_buffer_volatility": 0.1,
      "metric_deposit_multiplicity30": 3
    },
    "persist_score": false
  }' | jq .

# Test score endpoint with high-risk user
echo -e "\n${YELLOW}Testing score endpoint with high-risk user...${NC}"
curl -s -X POST $API_URL/score \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "risky_user_456",
    "features": {
      "metric_observed_history_days": 45,
      "metric_median_paycheck": 800,
      "metric_paycheck_regularity": 0.3,
      "metric_days_since_last_paycheck": 20,
      "metric_overdraft_count90": 8,
      "metric_net_cash30": -500,
      "metric_debt_load30": 0.7,
      "metric_volatility90": 0.8,
      "metric_clean_buffer7": 0.1,
      "metric_buffer_volatility": 0.9,
      "metric_deposit_multiplicity30": 1
    },
    "persist_score": false
  }' | jq .

# Test batch scoring endpoint
echo -e "\n${YELLOW}Testing batch scoring endpoint...${NC}"
curl -s -X POST $API_URL/score-batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "user_id": "user_normal_1",
        "features": {
          "metric_observed_history_days": 180,
          "metric_median_paycheck": 3000,
          "metric_paycheck_regularity": 0.8,
          "metric_days_since_last_paycheck": 5,
          "metric_overdraft_count90": 2,
          "metric_net_cash30": 1500,
          "metric_debt_load30": 0.3,
          "metric_volatility90": 0.2,
          "metric_clean_buffer7": 0.9,
          "metric_buffer_volatility": 0.1,
          "metric_deposit_multiplicity30": 3
        },
        "persist_score": false
      },
      {
        "user_id": "user_risky_1",
        "features": {
          "metric_observed_history_days": 45,
          "metric_median_paycheck": 800,
          "metric_paycheck_regularity": 0.3,
          "metric_days_since_last_paycheck": 20,
          "metric_overdraft_count90": 8,
          "metric_net_cash30": -500,
          "metric_debt_load30": 0.7,
          "metric_volatility90": 0.8,
          "metric_clean_buffer7": 0.1,
          "metric_buffer_volatility": 0.9,
          "metric_deposit_multiplicity30": 1
        },
        "persist_score": false
      }
    ],
    "persist_scores": false
  }' | jq .

echo -e "\n${GREEN}Tests completed!${NC}" 