#!/usr/bin/env python3
import csv, pathlib, datetime as dt, math, os
from tools.notify import send

ROOT = pathlib.Path(os.getenv("ETHBOT_ROOT", str(pathlib.Path(__file__).resolve().parent)))
TRADES = ROOT/"logs"/"trades.csv"

def today_utc_range():
    # Compute Berlin day in UTC so “today” is Europe/Berlin
    # Berlin = UTC+1 (CET) in winter, UTC+2 (CEST) in summer — we assume server on UTC.
    # We’ll read all trades and filter by local (Berlin) date from timestamp string if present.
    # Fallback: naive split by ' ' and take date part.
    start = dt.datetime.utcnow().date()  # UTC date
    return start

def parse_ts_date(ts: str):
    # expects "YYYY-MM-DD HH:MM:SS"
    try: return ts.split(" ")[0]
    except: return ""

def fifo_pnl(trades):
    """Simple FIFO on today's trades only: match SELLs against earlier BUYs from the same day.
       If your bot carries positions overnight, this stays conservative for the day report."""
    buys = []  # list of [qty_remaining, price]
    realized = 0.0
    wins = 0; losses = 0; sells = 0
    vol = 0.0
    for t in trades:
        side = t["action"].upper()
        qty  = float(t.get("qty","0") or 0)
        px   = float(t.get("price","0") or 0)
        if qty <= 0 or px <= 0: 
            continue
        if side == "BUY":
            buys.append([qty, px])
            vol += qty * px
        elif side == "SELL":
            sells += 1
            sell_qty = qty
            pnl_this = 0.0
            while sell_qty > 1e-12 and buys:
                q0, p0 = buys[0]
                use = min(q0, sell_qty)
                pnl_this += (px - p0) * use
                q0 -= use; sell_qty -= use
                if q0 <= 1e-12: buys.pop(0)
                else: buys[0][0] = q0
            realized += pnl_this
            if pnl_this >= 0: wins += 1
            else: losses += 1
            vol += qty * px
    winrate = (wins / sells * 100.0) if sells else 0.0
    return realized, sells, wins, losses, vol

def load_today():
    if not TRADES.exists():
        return []
    rows = []
    berlin_today = dt.datetime.now(dt.timezone(dt.timedelta(hours=1))).date()  # CET default
    with TRADES.open() as f:
        r = csv.DictReader(f)
        for t in r:
            d = parse_ts_date(t.get("timestamp",""))
            if not d: continue
            try:
                y,m,dd = map(int, d.split("-"))
                local_d = dt.date(y,m,dd)  # timestamps already local in your log; if UTC adjust here
            except:
                continue
            if local_d == berlin_today:
                rows.append(t)
    return rows

def main():
    rows = load_today()
    realized, sells, wins, losses, vol = fifo_pnl(rows)
    sign = "🟢" if realized >= 0 else "🔴"
    msg = (
        f"💰 <b>Daily PnL (Berlin Today)</b>\n"
        f"{sign} Realized: {realized:+.2f} USDT\n"
        f"📊 Trades: {sells}  |  Winrate: {(wins:=wins if (wins:=wins) else wins)*0+ (wins/ max(1,sells)*100 if sells else 0):.1f}%\n"
        f"📦 Notional Turnover: {vol:.2f}\n"
        f"🕒 Cutoff: 17:00 Europe/Berlin\n"
    )
    send(msg)

if __name__ == "__main__":
    main()
