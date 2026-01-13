#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, pathlib, csv, math, subprocess
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path("/root/ethbot")
LOGD = ROOT / "logs"
CON = LOGD / "console.out"
CSVF= LOGD / "trades.csv"
ENVF= ROOT / ".env.bot"
LOGA= LOGD / "adaptive_edge.log"
LOGD.mkdir(parents=True, exist_ok=True)

def log(msg):
    ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line=f"{ts} [ADAPT] {msg}"
    print(line, flush=True)
    with open(LOGA,"a",encoding="utf-8") as f: f.write(line+"\n")

def read_console(n=3000):
    if not CON.exists(): return ""
    p=subprocess.run(f"tail -n {n} {CON}", shell=True, capture_output=True, text=True, timeout=10)
    return p.stdout

def recent_pairs(hours=24):
    if not CSVF.exists(): return []
    rows=[]
    with open(CSVF, newline="", encoding="utf-8") as f:
        r=csv.DictReader(f)
        for d in r:
            try:
                d["timestamp"]=datetime.fromisoformat(d["timestamp"].replace("Z","")).replace(tzinfo=timezone.utc)
                d["price"]=float(d["price"]); d["qty"]=float(d["qty"])
                rows.append(d)
            except: pass
    rows=[x for x in rows if x["timestamp"]>=datetime.now(timezone.utc)-timedelta(hours=hours)]
    rows.sort(key=lambda x:x["timestamp"])
    buys=[]; pairs=[]
    for d in rows:
        if d["action"].upper()=="BUY":
            buys.append([d["timestamp"], d["qty"], d["price"]])
        elif d["action"].upper()=="SELL":
            s=d["qty"]
            while s>1e-12 and buys:
                bt,bq,bp=buys[0]; take=min(bq,s)
                pairs.append((bt,d["timestamp"],take,bp,d["price"]))
                bq-=take; s-=take
                if bq<=1e-12: buys.pop(0)
                else: buys[0]=[bt,bq,bp]
    return pairs

def load_env():
    env={}
    if ENVF.exists():
        for ln in ENVF.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k,v=ln.split("=",1); env[k.strip()]=v.strip()
    return env

def set_env(k,v):
    env=load_env()
    if env.get(k)==str(v): return False
    if ENVF.exists():
        txt=ENVF.read_text()
        if re.search(rf"^{re.escape(k)}=", txt, re.M):
            txt=re.sub(rf"^{re.escape(k)}=.*$", f"{k}={v}", txt, flags=re.M)
        else:
            txt=txt.rstrip()+"\n"+f"{k}={v}\n"
        ENVF.write_text(txt)
    else:
        ENVF.write_text(f"{k}={v}\n")
    return True

def clamp(x, lo, hi): 
    return max(lo, min(hi, x))

def main():
    con=read_console()
    soft = len(re.findall(r"regime soft-block", con))
    safes= len(re.findall(r"\[SAFEGUARD\]", con))
    pairs= recent_pairs(24)
    has_trades = len(pairs)>0

    log(f"soft={soft} safeguards={safes} trades24={len(pairs)}")

    # Trigger: > 200 Soft-Blocks in 24h und keine Trades → leicht lockern
    if soft>200 and not has_trades:
        env=load_env()
        adx_min = float(env.get("ADX_MIN", "18"))
        rsi_lo  = float(env.get("RSI_LO", "30"))
        rsi_hi  = float(env.get("RSI_HI", "58"))
        vwap_tol= float(env.get("VWAP_TOL", "1.000"))

        new_adx = clamp(adx_min - 1.0, 14.0, 30.0)
        new_rlo = clamp(rsi_lo - 1.0, 28.0, 40.0)
        new_rhi = clamp(rsi_hi + 1.0, 50.0, 62.0)
        new_vwp = clamp(vwap_tol + 0.001, 1.000, 1.003)

        changed=[]
        if set_env("ADX_MIN", f"{new_adx:.1f}"): changed.append(("ADX_MIN", adx_min, new_adx))
        if set_env("RSI_LO", f"{new_rlo:.1f}"):  changed.append(("RSI_LO", rsi_lo, new_rlo))
        if set_env("RSI_HI", f"{new_rhi:.1f}"):  changed.append(("RSI_HI", rsi_hi, new_rhi))
        if set_env("VWAP_TOL", f"{new_vwp:.3f}"):changed.append(("VWAP_TOL", vwap_tol, new_vwp))

        if changed:
            log("tuned: " + ", ".join([f"{k}:{a}->{b}" for k,a,b in changed]))
        else:
            log("no change (already at limits)")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
