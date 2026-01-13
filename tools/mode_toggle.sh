#!/usr/bin/env bash
# mode_toggle.sh — One-file control for ETHBot run mode (DRY/LIVE)
# CLI:   ./mode_toggle.sh [status|live|dry|toggle|bot]
# ENV:
#   TELEGRAM_BOT_TOKEN           (required for bot)
#   TELEGRAM_ALLOWED_USER_IDS    comma-separated numeric IDs (e.g. "123,456")
#   ETHBOT_ENV_PATH              default: /root/ethbot/.env.bot
#   ETHBOT_SERVICE_NAME          default: ethbot

set -euo pipefail

ENV_PATH="${ETHBOT_ENV_PATH:-/root/ethbot/.env.bot}"
SERVICE="${ETHBOT_SERVICE_NAME:-ethbot}"
LOCKFILE="/tmp/ethbot_mode_toggle.lock"

require_file() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "ERR: file not found: $p" >&2
    exit 2
  fi
}

bool_to_mode() {
  local v="${1,,}"
  case "$v" in
    1|true|yes|on)  echo "dry" ;;
    *)              echo "live" ;;
  esac
}

get_mode() {
  require_file "$ENV_PATH"
  local line val
  if line="$(grep -E '^\s*DRY_RUN=' "$ENV_PATH" || true)"; then
    val="${line#*=}"
    val="$(echo "$val" | tr -d '\"' | xargs)"
    bool_to_mode "$val"
  else
    echo "dry"
  fi
}

set_mode() {
  local new_mode="$1"
  [[ "$new_mode" == "dry" || "$new_mode" == "live" ]] || { echo "ERR: set_mode expects 'dry' or 'live'"; exit 2; }
  require_file "$ENV_PATH"
  exec 9>"$LOCKFILE"
  command -v flock >/dev/null 2>&1 && flock 9
  if grep -qE '^\s*DRY_RUN=' "$ENV_PATH"; then
    if [[ "$new_mode" == "dry" ]]; then sed -i 's/^\s*DRY_RUN=.*/DRY_RUN=true/' "$ENV_PATH"
    else                                  sed -i 's/^\s*DRY_RUN=.*/DRY_RUN=false/' "$ENV_PATH"
    fi
  else
    if [[ "$new_mode" == "dry" ]]; then printf "\nDRY_RUN=true\n"  >> "$ENV_PATH"
    else                                  printf "\nDRY_RUN=false\n" >> "$ENV_PATH"
    fi
  fi
  exec 9>&-
  get_mode
}

restart_service() {
  if systemctl restart "$SERVICE" 2>"/tmp/_svc_err.$$" 1>"/tmp/_svc_out.$$"; then
    local msg; msg="$(cat /tmp/_svc_out.$$ /tmp/_svc_err.$$ 2>/dev/null | sed 's/^[[:space:]]\+//;s/[[:space:]]\+$//')"
    rm -f /tmp/_svc_out.$$ /tmp/_svc_err.$$ || true
    echo "OK|$msg"
  else
    local msg; msg="$(cat /tmp/_svc_out.$$ /tmp/_svc_err.$$ 2>/dev/null | sed 's/^[[:space:]]\+//;s/[[:space:]]\+$//')"
    rm -f /tmp/_svc_out.$$ /tmp/_svc_err.$$ || true
    echo "FAIL|$msg"
  fi
}

status_summary() {
  local mode svc
  mode="$(get_mode)"
  svc="$(systemctl is-active "$SERVICE" 2>/dev/null || echo unknown)"
  echo "MODE: ${mode^^} | service: $svc"
}

send_usage() {
  cat <<'USAGE'
Usage: mode_toggle.sh [status|live|dry|toggle|bot]
USAGE
}

tg_api_base=""
tg_allowed=()

require_curl_jq() {
  command -v curl >/dev/null 2>&1 || { echo "ERR: curl missing"; exit 3; }
  command -v jq   >/dev/null 2>&1 || { echo "ERR: jq missing";   exit 3; }
}

tg_send_message() {
  local chat_id="$1" text="$2" reply_markup_json="${3:-}"
  local args=(-sS -X POST "${tg_api_base}/sendMessage"
    --data-urlencode "chat_id=${chat_id}"
    --data-urlencode "text=${text}"
    --data-urlencode "parse_mode=HTML"
    --data-urlencode "disable_web_page_preview=true")
  [[ -n "$reply_markup_json" ]] && args+=( --data "reply_markup=${reply_markup_json}" )
  curl "${args[@]}" >/dev/null
}

kb_json() {
  cat <<'JSON' | tr -d '\n'
{"inline_keyboard":[
  [{"text":"🟢 Go LIVE","callback_data":"set_live"},{"text":"🧪 Switch to DRY","callback_data":"set_dry"}],
  [{"text":"📊 Status","callback_data":"status"}]
]}
JSON
}

is_allowed() {
  local uid="$1"
  [[ "${#tg_allowed[@]}" -eq 0 ]] && return 0
  local x; for x in "${tg_allowed[@]}"; do [[ "$x" == "$uid" ]] && return 0; done
  return 1
}

handle_command() {
  local chat_id="$1" user_id="$2" text="$3"
  local t="${text,,}"
  if ! is_allowed "$user_id"; then tg_send_message "$chat_id" "⛔ Not allowed."; return; fi
  case "$t" in
    "/start"|"/help")
      tg_send_message "$chat_id" "ETHBot Mode Control
