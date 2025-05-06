#!/bin/bash
# Setup script for local development environment

echo "Setting up BlinkScoring ML local development environment..."

# Create necessary directories
mkdir -p models/latest

# Environment variables for local development
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/postgres"
export MODEL_DIR="models"
export PORT=8000

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3."
    exit 1
fi

# Install dependencies
echo "Installing Python dependencies..."
python3 -m pip install -r requirements.txt

# Create dummy model files if they don't exist
if [ ! -f "models/latest/model.txt" ]; then
    echo "Creating dummy model files..."
    echo "Dummy model for testing" > models/latest/model.txt
    
    # Create feature descriptions JSON
    cat > models/latest/feature_descriptions.json << EOF
{
  "metric_num_accounts": "Number of Accounts (Positive impact on score)",
  "metric_account_types": "Account Types (Positive impact on score)",
  "metric_total_balance": "Total Balance (Positive impact on score)",
  "metric_total_available": "Total Available (Positive impact on score)",
  "metric_checking_balance": "Checking Balance (Positive impact on score)",
  "metric_savings_balance": "Savings Balance (Positive impact on score)",
  "metric_transaction_count90": "Transaction Count 90 (Positive impact on score)",
  "metric_income_total90": "Income Total 90 (Positive impact on score)",
  "metric_expense_total90": "Expense Total 90 (Negative impact on score)",
  "metric_income_expense_ratio": "Income Expense Ratio (Positive impact on score)",
  "metric_balance_volatility": "Balance Volatility (Negative impact on score)",
  "metric_balance_min90": "Balance Min 90 (Positive impact on score)",
  "metric_balance_max90": "Balance Max 90 (Positive impact on score)",
  "metric_balance_range90": "Balance Range 90 (Neutral impact on score)",
  "metric_median_paycheck": "Median Paycheck (Positive impact on score)",
  "metric_overdraft_count90": "Overdraft Count 90 (Negative impact on score)",
  "metric_low_balance_days90": "Low Balance Days 90 (Negative impact on score)"
}
EOF
fi

echo "Local environment setup complete!"
echo ""
echo "To start the scoring API, run:"
echo "  python start_api.py"
echo ""
echo "To run the cron worker, run:"
echo "  python -m service-cron.worker"
echo ""
echo "To test the API, run:"
echo "  curl -X POST http://localhost:8000/score -H \"Content-Type: application/json\" -d '{\"user_id\": \"test-user\", \"features\": {\"metric_median_paycheck\": 1200, \"metric_overdraft_count90\": 0}}'" 