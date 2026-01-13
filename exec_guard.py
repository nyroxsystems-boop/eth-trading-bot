# Leichtgewichtige Guards für Live-Phase (nutzt ENV)
import os, time, hashlib, random
SLIP_CAP_BPS=int(os.getenv("SLIPPAGE_CAP_BPS","25"))   # 2.5%
RETRY_MAX=int(os.getenv("ORDER_RETRY_MAX","3"))
def order_key(symbol, side, qty, price):
    seed=f"{symbol}|{side}|{qty}|{price}|{int(time.time())}|{random.randint(0,999999)}"
    return hashlib.sha1(seed.encode()).hexdigest()[:24]
def slippage_ok(expected, filled):
    if not expected or not filled: return True
    bps=abs(filled-expected)/expected*10000.0
    return bps <= SLIP_CAP_BPS
def retry_budget():
    return RETRY_MAX
