#!/usr/bin/env bash
set -euo pipefail
LOG_DIR="/root/ethbot/logs"
PIDFILE="$LOG_DIR/bot.pid"
BOT_CMD="/root/ethbot/eth_master_bot.py"

mkdir -p "$LOG_DIR"

# 1) Falls PIDFILE-PID tot ist, versuchen laufende Python-Instanz zu finden
PID_FROM_FILE=$(cat "$PIDFILE" 2>/dev/null || echo 0)
if ! ps -p "$PID_FROM_FILE" >/dev/null 2>&1; then
  RUNNING_PY=$(pgrep -f "python.*${BOT_CMD}" || true)
  if [ -n "${RUNNING_PY:-}" ]; then
    echo "$RUNNING_PY" > "$PIDFILE"
    echo "$(date '+%F %T') ♻️ korrigierte PID -> $RUNNING_PY" >> "$LOG_DIR/watchdog.log"
    exit 0
  fi
fi

# 2) Wenn weiterhin nix läuft -> neu starten
if ! ps -p "$(cat "$PIDFILE" 2>/dev/null || echo 0)" >/dev/null 2>&1; then
  echo "$(date '+%F %T') 🔄 Bot down – restarting..." >> "$LOG_DIR/watchdog.log"
  cd /root/ethbot
  nohup ./run.sh > "$LOG_DIR/console.out" 2>&1 &
  sleep 2
  # echte Python-PID ermitteln & speichern
  PY_PID=$(pgrep -f "python.*${BOT_CMD}" | head -n1)
  echo "${PY_PID:-$!}" > "$PIDFILE"
  echo "$(date '+%F %T') ✅ Bot up (PID $(cat "$PIDFILE"))" >> "$LOG_DIR/watchdog.log"
else
  echo "$(date '+%F %T') ✅ Bot läuft (PID $(cat "$PIDFILE"))" >> "$LOG_DIR/watchdog.log"
fi
