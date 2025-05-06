# BlinkScoring Model Training

This module implements the machine learning pipeline for training and deploying risk scoring models.

## Overview

The training pipeline:

1. Extracts features and labels from the database (risk_score_audits table)
2. Performs feature engineering to improve model performance
3. Trains a LightGBM binary classification model
4. Evaluates model performance (ROC AUC, PR AUC)
5. Exports model artifacts (both native LightGBM and optimized Treelite formats)
6. Creates model metadata for monitoring and tracking

## Usage

### Training a New Model

```bash
# Local development
python -m service_trainer.run_training

# With deployment
python -m service_trainer.run_training --deploy

# Force deployment (even if metrics are worse)
python -m service_trainer.run_training --deploy --force
```

### On Railway

The training process can be run as a cron job using Railway's job scheduling:

```
train: python -m service_trainer.run_training
```

## Key Features

- **Temporal splitting**: Ensures validation is performed on future data to avoid look-ahead bias
- **Feature engineering**: Applies transformations to improve model performance
- **Treelite compilation**: Converts the model to optimized C/C++ for faster inference
- **Feature importance tracking**: Records which metrics have the biggest impact
- **Model metadata**: Saves evaluation metrics for monitoring and comparison

## Model Performance

The current model uses the following features ranked by importance:

1. metric_debt_load30 (negative correlation)
2. metric_overdraft_count90 (negative correlation)
3. metric_median_paycheck (positive correlation)
4. metric_clean_buffer7 (positive correlation)
5. metric_volatility90 (negative correlation)

The target for prediction is whether a user will ever fall into default or delinquency on cash advances.

## Integration with Scoring Service

The trained model is automatically loaded by the scoring service. The prediction module (`service_scoring/predict.py`) handles both:

- Individual user scoring
- Batch scoring for multiple users

## File Structure

- `train.py`: Core training logic
- `run_training.py`: CLI wrapper for training
- `README.md`: This documentation file

## Dependencies

- LightGBM: Gradient boosting framework
- Treelite: Model compiler for fast inference
- Pandas/NumPy: Data processing
- SQLAlchemy: Database access 