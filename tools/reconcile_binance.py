#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, time, hmac, hashlib, requests, urllib.parse, json
from pathlib import Path

BASE   = os.getenv("BINANCE_BASE", "https://api.binance.com")
APIKEY = os.getenv("BINANCE_API_KEY")
SECRET = os.getenv("BINANCE_API_SECRET")

CACHE = Path("/root/ethbot/cache"); CACHE.mkdir(parents=True, exist_ok=True)
LOGD  = Path("/root/ethbot/logs");  LOGD.mkdir(parents=True, exist_ok=True)

F_OPEN = CACHE/"binance_open_orders.json"
F_BAL  = CACHE/"binance_balances.json"

def log(msg: str):
    with (LOGD/"reconcile.log").open("a", encoding="utf-8") as f: f.write(msg.rstrip()+"\n")

def _signed_get(path, params=None):
    if not APIKEY or not SECRET:
        raise RuntimeError("no_api_keys")
    if params is None: params = {}
    params["timestamp"] = int(time.time()*1000)
    params["recvWindow"] = 5000
    q = urllib.parse.urlencode(params, doseq=True)
    sig = hmac.new(SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
    headers = {"X-MBX-APIKEY": APIKEY}
    r = requests.get(f"{BASE}{path}?{q}&signature={sig}", headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()

def reconcile(symbol="ETHUSDT"):
    # offene Orders
    try:
        oo = _signed_get("/api/v3/openOrders", {"symbol": symbol})
        F_OPEN.write_text(json.dumps({"ts": int(time.time()), "symbol": symbol, "openOrders": oo}, ensure_ascii=False, indent=2))
        log(f"openOrders {symbol}: {len(oo)}")
    except Exception as e:
        log(f"openOrders fail: {e}")

    # balances
    try:
        acc = _signed_get("/api/v3/account", {})
        bals = [{"asset": b["asset"], "free": b["free"], "locked": b["locked"]}
                for b in acc.get("balances", []) if float(b.get("free","0"))>0 or float(b.get("locked","0"))>0]
        F_BAL.write_text(json.dumps({"ts": int(time.time()), "balances": bals}, ensure_ascii=False, indent=2))
        log(f"balances ok: {len(bals)} nonzero")
    except Exception as e:
        log(f"balances fail: {e}")

def main():
    if not APIKEY or not SECRET:
        log("skip: no api keys in env")
        return 0
    reconcile(os.getenv("SYMBOL","ETHUSDT"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
