#!/usr/bin/env python3
import os, json, time, math, re, pathlib
ROOT=pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent))); LOG=ROOT/"logs/console.out"; OUT=ROOT/"state/profile_hint.json"
def pick(adx: float, rsi: float, last: float, highN: float) -> str:
    if adx is None: return "mr"
    # einfacher, robuster Heuristikmix
    near_break = (last is not None and highN and last >= highN*0.9990)
    if adx >= 20.0 or near_break: return "trend"
    if rsi and (45.0 <= rsi <= 58.0): return "mr"
    return "mr"
def parse_tail(n=600):
    adx=rsi=last=highN=None
    if not LOG.exists(): return adx,rsi,last,highN
    rx_adx=re.compile(r"adx=([0-9]+(?:\.[0-9]+)?)"); rx_rsi=re.compile(r"rsi=([0-9]+(?:\.[0-9]+)?)")
    rx_px =re.compile(r"px=([0-9]+(?:\.[0-9]+)?)")
    pxs=[]
    with open(LOG,"r",encoding="utf-8",errors="ignore") as f:
        lines=f.readlines()[-n:]
    for ln in lines:
        if "INFO px=" not in ln: continue
        ma=rx_adx.search(ln); mr=rx_rsi.search(ln); mp=rx_px.search(ln)
        if mp: 
            v=float(mp.group(1)); pxs.append(v); last=v
        if ma: adx=float(ma.group(1))
        if mr: rsi=float(mr.group(1))
    if len(pxs)>=20: highN=max(pxs[-20:])
    return adx,rsi,last,highN
def main():
    mode=os.getenv("PROFILE_MODE","auto")
    adx,rsi,last,highN=parse_tail()
    prof="mr" if mode=="mr" else "trend" if mode=="trend" else pick(adx,rsi,last,highN)
    OUT.write_text(json.dumps({"profile":prof,"ts":int(time.time())}))
    print(f"[REGIME] profile={prof} adx={adx} rsi={rsi} last={last} highN={highN}")
if __name__=="__main__": main()
