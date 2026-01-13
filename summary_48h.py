#!/usr/bin/env python3
import csv, sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

CSV = Path("/root/ethbot/logs/trades.csv")
NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(hours=48)

# toleranter Zeitparser
FMTS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"]
def parse_ts(s: str):
    s = (s or "").strip()
    if not s: return None
    for f in FMTS:
        try:
            dt = datetime.strptime(s, f)
            # als UTC auffassen, falls tz-los
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None

def read_rows():
    if not CSV.exists():
        return []
    rows = []
    with CSV.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        # fehlende Spalten abfangen
        fields = {k.lower(): k for k in r.fieldnames or []}
        # Aliase
        k_ts = fields.get("timestamp", "timestamp")
        k_ac = fields.get("action", "action")
        k_q  = fields.get("qty", "qty")
        k_p  = fields.get("price", "price")
        k_m  = fields.get("mode", "mode")
        for line in r:
            try:
                ts  = parse_ts(line.get(k_ts, ""))
                act = (line.get(k_ac, "") or "").strip().upper()
                qty = float((line.get(k_q, "") or "0").strip())
                prc = float((line.get(k_p, "") or "0").strip())
                mode= (line.get(k_m, "") or "DRY").strip().upper()
                # harte Filter: brauchbare Zeilen + Preis/Qty > 0 + ts vorhanden
                if not ts or qty <= 0 or prc <= 0 or act not in ("BUY","SELL"):
                    continue
                rows.append({"ts": ts, "action": act, "qty": qty, "price": prc, "mode": mode})
            except Exception:
                # defekte Zeile still überspringen
                continue
    return rows

def within_48h(rows):
    return [r for r in rows if r["ts"] >= SINCE]

def pair_pnl(rows48):
    """Simple FIFO-Pairing BUY -> nächster SELL; gleiche qty wird gepaart.
       Überschüssige Teilmengen werden entsprechend geteilt."""
    buys = []
    trades = []
    for r in sorted(rows48, key=lambda x: x["ts"]):
        if r["action"] == "BUY":
            buys.append({"qty": r["qty"], "price": r["price"], "ts": r["ts"], "mode": r["mode"]})
        else:  # SELL
            sell_qty = r["qty"]; sell_p = r["price"]
            while sell_qty > 1e-12 and buys:
                b = buys[0]
                take = min(b["qty"], sell_qty)
                pnl = (sell_p - b["price"]) * take
                trades.append({
                    "buy_ts": b["ts"], "sell_ts": r["ts"],
                    "qty": take, "buy_p": b["price"], "sell_p": sell_p,
                    "pnl": pnl, "mode": b["mode"]
                })
                b["qty"] -= take
                sell_qty -= take
                if b["qty"] <= 1e-12:
                    buys.pop(0)
    return trades

def summarize(trades):
    n = len(trades)
    pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    winrate = (wins / n) if n else 0.0
    return n, winrate, pnl

def main():
    rows = read_rows()
    rows48 = within_48h(rows)
    trades = pair_pnl(rows48)
    n, wr, pnl = summarize(trades)
    print(f"48h: trades={n} winrate={wr:.2f} pnl_usd={pnl:.2f}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"(summary error: {e})", file=sys.stderr)
        sys.exit(2)
