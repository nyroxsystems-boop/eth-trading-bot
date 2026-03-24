#!/usr/bin/env python3
import os, re, json, time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(os.getenv("ETHBOT_ROOT", str(Path(__file__).resolve().parent)))
LOGC = ROOT/"logs/console.out"
OUT  = ROOT/"logs/decisions.log"         # append-only, csv-like
STATE= ROOT/"runtime/perfmem_state.json"  # remember last processed byte
OUT.parent.mkdir(parents=True, exist_ok=True)
STATE.parent.mkdir(parents=True, exist_ok=True)

EDGE_RX = re.compile(r'\[(?:EDGE)\]\s+(?P<msg>OVERRIDE allow:.*|allow:.*|.*allow.*)', re.I)
VAL_RX  = re.compile(r'adx=(?P<adx>\d+(?:\.\d+)?)|rsi=(?P<rsi>\d+(?:\.\d+)?)|gap=(?P<gap>-?\d+(?:\.\d+)?)|last=(?P<last>\d+(?:\.\d+)?)|vwap=(?P<vwap>\d+(?:\.\d+)?)|uptrend=(?P<up>True|False)', re.I)

def now_utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

def load_pos():
    try:
        return json.loads(STATE.read_text()).get("pos", 0)
    except Exception:
        return 0

def save_pos(pos):
    STATE.write_text(json.dumps({"pos":pos}))

def parse_vals(s):
    vals = {"adx":None,"rsi":None,"gap":None,"last":None,"vwap":None,"uptrend":None}
    for m in VAL_RX.finditer(s):
        d = m.groupdict()
        for k,v in d.items():
            if v is None: continue
            if k in ("up",):
                vals["uptrend"] = (v.lower()=="true")
            else:
                try: vals[k] = float(v)
                except: pass
    return vals

def main():
    pos = load_pos()
    size = LOGC.stat().st_size if LOGC.exists() else 0
    if pos > size: pos = 0  # log rotated
    with LOGC.open('r', errors='ignore') as f:
        f.seek(pos)
        lines = f.readlines()
        pos = f.tell()
    if not lines:
        save_pos(pos); return

    out_lines=[]
    for ln in lines:
        if "ALLOW" in ln.upper() or "[EDGE]" in ln:
            mE = EDGE_RX.search(ln)
            if not mE: continue
            msg = mE.group('msg')
            vals = parse_vals(ln + " " + msg)
            entry_type = "MR" if "MR" in msg.upper() else ("BO" if "BO" in msg.upper() else "GEN")
            ts = ln[:19] if re.match(r'^\d{4}-\d{2}-\d{2} ', ln) else now_utc()
            out_lines.append(f'{ts},{entry_type},{vals["adx"]},{vals["rsi"]},{vals["gap"]},{vals["last"]},{vals["vwap"]},{vals["uptrend"]},{msg.strip()}')

    if out_lines:
        with OUT.open('a', encoding='utf-8') as g:
            for x in out_lines:
                g.write(x+"\n")
    save_pos(pos)

if __name__ == "__main__":
    main()
