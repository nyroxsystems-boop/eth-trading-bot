#!/bin/bash
# Entrypoint script for Railway — Ethbot v3
# Simplified: only 2 services (worker + web)

set -e

echo "═══ Ethbot v3 ═══"
echo "Service: ${RAILWAY_SERVICE_NAME:-unknown}"
echo "PORT: ${PORT:-not set}"

case "${RAILWAY_SERVICE_NAME}" in
  "worker")
    echo "Starting Ethbot v3 Trading Engine..."
    exec python3 main_v3.py
    ;;
  "web")
    echo "Starting Ethbot v3 API + Dashboard on port ${PORT}..."
    exec python3 api_v3.py --port "${PORT}"
    ;;
  *)
    # Default: run both bot + API in same process
    echo "Starting Ethbot v3 (unified mode)..."
    # Start bot in background
    python3 main_v3.py &
    BOT_PID=$!
    # Start API in foreground
    exec python3 api_v3.py --port "${PORT:-8000}"
    ;;
esac
