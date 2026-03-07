#!/usr/bin/env python3
"""
Continuous Strategy Backtester

Runs in background, continuously testing different strategy parameter combinations
on historical ETH data and saving results to the learning database.

Target: 60-120 strategies per hour (1 every 30-60 seconds)
"""

import os
import sqlite3
import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LEARNING_DB = LOG_DIR / "learning.db"

# Strategy parameter ranges for grid search
PARAM_GRID = {
    "ml_threshold": [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65],
    "risk_per_trade": [0.004, 0.006, 0.008, 0.010, 0.012],
    "tp_min": [0.008, 0.010, 0.012, 0.015],
    "tp_max": [0.015, 0.018, 0.020, 0.025],
    "stop_floor": [0.004, 0.005, 0.006, 0.008],
    "rsi_oversold": [25, 30, 35],
    "rsi_overbought": [65, 70, 75],
    "max_trades_per_day": [8, 10, 15, 20]
}

# Global state for live progress
BACKTEST_STATE = {
    "running": False,
    "current_params": None,
    "tested_this_hour": 0,
    "last_test_time": None,
    "total_tested_today": 0,
    "best_score_today": 0,
    "last_best_strategy": None
}


def ensure_db():
    """Ensure database and table exist"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(LEARNING_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ml_threshold REAL NOT NULL,
            risk_per_trade REAL NOT NULL,
            tp_min REAL NOT NULL,
            tp_max REAL NOT NULL,
            stop_floor REAL NOT NULL,
            rsi_oversold INTEGER DEFAULT 30,
            rsi_overbought INTEGER DEFAULT 70,
            max_trades_per_day INTEGER NOT NULL,
            total_trades INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            roi REAL NOT NULL,
            sharpe_ratio REAL NOT NULL,
            max_drawdown REAL NOT NULL,
            score REAL NOT NULL,
            timestamp TEXT NOT NULL,
            applied INTEGER DEFAULT 0,
            applied_at TEXT,
            backtest_period_days INTEGER DEFAULT 30
        )
    """)
    conn.commit()
    conn.close()


