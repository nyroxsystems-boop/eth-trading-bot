#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/ethbot"
LOG="$ROOT/logs/console.out"
TRADES="$ROOT/logs/trades.csv"
ENVF="$ROOT/.env.bot"

echo "===== 🧠 ETHBot System Summary $(date -u '+%F %T UTC') ====="

# 0) Essentials / Mode
echo "---- .env.bot ----"
if [ -f "$ENVF" ]; then
  grep -E '^(DRY_RUN|FOCUS_MODE|MAX_TRADES|TWITTER_SENTIMENT|KILL_SWITCH)=' "$ENVF" || true
else
  echo "(.env.bot fehlt)"
fi

# 1) Services/Timer
echo -e "\n---- services & timers ----"
systemctl status ethbot ethbot-focus.timer ethbot-learn.timer ethbot-jarvis.timer ethbot-sentiment.timer --no-pager -l \
  | grep -E "Loaded:|Active:|Trigger:" || true

# 2) Feed-Health (aus Log geparst) + Edge-Check (Python)
echo -e "\n---- feed health ----"
if [ -f "$LOG" ]; then
  # letzte 300 Zeilen nach px/adx/rsi scannen
  tail -n 300 "$LOG" | strings | grep -a "INFO px=" | tail -n 10 || echo "(keine px-Zeilen gefunden)"
else
  echo "(console.out fehlt)"
fi

echo -e "\n---- edge guard (now) ----"
/root/ethbot/.venv/bin/python3 - <<'PY' || true
import sys
sys.path.insert(0,"/root/ethbot")
try:
  from entry_edge_guard import load_series, vwap_like, simple_rsi
except Exception as e:
  print(f"[EDGE] import_error: {e}")
  sys.exit(0)

adx, rsi, px = load_series(250)
print(f"LEN px={len(px)} adx={len(adx)} rsi={len(rsi)}")
if px:
  last = px[-1]
  hi   = max(px[-20:]) if len(px)>=20 else None
  sma  = sum(px[-20:])/20.0 if len(px)>=20 else None
  vw   = vwap_like(px[-60:]) if len(px)>=60 else None
  a14  = adx[-1] if adx else None
  r14  = rsi[-1] if rsi else (simple_rsi(px,14) if len(px)>=14 else None)
  print(f"last={last} high20={hi} sma20={sma} vwap60={vw} adx14={a14} rsi14={r14}")
PY

echo -e "\n---- edge decision ----"
/root/ethbot/.venv/bin/python3 /root/ethbot/entry_edge_guard.py ; echo "exit=$?"

# 3) Console: relevante Events
echo -e "\n---- console (edge/safeguard/trades/sentiment) ----"
if [ -f "$LOG" ]; then
  tail -n 400 "$LOG" | strings | egrep -a 'regime soft-block|\[(DRY|LIVE)\] (BUY|SELL)|\[EDGE\]|SAFEGUARD|sentiment' | tail -n 60 || true
else
  echo "(console.out fehlt)"
fi

# 4) Trades (CSV)
echo -e "\n---- last trades (csv) ----"
if [ -f "$TRADES" ]; then
  head -n 1 "$TRADES"
  tail -n 15 "$TRADES"
else
  echo "(Noch keine Trades geloggt)"
fi

# 5) 48h Summary (falls vorhanden)
echo -e "\n---- 48h summary ----"
/root/ethbot/.venv/bin/python3 /root/ethbot/summary_48h.py || echo "(summary_48h.py nicht vorhanden oder kein Output)"

# 6) Sentiment (Cache)
echo -e "\n---- sentiment cache ----"
cat /root/ethbot/cache/sentiment.json 2>/dev/null || echo "(kein Score gespeichert)"
