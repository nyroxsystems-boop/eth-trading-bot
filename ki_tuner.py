#!/usr/bin/env python3
import os, csv, math, time, json, subprocess, sys
from datetime import datetime, timezone, timedelta
CSV  = "/root/ethbot/logs/trades.csv"
LOG  = "/root/ethbot/logs/console.out"
ENVF = "/root/ethbot/.env.bot"
OUT  = "/root/ethbot/logs/ki_tuner_report.txt"
TZI  = timezone.utc
FMT  = "%Y-%m-%d %H:%M:%S"

# --- Policy & Bounds ---
BOUNDS = {
  "RISK_PCT":             (0.0010, 0.0100),   # 0.10% .. 1.00% Equity
  "STOP_LOSS_PCT":        (0.0050, 0.0200),   # 0.5% .. 2.0%
  "TAKE_PROFIT_PCT":      (0.0100, 0.0300),   # 1.0% .. 3.0%
  "TRAIL_PCT":            (0.0040, 0.0200),   # 0.4% .. 2.0%
  "TIME_IN_TRADE_MIN":    (20, 240),          # 20 .. 240 Minuten
  "DAILY_MAX_DRAWDOWN_USDT": (100, 3000),     # Safety Budget pro Tag
  "DAILY_TARGET_PCT":     (0.01, 0.05),       # 1% .. 5%
}

NUDGE = { # maximale Änderung pro Tuning-Run
  "RISK_PCT":          0.0005,
  "STOP_LOSS_PCT":     0.0010,
  "TAKE_PROFIT_PCT":   0.0020,
  "TRAIL_PCT":         0.0010,
  "TIME_IN_TRADE_MIN": 10,
  "DAILY_MAX_DRAWDOWN_USDT": 100,
  "DAILY_TARGET_PCT":  0.005,
}

# Regime-Grid: (vola, trend) -> Basis-Parameter
# vola: low/med/high   trend: range/trend
GRID = {
  ("low","range"): {"TAKE_PROFIT_PCT":0.012, "TRAIL_PCT":0.006, "TIME_IN_TRADE_MIN":180},
  ("low","trend"): {"TAKE_PROFIT_PCT":0.015, "TRAIL_PCT":0.007, "TIME_IN_TRADE_MIN":180},
  ("med","range"): {"TAKE_PROFIT_PCT":0.018, "TRAIL_PCT":0.009, "TIME_IN_TRADE_MIN":150},
  ("med","trend"): {"TAKE_PROFIT_PCT":0.020, "TRAIL_PCT":0.010, "TIME_IN_TRADE_MIN":150},
  ("high","range"):{"TAKE_PROFIT_PCT":0.022, "TRAIL_PCT":0.012, "TIME_IN_TRADE_MIN":120},
  ("high","trend"):{"TAKE_PROFIT_PCT":0.024, "TRAIL_PCT":0.012, "TIME_IN_TRADE_MIN":120},
}

def read_env(path):
    d={}
    if not os.path.exists(path): return d
    for line in open(path,"r",encoding="utf-8"):
        line=line.strip()
        if not line or line.startswith("#"): continue
        if "=" in line:
            k,v=line.split("=",1)
            d[k]=v
    return d

def write_env(path, envdict):
    lines=[]
    for k,v in envdict.items():
        lines.append(f"{k}={v}")
    open(path,"w",encoding="utf-8").write("\n".join(lines)+"\n")

def clamp(x, lo, hi):
    if isinstance(x, float): return float(max(lo, min(hi, x)))
    return int(max(lo, min(hi, int(x))))

def parse_ts(s): return datetime.strptime(s,FMT).replace(tzinfo=TZI)

def load_trades():
    if not os.path.exists(CSV): return []
    rows=list(csv.DictReader(open(CSV,"r",encoding="utf-8")))
    # filter ungültige Preise
    clean=[r for r in rows if r.get("qty") and r.get("action")]
    return clean

def pair_fifo(rows, since=None):
    # Returns closed trade pairs since 'since'
    stack=[]; out=[]
    for r in rows:
        try:
            ts=parse_ts(r["timestamp"])
            if since and ts<since: continue
            act=r["action"].upper(); qty=float(r["qty"]); px=float(r.get("price","0") or 0)
            if act=="BUY":
                stack.append({"ts":ts,"qty":qty,"px":px})
            elif act=="SELL":
                s=qty
                while s>1e-12 and stack:
                    b=stack[0]
                    take=min(b["qty"], s)
                    out.append({"buy_ts":b["ts"],"sell_ts":ts,"qty":take,"buy_px":b["px"],"sell_px":px})
                    b["qty"]-=take; s-=take
                    if b["qty"]<=1e-12: stack.pop(0)
        except: pass
    return out

