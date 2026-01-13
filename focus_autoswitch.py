#!/usr/bin/env python3
import os, csv, json, time, sys
from datetime import datetime, timezone, timedelta

CSV = "/root/ethbot/logs/trades.csv"
ENV = "/root/ethbot/.env.bot"
STATEF = "/root/ethbot/logs/focus_state.json"
LOGF = "/root/ethbot/logs/focus_autoswitch.log"
FMT = "%Y-%m-%d %H:%M:%S"
TZ = timezone.utc

def log(s):
    ts = datetime.now(TZ).strftime(FMT)
    msg = f"{ts} [FOCUS-AUTO] {s}"
    print(msg)
    try:
        os.makedirs(os.path.dirname(LOGF), exist_ok=True)
        with open(LOGF,"a",encoding="utf-8") as f: f.write(msg+"\n")
    except Exception: pass

def read_env(path):
    d = {}
    if not os.path.exists(path):
        return d
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            # Inline-Kommentare (# ...) entfernen
            v = v.split("#", 1)[0].strip()
            d[k.strip()] = v
    return d


def write_env_update(path, key, val):
    lines=[]
    found=False
    if os.path.exists(path):
        for line in open(path,"r",encoding="utf-8"):
            if line.startswith(f"{key}="):
                lines.append(f"{key}={val}\n"); found=True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={val}\n")
    with open(path,"w",encoding="utf-8") as f: f.writelines(lines)

def parse_dt(s): return datetime.strptime(s,FMT).replace(tzinfo=TZ)

def load_pairs(csv_path, since):
    if not os.path.exists(csv_path): return []
    rows=list(csv.DictReader(open(csv_path,"r",encoding="utf-8")))
    # FIFO-Paarung BUY->SELL
    stack=[]; pairs=[]
    for r in rows:
        ts = parse_dt(r["timestamp"])
        act = r["action"].upper().strip()
        qty = float(r["qty"] or 0)
        px  = float(r["price"] or 0)
        if ts < since: continue
        if act=="BUY":
            stack.append([ts, qty, px])
        elif act=="SELL":
            s=qty
            while s>1e-12 and stack:
                b=stack[0]
                take=min(b[1], s)
                pairs.append((b[0], ts, take, b[2], px))  # (tbuy, tsell, qty, pbuy, psell)
                b[1]-=take; s-=take
                if b[1]<=1e-12: stack.pop(0)
    return pairs

def main():
    env = read_env(ENV)
    if env.get("FOCUS_AUTO","1") != "1":
        log("AUTO disabled (FOCUS_AUTO=0)"); return 0

    focus = int(env.get("FOCUS_MODE","1"))
    hours = int(env.get("FOCUS_CHECK_HOURS","72"))
    min_tr = int(env.get("FOCUS_MIN_TRADES","8"))
    target_pct = float(env.get("FOCUS_TARGET_MIN_PCT","0.010"))
    wr_min = float(env.get("FOCUS_WINRATE_MIN","0.52"))
    streak_need = int(env.get("FOCUS_STREAK_N","2"))
    equity = float(env.get("EQUITY_USDT", env.get("PAPER_BASE_USDT","100000")))

    since = datetime.now(TZ) - timedelta(hours=hours)
    pairs = load_pairs(CSV, since)

    # nur abgeschlossene Trades im Fenster zählen
    n = len(pairs)
    pnl_usd = sum((sp-bp)*q for (_,_,q,bp,sp) in pairs)
    wins = sum(1 for (_,_,q,bp,sp) in pairs if (sp-bp)>0)
    wr = (wins/n) if n else 0.0
    pnl_pct = (pnl_usd / equity) if equity>0 else 0.0

    # State laden
    try:
        state = json.load(open(STATEF,"r",encoding="utf-8"))
    except Exception:
        state = {"streak":0, "last_ok":0}

    ok = (n >= min_tr) and (pnl_pct >= target_pct) and (wr >= wr_min)
    if ok:
        state["streak"] = int(state.get("streak",0)) + 1
        state["last_ok"] = int(time.time())
    else:
        state["streak"] = 0

    json.dump(state, open(STATEF,"w",encoding="utf-8"))
    log(f"window={hours}h trades={n} pnl_usd={pnl_usd:.2f} pnl_pct={pnl_pct:.4f} wr={wr:.2f} streak={state['streak']} focus={focus}")

    # Deaktivieren, wenn in Focus & genug ok-Streak
    if focus==1 and state["streak"] >= streak_need:
        write_env_update(ENV, "FOCUS_MODE", "0")
        log(f"FOCUS_MODE -> 0 (stable reached; pnl_pct>={target_pct:.4f}, wr>={wr_min:.2f}, trades>={min_tr}, streak>={streak_need})")
        # Service neustarten
        os.system("systemctl restart ethbot")
        return 10

    return 0

if __name__=="__main__":
    sys.exit(main())
