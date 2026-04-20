#!/usr/bin/env python3
"""
Test Trade Data Injector
Generates realistic simulated trade data for testing dashboard and learning systems.
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
TRADES_CSV = PROJECT_ROOT / "logs" / "trades.csv"

# Trade parameters
ETH_PRICE_BASE = 3300  # Current approximate ETH price
ETH_PRICE_VOLATILITY = 100  # ±100 USD volatility
WIN_RATE = 0.65  # 65% winning trades
AVG_TRADE_QTY = 0.5  # Average trade size in ETH
QTY_VARIANCE = 0.3  # ±30% variance in quantity


def generate_test_trades(
    num_trades: int = 30,
    start_date: datetime = None,
    mode: str = "DRY"
) -> list:
    """
    Generate realistic test trade data.
    
    Returns list of trade dicts ready for CSV export.
    """
    if start_date is None:
        start_date = datetime.now() - timedelta(days=7)
    
    trades = []
    current_time = start_date
    position_open = False
    entry_price = 0.0
    entry_qty = 0.0
    entry_time = None
    
    total_pnl = 0.0
    wins = 0
    losses = 0
    
    for i in range(num_trades):
        # Add random time between trades (1-6 hours)
        current_time += timedelta(hours=random.uniform(1, 6))
        
        # Generate base price with trend
        trend = random.uniform(-0.002, 0.003)  # Slight upward bias
        base_price = ETH_PRICE_BASE + (i * ETH_PRICE_VOLATILITY * trend)
        price = round(base_price + random.uniform(-ETH_PRICE_VOLATILITY, ETH_PRICE_VOLATILITY), 2)
        
        # Generate quantity
        qty_mult = 1 + random.uniform(-QTY_VARIANCE, QTY_VARIANCE)
        qty = round(AVG_TRADE_QTY * qty_mult, 6)
        
        if not position_open:
            # Open position (BUY)
            trades.append({
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "action": "BUY",
                "qty": qty,
                "price": price,
                "mode": mode
            })
            position_open = True
            entry_price = price
            entry_qty = qty
            entry_time = current_time
        else:
            # Close position (SELL)
            # Determine if this is a winning trade based on WIN_RATE
            is_win = random.random() < WIN_RATE
            
            if is_win:
                # Winning trade: price goes up 0.5-2%
                sell_price = round(entry_price * (1 + random.uniform(0.005, 0.02)), 2)
                wins += 1
            else:
                # Losing trade: price goes down 0.3-1.5%
                sell_price = round(entry_price * (1 - random.uniform(0.003, 0.015)), 2)
                losses += 1
            
            pnl = (sell_price - entry_price) * entry_qty
            total_pnl += pnl
            
            trades.append({
                "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "action": "SELL",
                "qty": entry_qty,
                "price": sell_price,
                "mode": mode
            })
            position_open = False
    
    # Close any remaining open position
    if position_open:
        current_time += timedelta(hours=1)
        sell_price = round(entry_price * (1 + random.uniform(-0.01, 0.01)), 2)
        trades.append({
            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": "SELL",
            "qty": entry_qty,
            "price": sell_price,
            "mode": mode
        })
    
    print("\n📊 Generated Trade Summary:")
    print(f"   Total Trades: {len(trades)}")
    print(f"   Wins: {wins} | Losses: {losses}")
    print(f"   Win Rate: {(wins/(wins+losses)*100):.1f}%" if (wins+losses) > 0 else "   Win Rate: N/A")
    print(f"   Total PnL: ${total_pnl:.2f}")
    print(f"   Mode: {mode}")
    
    return trades


def inject_trades(trades: list, append: bool = True):
    """Write trades to CSV file."""
    TRADES_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    file_exists = TRADES_CSV.exists() and TRADES_CSV.stat().st_size > 0
    mode = "a" if (append and file_exists) else "w"
    
    with open(TRADES_CSV, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "action", "qty", "price", "mode"])
        
        if mode == "w" or not file_exists:
            writer.writeheader()
        
        for trade in trades:
            writer.writerow(trade)
    
    print(f"\n✅ Wrote {len(trades)} trades to {TRADES_CSV}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate test trade data")
    parser.add_argument("-n", "--num-trades", type=int, default=40, 
                        help="Number of trades to generate (default: 40)")
    parser.add_argument("-d", "--days-back", type=int, default=7,
                        help="Start date days back from now (default: 7)")
    parser.add_argument("-m", "--mode", choices=["DRY", "LIVE"], default="DRY",
                        help="Trading mode (default: DRY)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing trades.csv instead of appending")
    
    args = parser.parse_args()
    
    start_date = datetime.now() - timedelta(days=args.days_back)
    
    print(f"🔧 Generating {args.num_trades} test trades...")
    print(f"   Start date: {start_date.strftime('%Y-%m-%d %H:%M')}")
    
    trades = generate_test_trades(
        num_trades=args.num_trades,
        start_date=start_date,
        mode=args.mode
    )
    
    inject_trades(trades, append=not args.overwrite)
    
    print("\n🎉 Done! Dashboard should now show trade data.")


if __name__ == "__main__":
    main()
