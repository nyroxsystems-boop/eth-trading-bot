#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, time, math, datetime as dt, urllib.request, urllib.error, pathlib, sys

ROOT = pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))
LOG = ROOT / "logs" / "console.out"
SYMBOL   = "ETHUSDT"   # ggf. aus .env lesen, hier fix für Speed
INTERVAL = "1m"        # 1-Minute-Kerzen

def fetch_klines(symbol="ETHUSDT", interval="1m", limit=60):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def rsi(closes, period=14):
    if len(closes) < period+1: return None
    gains, losses = 0.0, 0.0
    # Initial
    for i in range(1, period+1):
        ch = closes[i]-closes[i-1]
        gains += max(ch, 0)
        losses+= -min(ch, 0)
    avg_gain = gains/period
    avg_loss = losses/period
    # Wilder
    for i in range(period+1, len(closes)):
        ch = closes[i]-closes[i-1]
        gain = max(ch, 0); loss = -min(ch, 0)
        avg_gain = (avg_gain*(period-1) + gain)/period
        avg_loss = (avg_loss*(period-1) + loss)/period
    if avg_loss == 0: return 100.0
    rs = avg_gain/avg_loss
    return 100.0 - (100.0/(1.0+rs))

def main():
    try:
        ks = fetch_klines(SYMBOL, INTERVAL, 60)
        closes = [float(k[4]) for k in ks]          # close
        close  = closes[-1]
        # RSI live berechnen, ADX simpel fallback (20.0)
        rsi14 = rsi(closes, 14)
        adx14 = 20.0
        # Timestamp = Close-Zeit der letzten Kerze (ms -> UTC)
        t_ms  = int(ks[-1][6]) if ks[-1][6] else int(time.time()*1000)
        t_utc = dt.datetime.utcfromtimestamp(t_ms/1000.0).strftime("%Y-%m-%d %H:%M:%S")
        line  = f"{t_utc} INFO px={close:.2f} adx={adx14:.1f} rsi={rsi14:.1f}\n"
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
        print(line.strip())
        return 0
    except urllib.error.HTTPError as e:
        print(f"HTTPError {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERR feeder: {e}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
