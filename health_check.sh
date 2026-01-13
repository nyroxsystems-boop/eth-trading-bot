#!/usr/bin/env bash
set -Eeuo pipefail
echo "===== 🧠 ETHBot Health $(date -u '+%F %T') UTC ====="

ROOT=/root/ethbot
LOGS="$ROOT/logs"
ENV="$ROOT/.env.bot"

echo "---- .env essentials ----"
grep -E '^(DRY_RUN|FOCUS_MODE|MAX_TRADES|TWITTER_SENTIMENT)=' "$ENV" || echo "(env missing)"

echo
echo "---- Feed Status (Binance) ----"
grep -a "INFO px=" "$LOGS/console.out" | tail -n 3 || echo "(no feed data)"
if [ -f "$LOGS/console.out" ]; then
  DIFF=$(( $(date +%s) - $(date -r "$LOGS/console.out" +%s) ))
  if [ "$DIFF" -gt 600 ]; then
    echo "⚠️ Feed stale (no update since ${DIFF}s)"
  else
    echo "✅ Feed active (updated ${DIFF}s ago)"
  fi
else
  echo "❌ console.out fehlt"
fi

echo
echo "---- Entry-Edge-Guard ----"
/root/ethbot/.venv/bin/python3 /root/ethbot/entry_edge_guard.py || true

echo
echo "---- Console (60 relevant lines) ----"
tail -n 400 "$LOGS/console.out" | strings | egrep -a 'BUY|SELL|EDGE|SAFEGUARD|sentiment|soft-block' | tail -n 60 || true

echo
echo "---- 48h Summary ----"
/root/ethbot/.venv/bin/python3 /root/ethbot/summary_48h.py || echo "(summary error)"

echo
echo "---- Sentiment Cache ----"
cat "$ROOT/cache/sentiment.json" 2>/dev/null || echo "(no cache yet)"

echo
echo "---- Systemd Timers ----"
systemctl status ethbot-tradenotify.timer ethbot-watchdog.timer ethbot-daily.timer --no-pager -l \
  | grep -E "Loaded:|Active:|Trigger:" || echo "(timers missing)"

echo
echo "===== ✅ Health Check complete ====="
