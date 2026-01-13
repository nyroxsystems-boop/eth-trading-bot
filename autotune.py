#!/usr/bin/env python3
# liest trades.csv, passt size_mult-Profil andeutungsweise um ±10% an (super konservativ)
import json, pathlib, time
ROOT=pathlib.Path("/root/ethbot"); LOG=ROOT/"logs/trades.csv"; HINT=ROOT/"state/profile_hint.json"
if not LOG.exists(): 
    print("[TUNE] no trades.csv"); raise SystemExit(0)
wins=loss=0
for i,ln in enumerate(LOG.read_text().strip().splitlines()):
    if i==0: continue
    _,action,qty,price = ln.split(",")[:4]
    # sehr grobe Heuristik: SELL nach BUY als Gewinn annehmen, sonst ignorieren
    if action=="SELL": wins+=1
    elif action=="BUY": loss+=0
adj=0.0
if wins+loss>=10:
    wr=wins/max(1,(wins+loss))
    if wr>=0.65: adj=+0.1
    elif wr<=0.45: adj=-0.1
# schreibe nur eine Richtungs-Empfehlung; Regime-Loader kann das berücksichtigen
D={"size_adj":adj,"ts":int(time.time())}
(ROOT/"state/auto_tune.json").write_text(json.dumps(D))
print("[TUNE]",D)
