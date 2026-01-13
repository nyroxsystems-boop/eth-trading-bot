#!/usr/bin/env python3
import csv, pathlib, time, json

ROOT = pathlib.Path("/root/ethbot")
TRADES = ROOT / "logs" / "trades.csv"
OUT = ROOT / "cache" / "auto_params.json"

def load_trades():
    rows=[]
    if not TRADES.exists():
        return rows
    with TRADES.open() as f:
        rd = csv.DictReader(f)
        for r in rd:
            # expected: timestamp,action,qty,price[,pnl]
            rows.append(r)
    return rows

def compute_suggestions(trades):
    # sehr simpel: count SELL minus BUY und grobe PnL-Erkennung falls Spalte existiert
    pnl_sum=0.0; wins=0; losses=0; sells=0
    for r in trades[-200:]:
        if r.get("action","").upper()=="SELL":
            sells += 1
            try:
                pnl = float(r.get("pnl", "0") or 0)
                pnl_sum += pnl
                if pnl > 0: wins += 1
                elif pnl < 0: losses += 1
            except Exception:
                pass
    winrate = (wins / max(1, wins+losses))
    # sanfte Heuristik für Vorschläge (nur Empfehlungen, kein Auto-Overwrite)
    rec = {}
    if sells >= 8:
        if winrate < 0.45:
            rec["adx_min_delta"] = +2.0     # strengerer Trendfilter
            rec["near_break_tighten"] = True
        elif pnl_sum > 0 and winrate >= 0.55:
            rec["tp_stretch_hint"] = +0.002 # TP leicht strecken
    return {
        "generated_at": int(time.time()),
        "window_sells": sells,
        "winrate_est": round(winrate, 3),
        "pnl_sum_est": round(pnl_sum, 2),
        "suggestions": rec
    }

def main():
    trades = load_trades()
    data = compute_suggestions(trades)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print("[AUTOTUNE] suggestions written:", data)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
