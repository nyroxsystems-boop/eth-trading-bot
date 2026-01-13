#!/usr/bin/env bash
echo "===== 🧠 ETHBot Full System Diagnostic $(date -u "+%F %T UTC") ====="
ROOT=/root/ethbot; LOGS="$ROOT/logs"; ENV="$ROOT/.env.bot"

echo; echo "---- .env essentials ----"
[ -f "$ENV" ] && grep -E "^(DRY_RUN|FOCUS_MODE|MAX_TRADES|TWITTER_SENTIMENT|TELEGRAM_)" "$ENV" || echo "✖ .env.bot fehlt"

echo; echo "---- Feed Status (px heartbeat) ----"
if [ -f "$LOGS/console.out" ]; then
  CNT=$(grep -a "px=" "$LOGS/console.out" | tail -n 200 | wc -l)
  echo "px-lines (last ~200): $CNT"; [ "$CNT" -ge 1 ] && echo "✅ Feed active" || echo "⚠️ no px seen"
else echo "✖ console.out fehlt"; fi

echo; echo "---- Feed Validator ----"
/root/ethbot/.venv/bin/python3 /root/ethbot/feed_validator.py ; echo "exit=$?"

echo; echo "---- ADX Probe ----"
/root/ethbot/.venv/bin/python3 /root/ethbot/adx_probe.py || echo "(adx probe error)"

echo; echo "---- Systemd (running) ----"
systemctl list-units --type=service --state=running | grep -E "ethbot|jarvis" || echo "(no active ethbot units)"

echo; echo "---- Systemd Timers ----"
systemctl list-timers --all | grep -E "ethbot" || echo "(no ethbot timers)"

echo; echo "---- Recent feed.log ----"
tail -n 10 "$LOGS/feed.log" 2>/dev/null || echo "(no feed.log)"

echo; echo "---- Recent px lines ----"
grep -a "px=" "$LOGS/console.out" | tail -n 5 2>/dev/null || echo "(no px lines)"

echo "===== ✅ Diagnostic completed ====="
