#!/usr/bin/env bash
set -euo pipefail
LOG="/root/ethbot/logs/console.out"
OUT="/root/ethbot/logs/feed_heartbeat.txt"
# per ENV überschreibbar: HEARTBEAT_GREP (Default "INFO px=")
PATTERN="${HEARTBEAT_GREP:-INFO px=}"
ts=$(date -u +%F_%T)

# Letzte passende Zeile (tolerant & binär-sicher)
last_line="$(tail -n 500 "$LOG" 2>/dev/null | grep -a "$PATTERN" | tail -n 1 || true)"
if [[ -z "${last_line}" ]]; then
  echo "$ts no_px_line" >> "$OUT"
  exit 1
fi

echo "$ts ok $last_line" >> "$OUT"
exit 0
