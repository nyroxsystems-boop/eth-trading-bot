#!/usr/bin/env python3
import os, csv, pathlib, time
from tools.notify import send
ROOT=pathlib.Path("/root/ethbot"); LOGS=ROOT/"logs"; TRADES=LOGS/"trades.csv"; STATE=ROOT/"runtime"/"trade_notify.offset"
STATE.parent.mkdir(parents=True,exist_ok=True)

def last_offset():
    try: return int(STATE.read_text().strip())
    except: return 0
def write_offset(n): STATE.write_text(str(n))

def main():
    if not TRADES.exists(): return 0
    rows=list(csv.DictReader(TRADES.open()))
    start=last_offset()
    if start<0 or start>len(rows): start=0
    new=rows[start:]
    for r in new:
        ts=r.get("timestamp",""); side=r.get("action","").upper()
        qty=r.get("qty","?"); px=r.get("price","?")
        send(f"🟢 <b>{side}</b>\n⏱ {ts}\n📦 qty={qty}\n💵 px={px}")
    write_offset(len(rows))
    return 0
if __name__=="__main__": main()