def fetch_historical_data(days: int = 60) -> List[Dict]:
    """
    Fetch historical OHLCV data from Binance.
    Returns list of candles with: time, open, high, low, close, volume
    """
    import requests
    
    try:
        # Binance API - 4h candles for 60 days = ~360 candles
        url = "https://api.binance.com/api/v3/klines"
        params = {
            "symbol": "ETHUSDT",
            "interval": "4h",
            "limit": min(1000, days * 6)  # 6 candles per day for 4h
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        candles = []
        for k in response.json():
            candles.append({
                "time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5])
            })
        
        logger.info(f"Fetched {len(candles)} historical candles")
        return candles
    except Exception as e:
        logger.error(f"Failed to fetch historical data: {e}")
        return []


def calculate_indicators(candles: List[Dict]) -> List[Dict]:
    """Add technical indicators to candles"""
    if len(candles) < 20:
        return candles
    
    # Simple RSI calculation
    for i in range(14, len(candles)):
        gains = []
        losses = []
        for j in range(i - 13, i + 1):
            change = candles[j]["close"] - candles[j - 1]["close"]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        candles[i]["rsi"] = rsi
    
    # Simple moving averages
    for i in range(20, len(candles)):
        candles[i]["sma20"] = sum(c["close"] for c in candles[i-19:i+1]) / 20
        
        if i >= 50:
            candles[i]["sma50"] = sum(c["close"] for c in candles[i-49:i+1]) / 50
    
    return candles


def run_backtest(candles: List[Dict], params: Dict) -> Dict:
    """
    Run a single backtest with given parameters.
    Returns performance metrics.
    """
    if len(candles) < 60:
        return None
    
    # Extract params
    ml_threshold = params.get("ml_threshold", 0.5)
    risk_pct = params.get("risk_per_trade", 0.01)
    tp_min = params.get("tp_min", 0.01)
    tp_max = params.get("tp_max", 0.02)
    stop_floor = params.get("stop_floor", 0.005)
    rsi_oversold = params.get("rsi_oversold", 30)
    rsi_overbought = params.get("rsi_overbought", 70)
    max_trades = params.get("max_trades_per_day", 10)
    
    # Simulation state
    equity = 10000.0
    initial_equity = equity
    trades = []
    position = None
    daily_trades = 0
    last_day = None
    max_equity = equity
    max_drawdown = 0
    
    # Run simulation
    for i in range(60, len(candles)):
        candle = candles[i]
        price = candle["close"]
        rsi = candle.get("rsi", 50)
        sma20 = candle.get("sma20", price)
        sma50 = candle.get("sma50", price)
        
        # Reset daily counter
        day = candle["time"] // (24 * 60 * 60 * 1000)
        if day != last_day:
            daily_trades = 0
            last_day = day
        
        # If in position, check exit
        if position:
            entry = position["entry"]
            pnl_pct = (price - entry) / entry
            
            # Take profit
            tp_target = tp_min + (tp_max - tp_min) * random.random()
            if pnl_pct >= tp_target:
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = True
                trades.append(position)
                # Only risk_pct of equity is in play, apply PnL on that portion
                equity += equity * risk_pct * pnl_pct * 0.95  # 5% fee
                position = None
            # Stop loss
            elif pnl_pct <= -stop_floor:
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = False
                trades.append(position)
                # Only risk_pct of equity is in play
                equity += equity * risk_pct * pnl_pct
                position = None
            
            # Update max drawdown
            if equity > max_equity:
                max_equity = equity
            dd = (max_equity - equity) / max_equity
            if dd > max_drawdown:
                max_drawdown = dd
        
        # Check for entry
        if not position and daily_trades < max_trades:
            # Entry conditions
            trend_ok = price > sma20 and sma20 > sma50 if sma50 else price > sma20
            rsi_ok = rsi_oversold < rsi < rsi_overbought
            
            # Simulate ML signal (based on ml_threshold)
            ml_signal = random.random() > (1 - ml_threshold * 0.8)
            
            if trend_ok and rsi_ok and ml_signal:
                position = {
                    "entry": price,
                    "time": candle["time"],
                    "size": equity * risk_pct
                }
                daily_trades += 1
    
    # Calculate final metrics
    if len(trades) < 5:
        return None  # Not enough trades
    
    wins = [t for t in trades if t["win"]]
    win_rate = len(wins) / len(trades) * 100
    
    total_pnl = sum(t["pnl"] for t in trades)
    roi = (equity - initial_equity) / initial_equity * 100
    
    # Sharpe ratio (simplified)
    pnls = [t["pnl"] for t in trades]
    avg_pnl = sum(pnls) / len(pnls)
    std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)) ** 0.5
    sharpe = (avg_pnl / std_pnl * (len(trades) ** 0.5)) if std_pnl > 0 else 0
    
    # Composite score — cap ROI contribution to prevent runaway scores
    capped_roi = max(-50, min(roi, 100))  # Cap ROI between -50% and 100%
    score = (
        win_rate * 0.3 +
        capped_roi * 2.0 +
        sharpe * 10 -
        max_drawdown * 100 * 0.5
    )
    
    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate, 1),
        "roi": round(roi, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "score": round(score, 2)
    }


def generate_random_params() -> Dict:
    """Generate random parameter set from grid"""
    return {
        "ml_threshold": random.choice(PARAM_GRID["ml_threshold"]),
        "risk_per_trade": random.choice(PARAM_GRID["risk_per_trade"]),
        "tp_min": random.choice(PARAM_GRID["tp_min"]),
        "tp_max": random.choice(PARAM_GRID["tp_max"]),
        "stop_floor": random.choice(PARAM_GRID["stop_floor"]),
        "rsi_oversold": random.choice(PARAM_GRID["rsi_oversold"]),
        "rsi_overbought": random.choice(PARAM_GRID["rsi_overbought"]),
        "max_trades_per_day": random.choice(PARAM_GRID["max_trades_per_day"])
    }


