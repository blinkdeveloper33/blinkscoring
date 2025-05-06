web: uvicorn service_scoring.main:app --host 0.0.0.0 --port ${PORT:-8000}
cron: python -m service_cron.start_cron
train: python -m service_trainer.run_training 