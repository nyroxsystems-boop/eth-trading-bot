#!/usr/bin/env python3
import csv, pathlib, os, json, statistics, subprocess, time
ROOT = pathlib.Path("/root/ethbot")
TRADES = ROOT/"logs/trades.csv"
CACHE = ROOT/"cache"; CACHE.mkdir(exist_ok=True, parents=True)
SUG = CACHE/"tune_suggest.json"
ENV = ROOT/".env.bot"

def load_trades(n=200):
    rows=[]
    if not TRADES.exists(): return rows
    with TRADES.open() as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)[-n:]
    return rows

def pnl_stats(rows):
    pnls=[]
    for r in rows:
        # optional: if your csv has realized pnl, replace this line
        # fallback: skip if missing
        if 'pnl' in r and r['pnl']:
            pnls.append(float(r['pnl']))
    if not pnls: return {"count":0,"winrate":0.0,"avg":0.0}
    wins = sum(1 for x in pnls if x>0)
    return {
        "count": len(pnls),
        "winrate": wins/len(pnls),
        "avg": statistics.mean(pnls)
    }

def sed_update(var, value):
    if not ENV.exists(): return
    txt = ENV.read_text()
    import re
    if re.search(rf'^{var}=', txt, flags=re.M):
        txt = re.sub(rf'^{var}=.*', f'{var}={value}', txt, flags=re.M)
    else:
        txt += f'\n{var}={value}\n'
    ENV.write_text(txt)

def main():
    rows = load_trades()
    stats = pnl_stats(rows)
    suggest = {"ts": int(time.time()), "stats": stats, "actions": []}

    # Heuristics (conservative)
    if stats["count"] >= 20:
        if stats["winrate"] < 0.45:
            suggest["actions"].append({"set":"FOCUS_MODE","to":0,"why":"winrate<45%, strenger filtern"})
            suggest["actions"].append({"set":"MAX_TRADES","to":3,"why":"drosseln"})
        elif stats["winrate"] > 0.58:
            suggest["actions"].append({"set":"FOCUS_MODE","to":1,"why":"gute Phase -> leicht aggressiver"})
            suggest["actions"].append({"set":"MAX_TRADES","to":6,"why":"etwas steigern"})
    else:
        suggest["actions"].append({"note":"zu wenige Trades für valides Tuning"})

    SUG.write_text(json.dumps(suggest, ensure_ascii=False, indent=2))

    if os.getenv("AUTOTUNE_APPLY","0") == "1":
        for act in suggest["actions"]:
            if "set" in act and "to" in act:
                sed_update(act["set"], act["to"])
        subprocess.run("systemctl restart ethbot", shell=True, timeout=10)

if __name__ == "__main__":
    main()
