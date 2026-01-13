from pathlib import Path
from datetime import datetime, timedelta, timezone
import csv, os, re, requests

ROOT = Path("/root/ethbot")
ENV = ROOT / ".env.bot"
LOGS = ROOT / "logs"
TRADES = LOGS / "trades.csv"
SENDLOG = LOGS / "trade_notify.log"

def load_env_file(p: Path):
    vals = {}
    if p.exists():
        for ln in p.read_text().splitlines():
            if not ln or ln.strip().startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals

envf = load_env_file(ENV)
def get(key, default=None):
    return os.getenv(key, envf.get(key, default))

TOK = get("TELEGRAM_BOT_TOKEN")
CID = get("TELEGRAM_CHAT_ID")
LIVE_ONLY = get("TELEGRAM_LIVE_ONLY", "0") == "1"
PUSH_TRADES = get("TELEGRAM_PUSH_TRADES", "1") == "1"

now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=2)

def row_ok(r):
    if not r or not isinstance(r, dict):
        return None
    ts = (r.get("timestamp") or "").strip()
    act = (r.get("action") or "").strip().upper()
    qty = (r.get("qty") or "").strip()
    price = (r.get("price") or "").strip()
    mode = (r.get("mode") or "").strip().upper() if "mode" in r else "DRY"

    if LIVE_ONLY and mode != "LIVE":
        return None
    if not ts or not act or not qty:
        return None

    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    if dt < cutoff:
        return None

    try:
        q = float(qty)
        p = float(price or 0)
    except Exception:
        return None

    return {"dt": dt, "act": act, "qty": q, "price": p, "mode": mode}

print("✅ row_ok() patch test loaded — ready to integrate.")
