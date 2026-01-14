worker: python3 eth_master_bot.py
web: uvicorn dashboard_api:app --host 0.0.0.0 --port $PORT
dashboard: uvicorn dashboard_server:app --host 0.0.0.0 --port $PORT
