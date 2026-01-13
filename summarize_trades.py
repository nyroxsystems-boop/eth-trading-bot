# === AUTOINJECT: load .env.bot early ===
import os
from pathlib import Path
_envp = Path("/root/ethbot/.env.bot")
if _envp.exists():
    for _ln in _envp.read_text().splitlines():
        if _ln.strip() and not _ln.startswith("#") and "=" in _ln:
            _k,_v = _ln.split("=",1)
            os.environ.setdefault(_k.strip(), _v.strip())
# === END AUTOINJECT ===

#!/usr/bin/env python3
# === ETHBot Daily Report (24h) — mit Sentiment + ADX + RSI ===
import os, csv, json, re, requests
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
LOG_FILE  = "/root/ethbot/logs/trades.csv"
CONSOLE   = "/root/ethbot/logs/console.out"
SENTCACHE = "/root/ethbot/cache/sentiment.json"
OUT_FILE  = "/root/ethbot/logs/summary_daily.log"

def tg_send(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print("[warn] Telegram not configured")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True}
    r = requests.post(url, json=data, timeout=15)
    if r.status_code != 200:
        print(f"[warn] Telegram send failed: {r.text}")
        return False
    return True

def load_trades(days=2):
    trades, cutoff = [], datetime.utcnow() - timedelta(days=days)
    if not os.path.exists(LOG_FILE): return trades
    with open(LOG_FILE, newline='') as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            try:
                ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                if ts >= cutoff:
                    trades.append({"ts": ts, "action": row["action"].upper(),
                                   "qty": float(row["qty"]), "price": float(row["price"])})
            except Exception:
                continue
    return trades

def summarize_trades(trades):
    if not trades:
        return {"n": 0, "pnl_usd": 0.0, "winrate": 0.0, "avg_entry": 0.0}
    buys  = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]
    pnl, wins = 0.0, 0
    for i in range(min(len(buys), len(sells))):
        diff = sells[i]["price"] - buys[i]["price"]
        pnl += diff * buys[i]["qty"]
        if diff > 0: wins += 1
    winrate = round(100 * wins / len(sells), 1) if sells else 0.0
    avg_entry = round(sum(b["price"] for b in buys)/len(buys), 2) if buys else 0.0
    return {"n": len(trades), "pnl_usd": round(pnl, 2), "winrate": winrate, "avg_entry": avg_entry}

def load_sentiment():
    try:
        with open(SENTCACHE, "r") as f:
            d = json.load(f)
        score = float(d.get("score", 0.0))
        label = "Bullish" if score > 0.15 else ("Bearish" if score < -0.15 else "Neutral")
        return score, label
    except Exception:
        return None, "n/a"

def from_console():
    """Parse letzte ~600 Zeilen für px/adx/rsi und liefere letzte Werte + einfache Labels."""
    if not os.path.exists(CONSOLE): return None
    try:
        with open(CONSOLE, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size-200_000))
            txt = f.read().decode("utf-8", "ignore")
    except Exception:
        return None

    rx = re.compile(r"INFO\s+px=([0-9]+(?:\.[0-9]+)?)\s+adx=([0-9]+(?:\.[0-9]+)?)\s+rsi=([0-9]+(?:\.[0-9]+)?)")
    last = None
    for m in rx.finditer(txt):
        px, adx, rsi = map(float, m.groups())
        last = (px, adx, rsi)
    if not last: return None
    px, adx, rsi = last

    # Labels
    adx_lbl = "trending" if adx >= 25 else ("range" if adx < 18 else "moderate")
    if   rsi >= 70: rsi_lbl = "overbought"
    elif rsi <= 30: rsi_lbl = "oversold"
    elif rsi >= 55: rsi_lbl = "neutral-bullish"
    elif rsi <= 45: rsi_lbl = "neutral-bearish"
    else:           rsi_lbl = "neutral"
    return {"px": round(px,2), "adx": round(adx,1), "rsi": round(rsi,1),
            "adx_lbl": adx_lbl, "rsi_lbl": rsi_lbl}

def main():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    # Trades
    trades = load_trades(days=2)  # 48h zur Sicherheit (Report trotzdem "Daily")
    stats  = summarize_trades(trades)
    # Markt-Lage
    sent_score, sent_lbl = load_sentiment()
    cons = from_console() or {"px":"n/a","adx":"n/a","rsi":"n/a","adx_lbl":"n/a","rsi_lbl":"n/a"}

    mode = "LIVE" if os.getenv("DRY_RUN", "true").lower() == "false" else "DRY"
    focus = os.getenv("FOCUS_MODE", "0")

    def fmt_score(s):
        try:
            return f"{float(s):+.3f}"
        except: return "n/a"

    msg = (
        f"<b>📊 ETHBot Daily Report</b>\n"
        f"🕒 <b>{now}</b>\n\n"
        f"💰 <b>Trades:</b> {stats['n']}\n"
        f"📈 <b>Winrate:</b> {stats['winrate']}%\n"
        f"💵 <b>24h PnL:</b> ${stats['pnl_usd']:.2f}\n"
        f"⚙️ <b>Avg Entry:</b> {stats['avg_entry']}\n\n"
        f"🧠 <b>Sentiment:</b> {sent_lbl} ({fmt_score(sent_score)})\n"
        f"📊 <b>ADX:</b> {cons['adx']} ({cons['adx_lbl']})\n"
        f"💫 <b>RSI:</b> {cons['rsi']} ({cons['rsi_lbl']})\n"
        f"💵 <b>Last px:</b> {cons['px']}\n\n"
        f"<i>Mode:</i> {mode} | <i>Focus:</i> {focus}\n"
        f"— — —\n"
        f"<i>Generated automatically by ETHBot</i>"
    )

    sent_ok = tg_send(msg)
    with open(OUT_FILE, "a") as f:
        f.write(f"{datetime.utcnow().isoformat()} | sent={sent_ok} | stats={stats}\n")

if __name__ == "__main__":
    main()

# === PATCH: load .env.bot automatically ===
from pathlib import Path
import os
env_path = Path("/root/ethbot/.env.bot")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k,v = line.split("=",1)
            os.environ.setdefault(k.strip(), v.strip())
# === END PATCH ===
