#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, urllib.request, urllib.parse, time, pathlib

ENV = pathlib.Path("/root/ethbot/.env.bot")
def load_env():
    data={}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k,v=line.split("=",1)
                data[k.strip()]=v.strip()
    return data

def send(msg: str) -> bool:
    env = load_env()
    tok = env.get("TELEGRAM_BOT_TOKEN","").strip()
    chat= env.get("TELEGRAM_CHAT_ID","").strip()
    if not tok or not chat: 
        return False
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    payload = {"chat_id": chat, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    data = urllib.parse.urlencode(payload).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as r:
            r.read()
        return True
    except Exception:
        return False

if __name__=="__main__":
    ok = send("✅ Telegram test from ETHBot notifier")
    print("sent" if ok else "skipped")

# === Minimal-Noise Filter ===
import os, re

TELEGRAM_PUSH_TRADES = os.getenv("TELEGRAM_PUSH_TRADES", "0")  # 0 = keine Trade-Logs (nur Fills)
TELEGRAM_LIVE_ONLY   = os.getenv("TELEGRAM_LIVE_ONLY", "1")    # 1 = nur LIVE, keine DRY

_ALLOW_PATTERNS = [
    r"\[LIVE\]\s+(BUY|SELL)",    # echte Live-Fills
    r"\[SAFEGUARD\]",            # Schutzmechanismen
    r"\b(ERROR|EXCEPTION|CRITICAL)\b",  # Fehler/Hart
    r"\bsummary\b",              # Daily/48h Summary
]

def _tg_should_send(text: str) -> bool:
    t = text or ""
    # Live-only blockt DRY
    if TELEGRAM_LIVE_ONLY == "1" and ("[DRY]" in t or "DRY" in t):
        return False
    # Wenn wir Trade-Logs global aus haben wollen:
    if TELEGRAM_PUSH_TRADES == "0":
        # Erlaube nur Whitelist:
        for pat in _ALLOW_PATTERNS:
            if re.search(pat, t, re.IGNORECASE):
                return True
        return False
    return True

# Hook in bestehende Sendefunktion
try:
    _orig_tg_send = tg_send
    def tg_send(text, *args, **kwargs):
        if _tg_should_send(str(text)):
            return _orig_tg_send(text, *args, **kwargs)
        # stumm
        return None
except NameError:
    # Falls die Funktion anders heißt, optional weitere Hooks ergänzen
    pass


# --- compat alias: expose tg_send() mapped to send ---
try:
    tg_send
except NameError:
    tg_send = send
