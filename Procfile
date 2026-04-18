release: echo "Ethbot v3 ready"
worker: python3 main_v3.py --paper
web: uvicorn api_v3:app --host 0.0.0.0 --port $PORT
