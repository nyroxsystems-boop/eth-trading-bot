#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Learn-Jarvis
- liest trades.csv, berechnet WR/PnL über 48–72h
- schlägt kleine Parameter-Adjustments vor (bounded, smooth)
- standardmäßig DRY (nur Log), kann real schreiben wenn LEARN_DRY=0
- schreibt Log nach logs/learn_jarvis.log
"""
import os, sys, csv, math, pathlib, time, re
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path("/root/ethbot")
LOGD = ROOT / "logs"
LOGD.mkdir(parents=True, exist_ok=True)
LOGF = LOGD / "learn_jarvis.log"
ENVF = ROOT / ".env.bot"
CSVF = LOGD / "trades.csv"
STATEF = ROOT / ".jarvis/learn_state.json"
pathlib.Path(ROOT / ".jarvis").mkdir(exist_ok=True)

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [LEARN] {msg}"
    print(line, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(line+"\n")

def read_env(fp: pathlib.Path) -> dict:
    data = {}
    if fp.exists():
        for line in fp.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#"): continue
            if "=" in line:
                k,v = line.split("=",1)
                data[k.strip()] = v.strip()
    return data

def write_env(fp: pathlib.Path, env: dict):
    # sichere, einfache Neu-Schreibung (Preserve order not required)
    lines = []
    seen = set()
    if fp.exists():
        for line in fp.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k = line.split("=",1)[0].strip()
                if k in env:
                    lines.append(f"{k}={env[k]}")
                    seen.add(k)
                else:
                    lines.append(line)
            else:
                lines.append(line)
    # append missing keys
    for k,v in env.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    fp.write_text("\n".join(lines) + "\n", encoding="utf-8")

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def to_float(env: dict, key: str, default: float) -> float:
    try:
        return float(str(env.get(key, default)).strip())
    except Exception:
        return float(default)

def to_int(env: dict, key: str, default: int) -> int:
    try:
        return int(str(env.get(key, default)).strip())
    except Exception:
        return int(default)

def load_pairs(hours=72):
    # CSV erwartetes Format: timestamp,action,qty,price
    if not CSVF.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = []
    with open(CSVF, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except Exception:
                # parse robust
                ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                rows.append({
                    "ts": ts,
                    "action": row["action"].strip().upper(),
                    "qty": float(row["qty"]),
                    "price": float(row["price"])
                })
    rows.sort(key=lambda x: x["ts"])
    # FIFO pairing BUY -> SELL
    buys = []
    pairs = []
    for r in rows:
        if r["action"] == "BUY":
            buys.append([r["ts"], r["qty"], r["price"]])
        elif r["action"] == "SELL":
            s = r["qty"]
            while s>1e-12 and buys:
                bt,bq,bp = buys[0]
                take = min(bq, s)
                pairs.append((bt, r["ts"], take, bp, r["price"]))
                bq -= take; s -= take
                if bq <= 1e-12:
                    buys.pop(0)
                else:
                    buys[0] = [bt,bq,bp]
    return pairs

def pnl_stats(pairs, equity_usdt: float):
    if not pairs:
        return {"trades":0, "winrate":0.0, "pnl_usd":0.0, "pnl_pct":0.0}
    pnls = [(sp-bp)*q for (_,_,q,bp,sp) in pairs]
    wins = sum(1 for x in pnls if x>0)
    pnl_usd = sum(pnls)
    pnl_pct = pnl_usd / max(equity_usdt, 1.0)
    wr = wins / len(pnls) if pnls else 0.0
    return {
        "trades": len(pnls),
        "winrate": wr,        # 0..1
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,   # Anteil an EQUITY_USDT
    }

def main():
    env = read_env(ENVF)
    EQUITY = to_float(env, "EQUITY_USDT", 100000.0)

    # Defaults & Grenzen
    LEARN_DRY   = to_int(env, "LEARN_DRY", 1)   # 1=dry (nur log), 0=schreiben
    COOLDOWN_MIN= to_int(env, "LEARN_COOLDOWN_MIN", 60)
    HOURS       = to_int(env, "LEARN_WINDOW_HOURS", 72)
    MIN_TRADES  = to_int(env, "LEARN_MIN_TRADES", 8)

    RISK_PCT    = to_float(env, "RISK_PCT", 0.0050)
    TAKE_PCT    = to_float(env, "TAKE_PROFIT_PCT", 0.015)
    STOP_PCT    = to_float(env, "STOP_LOSS_PCT", 0.0075)
    TRAIL_PCT   = to_float(env, "TRAIL_PCT", 0.008)
    MAX_TRADES  = to_int(env,   "MAX_TRADES", 3)

    # harte Klammern
    RISK_MIN,RISK_MAX   = 0.0020, 0.0100
    TAKE_MIN,TAKE_MAX   = 0.0080, 0.0400
    STOP_MIN,STOP_MAX   = 0.0040, 0.0200
    TRAIL_MIN,TRAIL_MAX = 0.0040, 0.0200
    MAXT_MIN,MAXT_MAX   = 1, 10

    pairs = load_pairs(HOURS)
    stats = pnl_stats(pairs, EQUITY)
    wr = stats["winrate"]; pnl_usd = stats["pnl_usd"]; pnl_pct = stats["pnl_pct"]; ntr = stats["trades"]

    log(f"window={HOURS}h trades={ntr} pnl_usd={pnl_usd:.2f} pnl_pct={pnl_pct:.4f} wr={wr:.2%} dry={LEARN_DRY}")

    if ntr < MIN_TRADES:
        log(f"skip: not enough trades (min {MIN_TRADES})")
        return 0

    # Cooldown (einfache Sperre via mtime STATEF)
    try:
        if STATEF.exists():
            last = STATEF.stat().st_mtime
            if time.time() - last < COOLDOWN_MIN*60:
                remain = COOLDOWN_MIN*60 - (time.time()-last)
                log(f"cooldown: {remain/60:.1f} min left")
                return 0
    except Exception:
        pass

    # Heuristik
    # Erfolg: wr >= 0.58 und pnl_pct >= 1.0% → kleine Up-Adjustments
    # Neutral: wr in [0.50..0.58] → kleine Feintuning-Schritte
    # Schwach: wr < 0.45 oder pnl_pct <= -0.5% → defensiver
    changed = {}
    def set_change(k, new):
        changed[k] = new

    if wr >= 0.58 and pnl_pct >= 0.010:
        # vorsichtig hoch
        set_change("RISK_PCT", clamp(RISK_PCT * 1.08, RISK_MIN, RISK_MAX))
        set_change("TAKE_PROFIT_PCT", clamp(TAKE_PCT + 0.001, TAKE_MIN, TAKE_MAX))
        set_change("STOP_LOSS_PCT", clamp(STOP_PCT * 0.95, STOP_MIN, STOP_MAX))  # etwas enger
        set_change("TRAIL_PCT", clamp(TRAIL_PCT * 0.95, TRAIL_MIN, TRAIL_MAX))
        if MAX_TRADES < 5:
            set_change("MAX_TRADES", clamp(MAX_TRADES+1, MAXT_MIN, MAXT_MAX))
        reason = "strong performance"
    elif wr < 0.45 or pnl_pct <= -0.005:
        # runterfahren
        set_change("RISK_PCT", clamp(RISK_PCT * 0.85, RISK_MIN, RISK_MAX))
        set_change("TAKE_PROFIT_PCT", clamp(TAKE_PCT * 0.95, TAKE_MIN, TAKE_MAX))
        set_change("STOP_LOSS_PCT", clamp(STOP_PCT * 1.10, STOP_MIN, STOP_MAX))  # weiter
        set_change("TRAIL_PCT", clamp(TRAIL_PCT * 1.05, TRAIL_MIN, TRAIL_MAX))
        if MAX_TRADES > 3:
            set_change("MAX_TRADES", clamp(MAX_TRADES-1, MAXT_MIN, MAXT_MAX))
        reason = "weak performance"
    else:
        # sanftes Feintuning
        drift = 1.02 if wr >= 0.52 else 0.98
        set_change("RISK_PCT", clamp(RISK_PCT * drift, RISK_MIN, RISK_MAX))
        set_change("TAKE_PROFIT_PCT", clamp(TAKE_PCT + (0.0005 if wr>=0.52 else -0.0005), TAKE_MIN, TAKE_MAX))
        set_change("STOP_LOSS_PCT", clamp(STOP_PCT * (0.98 if wr>=0.52 else 1.02), STOP_MIN, STOP_MAX))
        set_change("TRAIL_PCT", clamp(TRAIL_PCT * (0.98 if wr>=0.52 else 1.02), TRAIL_MIN, TRAIL_MAX))
        reason = "neutral fine-tune"

    # Nur loggen, wenn sich wirklich etwas ändert
    preview = []
    for k,new in changed.items():
        old = {"RISK_PCT":RISK_PCT,"TAKE_PROFIT_PCT":TAKE_PCT,"STOP_LOSS_PCT":STOP_PCT,"TRAIL_PCT":TRAIL_PCT,"MAX_TRADES":MAX_TRADES}[k]
        if isinstance(old, float):
            if abs(new-old) < 1e-6: continue
            preview.append(f"{k}: {old:.4f} -> {new:.4f}")
        else:
            if int(new) == int(old): continue
            preview.append(f"{k}: {old} -> {int(new)}")

    if not preview:
        log("no-op: nothing to change")
        STATEF.touch()
        return 0

    log(f"plan ({reason}): " + "; ".join(preview))

    if int(LEARN_DRY) == 1:
        log("DRY-RUN=1 -> no changes written")
        STATEF.touch()
        return 0

    # Schreiben
    new_env = env.copy()
    for k,new in changed.items():
        if isinstance(new, float):
            new_env[k] = f"{new:.4f}"
        else:
            new_env[k] = str(int(new))

    write_env(ENVF, new_env)
    log("env updated. Restarting ethbot to apply...")
    try:
        os.system("systemctl restart ethbot")
    except Exception as e:
        log(f"restart failed: {e}")

    STATEF.touch()
    return 0

if __name__ == "__main__":
    sys.exit(main())