def metrics(pairs):
    if not pairs: return {"trades":0,"winrate":0.0,"r_avg":0.0,"pnl":0.0,"max_consec_loss":0}
    pnl=0.0; wins=0; rlist=[]; consec=0; maxconsec=0
    for p in pairs:
        # R multiple: (exit-entry)/entry
        r=(p["sell_px"]-p["buy_px"])/p["buy_px"] if p["buy_px"]>0 else 0.0
        rlist.append(r)
        q=p["qty"]
        pnl+= (p["sell_px"]-p["buy_px"])*q
        if r>0: wins+=1; consec=0
        else: consec+=1; maxconsec=max(maxconsec, consec)
    wr = wins/len(pairs)
    r_avg = sum(rlist)/len(rlist) if rlist else 0.0
    return {"trades":len(pairs),"winrate":wr,"r_avg":r_avg,"pnl":pnl,"max_consec_loss":maxconsec}

def regime_from_log():
    # Schätzt Vola/Trend grob aus console.out (ADX + Preisbewegung), failsafe auf "med/trend"
    vola, trend = "med","trend"
    try:
        if not os.path.exists(LOG): return vola, trend
        tail = open(LOG,"r",encoding="utf-8",errors="ignore").read().splitlines()[-300:]
        # parse letzte ADX und RSI Zeilen
        adx_vals=[]; px_vals=[]
        for ln in tail:
            if "INFO no entry" in ln:
                # ... adx=14.3 px=3792.39 ...
                parts=ln.split()
                for t in parts:
                    if t.startswith("adx="):
                        try: adx_vals.append(float(t.split("=")[1]))
                        except: pass
                    if t.startswith("px="):
                        try: px_vals.append(float(t.split("=")[1]))
                        except: pass
        if len(px_vals)>=5:
            span = max(px_vals)-min(px_vals)
            mid  = (max(px_vals)+min(px_vals))/2 or 1.0
            atrp = span/mid  # grobe 5-min Range als ATR%
            if atrp < 0.006: vola="low"
            elif atrp < 0.015: vola="med"
            else: vola="high"
        if adx_vals:
            a = sum(adx_vals[-10:])/max(1,len(adx_vals[-10:]))
            trend = "trend" if a>=18.0 else "range"
    except: pass
    return vola, trend

def decide(env, day_pairs, week_pairs):
    # Baseline aus Regime
    vola, trend = regime_from_log()
    base = GRID[(vola,trend)].copy()

    # aktuelles env
    cur = {
        "RISK_PCT": float(env.get("RISK_PCT","0.0050")),
        "STOP_LOSS_PCT": float(env.get("STOP_LOSS_PCT","0.0075")),
        "TAKE_PROFIT_PCT": float(env.get("TAKE_PROFIT_PCT","0.015")),
        "TRAIL_PCT": float(env.get("TRAIL_PCT","0.008")),
        "TIME_IN_TRADE_MIN": int(env.get("TIME_IN_TRADE_MIN","120")),
        "DAILY_MAX_DRAWDOWN_USDT": float(env.get("DAILY_MAX_DRAWDOWN_USDT","300")),
        "DAILY_TARGET_PCT": float(env.get("DAILY_TARGET_PCT","0.02")),
    }
    # starte von cur, mische sanft in Richtung base
    targ = cur.copy()
    for k,v in base.items():
        if k in targ:
            step = NUDGE.get(k, 0.0)
            want = v
            if isinstance(step,float):
                delta = max(-step, min(step, float(want)-float(targ[k])))
                targ[k] = float(targ[k]) + delta
            else:
                delta = max(-step, min(step, int(want)-int(targ[k])))
                targ[k] = int(targ[k]) + delta

    # Performance Nudges (48h)
    perf48 = metrics(day_pairs)
    # wenn r_avg < 0 oder winrate < 0.45 → defensiver
    if perf48["trades"]>=4:
        if perf48["r_avg"] < 0 or perf48["winrate"] < 0.45:
            targ["RISK_PCT"]       = float(targ["RISK_PCT"]) - NUDGE["RISK_PCT"]
            targ["STOP_LOSS_PCT"]  = float(targ["STOP_LOSS_PCT"]) + NUDGE["STOP_LOSS_PCT"]
            targ["TAKE_PROFIT_PCT"]= float(targ["TAKE_PROFIT_PCT"]) + 0.0  # lass TP gleich
            targ["TRAIL_PCT"]      = float(targ["TRAIL_PCT"]) + NUDGE["TRAIL_PCT"]
        # wenn r_avg > 0.002 (~0.2%) & winrate >= 0.55 → aggressiver
        elif perf48["r_avg"] > 0.002 and perf48["winrate"] >= 0.55:
            targ["RISK_PCT"]       = float(targ["RISK_PCT"]) + NUDGE["RISK_PCT"]
            targ["STOP_LOSS_PCT"]  = float(targ["STOP_LOSS_PCT"]) - NUDGE["STOP_LOSS_PCT"]
            targ["TRAIL_PCT"]      = float(targ["TRAIL_PCT"]) - NUDGE["TRAIL_PCT"]

    # Clamps
    for k,(lo,hi) in BOUNDS.items():
        if k in targ:
            targ[k] = clamp(targ[k], lo, hi)

    return targ, (vola,trend), perf48

