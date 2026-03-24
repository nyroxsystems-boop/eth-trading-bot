#!/usr/bin/env python3
import csv, os, sys
from datetime import datetime, timezone

import pathlib
_ROOT=pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))
CSV=str(_ROOT/"logs/trades.csv")
FMT="%Y-%m-%d %H:%M:%S"
TZI=timezone.utc

TARGET_PCT = float(os.getenv("DAILY_TARGET_PCT", "0.02"))  # 2% default
EQUITY     = float(os.getenv("EQUITY_USDT",  os.getenv("PAPER_BASE_USDT","100000")))

def parse_ts(s): return datetime.strptime(s, FMT).replace(tzinfo=TZI)

def pnl_today(rows):
    # FIFO-PNL nur für heute
    from collections import deque
    start = datetime.now(TZI).replace(hour=0, minute=0, second=0, microsecond=0)
    fifo = deque(); realized = 0.0
    for r in rows:
        try:
            ts = parse_ts(r["timestamp"])
            if ts < start:  # nur heute
                continue
            act = r["action"].upper(); qty = float(r["qty"]); px = float(r["price"])
            if px <= 0:  # Skip invalid prices
                continue
            if act == "BUY":
                fifo.append([qty, px])
            elif act == "SELL" and px > 0:
                s = qty
                while s > 1e-12 and fifo:
                    bq, bp = fifo[0]
                    take = min(bq, s)
                    realized += (px - bp) * take
                    bq -= take; s -= take
                    if bq <= 1e-12: fifo.popleft()
                    else: fifo[0] = [bq, bp]
        except:
            pass
    return realized

try:
    with open(CSV, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
except:
    rows = []

p = pnl_today(rows)
target_usd = float(EQUITY) * float(TARGET_PCT)
print(f"[DAILY_TARGET] pnl_today={p:.2f} target={target_usd:.2f}")
# Exit 2 ⇒ block BUY
sys.exit(2 if p >= target_usd else 0)
