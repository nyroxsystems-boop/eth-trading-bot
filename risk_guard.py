#!/usr/bin/env python3
import csv, sys
from datetime import datetime, timezone
import os, pathlib
_ROOT=pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))
CSV=str(_ROOT/"logs/trades.csv"); FMT="%Y-%m-%d %H:%M:%S"; TZI=timezone.utc
DD=float(sys.argv[1]) if len(sys.argv)>1 else 300.0
def parse(s): return datetime.strptime(s,FMT).replace(tzinfo=TZI)
def today_range():
    now=datetime.now(TZI); return now.replace(hour=0,minute=0,second=0,microsecond=0), now
def pnl_today(rows):
    from collections import deque
    start,end=today_range(); fifo=deque(); realized=0.0
    for r in rows:
        try:
            ts=parse(r["timestamp"])
            if not(start<=ts<=end): continue
            act=r["action"].upper(); qty=float(r["qty"]); px=float(r["price"])
            if px <= 0:  # Skip invalid prices
                continue
            if act=="BUY": fifo.append([qty,px])
            elif act=="SELL" and px>0:
                s=qty
                while s>1e-12 and fifo:
                    bq,bp=fifo[0]; take=min(bq,s); realized+=(px-bp)*take
                    bq-=take; s-=take; fifo.popleft() if bq<=1e-12 else fifo.__setitem__(0,[bq,bp])
        except: pass
    return realized
try:
    with open(CSV,"r",encoding="utf-8") as f: rows=list(csv.DictReader(f))
except: rows=[]
p=pnl_today(rows)
print(f"[GUARD] realized_pnl_today={p:.2f}  limit=-{DD:.2f}")
sys.exit(2 if p<=-DD else 0)
