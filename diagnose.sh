#!/usr/bin/env bash
set -Eeuo pipefail

RED() { printf "\e[31m%s\e[0m\n" "$*"; }
GRN() { printf "\e[32m%s\e[0m\n" "$*"; }
YEL() { printf "\e[33m%s\e[0m\n" "$*"; }
SEC() { echo; printf "===== %s =====\n" "$*"; }

ok()  { GRN "✔ $*"; }
warn(){ YEL "⚠ $*"; }
fail(){ RED "✖ $*"; }

TS="$(date -u '+%F %T') UTC"
echo "===== 🧪 ETHBot Full Diagnostics $TS ====="

ROOT=/root/ethbot
LOGD="$ROOT/logs"
ENVF="$ROOT/.env.bot"
CONSOLE="$LOGD/console.out"
TRCSV="$LOGD/trades.csv"

SEC ".env.bot & Essentials"
if [[ -f "$ENVF" ]]; then
  ok ".env.bot gefunden"
  DRY=$(grep -E '^DRY_RUN=' "$ENVF" | cut -d= -f2- || true)
  TBT=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENVF" | cut -d= -f2- || true)
  TID=$(grep -E '^TELEGRAM_CHAT_ID=' "$ENVF" | cut -d= -f2- || true)
  BAK=$(grep -E '^BINANCE_API_KEY=' "$ENVF" | cut -d= -f2- || true)
  TPT=$(grep -E '^TELEGRAM_PUSH_TRADES=' "$ENVF" | cut -d= -f2- || echo 0)
  TLO=$(grep -E '^TELEGRAM_LIVE_ONLY='   "$ENVF" | cut -d= -f2- || echo 1)
  TFA=$(grep -E '^TELEGRAM_FEED_ALERTS=' "$ENVF" | cut -d= -f2- || echo 0)
  TWA=$(grep -E '^TELEGRAM_WATCHDOG_ALERTS=' "$ENVF" | cut -d= -f2- || echo 0)
  WMR=$(grep -E '^WATCHDOG_MIN_RESTART_SEC=' "$ENVF" | cut -d= -f2- || echo 600)

  printf "    DRY_RUN=%s | TELEGRAM_PUSH_TRADES=%s | LIVE_ONLY=%s | FEED_ALERTS=%s | WATCHDOG_ALERTS=%s | WD_MIN=%s\n" \
     "${DRY:-<leer>}" "$TPT" "$TLO" "$TFA" "$TWA" "$WMR"
  [[ -n "${TBT:-}" && -n "${TID:-}" ]] || fail "Telegram Token/ChatID fehlen"; [[ -n "${BAK:-}" ]] || warn "BINANCE_API_KEY nicht gesetzt?"
else
  fail ".env.bot fehlt"; exit 1
fi

SEC "Systemd Units (Service + Timer)"
UNITS=(ethbot.service ethbot-focus.timer ethbot-learn.timer ethbot-jarvis.timer ethbot-sentiment.timer ethbot-tradenotify.timer ethbot-watchdog.timer ethbot-daily.timer)
ANY_FAIL=0
for u in "${UNITS[@]}"; do
  if systemctl status "$u" >/dev/null 2>&1; then
    ACT=$(systemctl is-active "$u" || true)
    ENA=$(systemctl is-enabled "$u" 2>/dev/null || echo "disabled")
    printf "    %-26s active=%-8s enabled=%s\n" "$u" "$ACT" "$ENA"
    [[ "$ACT" == "active" || "$ACT" == "waiting" ]] || ANY_FAIL=1
  else
    warn "Unit fehlt: $u"
    ANY_FAIL=1
  fi
done
[[ $ANY_FAIL -eq 0 ]] && ok "Alle erkannten Units aktiv/ok" || warn "Einige Units fehlen oder sind nicht aktiv"

SEC "Telegram Filter Hook"
TN="$ROOT/telegram_notify.py"
if [[ -f "$TN" ]]; then
  if grep -q "def _tg_should_send(" "$TN" && grep -q "_orig_tg_send = tg_send" "$TN"; then
    ok "Filter-Hook aktiv (_tg_should_send wrap)"
  else
    fail "Filter-Hook NICHT aktiv – Minutenspam möglich"
  fi
else
  warn "telegram_notify.py nicht gefunden"
fi

SEC "Watchdog Quiet & Debounce"
WD="$ROOT/watchdog_console.py"
if [[ -f "$WD" ]]; then
  grep -q "MIN_GAP" "$WD" && ok "Debounce vorhanden" || warn "Kein Debounce in watchdog_console.py"
  [[ "${TWA:-0}" == "0" ]] && ok "Watchdog quiet (TELEGRAM_WATCHDOG_ALERTS=0)" || warn "Watchdog sendet Alerts (TELEGRAM_WATCHDOG_ALERTS=1)"
