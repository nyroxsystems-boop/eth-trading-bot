#!/usr/bin/env python3
import os, json, time, pathlib

ROOT = pathlib.Path("/root/ethbot")
CACHE = ROOT / "cache"
LOG   = ROOT / "logs" / "signal_gate.log"
CACHE.mkdir(parents=True, exist_ok=True)

def read_json(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None

def main():
    env  = {k:v for k,v in os.environ.items()}
    on   = env.get("SENTIMENT_GATE","1") == "1"
    smin = float(env.get("SENT_ENTRY_MIN","-0.2"))
    sstr = float(env.get("SENT_STRONG","0.8"))
    nmin = int(env.get("SENT_MIN_TWEETS","3"))
    tpmax_mult = float(env.get("TP_MAX_MULT","3.0"))
    tighten = float(env.get("RISK_TIGHTEN_NEG","0.8"))
    daily_boost = float(env.get("DAILY_STRONG_BOOST","0.015"))

    sent = read_json(CACHE/"sentiment.json") or {}
    score = float(sent.get("score", 0.0))
    n     = int(sent.get("n", 0))
    src   = sent.get("source", "none")
    ts    = int(sent.get("ts", 0))

    now = int(time.time())
    age = now - ts if ts else 999999

    result = {
        "on": bool(on),
        "block": False,
        "reason": "",
        "score": score,
        "n": n,
        "age_s": age,
        "source": src,
        "tp_mult": 1.0,
        "risk_mult": 1.0,
        "daily_target_boost": 0.0
    }

    if not on:
        (CACHE/"signal_block.flag").write_text("0")
        (CACHE/"signal_gate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        LOG.open("a").write(f"{time.strftime('%F %T', time.gmtime())} off\n")
        return 0

    # nur frische Daten werten (10 Min)
    if age > 600 or n < nmin:
        # keine Entscheidung -> neutral
        pass
    else:
        if score <= smin:
            result["block"] = True
            result["reason"] = "sentiment_negative"
            result["risk_mult"] = tighten
        elif score >= sstr:
            # starkes Event: TP strecken + Daily-Target-Booster
            result["tp_mult"] = min(tpmax_mult, 1.0 + (score - sstr) * 1.5)  # zarte Skalierung
            result["daily_target_boost"] = daily_boost

    (CACHE/"signal_block.flag").write_text("1" if result["block"] else "0")
    (CACHE/"signal_gate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    LOG.open("a").write(f"{time.strftime('%F %T', time.gmtime())} {result}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
