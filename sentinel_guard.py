#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, shutil, subprocess, re, pathlib
from datetime import datetime, timezone
from telegram_notify import send

ROOT=pathlib.Path("/root/ethbot")
LOG =ROOT/"logs"/"sentinel_guard.log"
ENVF=ROOT/".env.bot"

TERMS_NEG = ["crash","selloff","halt","liquidation","rug","bankrupt","panic","dump","meltdown"]
TERMS_ETH = ["ETH","Ethereum","crypto","altcoin"]

def log(msg):
    ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line=f"{ts} [SENTINEL] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG,"a",encoding="utf-8") as f: f.write(line+"\n")

def have_snscrape(): return shutil.which("snscrape") is not None

def env(k, d=""): 
    if not ENVF.exists(): return d
    for ln in ENVF.read_text().splitlines():
        if "=" in ln and not ln.strip().startswith("#"):
            kk,v=ln.split("=",1)
            if kk.strip()==k: return v.strip()
    return d

def fetch(n=120):
    q = "(ETH OR Ethereum OR crypto) lang:en"
    cmd=f"snscrape --max-results {n} twitter-search '{q}'"
    r=subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=45)
    return r.stdout.splitlines()

def score(lines):
    text=" ".join(lines).lower()
    neg=sum(1 for t in TERMS_NEG if t in text)
    eth=sum(1 for t in TERMS_ETH if t in text)
    return neg, eth, len(lines)

def maybe_restart():
    if env("SENTINEL_KILL","0")!="1": 
        return False
    subprocess.run("systemctl restart ethbot", shell=True, timeout=20)
    return True

def main():
    if env("TWITTER_SENTIMENT","0")!="1":
        log("disabled")
        return 0
    if not have_snscrape():
        log("snscrape missing")
        return 0
    lines=fetch(150)
    neg, eth, total = score(lines)
    trig = (neg>=3 and eth>=2)  # simple anomaly tripwire
    log(f"scan total={total} neg={neg} eth={eth} trigger={trig}")
    if trig:
        send(f"🚨 Market anomaly detected (neg={neg}, eth={eth}). Guard tightening / pause suggested.")
        maybe_restart()
    return 0

if __name__=="__main__":
    raise SystemExit(main())
