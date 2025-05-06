# BlinkScoring ML

A machine learning platform for credit risk scoring built with Nix and deployed on Railway.

## Overview

BlinkScoring ML is a production-ready platform for risk scoring users based on their financial transaction data. The system:

- Scores users every 5 minutes based on new financial data
- Automatically retrains models weekly using historical repayment data
- Provides explainable decisions using SHAP values
- Self-heals by detecting performance drift and promoting better models

## Architecture

The platform consists of three microservices:

1. **Scoring Service** (`service-scoring/`): FastAPI model server that predicts repayment probability
2. **Cron Service** (`service-cron/`): Worker that runs every 5 minutes to score users with new transaction data
3. **Trainer Service** (`service-trainer/`): Runs weekly to build and deploy improved models

All services use a shared PostgreSQL database and Railway persistent storage.

## Getting Started

### Prerequisites

- [Nix](https://nixos.org/download.html) for reproducible builds
- [Railway CLI](https://docs.railway.app/develop/cli) for deployment
- PostgreSQL database (URL provided via `DATABASE_URL` environment variable)

### Setup with Nix

```bash
# Enter Nix development shell
nix develop

# Start the scoring API
python -m uvicorn service-scoring.main:app --host 0.0.0.0 --port 8000
```

### Setup with Python directly

```bash
# Install dependencies
pip install -r requirements.txt

# Start the scoring API
python start_api.py
```

### Test the API

```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user", 
    "features": {
      "metric_median_paycheck": 1200, 
      "metric_overdraft_count90": 0,
      "metric_total_balance": 5000,
      "metric_transaction_count90": 55
    }
  }'
```

## Database Schema

The system uses the following database tables:

- `risk_score_audits`: Stores ML model risk scores and explanations
- `feature_store_snapshots`: Historical feature snapshots for training
- `blink_models`: Model metadata and deployment status

## Development

### Project Structure

```
blinkscoring-ml/
├── common/              # Shared utilities
├── models/              # Model storage
├── service-scoring/     # API service
├── service-cron/        # Periodic scoring service
├── service-trainer/     # Model training service
├── sql/                 # Database migrations
├── tests/               # Unit tests
├── flake.nix            # Nix build configuration
├── nixpacks.toml        # Railway builder config
└── railway.json         # Railway service definitions
```

### Testing

Run the test suite with:

```bash
python -m unittest discover tests
```

## Deployment

The system is designed to be deployed on Railway:

1. Configure Railway with the required environment variables:
   - `DATABASE_URL`: PostgreSQL connection string
   - `MODEL_DIR`: Directory for model storage
   - `PROMOTE_TO_PROD`: Whether to auto-promote models (true/false)

2. Deploy using the Railway CLI:
   ```bash
   railway up
   ```

## License

This project is licensed under the MIT License - see the LICENSE file for details. 