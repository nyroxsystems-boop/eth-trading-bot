#!/usr/bin/env bash
# === Watchdog Quiet Patch ===
# Filtert Feed/ADX-bezogene Fails heraus

LOG=/root/ethbot/logs/console.out
if grep -qE 'FAIL\[1[0-9]\]|ADX=0\.0 soft-block' /root/ethbot/logs/feed.log 2>/dev/null; then
  echo "[guard] Feed/ADX FAIL ignored"
  exit 0
fi

# echte Fehler (Traceback, CRITICAL, Exception)
grep -qE 'Traceback|CRITICAL|Exception' "$LOG"
exit $?