Use buttons or commands: /status, /live, /dry, /toggle" "$(kb_json)";;
    "/status")
      tg_send_message "$chat_id" "📊 <b>$(status_summary | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</b>" "$(kb_json)";;
    "/live")
      set_mode "live"; local res; res="$(restart_service)"; local ok="${res%%|*}"
      tg_send_message "$chat_id" "✅ Set <b>LIVE</b> | restart: $([[ "$ok" == "OK" ]] && echo OK || echo FAIL)" "$(kb_json)";;
    "/dry")
      set_mode "dry"; local res; res="$(restart_service)"; local ok="${res%%|*}"
      tg_send_message "$chat_id" "✅ Set <b>DRY</b> | restart: $([[ "$ok" == "OK" ]] && echo OK || echo FAIL)" "$(kb_json)";;
    "/toggle")
      local cur; cur="$(get_mode)"; local nm="live"; [[ "$cur" == "live" ]] && nm="dry"
      set_mode "$nm"; local res; res="$(restart_service)"; local ok="${res%%|*}"
      tg_send_message "$chat_id" "🔁 Toggle -> <b>${nm^^}</b> | restart: $([[ "$ok" == "OK" ]] && echo OK || echo FAIL)" "$(kb_json)";;
    *)
      tg_send_message "$chat_id" "❓ Unknown. Use /status /live /dry /toggle" "$(kb_json)";;
  esac
}

handle_callback() {
  local chat_id="$1" user_id="$2" data="$3"
  if ! is_allowed "$user_id"; then tg_send_message "$chat_id" "⛔ Not allowed."; return; fi
  case "$data" in
    "set_live")
      set_mode "live"; local res; res="$(restart_service)"; local ok="${res%%|*}"
      tg_send_message "$chat_id" "✅ Set <b>LIVE</b> | restart: $([[ "$ok" == "OK" ]] && echo OK || echo FAIL)" "$(kb_json)";;
    "set_dry")
      set_mode "dry"; local res; res="$(restart_service)"; local ok="${res%%|*}"
      tg_send_message "$chat_id" "✅ Set <b>DRY</b> | restart: $([[ "$ok" == "OK" ]] && echo OK || echo FAIL)" "$(kb_json)";;
    "status")
      tg_send_message "$chat_id" "📊 <b>$(status_summary | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</b>" "$(kb_json)";;
  esac
}

run_bot() {
  require_curl_jq
  local token="${TELEGRAM_BOT_TOKEN:-}"
  [[ -n "$token" ]] || { echo "ERR: TELEGRAM_BOT_TOKEN missing" >&2; return 2; }
  tg_api_base="https://api.telegram.org/bot${token}"
  local ids="${TELEGRAM_ALLOWED_USER_IDS:-}"
  if [[ -n "$ids" ]]; then
    IFS=',' read -r -a tg_allowed <<<"$ids"
    for i in "${!tg_allowed[@]}"; do tg_allowed[$i]="${tg_allowed[$i]//[[:space:]]/}"; done
  fi
  echo "Telegram bot started. Allowed=${ids:-'(any)'}"

  local offset=""
  while true; do
    local resp; resp="$(curl -sS "${tg_api_base}/getUpdates" --get --data-urlencode "timeout=30" ${offset:+--data-urlencode "offset=${offset}"} )" || { sleep 2; continue; }
    local count; count="$(echo "$resp" | jq '.result | length')" || { sleep 1; continue; }
    if [[ "$count" -gt 0 ]]; then
      for i in $(seq 0 $((count-1))); do
        local upd; upd="$(echo "$resp" | jq ".result[$i]")"
        local uid; uid="$(echo "$upd" | jq -r '.update_id')"
        offset=$((uid+1))
        if echo "$upd" | jq -e '.message' >/dev/null; then
          local chat_id user_id text
          chat_id="$(echo "$upd" | jq -r '.message.chat.id')"
          user_id="$(echo "$upd" | jq -r '.message.from.id')"
          text="$(echo "$upd" | jq -r '.message.text // ""')"
          handle_command "$chat_id" "$user_id" "$text"
        fi
        if echo "$upd" | jq -e '.callback_query' >/dev/null; then
          local chat_id user_id data
          chat_id="$(echo "$upd" | jq -r '.callback_query.message.chat.id')"
          user_id="$(echo "$upd" | jq -r '.callback_query.from.id')"
          data="$(echo "$upd" | jq -r '.callback_query.data // ""')"
          handle_callback "$chat_id" "$user_id" "$data"
        fi
      done
    fi
  done
}

main() {
  if [[ $# -lt 1 ]]; then send_usage; exit 0; fi
  case "${1,,}" in
    -h|--help|help) send_usage ;;
    status)         status_summary ;;
    live)           final="$(set_mode live)";   IFS='|' read -r ok msg <<<"$(restart_service)"; echo "Set mode -> ${final^^} | restart=${ok} ${msg:+- $msg}"; [[ "$ok" == "OK" ]] || exit 1 ;;
    dry)            final="$(set_mode dry)";    IFS='|' read -r ok msg <<<"$(restart_service)"; echo "Set mode -> ${final^^} | restart=${ok} ${msg:+- $msg}"; [[ "$ok" == "OK" ]] || exit 1 ;;
    toggle)         cur="$(get_mode)"; new="live"; [[ "$cur" == "live" ]] && new="dry"; final="$(set_mode "$new")"; IFS='|' read -r ok msg <<<"$(restart_service)"; echo "Toggle -> ${final^^} | restart=${ok} ${msg:+- $msg}"; [[ "$ok" == "OK" ]] || exit 1 ;;
    bot)            run_bot ;;
    *)              echo "Unknown command."; send_usage; exit 2 ;;
  esac
}
main "$@"
