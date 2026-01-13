#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv, pathlib, time, os, math, statistics as st

ROOT = pathlib.Path("/root/ethbot")
LOGS = ROOT / "logs"
TRADES = LOGS / "trades.csv"
RLOG  = LOGS / "auto_tuner.log"
ENV   = ROOT / ".env.bot"

def log(msg):
    with RLOG.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%F %T ")+msg.strip()+"\n")

def load_rounds(limit=50):
    if not TRADES.exists(): return []
    rows=[]
    with TRADES.open() as f:
        r=csv.DictReader(f)
        for x in r:
            try:
                rows.append(dict(
                    ts=x["timestamp"], action=x["action"].upper(),
                    qty=float(x.get("qty","0") or 0), price=float(x.get("price","0") or 0)
                ))
            except: pass
    # Pair FIFO BUY→SELL
    rounds=[]; qty=0.0; cost=0.0
    for t in rows:
        if t["action"]=="BUY":
            qty+=t["qty"]; cost+=t["qty"]*t["price"]
        elif t["action"]=="SELL" and qty>0:
            sell=min(qty, t["qty"])
            avg= cost/max(qty,1e-12)
            pnl = (t["price"]-avg)*sell
            rr  = pnl/(avg*sell)  # ~pct
            rounds.append(rr)
            qty-=sell; cost-=avg*sell
    return rounds[-limit:]

def set_env(key, val):
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    seen=False
    for i,l in enumerate(lines):
        if l.startswith(key+"="):
            lines[i]=f"{key}={val}"; seen=True; break
    if not seen: lines.append(f"{key}={val}")
    ENV.write_text("\n".join(lines)+"\n")

def main():
    r = load_rounds(50)
    if len(r)<8:
        log("not enough rounds for tuning"); return 0
    hit = sum(1 for x in r if x>0)/len(r)
    med = st.median(r)
    avg = st.mean(r)
    # Konservativ: wenn Trefferquote > 58% → TP leicht anheben, Stop leicht senken
    # wenn < 45% → TP leicht runter, Stop etwas hoch
    try:
        tp_min = float(os.getenv("TP_MIN","0.004"))
        tp_max = float(os.getenv("TP_MAX","0.012"))
        stop   = float(os.getenv("STOP_ATR_MULT","1.8"))
    except: tp_min,tp_max,stop = 0.004,0.012,1.8

    new_tp_min, new_tp_max, new_stop = tp_min, tp_max, stop
    if hit >= 0.58 and med > 0:
        new_tp_min = min(tp_min*1.05, tp_max*0.9)
        new_tp_max = min(tp_max*1.05, 0.03)
        new_stop   = max(1.2, stop*0.97)
    elif hit <= 0.45:
        new_tp_min = max(0.0025, tp_min*0.93)
        new_tp_max = max(new_tp_min*1.5, tp_max*0.93)
        new_stop   = min(2.8, stop*1.05)

    # Nur schreiben, wenn Änderungen > sehr kleine Schwellen
    def diff(a,b): return abs(a-b) > 1e-6
    if diff(tp_min,new_tp_min): set_env("TP_MIN", f"{new_tp_min:.6f}")
    if diff(tp_max,new_tp_max): set_env("TP_MAX", f"{new_tp_max:.6f}")
    if diff(stop,  new_stop  ): set_env("STOP_ATR_MULT", f"{new_stop:.4f}")

    log(f"hit={hit:.2%} med={med:+.3%} avg={avg:+.3%} -> TP_MIN={new_tp_min:.4%} TP_MAX={new_tp_max:.4%} STOP_ATR_MULT={new_stop:.2f}")
    return 0

if __name__=="__main__":
    main()
