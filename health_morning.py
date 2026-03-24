#!/usr/bin/env python3
import os, subprocess, pathlib, json, time, csv
from tools.notify import send
ROOT=pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))

def sh(cmd): return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def last_px_line():
    p=ROOT/"logs"/"console.out"
    if not p.exists(): return "(no console)"
    for ln in reversed(p.read_text(errors="ignore").splitlines()[-800:]):
        if "px=" in ln: return ln
    return "(no px line found)"

def last_trades(n=5):
    p=ROOT/"logs"/"trades.csv"
    out=[]
    if p.exists():
        rows=list(csv.DictReader(p.open()))
        for r in rows[-n:]:
            out.append(f"{r.get('timestamp','?')} {r.get('action','?')} qty={r.get('qty','?')} px={r.get('price','?')}")
    return out

def flags():
    d=ROOT/"flags"
    if not d.exists(): return []
    return sorted([x.name for x in d.glob("*.stop")])

def summary_headline():
    try:
        out = subprocess.run([str(ROOT/".venv/bin/python3"), str(ROOT/"summary_48h.py")], capture_output=True, text=True, timeout=20)
        first = out.stdout.strip().splitlines()[0:3]
        return "\n".join(first)
    except: return "(summary error)"

def main():
    svc = sh("systemctl is-active ethbot ethbot-risk.timer ethbot-feed.timer ethbot-autotune.timer ethbot-tradenotify.timer | xargs -n1 echo '-'")
    msg = f"""🩺 <b>ETHBot Health</b>
{time.strftime('%F %T UTC')}
Services:
{svc}

Last px:
{last_px_line()}

Flags:
{', '.join(flags()) or '(none)'}

Last trades:
{chr(10).join(last_trades()) or '(none)'}

48h:
{summary_headline()}
"""
    send(msg[:3900])

if __name__=="__main__": main()
