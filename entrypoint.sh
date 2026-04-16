#!/bin/bash
# Entrypoint script for Railway multi-service deployment
# Routes to the correct service based on RAILWAY_SERVICE_NAME

set -e

echo "Starting service: ${RAILWAY_SERVICE_NAME:-unknown}"
echo "PORT: ${PORT:-not set}"

case "${RAILWAY_SERVICE_NAME}" in
  "worker")
    echo "Starting ETH Trading Bot..."
    exec python3 eth_master_bot.py
    ;;
  "web")
    echo "Starting Dashboard API on port ${PORT}..."
    exec uvicorn dashboard_api:app --host 0.0.0.0 --port "${PORT}"
    ;;
  "auto-learning")
    echo "Starting Auto-Learning Service..."
    exec python3 auto_learning_service.py
    ;;
  "dashboard")
    echo "Starting Dashboard Server on port ${PORT}..."
    # First build the dashboard if not already built
    if [ ! -d "dashboard/dist" ]; then
      echo "Building dashboard..."
      cd dashboard && npm install && npm run build && cd ..
    fi
    exec uvicorn dashboard_server:app --host 0.0.0.0 --port "${PORT}"
    ;;
  "backtester")
    echo "ERROR: Backtester is LOCAL-ONLY. Do NOT deploy on Railway."
    echo "Use: ./tools/run_backtest_local.sh"
    exit 1
    ;;
  *)
    echo "ERROR: Unknown service '${RAILWAY_SERVICE_NAME}'"
    echo "Valid services: worker, web, auto-learning, dashboard"
    exit 1
    ;;
esac
