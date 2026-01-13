#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import math, time

# Statische (konservative) Defaults für ETHUSDT – passen auf Spot i.d.R.
# Wenn du später die echten ExchangeInfos ziehst, kannst du das dynamisieren.
DEFAULT_RULES = {
    "tickSize": 0.01,       # Preisauflösung
    "stepSize": 0.0001,     # Mengenauflösung
    "minQty":   0.0005,     # kleinste Menge
    "minNotional": 5.0,     # Mindestwert in USDT
    "maxQty":   5000.0
}

def _quantize(x: float, step: float) -> float:
    if step <= 0: return x
    return math.floor(x / step + 1e-12) * step

def quantize_price_qty(price: float, qty: float, rules: dict = None):
    r = dict(DEFAULT_RULES)
    if rules: r.update(rules)
    q_price = _quantize(max(price, 0.0), r["tickSize"])
    q_qty   = _quantize(max(qty,   0.0), r["stepSize"])
    # clamp
    if q_qty < r["minQty"]: q_qty = 0.0
    if q_qty > r["maxQty"]: q_qty = r["maxQty"]
    return q_price, q_qty

def preflight_order(symbol: str, price: float, qty: float, rules: dict = None):
    """Gibt (ok, payload) zurück. Bei ok=True enthält payload quantisierten price/qty."""
    q_price, q_qty = quantize_price_qty(price, qty, rules)
    notional = q_price * q_qty
    r = dict(DEFAULT_RULES)
    if rules: r.update(rules)
    if q_qty <= 0:
        return False, {"reason": "qty_below_min", "price": q_price, "qty": q_qty}
    if notional < r["minNotional"]:
        return False, {"reason": "min_notional", "price": q_price, "qty": q_qty, "notional": notional}
    return True, {"price": q_price, "qty": q_qty, "notional": notional, "ts": int(time.time())}
