release: python3 create_admin.py || true
worker: python3 eth_master_bot.py
ml-trainer: python3 tools/continuous_ml_trainer.py --continuous
web: uvicorn dashboard_api:app --host 0.0.0.0 --port $PORT
