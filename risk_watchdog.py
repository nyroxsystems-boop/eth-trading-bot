#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, time, json, pathlib, csv, math, re
ROOT = pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))
LOGS = pathlib.Path(os.getenv("LOG_DIR", str(ROOT / "logs")))
FLAGS = ROOT / "flags"
RUNTIME = ROOT / "runtime"
COUT = LOGS / "console.out"
TRADES = LOGS / "trades.csv"
SENTI = ROOT / "cache" / "sentiment.json"
RLOG  = LOGS / "risk_watchdog.log"

def envf(key, default):
    try:
        return float(os.getenv(key, str(default)))
    except Exception:
        return float(default)

def envi(key, default):
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return int(default)

DAILY_PNL_STOP = envf("DAILY_PNL_STOP", -0.015)   # -1.5%
MAX_CONS_LOSSES= envi("MAX_CONS_LOSSES", 3)
VOL_SPIKE_BLOCK = envf("VOL_SPIKE_BLOCK", 0.012)  # 1.2% in ~1min
SENTIMENT_HARD  = envf("SENTIMENT_HARD", -0.60)
ALLOW_MULTI_POS = envi("ALLOW_MULTI_POS", 0)

FLAGS.mkdir(parents=True, exist_ok=True)
RUNTIME.mkdir(parents=True, exist_ok=True)

def log(msg):
    with RLOG.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%F %T ") + msg.strip() + "\n")

def set_flag(name, reason):
    p = FLAGS / (name + ".stop")
    p.write_text(json.dumps({"reason": reason, "ts": int(time.time())}))
    log(f"FLAG ON  {name}: {reason}")

def clear_flag(name):
    p = FLAGS / (name + ".stop")
    if p.exists():
        p.unlink()
        log(f"FLAG OFF {name}")

def read_sentiment():
    try:
        obj = json.loads(SENTI.read_text())
        return float(obj.get("score", 0.0))
    except Exception:
        return None

def today_str(ts=None):
    return time.strftime("%Y-%m-%d", time.gmtime(ts or time.time()))

def load_trades_today():
    if not TRADES.exists(): return []
    out, today = [], today_str()
    with TRADES.open() as f:
        r = csv.DictReader(f)
        for row in r:
            ts = row.get("timestamp","")
            if ts[:10] == today:
                try:
                    out.append({
                        "ts": ts,
                        "action": row["action"].strip(),
                        "qty": float(row.get("qty", "0") or 0),
                        "price": float(row.get("price","0") or 0)
                    })
                except: pass
    return out

def realized_pnl_and_streak(trades):
    # Simple FIFO pairing BUY → SELL
    pos_qty, pos_cost, realized = 0.0, 0.0, 0.0
    last_results = []  # +win/-loss per round
    for t in trades:
        if t["action"].upper() == "BUY":
            pos_qty += t["qty"]
            pos_cost += t["qty"] * t["price"]
        elif t["action"].upper() == "SELL" and pos_qty > 0:
            sell_qty = min(pos_qty, t["qty"])
            avg_cost = pos_cost / max(pos_qty, 1e-12)
            pnl = (t["price"] - avg_cost) * sell_qty
            realized += pnl
            # für Sieg/Niederlage:
            last_results.append(1 if pnl > 0 else (-1 if pnl < 0 else 0))
            # Bestand reduzieren
            pos_qty -= sell_qty
            pos_cost -= avg_cost * sell_qty
    # Consecutive losses:
    cons = 0
    for r in reversed(last_results):
        if r < 0: cons += 1
        else: break
    return realized, cons

def last_prices(n=3, window=120):
    if not COUT.exists(): return []
    lines = []
    try:
        raw = COUT.read_text(errors="ignore").splitlines()[-800:]
    except:
        return []
    rx = re.compile(r"px=([0-9]+(?:\.[0-9]+)?)")
    for ln in reversed(raw):
        m = rx.search(ln)
        if m: lines.append(float(m.group(1)))
        if len(lines) >= n: break
    return list(reversed(lines))

def main():
    # 1) News/Sentiment Kill-Switch
    s = read_sentiment()
    if s is not None and s <= SENTIMENT_HARD:
        set_flag("news", f"sentiment={s:.2f} <= {SENTIMENT_HARD:.2f}")
    else:
        clear_flag("news")

    # 2) Volatility Spike (1-Min-Kante, approximiert mit letzten zwei px)
    px = last_prices(n=2)
    if len(px) == 2 and px[0] > 0:
        spike = abs(px[1] / px[0] - 1.0)
        if spike >= VOL_SPIKE_BLOCK:
            set_flag("vol_spike", f"Δpx≈{spike:.3%} >= {VOL_SPIKE_BLOCK:.1%}")
        else:
            clear_flag("vol_spike")

    # 3) Daily PnL Stop + Max Cons. Losses
    trades = load_trades_today()
    realized, cons = realized_pnl_and_streak(trades)

    # Prozent relativ zu nomineller "Basis": wir schätzen 1 ETH = Referenz; oder nutze Portfolio-Proxy
    # Für DRY brauchbar: relative Schwelle über Betrag => wir nehmen Preis * Menge Summe als Proxy.
    notional = sum(t["qty"] * t["price"] for t in trades if t["action"].upper() == "BUY") or 1.0
    pnl_pct = realized / notional

    if pnl_pct <= DAILY_PNL_STOP:
        set_flag("daily", f"pnl={pnl_pct:.2%} <= {DAILY_PNL_STOP:.2%}")
    else:
        clear_flag("daily")

    if cons >= MAX_CONS_LOSSES:
        set_flag("lossstreak", f"cons_losses={cons} >= {MAX_CONS_LOSSES}")
    else:
        clear_flag("lossstreak")

    # 4) Single-Position Guard (einfach: wenn letzte Aktion BUY und danach kein SELL)
    openish = False
    for t in reversed(trades):
        if t["action"].upper() == "SELL":
            openish = False; break
        if t["action"].upper() == "BUY":
            openish = True; break
    if not ALLOW_MULTI_POS and openish:
        set_flag("singlepos", "open position detected (no multi-pos allowed)")
    else:
        clear_flag("singlepos")

    log("ok run")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
