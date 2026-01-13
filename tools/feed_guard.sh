#!/usr/bin/env bash
set -euo pipefail

BASE=/root/ethbot
[ -f "$BASE/.env.bot" ] && . "$BASE/.env.bot"

THRESHOLD_SEC="${FEED_GUARD_THRESHOLD_SEC:-300}"     # >300s = stale
COOLDOWN="${FEED_GUARD_COOLDOWN:-3600}"              # Reminder höchstens 1×/h
ALERTS="${TELEGRAM_FEED_ALERTS:-0}"                  # 0=stumm, 1=an

STATE="$BASE/cache/feed_guard_state.json"
FLAG="$BASE/cache/feed_guard_flag"                   # 0=ok, 1=stale
LOG="$BASE/logs/console.out"

tg_send_native() {
  # nutzt telegram_notify.py wenn vorhanden, sonst direct API
  if python3 - <<'PY' 2>/dev/null; then exit 0; else :; fi
import os, sys
try:
  import telegram_notify as tn
  tn.tg_send(sys.stdin.read())
  print("ok")
except Exception:
  pass
PY
  then
    :
  else
    [ -z "${TELEGRAM_BOT_TOKEN:-}" ] && exit 0
    [ -z "${TELEGRAM_CHAT_ID:-}" ] && exit 0
    curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d "chat_id=${TELEGRAM_CHAT_ID}" \
      --data-urlencode "text=$(cat -)"
  fi
}

json_get() { python3 - "$1" "$2" <<'PY'
import json,sys,os
p=sys.argv[1]; k=sys.argv[2]
try:
  print(json.load(open(p)).get(k,""))
except Exception:
  print("")
PY
}

json_set() { python3 - "$1" "$2" "$3" <<'PY'
import json,sys,os,time
p,k,v=sys.argv[1:4]
d={}
try:
  if os.path.exists(p):
    d=json.load(open(p))
except Exception:
  d={}
d[k]=v
os.makedirs(os.path.dirname(p), exist_ok=True)
json.dump(d, open(p,"w"))
PY
}

# --- Alter des Feeds ermitteln
now=$(date +%s)
if [ ! -f "$LOG" ]; then
  diff=$((THRESHOLD_SEC+1))  # treat as stale
else
  mtime=$(stat -c %Y "$LOG" 2>/dev/null || stat -f %m "$LOG")
  diff=$(( now - mtime ))
fi

status="ok"
flag=0
if [ "$diff" -gt "$THRESHOLD_SEC" ]; then
  status="stale"
  flag=1
fi

echo -n "$flag" > "$FLAG"

# --- Nur bei Statuswechsel/Reminder senden und NIE bei ok
[ "$ALERTS" = "1" ] || exit 0
[ "$status" = "ok" ] && exit 0

last_flag="$(json_get "$STATE" last_flag)"
last_sent="$(json_get "$STATE" last_sent)"
[ -z "$last_flag" ] && last_flag=""

changed=0; [ "$last_flag" != "$flag" ] && changed=1
elapsed=$(( now - ${last_sent:-0} ))
cool=0; [ "$elapsed" -ge "$COOLDOWN" ] && cool=1

if [ "$changed" -eq 1 ] || [ "$cool" -eq 1 ]; then
  msg="⚠️ ETHBot Feed stale: diff=${diff}s (>${THRESHOLD_SEC}s), flag=${flag}. (status changed=${changed}, +${elapsed}s)"
  echo "$msg" | tg_send_native
  python3 - <<PY
import time, json, os, sys
p=os.environ.get("STATE")
os.makedirs(os.path.dirname(p), exist_ok=True)
json.dump({"last_flag": int(os.environ.get("flag")),
           "last_sent": int(time.time())}, open(p,"w"))
PY
fi
