#!/usr/bin/env python3
import os, re, sys, statistics as stats
from math import isnan

LOG = "/root/ethbot/logs/console.out"

def load_series(n=200):
    adx, rsi, px = [], [], []
    try:
        with open(LOG, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-1000:]  # genug Kontext
    except Exception as e:
        print(f"[EDGE] ERROR loading console.out: {e}")
        return adx, rsi, px


    # Versuche, adx / rsi / px aus INFO-Zeilen zu ziehen (Reihenfolge tolerant)
    rx_adx = re.compile(r"adx\s*=\s*([0-9]+(?:\.[0-9]+)?)")
    rx_rsi = re.compile(r"rsi\s*=\s*([0-9]+(?:\.[0-9]+)?)")
    rx_px  = re.compile(r"px\s*=\s*([0-9]+(?:\.[0-9]+)?)")

    for line in lines:
        if "INFO no entry" not in line and "INFO" not in line:
            continue
        ma = rx_adx.search(line)
        mr = rx_rsi.search(line)
        mp = rx_px.search(line)
        if mp:
            px.append(float(mp.group(1)))
        if ma:
            adx.append(float(ma.group(1)))
        if mr:
            rsi.append(float(mr.group(1)))
    # Nur die letzten n Werte
    return adx[-n:], rsi[-n:], px[-n:]

def simple_rsi(series, period=14):
    if len(series) < period + 1: return float("nan")
    gains, losses = [], []
    for i in range(1, period+1):
        diff = series[-i] - series[-i-1]
        if diff >= 0: gains.append(diff)
        else: losses.append(-diff)
    avg_gain = (sum(gains)/period) if gains else 0.0
    avg_loss = (sum(losses)/period) if losses else 0.0
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100/(1+rs))

def vwap_like(series):
    # Ohne Volumen approximieren wir via gleitendem Mittel
    if not series: return float("nan")
    return sum(series)/len(series)


def _read_sentiment_score(path="/root/ethbot/logs/sentiment_state.json"):
    try:
        import json, os
        if os.getenv("TWITTER_SENTIMENT", "0") != "1":
            return None
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return float(obj.get("score", 0.0))
    except Exception:
        return None

def read_sentiment_score():
    try:
        import json
        from pathlib import Path
        p = Path('/root/ethbot/cache/sentiment.json')
        if not p.exists():
            return 0.0
        return float(json.loads(p.read_text()).get('score', 0.0))
    except Exception:
        return 0.0


def main():
    # --- global risk-off guard ---
    try:
        from pathlib import Path
        rf = Path('/root/ethbot/state/risk_off.flag')
        if rf.exists():
            print('[EDGE] risk-off active; blocking entries')
            import sys; sys.exit(2)
    except Exception:
        pass
    # --- Live-Guards: Flags aus /root/ethbot/flags ---
    try:
        import os, json, glob
        for fp in glob.glob('/root/ethbot/flags/*.stop'):
            try:
                obj=json.loads(open(fp,'r').read()); reason=obj.get('reason','')
            except Exception:
                reason=''
            print(f"[EDGE] live-guard block: {fp.split('/')[-1]} {reason}")
            import sys; sys.exit(3)
    except Exception:
        pass
    # -----------------------------------------------

    import os, sys

    # Focus-Flag
    FOCUS = int(os.getenv("FOCUS_MODE", "0") or "0")

    # Daten laden
    adx_s, rsi_s, px_s = load_series(200)
    if not px_s or len(px_s) < 25:
        # falls Sentiment aktiv ist: kurz anzeigen
        try:
            _sd = _read_sentiment_score()
            if _sd is not None:
                print(f"[EDGE_SENT] score={_sd:+.2f}")
        except Exception:
            pass
        print("[EDGE] not-enough-data")
        sys.exit(2)

    # Basismetriken
    last   = px_s[-1]
    highN  = max(px_s[-20:])                 # 20-Window High
    sma20  = sum(px_s[-20:]) / 20.0
    vwap   = vwap_like(px_s[-60:])           # 60-Ticks Durchschnitt

    adx14  = adx_s[-1] if adx_s else 20.0
    rsi14  = rsi_s[-1] if rsi_s else simple_rsi(px_s, 14)
    if isnan(rsi14):
        rsi14 = 50.0

    # Regeln (balanced-plus)
    adx_min   = 18.0 * (0.85 if FOCUS else 1.0)   # im Focus 15% lockerer
    brk_tol   = 0.9985 if FOCUS else 0.9990       # near-breakout Toleranz
    rsi_hi    = 55.0  if FOCUS else 52.0          # MR RSI Obergrenze
    vwap_tol  = 0.996  if FOCUS else 0.995        # MR Abstand zu VWAP

    uptrend    = (last >= sma20)
    trend_ok   = uptrend
    brk_ok     = (last >= highN * 1.0000)         # echter Ausbruch
    near_break = (last >= highN * brk_tol)        # knapp unter High
    mr_ok      = ((last <= vwap * (1.0000 if FOCUS else 0.9980)) and (30.0 <= rsi14 <= (58.0 if FOCUS else 56.0)))

    allow = (
        (trend_ok and (brk_ok or near_break)) or
        mr_ok or
        (FOCUS and (rsi14 <= 42.0 and last <= vwap * 1.0010))
    )

    # --- Sentiment Gate (optional via TWITTER_SENTIMENT=1) ---
    try:
        _sent = _read_sentiment_score()
        if os.getenv("TWITTER_SENTIMENT", "0") == "1" and _sent is not None:
            # stark negativ => blocken
            if _sent <= -0.30:
                allow = False
            # deutlich positiv => soft unlock, wenn Setup halbwegs passt
            elif _sent >= 0.35 and not allow:
                if (trend_ok or mr_ok or near_break):
                    allow = True
            try:
                print(f"[EDGE] sentiment={_sent:+.2f}")
            except Exception:
                pass
    except Exception as e:
        try:
            print(f"[EDGE] sentiment_error: {e}")
        except Exception:
            pass
    # ---------------------------------------------------------

    near = (last / highN - 1.0) if highN else 0.0
    print("[EDGE] uptrend=%s trend_ok=%s brk_ok=%s near=%.3f mr_ok=%s adx=%.1f rsi=%.1f last=%.2f highN=%.2f vwap=%.2f"
          % (str(uptrend), str(trend_ok), str(brk_ok), near, str(mr_ok), adx14, rsi14, last, highN, vwap))

    sys.exit(0 if allow else 2)


if __name__ == "__main__":
    main()
# --- Health alias ---
try:
    probe
except NameError:
    try:
        probe = main
    except NameError:
        pass

# --- Health alias ---
try:
    probe
except NameError:
    try:
        probe = main
    except NameError:
        pass
