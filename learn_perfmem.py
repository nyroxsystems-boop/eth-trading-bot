#!/usr/bin/env python3
import csv, json, re, os
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT=Path(os.getenv("ETHBOT_ROOT", str(Path(__file__).resolve().parent)))
LOGS=ROOT/"logs"
RUNTIME=ROOT/"runtime"
DECIS=LOGS/"decisions.log"
TRADES=LOGS/"trades.csv"
WEIGHTS=RUNTIME/"perf_weights.json"
AUTENV=RUNTIME/"auto_tune.env"
REPORT=LOGS/"perfmem_report.txt"

HORIZON_DAYS = int(os.getenv("PERFMEM_HORIZON_DAYS", "7"))
FOCUS_MODE = (os.getenv("FOCUS_MODE","0") == "1")

def parse_ts(s):
    try: return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except: return None

def load_trades():
    rows=[]
    if not TRADES.exists(): return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=HORIZON_DAYS)
    with TRADES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            ts = parse_ts((row.get("timestamp") or "").strip())
            if not ts or ts<cutoff: continue
            try:
                rows.append({
                    "ts": ts,
                    "action": row.get("action","").strip().upper(),
                    "qty": float(row.get("qty") or 0),
                    "price": float(row.get("price") or 0),
                    "mode": (row.get("mode","DRY").strip().upper())
                })
            except: pass
    return rows

def pair_trades(rows):
    # simple FIFO BUY->SELL pairing
    buys=[]
    pairs=[]
    for r in rows:
        if r["action"]=="BUY":
            buys.append(r)
        elif r["action"]=="SELL" and buys:
            b = buys.pop(0)
            pnl = (r["price"]-b["price"])*min(b["qty"], r["qty"])
            dur = (r["ts"] - b["ts"]).total_seconds()/60.0
            pairs.append({"buy":b,"sell":r,"pnl":pnl,"dur_min":dur})
    return pairs

def adx_bucket(v):
    if v is None: return "NA"
    v=float(v)
    if v<15: return "adx<15"
    if v<25: return "15-25"
    if v<35: return "25-35"
    if v<50: return "35-50"
    return ">=50"

def load_decisions():
    # Format: ts,entry,adx,rsi,gap,last,vwap,uptrend,msg
    decs=[]
    if not DECIS.exists(): return decs
    cutoff = datetime.now(timezone.utc) - timedelta(days=HORIZON_DAYS)
    with DECIS.open() as f:
        for ln in f:
            parts = ln.strip().split(",", 8)
            if len(parts)<9: continue
            ts = parse_ts(parts[0].strip())
            if not ts or ts<cutoff: continue
            def fnum(x):
                try: return float(x)
                except: return None
            decs.append({
                "ts": ts,
                "type": parts[1].strip(),
                "adx": fnum(parts[2]),
                "rsi": fnum(parts[3]),
                "gap": fnum(parts[4]),
                "last": fnum(parts[5]),
                "vwap": fnum(parts[6]),
                "uptrend": (parts[7].strip().lower()=="true"),
                "msg": parts[8].strip()
            })
    return decs

def attach_outcomes(pairs, decs):
    # match each BUY to nearest decision <= BUY ts (within 60s)
    decs_sorted = sorted(decs, key=lambda d: d["ts"])
    out=[]
    for pr in pairs:
        buy_ts = pr["buy"]["ts"]
        sel = [d for d in decs_sorted if 0 <= (buy_ts - d["ts"]).total_seconds() <= 60]
        d = sel[-1] if sel else None
        out.append({"decision":d, "pair":pr})
    return out

def aggregate(attached):
    buckets={}
    for item in attached:
        dec=item["decision"]
        pr=item["pair"]
        pnl=pr["pnl"]
        entry = dec["type"] if dec else "UNK"
        adxb = adx_bucket(dec["adx"] if dec else None)
        key=(entry, adxb)
        if key not in buckets:
            buckets[key]={"count":0,"wins":0,"pnl":0.0,"dur_min":[],"rsi":[],"gap":[]}
        b=buckets[key]
        b["count"]+=1
        b["pnl"]+=pnl
        if pnl>0: b["wins"]+=1
        if dec:
            if dec["rsi"] is not None: b["rsi"].append(dec["rsi"])
            if dec["gap"] is not None: b["gap"].append(dec["gap"])
            b["dur_min"].append(pr["dur_min"])
    return buckets

