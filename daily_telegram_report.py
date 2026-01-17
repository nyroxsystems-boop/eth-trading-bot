#!/usr/bin/env python3
"""
ETH Trading Bot - Enhanced Daily Telegram Report
Sends a beautiful formatted summary of trading performance to Telegram.

Features:
- Daily P&L overview with emoji indicators
- Win rate with visual progress bar
- Best/worst trade highlights
- Trading mode indicator
- Market sentiment and technical indicators
- Weekly trend sparkline
"""

import os
import csv
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Configuration
PROJECT_ROOT = Path(__file__).parent
LOGS_DIR = Path(os.getenv("LOG_DIR", PROJECT_ROOT / "logs"))
TRADES_CSV = LOGS_DIR / "trades.csv"
SENTIMENT_CACHE = PROJECT_ROOT / "cache" / "sentiment.json"
CONSOLE_LOG = LOGS_DIR / "console.out"

# Telegram settings
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def load_trades(days: int = 7) -> List[Dict]:
    """Load trades from CSV for the specified number of days."""
    if not TRADES_CSV.exists():
        return []
    
    trades = []
    cutoff = datetime.now() - timedelta(days=days)
    
    try:
        with open(TRADES_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff:
                        trades.append({
                            "timestamp": ts,
                            "action": row["action"].upper(),
                            "qty": float(row["qty"]),
                            "price": float(row["price"]),
                            "mode": row.get("mode", "DRY")
                        })
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        print(f"Error loading trades: {e}")
    
    return trades


def calculate_metrics(trades: List[Dict]) -> Dict:
    """Calculate performance metrics from trades."""
    if not trades:
        return {
            "total_trades": 0,
            "complete_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_entry": 0.0,
            "avg_exit": 0.0,
            "mode": "DRY"
        }
    
    buys = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]
    
    pnls = []
    for i in range(min(len(buys), len(sells))):
        pnl = (sells[i]["price"] - buys[i]["price"]) * buys[i]["qty"]
        pnls.append(pnl)
    
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    
    return {
        "total_trades": len(trades),
        "complete_trades": len(pnls),
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / len(pnls) * 100) if pnls else 0.0,
        "total_pnl": sum(pnls),
        "best_trade": max(pnls) if pnls else 0.0,
        "worst_trade": min(pnls) if pnls else 0.0,
        "avg_entry": sum(b["price"] for b in buys) / len(buys) if buys else 0.0,
        "avg_exit": sum(s["price"] for s in sells) / len(sells) if sells else 0.0,
        "mode": trades[0]["mode"] if trades else "DRY"
    }


def load_sentiment() -> Tuple[Optional[float], str]:
    """Load sentiment score from cache."""
    try:
        if SENTIMENT_CACHE.exists():
            with open(SENTIMENT_CACHE) as f:
                data = json.load(f)
            score = float(data.get("score", 0.0))
            if score > 0.15:
                return score, "🟢 Bullish"
            elif score < -0.15:
                return score, "🔴 Bearish"
            else:
                return score, "⚪ Neutral"
    except Exception:
        pass
    return None, "⚪ n/a"


def get_market_indicators() -> Dict:
    """Parse latest market indicators from console log."""
    if not CONSOLE_LOG.exists():
        return {"px": "n/a", "adx": "n/a", "rsi": "n/a"}
    
    try:
        with open(CONSOLE_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 100_000))
            content = f.read().decode("utf-8", "ignore")
        
        import re
        pattern = r"INFO\s+px=([0-9.]+)\s+adx=([0-9.]+)\s+rsi=([0-9.]+)"
        matches = list(re.finditer(pattern, content))
        
        if matches:
            last = matches[-1]
            return {
                "px": round(float(last.group(1)), 2),
                "adx": round(float(last.group(2)), 1),
                "rsi": round(float(last.group(3)), 1)
            }
    except Exception:
        pass
    
    return {"px": "n/a", "adx": "n/a", "rsi": "n/a"}


def create_progress_bar(value: float, max_val: float = 100, width: int = 10) -> str:
    """Create a visual progress bar using emoji blocks."""
    filled = int((value / max_val) * width)
    filled = max(0, min(width, filled))
    empty = width - filled
    return "█" * filled + "░" * empty


def format_pnl(pnl: float) -> str:
    """Format P&L with appropriate emoji."""
    if pnl > 0:
        return f"🟢 +${pnl:.2f}"
    elif pnl < 0:
        return f"🔴 -${abs(pnl):.2f}"
    else:
        return "⚪ $0.00"


