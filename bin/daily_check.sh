#!/usr/bin/env bash
set -euo pipefail
echo "===== ETHBot Daily $(date -u '+%F %T UTC') ====="
systemctl status ethbot --no-pager -l | grep -E "Active:|Loaded:" || true
echo "---- last 20 trade lines ----"
[ -f /root/ethbot/logs/trades.csv ] && tail -n 20 /root/ethbot/logs/trades.csv || echo "(no trades.csv)"
echo "---- 48h summary ----"
/root/ethbot/.venv/bin/python3 /root/ethbot/summary_48h.py || true
echo "---- sentiment ----"
cat /root/ethbot/cache/sentiment.json 2>/dev/null || echo "(no sentiment yet)"
echo "---- feed health ----"
cat /root/ethbot/cache/feed_health.json 2>/dev/null || echo "(no feed health yet)"
