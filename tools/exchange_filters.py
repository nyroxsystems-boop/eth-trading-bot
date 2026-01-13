#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, time, math, hmac, hashlib, urllib.parse, requests
from pathlib import Path

CACHE = Path("/root/ethbot/cache"); CACHE.mkdir(parents=True, exist_ok=True)
LOGD  = Path("/root/ethbot/logs");  LOGD.mkdir(parents=True, exist_ok=True)
F_CACHE = CACHE / "symbol_filters.json"

BINANCE_BASE = os.getenv("BINANCE_BASE", "https://api.binance.com")

def _log(msg: str):
    with (LOGD/"exchange_filters.log").open("a", encoding="utf-8") as f: f.write(msg.rstrip()+"\n")

def _get(url, params=None):
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def _load_remote_filters(symbol: str):
    info = _get(f"{BINANCE_BASE}/api/v3/exchangeInfo", {"symbol": symbol})
    sym = info["symbols"][0]
    out = {"symbol": sym["symbol"], "filters": {}}
    for f in sym["filters"]:
        out["filters"][f["filterType"]] = f
    return out

def load_filters(symbol: str, ttl_sec: int = 6*3600):
    symbol = symbol.upper()
    now = int(time.time())
    data = {}
    if F_CACHE.exists():
        try:
            data = json.loads(F_CACHE.read_text())
        except Exception:
            data = {}
    if symbol in data and now - data[symbol]["ts"] < ttl_sec:
        return data[symbol]["payload"]
    try:
        payload = _load_remote_filters(symbol)
        data[symbol] = {"ts": now, "payload": payload}
        F_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return payload
    except Exception as e:
        _log(f"err load_filters {symbol}: {e}")
        # fallback: wenn existiert, nimm alten Eintrag
        if symbol in data:
            return data[symbol]["payload"]
        raise

def _step_round(x: float, step: float) -> float:
    if step <= 0: return x
    return math.floor(x/step)*step

def round_price(symbol: str, price: float) -> float:
    f = load_filters(symbol)["filters"].get("PRICE_FILTER", {})
    tick = float(f.get("tickSize", "0"))
    return round(_step_round(float(price), tick), 8) if tick else float(price)

def round_qty(symbol: str, qty: float) -> float:
    f = load_filters(symbol)["filters"].get("LOT_SIZE", {})
    step = float(f.get("stepSize", "0"))
    min_q = float(f.get("minQty", "0"))
    q = _step_round(float(qty), step) if step else float(qty)
    if q < min_q: q = 0.0
    return round(q, 8)

def min_notional_ok(symbol: str, qty: float, price: float) -> bool:
    f = load_filters(symbol)["filters"].get("MIN_NOTIONAL", {})
    mn = float(f.get("minNotional", "0"))
    if mn <= 0: return True
    return (float(qty)*float(price)) >= mn

def sanitize_order(symbol: str, qty: float, price: float):
    """Gibt (qty_sanitized, price_sanitized, ok_bool, reason) zurück."""
    p = round_price(symbol, price)
    q = round_qty(symbol, qty)
    if q == 0.0: return (0.0, p, False, "qty_below_min")
    if not min_notional_ok(symbol, q, p):
        return (q, p, False, "min_notional")
    return (q, p, True, "ok")
