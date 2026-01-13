#!/usr/bin/env bash
set -euo pipefail
LOG="/root/ethbot/logs/console.out"
if [ ! -f "$LOG" ]; then echo "[FEED] no log"; exit 0; fi
NOW=$(date +%s)
LAST=$(grep -a "INFO px=" "$LOG" | tail -n1 | awk '{print $1" "$2}')
if [ -z "$LAST" ]; then echo "[FEED] no px lines yet"; exit 0; fi
LAST_TS=$(date -d "$LAST" +%s 2>/dev/null || echo $NOW)
AGE=$(( NOW - LAST_TS ))
if [ $AGE -gt 420 ]; then
  echo "[FEED] stale ($AGE s) -> restart ethbot"
  systemctl restart ethbot || true
  echo "[FEED] restarted"
else
  echo "[FEED] ok ($AGE s)"
fi
