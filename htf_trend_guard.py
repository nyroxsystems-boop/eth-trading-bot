#!/usr/bin/env python3
import sys, json, urllib.request
symbol = sys.argv[1] if len(sys.argv)>1 else "ETHUSDT"
period = 200  # EMA200
# Hole 210 * 1h-Kerzen
url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=210"
with urllib.request.urlopen(url, timeout=10) as r:
    data = json.load(r)
closes = [float(k[4]) for k in data][-210:]
# EMA
k = 2/(period+1); ema=None
for c in closes:
    ema = c if ema is None else (c-ema)*k + ema
last = closes[-1]
print(f"[TREND] last={last:.2f} ema200={ema:.2f}")
# Exitcode 0 = uptrend, 2 = block
sys.exit(0 if last>ema else 2)
