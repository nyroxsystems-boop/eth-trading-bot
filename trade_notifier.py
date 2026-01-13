#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, pathlib, time, json, os
from datetime import datetime, timezone
from telegram_notify import send

ROOT = pathlib.Path("/root/ethbot")
LOG  = ROOT / "logs" / "console.out"
POS  = ROOT / "logs" / ".trade_notify.pos"

BUY  = re.compile(r'\[(?:DRY|LIVE)\]\s*BUY\s+([0-9.]+)\s+(\w+)(?:\s*@\s*~?([0-9.]+))?', re.I)
SELL = re.compile(r'\[(?:DRY|LIVE)\]\s*SELL\s+([0-9.]+)\s+(\w+)(?:\s*@\s*~?([0-9.]+))?', re.I)
WARNERR = re.compile(r'\b(ERROR|WARN)\b', re.I)

def read_from(offset: int):
    if not LOG.exists(): 
        return offset, []
    size = LOG.stat().st_size
    if offset > size:  # log rotiert
        offset = 0
    with LOG.open("rb") as f:
        f.seek(offset)
        chunk = f.read().decode(errors="ignore")
    lines = chunk.splitlines()
    return size, lines

def main():
    pos = 0
    if POS.exists():
        try: pos = int(POS.read_text().strip())
        except: pos = 0

    newpos, lines = read_from(pos)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for ln in lines:
        m1 = BUY.search(ln) or SELL.search(ln)
        if m1:
            qty, asset, px = m1.group(1), m1.group(2), (m1.group(3) or "n/a")
            kind = "BUY" if "BUY" in ln else "SELL"
            live = "LIVE" if "[LIVE]" in ln else "DRY"
            send(f"🟢 <b>{live} {kind}</b>\nQty: <b>{qty}</b> {asset}\nPx: <b>{px}</b>")
            continue
        if WARNERR.search(ln):
            send(f"⚠️ <b>Log</b>: {ln.strip()[:400]}")

    POS.write_text(str(newpos))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