def create_daily_report(days: int = 1) -> str:
    """Create a beautifully formatted daily report."""
    now = datetime.now()
    trades = load_trades(days=days)
    metrics = calculate_metrics(trades)
    sentiment_score, sentiment_label = load_sentiment()
    indicators = get_market_indicators()
    
    # Mode indicator
    if metrics["mode"] == "LIVE":
        mode_badge = "⚡ LIVE"
    else:
        mode_badge = "📄 PAPER"
    
    # Win rate bar
    win_bar = create_progress_bar(metrics["win_rate"], 100, 10)
    
    # Trend emoji
    if metrics["total_pnl"] > 50:
        trend = "📈"
    elif metrics["total_pnl"] < -50:
        trend = "📉"
    else:
        trend = "➡️"
    
    report = f"""
<b>🤖 ETH Trading Bot Report</b>
━━━━━━━━━━━━━━━━━━━
<code>{now.strftime('%Y-%m-%d %H:%M UTC')}</code>

<b>📊 Performance ({days}d)</b>
┌────────────────────
│ Trades:    <b>{metrics['complete_trades']}</b>
│ Win Rate:  <b>{metrics['win_rate']:.1f}%</b> {win_bar}
│ Total P&L: {format_pnl(metrics['total_pnl'])} {trend}
└────────────────────

<b>💎 Trade Highlights</b>
┌────────────────────
│ Best:  {format_pnl(metrics['best_trade'])}
│ Worst: {format_pnl(metrics['worst_trade'])}
│ Avg Entry: ${metrics['avg_entry']:.2f}
└────────────────────

<b>🌐 Market Status</b>
┌────────────────────
│ ETH: ${indicators['px']}
│ ADX: {indicators['adx']} | RSI: {indicators['rsi']}
│ Sentiment: {sentiment_label}
└────────────────────

<i>Mode: {mode_badge}</i>
""".strip()
    
    return report


def create_trade_alert(action: str, price: float, qty: float, pnl: Optional[float] = None) -> str:
    """Create a trade execution alert message."""
    now = datetime.now().strftime("%H:%M:%S")
    
    if action.upper() == "BUY":
        emoji = "🟢"
        title = "OPENED POSITION"
    else:
        emoji = "🔴"
        title = "CLOSED POSITION"
    
    msg = f"""
{emoji} <b>{title}</b>
━━━━━━━━━━━━━
<code>{now}</code>

<b>Action:</b> {action.upper()}
<b>Price:</b> ${price:.2f}
<b>Size:</b> {qty:.4f} ETH
<b>Value:</b> ${price * qty:.2f}
"""
    
    if pnl is not None:
        msg += f"\n<b>P&L:</b> {format_pnl(pnl)}"
    
    return msg.strip()


def send_telegram(message: str, parse_mode: str = "HTML") -> bool:
    """Send message to Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️  Telegram not configured (missing BOT_TOKEN or CHAT_ID)")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    
    try:
        resp = requests.post(url, json=data, timeout=15)
        if resp.status_code == 200:
            print("✅ Telegram message sent successfully")
            return True
        else:
            print(f"❌ Telegram send failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def send_daily_report(days: int = 1) -> bool:
    """Send the daily summary report."""
    report = create_daily_report(days=days)
    return send_telegram(report)


def send_weekly_report() -> bool:
    """Send the weekly summary report."""
    report = create_daily_report(days=7)
    return send_telegram(report)


def send_trade_notification(action: str, price: float, qty: float, pnl: Optional[float] = None) -> bool:
    """Send a trade execution notification."""
    alert = create_trade_alert(action, price, qty, pnl)
    return send_telegram(alert)


# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ETH Bot Telegram Notifications")
    parser.add_argument("--daily", action="store_true", help="Send daily report")
    parser.add_argument("--weekly", action="store_true", help="Send weekly report")
    parser.add_argument("--preview", action="store_true", help="Preview report without sending")
    parser.add_argument("--days", type=int, default=1, help="Number of days for report")
    
    args = parser.parse_args()
    
    if args.preview:
        print("\n" + "="*50)
        print("PREVIEW (not sending):")
        print("="*50)
        print(create_daily_report(days=args.days))
        print("="*50)
    elif args.weekly:
        send_weekly_report()
    elif args.daily:
        send_daily_report(days=args.days)
    else:
        # Default: show preview
        print("Usage: python daily_telegram_report.py --daily|--weekly|--preview")
        print("\nCurrent report preview:")
        print(create_daily_report(days=1))
