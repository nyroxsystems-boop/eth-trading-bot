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
  "dashboard")
    echo "Starting Dashboard Server on port ${PORT}..."
    # First build the dashboard if not already built
    if [ ! -d "dashboard/dist" ]; then
      echo "Building dashboard..."
      cd dashboard && npm install && npm run build && cd ..
    fi
    exec uvicorn dashboard_server:app --host 0.0.0.0 --port "${PORT}"
    ;;
  *)
    echo "ERROR: Unknown service '${RAILWAY_SERVICE_NAME}'"
    echo "Valid services: worker, web, dashboard"
    exit 1
    ;;
esac
