#!/usr/bin/env python3
import csv, os, sys
from datetime import datetime, timezone, timedelta

CSV="/root/ethbot/logs/trades.csv"
FMT="%Y-%m-%d %H:%M:%S"
TZI=timezone.utc

N   = int(os.getenv("MAX_CONSEC_LOSSES", "3"))          # z.B. 3
COOL= int(os.getenv("COOLDOWN_AFTER_MAX_LOSSES_MIN","60"))  # z.B. 60 min

def parse(s): return datetime.strptime(s,FMT).replace(tzinfo=TZI)

def closed_pairs(rows, limit=200):
    rows = [r for r in rows if r.get("price") not in ("","0","0.0","0.00")]
    rows.sort(key=lambda r: r["timestamp"])
    pairs=[]; stack=[]
    for r in rows:
        a=r["action"].upper()
        if a=="BUY":
            stack.append(r)
        elif a=="SELL" and stack:
            b = stack.pop(0)            # FIFO-Pairing
            pairs.append((b, r))
    return pairs[-limit:]

def main():
    try:
        with open(CSV,"r",encoding="utf-8") as f:
            rd=list(csv.DictReader(f))
    except Exception:
        print("[MAXLOSS] no csv")
        sys.exit(0)

    pairs=closed_pairs(rd,200)
    consec=0; last_sell_ts=None
    for b,s in reversed(pairs):
        pnl=(float(s["price"])-float(b["price"])) * min(float(b["qty"]), float(s["qty"]))
        last_sell_ts = parse(s["timestamp"])
        if pnl < 0: consec += 1
        else: break

    if consec >= N and last_sell_ts:
        until = last_sell_ts + timedelta(minutes=COOL)
        if datetime.now(TZI) < until:
            print(f"[MAXLOSS] consec={consec}  cooldown active until {until.isoformat()}")
            sys.exit(2)

    print(f"[MAXLOSS] consec={consec} ok")
    sys.exit(0)

if __name__=="__main__":
    main()
