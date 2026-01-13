import json, pathlib, time
ROOT=pathlib.Path("/root/ethbot"); F=ROOT/"state/state.json"
def load():
    try: return json.loads(F.read_text())
    except: return {"ts":int(time.time()),"open":None}
def save(st):
    st["ts"]=int(time.time()); F.write_text(json.dumps(st))
def reconcile_from_trades():
    # Falls letztes Event BUY ohne SELL -> markiere als offen (vereinfachte Heuristik)
    T=ROOT/"logs/trades.csv"
    if not T.exists(): return None
    last=None
    for ln in T.read_text().strip().splitlines()[1:]:
        ts,action,qty,price = ln.split(",")[:4]
        last=(ts,action,qty,price)
    if last and last[1]=="BUY":
        return {"entry": float(last[3]), "qty": float(last[2]), "open_bar_time": last[0]}
    return None