def main():
    env = read_env(ENVF)
    now = datetime.now(TZI)
    rows = load_trades()

    day_since  = now - timedelta(hours=48)
    week_since = now - timedelta(days=7)

    day_pairs  = pair_fifo(rows, day_since)
    week_pairs = pair_fifo(rows, week_since)

    targ, regime, perf48 = decide(env, day_pairs, week_pairs)

    # Nur schreiben, wenn Änderung bedeutsam ist (Summe %-Deltas > Schwelle)
    def delta_mag(a,b):
        keys = ["RISK_PCT","STOP_LOSS_PCT","TAKE_PROFIT_PCT","TRAIL_PCT","TIME_IN_TRADE_MIN","DAILY_MAX_DRAWDOWN_USDT","DAILY_TARGET_PCT"]
        s=0.0
        for k in keys:
            if k not in a or k not in b: continue
            va, vb = float(a[k]), float(b[k])
            if vb==0: continue
            s += abs((va-vb)/vb)
        return s

    mag = delta_mag(targ, {
        "RISK_PCT":float(env.get("RISK_PCT",0)),
        "STOP_LOSS_PCT":float(env.get("STOP_LOSS_PCT",0)),
        "TAKE_PROFIT_PCT":float(env.get("TAKE_PROFIT_PCT",0)),
        "TRAIL_PCT":float(env.get("TRAIL_PCT",0)),
        "TIME_IN_TRADE_MIN":float(env.get("TIME_IN_TRADE_MIN",0) or 0),
        "DAILY_MAX_DRAWDOWN_USDT":float(env.get("DAILY_MAX_DRAWDOWN_USDT",0)),
        "DAILY_TARGET_PCT":float(env.get("DAILY_TARGET_PCT",0)),
    })

    # Report
    os.makedirs("/root/ethbot/logs", exist_ok=True)
    open(OUT,"w",encoding="utf-8").write(
        f"[{now.isoformat()}] regime={regime} perf48={{trades:{perf48['trades']}, winrate:{perf48['winrate']:.2f}, r_avg:{perf48['r_avg']:.4f}, pnl:{perf48['pnl']:.2f}}}\n"
        f"target={json.dumps(targ, indent=2)}\n"
        f"delta_mag={mag:.4f}\n"
    )

    # Wenn kaum Trades → nur Report, nichts ändern
    if perf48["trades"] < 2:
        print("[KI] zu wenige Trades in 48h – nur Report.")
        return 0

    # Wenn Änderung signifikant → .env.bot überschreiben & Service restarten
    if mag >= 0.05:
        new_env = read_env(ENVF)
        for k,v in targ.items():
            new_env[k] = str(int(v)) if isinstance(v,int) else f"{float(v):.6f}".rstrip('0').rstrip('.')
        write_env(ENVF, new_env)
        open(OUT,"a",encoding="utf-8").write("APPLY: wrote .env.bot and restarting service\n")
        try:
            subprocess.run(["systemctl","restart","ethbot"], check=False)
        except Exception as e:
            open(OUT,"a",encoding="utf-8").write(f"restart failed: {e}\n")
        print("[KI] applied & restarted.")
    else:
        print("[KI] small delta – no apply.")
    return 0

if __name__=="__main__":
    sys.exit(main())