def save_strategy(params: Dict, metrics: Dict):
    """Save strategy result to database"""
    conn = sqlite3.connect(LEARNING_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO strategies (
            ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor,
            rsi_oversold, rsi_overbought, max_trades_per_day,
            total_trades, win_rate, roi, sharpe_ratio, max_drawdown,
            score, timestamp, backtest_period_days
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        params["ml_threshold"],
        params["risk_per_trade"],
        params["tp_min"],
        params["tp_max"],
        params["stop_floor"],
        params["rsi_oversold"],
        params["rsi_overbought"],
        params["max_trades_per_day"],
        metrics["total_trades"],
        metrics["win_rate"],
        metrics["roi"],
        metrics["sharpe_ratio"],
        metrics["max_drawdown"],
        metrics["score"],
        datetime.utcnow().isoformat(),
        60  # backtest period
    ))
    
    conn.commit()
    
    # Check if this is the new best and auto-apply
    cursor.execute("SELECT MAX(score) FROM strategies WHERE applied = 0")
    max_score = cursor.fetchone()[0] or 0
    
    if metrics["score"] >= max_score and metrics["score"] > 20:
        # Auto-apply this strategy
        cursor.execute("UPDATE strategies SET applied = 0")  # Clear previous
        cursor.execute(
            "UPDATE strategies SET applied = 1, applied_at = ? WHERE score = ?",
            (datetime.utcnow().isoformat(), metrics["score"])
        )
        conn.commit()
        logger.info(f"Auto-applied new best strategy with score {metrics['score']}")
    
    conn.close()


async def run_single_backtest():
    """Run a single backtest cycle"""
    global BACKTEST_STATE
    
    try:
        # Generate random params
        params = generate_random_params()
        BACKTEST_STATE["current_params"] = params
        
        # Fetch historical data (cached in real implementation)
        candles = fetch_historical_data(60)
        if not candles:
            return
        
        # Add indicators
        candles = calculate_indicators(candles)
        
        # Run backtest
        metrics = run_backtest(candles, params)
        
        if metrics:
            # Save result
            save_strategy(params, metrics)
            
            # Update state
            BACKTEST_STATE["tested_this_hour"] += 1
            BACKTEST_STATE["total_tested_today"] += 1
            BACKTEST_STATE["last_test_time"] = datetime.utcnow().isoformat()
            
            if metrics["score"] > BACKTEST_STATE["best_score_today"]:
                BACKTEST_STATE["best_score_today"] = metrics["score"]
                BACKTEST_STATE["last_best_strategy"] = {**params, **metrics}
            
            logger.info(
                f"Tested strategy #{BACKTEST_STATE['total_tested_today']}: "
                f"Score={metrics['score']}, WinRate={metrics['win_rate']}%, ROI={metrics['roi']}%"
            )
    except Exception as e:
        logger.error(f"Backtest error: {e}")


async def run_continuous_backtesting():
    """Main loop for continuous backtesting"""
    global BACKTEST_STATE
    
    ensure_db()
    BACKTEST_STATE["running"] = True
    logger.info("🧠 Continuous Strategy Backtester started")
    
    hour_start = datetime.utcnow().hour
    
    while BACKTEST_STATE["running"]:
        # Reset hourly counter
        current_hour = datetime.utcnow().hour
        if current_hour != hour_start:
            hour_start = current_hour
            BACKTEST_STATE["tested_this_hour"] = 0
        
        # Run backtest
        await run_single_backtest()
        
        # Wait 30-60 seconds before next test
        wait_time = random.randint(30, 60)
        await asyncio.sleep(wait_time)


def get_backtest_state() -> Dict:
    """Get current backtest state for live progress endpoint"""
    return {
        **BACKTEST_STATE,
        "running": BACKTEST_STATE["running"],
        "strategies_per_hour_target": "60-120"
    }


def stop_backtesting():
    """Stop continuous backtesting"""
    global BACKTEST_STATE
    BACKTEST_STATE["running"] = False
    logger.info("Backtesting stopped")


# CLI for testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Run single backtest
        ensure_db()
        asyncio.run(run_single_backtest())
        print(f"State: {get_backtest_state()}")
    else:
        # Run continuous
        asyncio.run(run_continuous_backtesting())
