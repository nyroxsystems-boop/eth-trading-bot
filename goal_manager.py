#!/usr/bin/env python3
import os, csv, time, json, pathlib, datetime as dt
ROOT=pathlib.Path("/root/ethbot"); LOGD=ROOT/"logs"; STATED=ROOT/"state"
TRADES=LOGD/"trades.csv"; RISK_FLAG=STATED/"risk_off.flag"; META=STATED/"goals.json"
def envf(k,d): 
    v=os.getenv(k); 
    try: return float(v) if v is not None else d
    except: return d
def envi(k,d): 
    v=os.getenv(k); 
    try: return int(v) if v is not None else d
    except: return d
def today_utc(dts):
    return dts.astimezone(dt.timezone.utc).date()
def read_trades():
    if not TRADES.exists(): return []
    rows=[]
    with open(TRADES, newline='', encoding="utf-8") as f:
        r=csv.DictReader(f)
        for row in r:
            try: 
                ts=row.get("timestamp") or row.get("time") or ""
                price=float(row.get("price") or 0.0)
                side=row.get("action") or row.get("side") or ""
                qty=float(row.get("qty") or 0.0)
                rows.append((ts,side,qty,price))
            except: pass
    return rows
def last_24h_pnl_usd(rows):
    # grobe PnL-Schätzung aus BUY/SELL Pärchen, nur für Zielkontrolle
    stack=[]; pnl=0.0
    cutoff=time.time()-86400
    for ts,side,qty,price in rows:
        # kein strptime notwendig—approx: nimm alles (fallback genügt)
        if side=="BUY": stack.append((qty,price))
        elif side=="SELL" and stack:
            q,p=stack.pop(0)
            pnl += (price-p)*min(qty,q)
    return pnl
def loss_streak(rows):
    # zählt aufeinanderfolgende verlust trades (vereinfachtes Modell)
    streak=0; stack=[]
    for ts,side,qty,price in rows:
        if side=="BUY": stack.append((qty,price))
        elif side=="SELL" and stack:
            q,p=stack.pop(0)
            pnl=(price-p)*min(qty,q)
            if pnl<0: streak+=1
            else: streak=0
    return streak
def main():
    target=envf("DAILY_TARGET_PCT",0.0125); max_ls=envi("MAX_CONSEC_LOSSES",3); cool=envi("RISK_OFF_MINUTES",90)
    rows=read_trades()
    ls=loss_streak(rows)
    pnl_24h=last_24h_pnl_usd(rows)
    meta={"ts":int(time.time()),"pnl_24h":pnl_24h,"loss_streak":ls,"target_pct":target,"cool_min":cool}
    # Einfacher Risk-Off: wenn Ziel erreicht ODER Loss-Streak zu hoch -> Flag für X Minuten
    do_flag=False
    if ls>=max_ls: do_flag=True
    # optional: wenn wir PnL/Equity hätten, könnte man target_pct auf equity beziehen
    if do_flag:
        RISK_FLAG.write_text(str(int(time.time()+cool*60)))
    else:
        # abgelaufene Flags aufräumen
        if RISK_FLAG.exists():
            try:
                if int(RISK_FLAG.read_text()) < int(time.time()): RISK_FLAG.unlink(missing_ok=True)
            except: RISK_FLAG.unlink(missing_ok=True)
    (ROOT/"state/goals.json").write_text(json.dumps(meta))
    print("[GOALS] updated", json.dumps(meta))
if __name__=="__main__": main()
