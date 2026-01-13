#!/usr/bin/env python3
import time, json, pathlib, re

ROOT = pathlib.Path("/root/ethbot")
LOG = ROOT / "logs" / "console.out"
OUT = ROOT / "cache" / "feed_state.json"

RX = re.compile(r'INFO\s+px=([0-9]+(?:\.[0-9]+)?)\s+adx=([0-9]+(?:\.[0-9]+)?)\s+rsi=([0-9]+(?:\.[0-9]+)?)')

def main():
    now = int(time.time())
    ok = False; samples=0; last_line=None
    try:
        lines = LOG.read_text(errors="ignore").splitlines()[-800:]
        for ln in reversed(lines):
            m = RX.search(ln)
            if not m: 
                continue
            samples += 1
            last_line = ln
            # Heuristik: Zeile hat Timestamp "YYYY-MM-DD HH:MM:SS"
            # Wir werten die "letzten ~5 Minuten" über Position in den letzten 300 Zeilen
            if samples <= 60:  # sehr grob: ~letzte Minuten
                ok = True
                break
    except Exception:
        pass

    OUT.write_text(json.dumps({
        "ok": bool(ok),
        "samples_seen": samples,
        "last_sample_line": last_line,
        "ts": now
    }, ensure_ascii=False))

    print(f"[FEED] ok={ok} samples={samples}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