else
  warn "watchdog_console.py nicht gefunden (nutzt evtl. anderes Script)"
fi

SEC "Feed Guard Quiet"
FG="$ROOT/tools/feed_guard.sh"
if [[ -f "$FG" ]]; then
  if grep -q 'TELEGRAM_FEED_ALERTS' "$FG"; then ok "Feed-Guard beachtet TELEGRAM_FEED_ALERTS"
  else warn "Feed-Guard patch fehlt (Quiet-Check nicht gefunden)"; fi
else
  warn "tools/feed_guard.sh nicht gefunden"
fi

SEC "Console Stream (letzte 40 Zeilen, zusammengefasst)"
if [[ -f "$CONSOLE" ]]; then
  tail -n 400 "$CONSOLE" | strings | grep -E "INFO px=|EDGE|SAFEGUARD|\[(DRY|LIVE)\] (BUY|SELL)" | tail -n 40 || true
  # ADX-Stuck-Heuristik
  STUCK=$(tail -n 120 "$CONSOLE" | grep -Eo "adx=([0-9]+\.[0-9]+|[0-9]+)" | awk -F= '{print $2}' | awk '{c[$1]++} END{for(k in c){if(c[k]>80 && k==20) print "stuck"}}')
  [[ "$STUCK" == "stuck" ]] && warn "ADX scheint bei 20.0 zu 'kleben' (Quelle prüfen)" || ok "ADX wirkt variabel/ok (Heuristik)"
else
  warn "console.out nicht gefunden"
fi

SEC "Entry Edge Guard (Probe)"
if [[ -f "$ROOT/entry_edge_guard.py" || -f "$ROOT/guards/entry_edge_guard.py" ]]; then
  /root/ethbot/.venv/bin/python3 - <<'PY' || exit 0
import sys, importlib.util, pathlib, traceback
cands=[(pathlib.Path("/root/ethbot/entry_edge_guard.py"),"entry_edge_guard"),
       (pathlib.Path("/root/ethbot/guards/entry_edge_guard.py"),"guards.entry_edge_guard")]
for p,n in cands:
    if p.exists():
        spec=importlib.util.spec_from_file_location(n,str(p)); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        probe=getattr(m,"probe",None) or getattr(m,"main",None)
        if callable(probe):
            try:
                print(probe())
            except Exception:
                print("[edge_probe_error]"); traceback.print_exc()
        else:
            print("[edge_probe_error] probe() not found")
        break
PY
else
  warn "entry_edge_guard.py nicht gefunden"
fi

SEC "Trades CSV"
if [[ -f "$TRCSV" ]]; then
  head -n 1 "$TRCSV" | grep -q '^timestamp,action,qty,price$' && H=1 || H=0
  TAIL=$(tail -n 3 "$TRCSV" || true)
  printf "%s\n%s\n" "HeaderOK=$H" "$TAIL"
  [[ -w "$TRCSV" ]] && ok "trades.csv beschreibbar" || fail "trades.csv nicht beschreibbar"
else
  warn "trades.csv nicht gefunden – wurde noch nichts geloggt?"
  [[ -w "$LOGD" ]] && ok "logs/ Ordner beschreibbar" || fail "logs/ Ordner NICHT beschreibbar"
fi

SEC "Twitter Sentiment (Log & Cache)"
TSLOG="$LOGD/twitter_sentiment.log"
CACHE="$ROOT/cache/sentiment.json"
[[ -f "$TSLOG" ]] && tail -n 20 "$TSLOG" | sed 's/\r//g' || warn "twitter_sentiment.log fehlt"
if [[ -f "$CACHE" ]]; then
  echo -n "cache: "; tail -n 1 "$CACHE"
  # Alter des Caches
  NOW=$(date +%s); MT=$(stat -c %Y "$CACHE" 2>/dev/null || stat -f %m "$CACHE")
  AGE=$((NOW-MT)); echo "cache_age_sec=$AGE"
  [[ $AGE -lt 900 ]] && ok "Sentiment-Cache frisch (<15min)" || warn "Sentiment-Cache alt (>=15min)"
else
  warn "cache/sentiment.json fehlt"
fi

SEC "Daily/48h Summary"
if [[ -f "$ROOT/summary_48h.py" ]]; then
  /root/ethbot/.venv/bin/python3 "$ROOT/summary_48h.py" || warn "summary_48h.py Fehler"
else
  warn "summary_48h.py nicht gefunden"
fi

SEC "Final Service Snapshot"
systemctl status ethbot.service --no-pager -l | sed -n '1,30p' || true

echo
echo "===== ✅ Diagnose fertig ====="
