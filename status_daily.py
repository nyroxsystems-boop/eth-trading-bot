#!/usr/bin/env python3
import time, json, pathlib, csv

ROOT = pathlib.Path("/root/ethbot")
LOG = ROOT / "logs" / "console.out"
TRADES = ROOT / "logs" / "trades.csv"
OUT = ROOT / "logs" / "status_daily.txt"
FEED = ROOT / "cache" / "feed_state.json"
SENT = ROOT / "cache" / "sentiment.json"
AUTO = ROOT / "cache" / "auto_params.json"

def tail_metrics():
    adx=None;rsi=None;px=None
    try:
        for ln in LOG.read_text(errors="ignore").splitlines()[-600:][::-1]:
            if "INFO px=" in ln and "adx=" in ln and "rsi=" in ln:
                # crude parse
                parts = ln.split()
                # px=### adx=### rsi=###
                for p in parts:
                    if p.startswith("px="): px=float(p[3:])
                    if p.startswith("adx="): adx=float(p[4:])
                    if p.startswith("rsi="): rsi=float(p[4:])
                if all(v is not None for v in (px, adx, rsi)):
                    return px, adx, rsi, ln
    except Exception:
        pass
    return px, adx, rsi, None

def last_trades(n=10):
    out=[]
    try:
        with TRADES.open() as f:
            rd = list(csv.reader(f))
        hdr = rd[0] if rd else []
        for row in rd[-n:]:
            out.append(row)
        return hdr, out
    except Exception:
        return [], out

def maybe(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def main():
    px, adx, rsi, last_line = tail_metrics()
    hdr, trs = last_trades(12)
    feed = maybe(FEED)
    sent = maybe(SENT)
    auto = maybe(AUTO)
    now = time.strftime("%F %T", time.gmtime())

    with OUT.open("w", encoding="utf-8") as f:
        f.write(f"== ETHBot Daily Status {now} UTC ==\n")
        f.write(f"PX/ADX/RSI last: px={px} adx={adx} rsi={rsi}\n")
        f.write(f"Last console line: {last_line}\n")
        f.write(f"Feed OK: {feed.get('ok') if isinstance(feed, dict) else None}\n")
        f.write(f"Sentiment: {sent}\n")
        f.write(f"AutoTune: {auto}\n")
        f.write("\nTrades (tail):\n")
        if hdr: f.write(",".join(hdr)+"\n")
        for r in trs: f.write(",".join(r)+"\n")
    print("[DAILY] status written:", OUT)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
