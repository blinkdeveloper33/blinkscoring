web: source /opt/venv/bin/activate && python /app/debug_path.py && cd /app && PYTHONPATH=/app python -m uvicorn service_scoring.main:app --host 0.0.0.0 --port $PORT
diagnostic: source /opt/venv/bin/activate && ls -la /app && python /app/debug_path.py
cron: source /opt/venv/bin/activate && cd /app && PYTHONPATH=/app python -m service_cron.worker
trainer: source /opt/venv/bin/activate && cd /app && PYTHONPATH=/app python -m service_trainer.train 