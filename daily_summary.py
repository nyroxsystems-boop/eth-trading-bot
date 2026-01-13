#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd, pathlib, os
from datetime import datetime, timezone, timedelta
from telegram_notify import send

CSV = pathlib.Path("/root/ethbot/logs/trades.csv")
OUT = pathlib.Path("/root/ethbot/logs/daily_summary.txt")

def pair_fifo(df):
    buys=[]; pairs=[]
    for _,r in df.sort_values("timestamp").iterrows():
        q=float(r.qty); p=float(r.price); a=r.action.upper()
        if a=="BUY": buys.append([r.timestamp,q,p])
        elif a=="SELL":
            s=q
            while s>1e-12 and buys:
                bt,bq,bp=buys[0]; take=min(bq,s)
                pairs.append((bt,r.timestamp,take,bp,p))
                bq-=take; s-=take
                if bq<=1e-12: buys.pop(0)
                else: buys[0]=[bt,bq,bp]
    return pairs

def main():
    if not CSV.exists():
        OUT.write_text("No trades yet.\n")
        return 0
    df = pd.read_csv(CSV)
    if df.empty: 
        OUT.write_text("No trades yet.\n"); return 0
    df["timestamp"]=pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    cut = (datetime.now(timezone.utc)-timedelta(hours=24))
    dfl = df[df["timestamp"]>=cut]
    pairs = pair_fifo(dfl)
    pnl = [ (sp-bp)*q for (bt,st,q,bp,sp) in pairs ]
    wr  = (pd.Series(pnl)>0).mean()*100 if pnl else 0.0
    txt = f"🗓️ 24h Summary\nTrades: {len(pairs)}\nPnL: {sum(pnl):.2f} USD\nWinrate: {wr:.1f}%"
    OUT.write_text(txt+"\n")
    send(txt)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
