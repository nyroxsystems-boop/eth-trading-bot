#!/usr/bin/env python3
"""
Inject test strategies into learning.db for dashboard testing.

Usage:
    python tools/inject_test_strategies.py [--overwrite] [--num-strategies 20]
"""

import os
import random
import sqlite3
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Determine log directory
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LEARNING_DB = LOG_DIR / "learning.db"


def create_strategies_table(conn):
    """Create the strategies table if it doesn't exist"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ml_threshold REAL NOT NULL,
            risk_per_trade REAL NOT NULL,
            tp_min REAL NOT NULL,
            tp_max REAL NOT NULL,
            stop_floor REAL NOT NULL,
            max_trades_per_day INTEGER NOT NULL,
            total_trades INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            roi REAL NOT NULL,
            sharpe_ratio REAL NOT NULL,
            max_drawdown REAL NOT NULL,
            score REAL NOT NULL,
            timestamp TEXT NOT NULL,
            applied INTEGER DEFAULT 0,
            applied_at TEXT
        )
    """)
    conn.commit()
    print(f"✅ Created/verified strategies table in {LEARNING_DB}")


def generate_random_strategy(days_ago: int = 0) -> dict:
    """Generate a random strategy with realistic parameters"""
    
    # Random parameters
    ml_threshold = round(random.uniform(0.30, 0.55), 3)
    risk_per_trade = round(random.uniform(0.004, 0.012), 4)
    tp_min = round(random.uniform(0.008, 0.015), 3)
    tp_max = round(random.uniform(tp_min, 0.025), 3)
    stop_floor = round(random.uniform(0.003, 0.008), 3)
    max_trades_per_day = random.randint(5, 20)
    
    # Simulate metrics based on parameters
    # Better ML threshold = higher win rate
    base_win_rate = 45 + (ml_threshold - 0.30) * 100  # 45-70%
    win_rate = min(85, max(40, base_win_rate + random.uniform(-10, 10)))
    
    # ROI depends on win rate and TP
    avg_tp = (tp_min + tp_max) / 2
    roi = (win_rate / 100 * avg_tp - (1 - win_rate/100) * stop_floor) * 100 * random.uniform(0.8, 1.5)
    roi = round(roi, 2)
    
    # Total trades
    total_trades = random.randint(20, 150)
    
    # Sharpe ratio (higher with higher win rate)
    sharpe_ratio = round(random.uniform(0.5, 2.5) * (win_rate / 60), 2)
    
    # Max drawdown
    max_drawdown = round(random.uniform(3, 15), 2)
    
    # Composite score (weighted sum)
    score = round(
        win_rate * 0.3 + 
        roi * 2 + 
        sharpe_ratio * 10 - 
        max_drawdown * 0.5,
        2
    )
    
    # Timestamp
    timestamp = (datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(0, 23))).strftime("%Y-%m-%d %H:%M:%S")
    
    return {
        "ml_threshold": ml_threshold,
        "risk_per_trade": risk_per_trade,
        "tp_min": tp_min,
        "tp_max": tp_max,
        "stop_floor": stop_floor,
        "max_trades_per_day": max_trades_per_day,
        "total_trades": total_trades,
        "win_rate": round(win_rate, 1),
        "roi": roi,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "score": score,
        "timestamp": timestamp,
        "applied": 0,
        "applied_at": None
    }


def insert_strategies(conn, num_strategies: int = 20):
    """Insert sample strategies into the database"""
    cursor = conn.cursor()
    
    strategies = []
    
    # Generate strategies over the last 7 days
    for i in range(num_strategies):
        days_ago = i % 7  # Distribute across 7 days
        strategy = generate_random_strategy(days_ago)
        strategies.append(strategy)
    
    # Sort by score descending
    strategies.sort(key=lambda x: x["score"], reverse=True)
    
    # Mark the best strategy as applied
    strategies[0]["applied"] = 1
    strategies[0]["applied_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # Insert all strategies
    for s in strategies:
        cursor.execute("""
            INSERT INTO strategies (
                ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                total_trades, win_rate, roi, sharpe_ratio, max_drawdown, score, timestamp, applied, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["ml_threshold"], s["risk_per_trade"], s["tp_min"], s["tp_max"], 
            s["stop_floor"], s["max_trades_per_day"], s["total_trades"],
            s["win_rate"], s["roi"], s["sharpe_ratio"], s["max_drawdown"],
            s["score"], s["timestamp"], s["applied"], s["applied_at"]
        ))
    
    conn.commit()
    return strategies


def main():
    parser = argparse.ArgumentParser(description="Inject test strategies into learning.db")
    parser.add_argument("--overwrite", action="store_true", help="Delete existing strategies before inserting")
    parser.add_argument("--num-strategies", "-n", type=int, default=25, help="Number of strategies to generate")
    args = parser.parse_args()
    
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"📂 Using database: {LEARNING_DB}")
    
    # Connect to database
    conn = sqlite3.connect(LEARNING_DB)
    
    # Create table
    create_strategies_table(conn)
    
    # Optionally clear existing data
    if args.overwrite:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM strategies")
        conn.commit()
        print("🗑️  Cleared existing strategies")
    
    # Insert strategies
    print(f"🧠 Generating {args.num_strategies} strategies...")
    strategies = insert_strategies(conn, args.num_strategies)
    
    # Summary
    best = strategies[0]
    print("\n📊 Generated Strategy Summary:")
    print(f"   Total Strategies: {len(strategies)}")
    print(f"   Best Score: {best['score']}")
    print(f"   Best Win Rate: {best['win_rate']}%")
    print(f"   Best ROI: {best['roi']}%")
    print(f"   Applied Strategy: ID 1 (Score: {best['score']})")
    
    # Show distribution
    today = sum(1 for s in strategies if "today" in s["timestamp"] or datetime.utcnow().strftime("%Y-%m-%d") in s["timestamp"])
    this_hour = sum(1 for s in strategies if datetime.utcnow().strftime("%Y-%m-%d %H") in s["timestamp"])
    print(f"\n   Today: ~{len(strategies) // 7} strategies")
    print("   Applied: 1 strategy")
    
    conn.close()
    print(f"\n✅ Done! Strategies saved to {LEARNING_DB}")
    print("\n🔗 Test with: curl -s 'http://localhost:8000/api/learning/stats' | jq .")


if __name__ == "__main__":
    main()
