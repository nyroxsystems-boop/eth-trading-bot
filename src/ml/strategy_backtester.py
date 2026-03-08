#!/usr/bin/env python3
"""
Continuous Strategy Backtester

Runs in background, continuously testing different strategy parameter combinations
on historical ETH data and saving results to the learning database.

Target: 60-120 strategies per hour (1 every 30-60 seconds)
"""

import os
import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Import shared learning store (PostgreSQL-backed, persistent across deploys)
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import learning_store

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ensure_db():
    """Ensure PostgreSQL tables exist via learning_store"""
    learning_store.ensure_learning_tables()
    logger.info("✅ Strategy Backtester: using PostgreSQL via learning_store")


# Strategy parameter ranges for grid search
PARAM_GRID = {
    "ml_threshold": [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65],
    "risk_per_trade": [0.004, 0.006, 0.008, 0.010, 0.012],
    "tp_min": [0.008, 0.010, 0.012, 0.015],
    "tp_max": [0.015, 0.018, 0.020, 0.025],
    "stop_floor": [0.004, 0.005, 0.006, 0.008],
    "rsi_oversold": [25, 30, 35],
    "rsi_overbought": [65, 70, 75],
    "max_trades_per_day": [8, 10, 15, 20],
    "entry_score_min": [0.15, 0.20, 0.25, 0.30, 0.35],
    "breakout_weight": [0.20, 0.25, 0.30, 0.35, 0.40],
    "trend_weight": [0.10, 0.15, 0.20, 0.25, 0.30],
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

# Cached historical data
_cached_candles = None
_cache_time = None
CACHE_TTL = 3600  # 1 hour


def fetch_historical_data(days: int = 7) -> List[Dict]:
    """
    Fetch historical OHLCV data from Binance with caching.
    Uses 5m candles to MATCH the bot's trading timeframe.
    Returns list of candles with: time, open, high, low, close, volume
    """
    global _cached_candles, _cache_time
    import time as _time
    
    # Return cached data if fresh
    if _cached_candles and _cache_time and (_time.time() - _cache_time) < CACHE_TTL:
        return _cached_candles
    
    import requests
    
    try:
        # Binance API - 5m candles to match bot's INTERVAL
        # 7 days × 288 candles/day = ~2016 candles (needs 2 requests)
        url = "https://api.binance.com/api/v3/klines"
        all_candles = []
        candles_needed = min(days * 288, 2000)  # 288 5m candles per day
        
        # Paginate (Binance limit = 1000 per request)
        start_time = int((_time.time() - days * 86400) * 1000)
        
        while len(all_candles) < candles_needed:
            params = {
                "symbol": "ETHUSDT",
                "interval": "5m",
                "startTime": start_time,
                "limit": 1000
            }
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            
            for k in data:
                all_candles.append({
                    "time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                })
            
            if len(data) < 1000:
                break
            start_time = int(data[-1][6]) + 1  # Next batch after last close_time
        
        _cached_candles = all_candles
        _cache_time = _time.time()
        logger.info(f"Fetched {len(all_candles)} 5m candles ({days} days)")
        return all_candles
    except Exception as e:
        logger.error(f"Failed to fetch historical data: {e}")
        return _cached_candles or []


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
    Uses TA-based entry signals (not random), fixed take-profit.
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
    
    # Pre-compute average volume for volume spike detection
    volumes = [c.get("volume", 0) for c in candles[40:60]]
    avg_volume = sum(volumes) / len(volumes) if volumes else 1
    
    # Run simulation
    for i in range(60, len(candles)):
        candle = candles[i]
        price = candle["close"]
        rsi = candle.get("rsi", 50)
        sma20 = candle.get("sma20", price)
        sma50 = candle.get("sma50", price)
        vol = candle.get("volume", 0)
        
        # Update rolling average volume
        avg_volume = avg_volume * 0.95 + vol * 0.05
        
        # Reset daily counter
        day = candle["time"] // (24 * 60 * 60 * 1000)
        if day != last_day:
            daily_trades = 0
            last_day = day
        
        # If in position, check exit
        if position:
            entry = position["entry"]
            pnl_pct = (price - entry) / entry
            
            # Fixed take-profit at tp_max (not random)
            if pnl_pct >= tp_max:
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = True
                trades.append(position)
                equity += equity * risk_pct * pnl_pct * 0.95  # 5% fee
                position = None
            # Partial take-profit at tp_min if RSI overbought
            elif pnl_pct >= tp_min and rsi > rsi_overbought:
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = True
                trades.append(position)
                equity += equity * risk_pct * pnl_pct * 0.95
                position = None
            # Stop loss
            elif pnl_pct <= -stop_floor:
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = False
                trades.append(position)
                equity += equity * risk_pct * pnl_pct
                position = None
            
            # Update max drawdown
            if equity > max_equity:
                max_equity = equity
            dd = (max_equity - equity) / max_equity
            if dd > max_drawdown:
                max_drawdown = dd
        
        # Check for entry using TA-based signals (no randomness!)
        if not position and daily_trades < max_trades:
            entry_min = params.get("entry_score_min", 0.25)
            brk_w = params.get("breakout_weight", 0.30)
            trn_w = params.get("trend_weight", 0.20)
            
            # --- TA-based signal components (deterministic) ---
            # 1. Trend: price > SMA20 > SMA50
            trend_ok = price > sma20 and (sma50 is None or sma20 > sma50)
            
            # 2. RSI conditions
            rsi_ok = rsi_oversold < rsi < rsi_overbought
            oversold = rsi <= rsi_oversold + 5
            
            # 3. Breakout: price above 20-period high
            recent_high = max(c["high"] for c in candles[max(0,i-20):i])
            breakout = price > recent_high * 1.0001
            
            # 4. Volume spike: current volume > 1.5x average
            vol_spike = vol > avg_volume * 1.5 if avg_volume > 0 else False
            
            # 5. Momentum: price higher than 3 candles ago
            momentum = price > candles[i-3]["close"] if i >= 3 else False
            
            # Composite TA score (deterministic, no random!)
            ta_score = (
                brk_w * (1.0 if breakout else 0.0) +
                trn_w * (1.0 if trend_ok else 0.0) +
                0.15 * (1.0 if oversold else 0.0) +
                0.10 * (1.0 if vol_spike else 0.0) +
                0.10 * (1.0 if momentum else 0.0) +
                0.10 * (1.0 if rsi_ok else 0.0)
            )
            
            # ML signal: TA score exceeds threshold (deterministic!)
            if ta_score >= entry_min and ta_score >= ml_threshold * 0.7:
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
    """Generate completely random parameter set (exploration)"""
    return {
        "ml_threshold": random.choice(PARAM_GRID["ml_threshold"]),
        "risk_per_trade": random.choice(PARAM_GRID["risk_per_trade"]),
        "tp_min": random.choice(PARAM_GRID["tp_min"]),
        "tp_max": random.choice(PARAM_GRID["tp_max"]),
        "stop_floor": random.choice(PARAM_GRID["stop_floor"]),
        "rsi_oversold": random.choice(PARAM_GRID["rsi_oversold"]),
        "rsi_overbought": random.choice(PARAM_GRID["rsi_overbought"]),
        "max_trades_per_day": random.choice(PARAM_GRID["max_trades_per_day"]),
        "entry_score_min": random.choice(PARAM_GRID["entry_score_min"]),
        "breakout_weight": random.choice(PARAM_GRID["breakout_weight"]),
        "trend_weight": random.choice(PARAM_GRID["trend_weight"]),
    }


def get_top_strategies(n: int = 10) -> List[Dict]:
    """Fetch top N strategies from PostgreSQL for evolution"""
    try:
        all_strats = learning_store.get_all_strategies(limit=n)
        results = []
        for s in all_strats:
            p = s.get("params", {})
            # Extract params for mutation/crossover
            p["score"] = s.get("score", 0)
            results.append(p)
        return results
    except Exception as e:
        logger.error(f"Failed to fetch top strategies: {e}")
        return []


def mutate_strategy(parent: Dict, mutation_rate: float = 0.20) -> Dict:
    """
    Mutate a parent strategy's params by ±mutation_rate.
    Also randomly picks entry_score_min/breakout_weight/trend_weight
    from grid since they're not in the DB schema.
    """
    def mutate_float(val, grid_key=None):
        """Mutate a float value by ±mutation_rate, clamp to grid range"""
        delta = val * mutation_rate * random.uniform(-1, 1)
        new_val = val + delta
        if grid_key and grid_key in PARAM_GRID:
            grid = PARAM_GRID[grid_key]
            new_val = max(min(grid), min(max(grid), new_val))
        return round(new_val, 6)
    
    def mutate_int(val, grid_key=None):
        """Mutate an int value by ±1-2 steps"""
        delta = random.choice([-2, -1, 0, 0, 1, 2])
        new_val = val + delta
        if grid_key and grid_key in PARAM_GRID:
            grid = PARAM_GRID[grid_key]
            new_val = max(min(grid), min(max(grid), new_val))
        return int(new_val)
    
    return {
        "ml_threshold": mutate_float(parent.get("ml_threshold", 0.5), "ml_threshold"),
        "risk_per_trade": mutate_float(parent.get("risk_per_trade", 0.008), "risk_per_trade"),
        "tp_min": mutate_float(parent.get("tp_min", 0.01), "tp_min"),
        "tp_max": mutate_float(parent.get("tp_max", 0.02), "tp_max"),
        "stop_floor": mutate_float(parent.get("stop_floor", 0.005), "stop_floor"),
        "rsi_oversold": mutate_int(parent.get("rsi_oversold", 30), "rsi_oversold"),
        "rsi_overbought": mutate_int(parent.get("rsi_overbought", 70), "rsi_overbought"),
        "max_trades_per_day": mutate_int(parent.get("max_trades_per_day", 10), "max_trades_per_day"),
        # NOW EVOLVED from parent instead of random!
        "entry_score_min": mutate_float(parent.get("entry_score_min", 0.25), "entry_score_min"),
        "breakout_weight": mutate_float(parent.get("breakout_weight", 0.30), "breakout_weight"),
        "trend_weight": mutate_float(parent.get("trend_weight", 0.20), "trend_weight"),
    }


def crossover(parent_a: Dict, parent_b: Dict) -> Dict:
    """Combine two parents: randomly pick each param from either parent"""
    child = {}
    for key in parent_a:
        if key == "score":
            continue
        child[key] = parent_a[key] if random.random() > 0.5 else parent_b[key]
    # Ensure entry weights are included
    for key in ["entry_score_min", "breakout_weight", "trend_weight"]:
        if key not in child:
            child[key] = random.choice(PARAM_GRID[key])
    return child


def generate_evolved_params() -> Dict:
    """
    Evolutionary parameter generation:
    - 70% chance: mutate or crossover from top strategies
    - 30% chance: random exploration (discover new regions)
    """
    top = get_top_strategies(10)
    
    # If no top strategies yet, explore randomly
    if len(top) < 3:
        return generate_random_params()
    
    if random.random() < 0.70:
        # EVOLUTION: build on what works
        roll = random.random()
        if roll < 0.50:
            # Mutate single parent (most common)
            parent = random.choice(top[:5])  # Focus on top 5
            child = mutate_strategy(parent)
            logger.info(f"🧬 MUTATE from parent score={parent['score']:.1f}")
            return child
        elif roll < 0.80:
            # Crossover two parents
            pa = random.choice(top[:5])
            pb = random.choice(top[:10])
            child = crossover(pa, pb)
            logger.info(f"🧬 CROSSOVER parents score={pa['score']:.1f} x {pb['score']:.1f}")
            return child
        else:
            # Mutate with higher rate (explore around known good)
            parent = random.choice(top[:3])  # Only top 3
            child = mutate_strategy(parent, mutation_rate=0.35)
            logger.info(f"🧬 BIG MUTATE from top parent score={parent['score']:.1f}")
            return child
    else:
        # EXPLORATION: try completely new combinations
        logger.info("🔍 EXPLORE random params")
        return generate_random_params()


def save_strategy(params: Dict, metrics: Dict):
    """Save strategy result to PostgreSQL via learning_store"""
    strategy = {
        "params": params,
        "metrics": metrics,
        "score": metrics.get("score", 0),
        "applied": False,
        "data_source": metrics.get("data_source", "historical_binance")
    }
    
    try:
        learning_store.save_strategy(strategy)
        
        # Check if this is the new best and auto-apply
        current = learning_store.get_current_strategy()
        current_score = current.get("score", 0) if current else 0
        
        if metrics["score"] > current_score and metrics["score"] > 15:
            # Auto-apply this strategy as current best
            strategy["applied"] = True
            strategy["applied_at"] = datetime.utcnow().isoformat()
            learning_store.set_current_strategy(strategy)
            logger.info(f"🏆 Auto-applied new best strategy! Score: {metrics['score']:.1f} (was {current_score:.1f})")
    except Exception as e:
        logger.error(f"Error saving strategy: {e}")


async def run_single_backtest():
    """Run a single backtest with walk-forward validation (70/30 split)"""
    global BACKTEST_STATE
    
    try:
        # Generate random params
        # Generate params: 70% evolved from top strategies, 30% random exploration
        params = generate_evolved_params()
        BACKTEST_STATE["current_params"] = params
        
        # Fetch historical data (cached for 1 hour)
        candles = fetch_historical_data(60)
        if not candles or len(candles) < 120:
            return
        
        # Add indicators
        candles = calculate_indicators(candles)
        
        # Walk-Forward Validation: 70% train / 30% test
        split_idx = int(len(candles) * 0.7)
        train_candles = candles[:split_idx]
        test_candles = candles[split_idx:]
        
        # Run backtest on TRAIN set first (for param validation)
        train_metrics = run_backtest(train_candles, params)
        if not train_metrics or train_metrics["score"] < 0:
            # Strategy doesn't even work on train data, skip
            BACKTEST_STATE["tested_this_hour"] += 1
            BACKTEST_STATE["total_tested_today"] += 1
            return
        
        # Run backtest on TEST set (out-of-sample, this is the real score)
        test_metrics = run_backtest(test_candles, params)
        if not test_metrics:
            return
        
        # Use TEST score as the final score (out-of-sample validation)
        # Average with train score to reduce variance, but weight test higher
        oos_score = test_metrics["score"] * 0.7 + train_metrics["score"] * 0.3
        test_metrics["score"] = round(oos_score, 2)
        test_metrics["train_score"] = train_metrics["score"]
        test_metrics["data_source"] = "historical_binance"
        
        # Save result (using test metrics)
        save_strategy(params, test_metrics)
        
        # Update state
        BACKTEST_STATE["tested_this_hour"] += 1
        BACKTEST_STATE["total_tested_today"] += 1
        BACKTEST_STATE["last_test_time"] = datetime.utcnow().isoformat()
        
        if test_metrics["score"] > BACKTEST_STATE["best_score_today"]:
            BACKTEST_STATE["best_score_today"] = test_metrics["score"]
            BACKTEST_STATE["last_best_strategy"] = {**params, **test_metrics}
        
        logger.info(
            f"Tested strategy #{BACKTEST_STATE['total_tested_today']}: "
            f"Train={train_metrics['score']:.1f} Test={test_metrics['score']:.1f} "
            f"WinRate={test_metrics['win_rate']}% ROI={test_metrics['roi']}%"
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
