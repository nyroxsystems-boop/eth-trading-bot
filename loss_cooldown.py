#!/usr/bin/env python3
import csv, os
from datetime import datetime, timedelta

CSV="/root/ethbot/logs/trades.csv"
FMT="%Y-%m-%d %H:%M:%S"
COOLDOWN_MIN=int(os.getenv("LOSS_COOLDOWN_MIN","15"))

def parse(s): return datetime.strptime(s,FMT)
def last_pair_pnl():
    # Naiv: nimmt die letzten BUY/SELL mit Preis>0
    if not os.path.exists(CSV):
        return None
    rows=[]
    with open(CSV,"r") as f:
        rows=list(csv.DictReader(f))
    rows=[r for r in rows if r["price"] not in ("0","0.0","0.00","")]
    # finde letztes SELL und dazugehörige BUYs
    rows.sort(key=lambda r: r["timestamp"])
    last_sell=None
    for r in reversed(rows):
        if r["action"].upper()=="SELL":
            last_sell=r; break
    if not last_sell: return None
    sell_ts=parse(last_sell["timestamp"]); sell_px=float(last_sell["price"]); qty=float(last_sell["qty"])
    # suche vorherige BUYs (vereinfachung: ein BUY)
    for r in reversed(rows):
        if r["action"].upper()=="BUY" and parse(r["timestamp"])<=sell_ts:
            buy_px=float(r["price"]); bqty=float(r["qty"])
            take=min(bqty,qty)
            return sell_ts, (sell_px-buy_px)*take
    return None

def main():
    lp = last_pair_pnl()
    if not lp:
        print("[COOLDOWN] no last closed trade")
        return
    ts,pnl = lp
    if pnl < 0:
        cd_until = ts + timedelta(minutes=COOLDOWN_MIN)
        now = datetime.utcnow()
        if now < cd_until:
            print(f"[COOLDOWN] active until {cd_until}")
            exit(2)
    print("[COOLDOWN] not active")

if __name__=="__main__":
    main()