def recommend(buckets):
    rec={}
    # Simple heuristics:
    # - Wenn MR & (adx 25-50) Verlust → MR_RSI_MAX -1 (min 18)
    # - Wenn MR & (adx <15) Gewinn → MR_RSI_MAX +1 (max 32)
    # - Wenn BO & (adx 25-35) Gewinn → BO_RELAX_ADX_MIN = min(BO_RELAX_ADX_MIN, 22)
    # - Wenn BO & (adx <15) Verlust → BO_RELAX_ADX_MIN = max(BO_RELAX_ADX_MIN, 20)
    def rate(e, a): return buckets.get((e,a), {"count":0,"pnl":0})
    pnl = lambda e,a: rate(e,a)["pnl"]
    cnt = lambda e,a: rate(e,a)["count"]
    rec["MR_RSI_MAX_DELTA"]=0
    rec["BO_RELAX_ADX_MIN_TARGET"]=None

    if cnt("MR","25-35")+cnt("MR","35-50")>=3 and (pnl("MR","25-35")+pnl("MR","35-50"))<0:
        rec["MR_RSI_MAX_DELTA"] -= 1
    if cnt("MR","adx<15")>=3 and pnl("MR","adx<15")>0:
        rec["MR_RSI_MAX_DELTA"] += 1

    if cnt("BO","25-35")+cnt("BO","35-50")>=3 and (pnl("BO","25-35")+pnl("BO","35-50"))>0:
        rec["BO_RELAX_ADX_MIN_TARGET"] = 20
    if cnt("BO","adx<15")>=3 and pnl("BO","adx<15")<0:
        rec["BO_RELAX_ADX_MIN_TARGET"] = max(20, (rec.get("BO_RELAX_ADX_MIN_TARGET") or 0))

    return rec

def bounded_update_env(path, rec):
    # only if FOCUS_MODE=1 → cautious nudges
    cur={}
    if path.exists():
        for ln in path.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k,v = ln.split("=",1); cur[k.strip()]=v.strip()
    def getf(k, d): 
        try: return float(cur.get(k,d))
        except: return d
    updates=[]
    if rec.get("MR_RSI_MAX_DELTA"):
        val = max(18.0, min(32.0, getf("MR_RSI_MAX", 26.0) + rec["MR_RSI_MAX_DELTA"]))
        updates.append(("MR_RSI_MAX", f"{val:.0f}"))
    if rec.get("BO_RELAX_ADX_MIN_TARGET") is not None:
        val = max(15.0, min(30.0, rec["BO_RELAX_ADX_MIN_TARGET"]))
        base = getf("BO_RELAX_ADX_MIN", 18.0)
        # pick the more conservative of current vs target, but move by at most 1 per run
        step = 1.0 if val>base else -1.0
        if abs(val-base) < 1.0: new=val
        else: new=base+step
        updates.append(("BO_RELAX_ADX_MIN", f"{new:.0f}"))

    if not updates: return False, cur
    # write suggestion file
    with AUTENV.open("w") as f:
        for k,v in updates: f.write(f"{k}={v}\n")

    # If in FOCUS_MODE → apply to .env.bot gently
    if FOCUS_MODE:
        envp = ROOT/".env.bot"
        s = envp.read_text() if envp.exists() else ""
        for k,v in updates:
            if re.search(rf"^{k}=", s, flags=re.M):
                s = re.sub(rf"^{k}=.*$", f"{k}={v}", s, flags=re.M)
            else:
                s += f"\n{k}={v}\n"
        envp.write_text(s)
    return True, updates

def main():
    trades = load_trades()
    pairs  = pair_trades(sorted(trades, key=lambda r:r["ts"]))
    decs   = load_decisions()
    attached = attach_outcomes(pairs,decs)
    buckets = aggregate(attached)
    rec = recommend(buckets)

    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    with WEIGHTS.open("w") as f:
        # normalize pretty keys (tuple -> "A|B")
        norm_buckets = {}
        for _k, _v in buckets.items():
            if isinstance(_k, tuple) and len(_k) == 2:
                norm_buckets[f"{_k[0]}|{_k[1]}"] = _v
            else:
                norm_buckets[str(_k)] = _v
        try:
            json.dump({'buckets': norm_buckets, 'recommend': rec}, f, indent=2, default=str)
        except Exception as e:
            json.dump({'buckets': {}, 'recommend': {'note': f'fallback: {e}'}}, f, indent=2)

    applied, upd = bounded_update_env(ROOT/".env.bot", rec)

    # write a human report
    lines=["=== Performance-Memory Report ==="]
    lines.append(f"Horizon: {HORIZON_DAYS}d  Pairs: {len(pairs)}  Decisions: {len(decs)}  Applied: {applied}  FocusMode={FOCUS_MODE}")
    for (entry,ab),b in sorted(buckets.items()):
        wr = (b["wins"]/b["count"]*100.0) if b["count"] else 0.0
        lines.append(f"- {entry:3s} | {ab:6s} | n={b['count']:3d} | win%={wr:5.1f} | pnl={b['pnl']:+.2f}")
    if applied:
        lines.append("→ Suggested/Applied:")
        for k,v in upd:
            lines.append(f"  {k}={v}")
    REPORT.write_text("\n".join(lines)+"\n")

if __name__=="__main__":
    main()
