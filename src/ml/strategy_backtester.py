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


# Strategy parameter CONTINUOUS RANGES (wider than old discrete grid!)
PARAM_RANGES = {
    "ml_threshold":       (0.20, 0.75),   # was [0.35-0.65]
    "risk_per_trade":     (0.002, 0.020),  # was [0.004-0.012]
    "tp_min":             (0.004, 0.025),  # was [0.008-0.015]
    "tp_max":             (0.010, 0.050),  # was [0.015-0.025] — now up to 5%!
    "stop_floor":         (0.002, 0.015),  # was [0.004-0.008]
    "rsi_oversold":       (15, 40),        # was [25-35]
    "rsi_overbought":     (60, 85),        # was [65-75]
    "max_trades_per_day": (3, 30),         # was [8-20]
    "entry_score_min":    (0.10, 0.50),    # was [0.15-0.35]
    "breakout_weight":    (0.10, 0.50),    # was [0.20-0.40]
    "trend_weight":       (0.05, 0.40),    # was [0.10-0.30]
}
# Backwards compat
PARAM_GRID = {k: list(v) for k, v in PARAM_RANGES.items()}

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
            
            # Position size = risk_capital / stop_loss_pct
            # This is how the real bot sizes positions too
            pos_size = equity * risk_pct / max(stop_floor, 0.001)
            
            # Fixed take-profit at tp_max
            if pnl_pct >= tp_max:
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = True
                trades.append(position)
                equity += pos_size * pnl_pct * 0.999  # 0.1% fee
                position = None
            # Partial take-profit at tp_min if RSI overbought
            elif pnl_pct >= tp_min and rsi > rsi_overbought:
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = True
                trades.append(position)
                equity += pos_size * pnl_pct * 0.999
                position = None
            # Stop loss
            elif pnl_pct <= -stop_floor:
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = False
                trades.append(position)
                equity += pos_size * pnl_pct  # Full loss, no fee
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
            
            # --- 1H CONTEXT SIMULATION (aggregate 12 x 5m candles) ---
            hourly_bias = "NEUTRAL"
            if i >= 168:  # Need 14 * 12 = 168 candles for 14h RSI
                # Aggregate 5m to 1h: take every 12th candle's close
                h1_closes = [candles[j]["close"] for j in range(i - 167, i + 1, 12)]
                if len(h1_closes) >= 14:
                    # Simple RSI on 1h closes
                    h1_gains, h1_losses = [], []
                    for k in range(1, len(h1_closes)):
                        chg = h1_closes[k] - h1_closes[k-1]
                        h1_gains.append(max(0, chg))
                        h1_losses.append(max(0, -chg))
                    ag = sum(h1_gains[-14:]) / 14
                    al = sum(h1_losses[-14:]) / 14
                    h1_rsi = 100 - 100 / (1 + ag / max(al, 1e-9)) if al > 0 else 100
                    
                    # 1h EMAs
                    h1_ema20 = sum(h1_closes[-min(20, len(h1_closes)):]) / min(20, len(h1_closes))
                    h1_ema50 = sum(h1_closes[-min(len(h1_closes), 14):]) / min(len(h1_closes), 14)
                    
                    if h1_rsi < 35 and price < h1_ema20:
                        hourly_bias = "OVERSOLD_BOUNCE"
                    elif price > h1_ema20 and h1_ema20 > h1_ema50:
                        hourly_bias = "TREND_UP"
                    elif price < h1_ema20 and h1_ema20 < h1_ema50:
                        hourly_bias = "TREND_DOWN"
            
            # BLOCK entries during 1h downtrend
            if hourly_bias == "TREND_DOWN":
                continue  # Skip this candle entirely
            
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
            
            # 1h bias bonuses (match live bot behavior)
            if hourly_bias == "OVERSOLD_BOUNCE":
                ta_score += 0.15
                entry_min *= 0.60  # Lower bar for mean reversion
            elif hourly_bias == "TREND_UP":
                ta_score += 0.10
            
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
    losses = [t for t in trades if not t["win"]]
    win_rate = len(wins) / len(trades) * 100
    
    # QUALITY FILTER: reject strategies with win rate below 45%
    if win_rate < 45.0:
        return None
    
    roi = (equity - initial_equity) / initial_equity * 100
    
    # Profit factor: gross wins / gross losses (>1.5 is good, >2.0 is excellent)
    gross_wins = sum(t["pnl"] for t in wins) if wins else 0
    gross_losses = abs(sum(t["pnl"] for t in losses)) if losses else 0.0001
    profit_factor = gross_wins / max(gross_losses, 0.0001)
    
    # Sharpe ratio (simplified)
    pnls = [t["pnl"] for t in trades]
    avg_pnl = sum(pnls) / len(pnls)
    std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)) ** 0.5
    sharpe = (avg_pnl / std_pnl * (len(trades) ** 0.5)) if std_pnl > 0 else 0
    
    # === SCORING: MAXIMIZE WIN RATE & ROI ===
    capped_roi = max(-50, min(roi, 100))  # Cap ROI between -50% and 100%
    
    # Win rate bonus tiers
    wr_bonus = 0
    if win_rate >= 70:
        wr_bonus = 30    # Excellent
    elif win_rate >= 60:
        wr_bonus = 15    # Good
    elif win_rate >= 55:
        wr_bonus = 5     # Decent
    
    # Profit factor bonus (penalizes bad risk/reward)
    pf_bonus = min(profit_factor * 5, 20)  # Up to +20 for PF > 4.0
    
    score = (
        win_rate * 1.5 +          # 1.5x win rate (was 0.3) — HEAVILY weighted
        capped_roi * 3.0 +        # 3x ROI contribution (was 2.0)
        sharpe * 8 +              # Sharpe still matters
        wr_bonus +                # Win rate tier bonus
        pf_bonus -                # Profit factor bonus
        max_drawdown * 100 * 1.0  # Higher drawdown penalty (was 0.5)
    )
    
    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate, 1),
        "roi": round(roi, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "profit_factor": round(profit_factor, 2),
        "score": round(score, 2)
    }


def generate_random_params() -> Dict:
    """Generate random params from CONTINUOUS ranges (infinite unique combos)"""
    p = {}
    for key, (lo, hi) in PARAM_RANGES.items():
        if key in ("rsi_oversold", "rsi_overbought", "max_trades_per_day"):
            p[key] = random.randint(int(lo), int(hi))
        else:
            p[key] = round(random.uniform(lo, hi), 6)
    # Enforce tp_min < tp_max
    if p["tp_min"] >= p["tp_max"]:
        p["tp_min"], p["tp_max"] = p["tp_max"], p["tp_min"]
        if p["tp_min"] == p["tp_max"]:
            p["tp_max"] += 0.005
    return p


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
    Gaussian mutation: each param shifted by N(0, range_width * mutation_rate).
    Clamps to PARAM_RANGES. Smaller rate = fine-tuning, larger = exploration.
    """
    child = {}
    for key, (lo, hi) in PARAM_RANGES.items():
        val = parent.get(key, (lo + hi) / 2)
        spread = (hi - lo) * mutation_rate
        new_val = val + random.gauss(0, spread)
        new_val = max(lo, min(hi, new_val))
        if key in ("rsi_oversold", "rsi_overbought", "max_trades_per_day"):
            child[key] = int(round(new_val))
        else:
            child[key] = round(new_val, 6)
    # Enforce tp_min < tp_max
    if child["tp_min"] >= child["tp_max"]:
        child["tp_min"], child["tp_max"] = child["tp_max"], child["tp_min"]
    return child


def crossover(parent_a: Dict, parent_b: Dict) -> Dict:
    """Blend crossover: weighted average of two parents with random alpha"""
    child = {}
    for key, (lo, hi) in PARAM_RANGES.items():
        a_val = parent_a.get(key, (lo + hi) / 2)
        b_val = parent_b.get(key, (lo + hi) / 2)
        alpha = random.uniform(0.2, 0.8)
        new_val = a_val * alpha + b_val * (1 - alpha)
        new_val = max(lo, min(hi, new_val))
        if key in ("rsi_oversold", "rsi_overbought", "max_trades_per_day"):
            child[key] = int(round(new_val))
        else:
            child[key] = round(new_val, 6)
    return child


def generate_evolved_params() -> Dict:
    """
    Bayesian-inspired evolutionary optimization:
    - 35% Fine-tune: small Gaussian mutation of top parent (intensification)
    - 25% Crossover + mutate: blend two parents, then tiny polish
    - 15% Big mutation: large perturbation to escape local minimum
    - 25% Pure exploration: random from continuous ranges
    
    Score-proportional parent selection (roulette wheel).
    """
    top = get_top_strategies(10)
    
    if len(top) < 3:
        return generate_random_params()
    
    # Score-proportional selection (roulette wheel)
    scores = [max(s.get("score", 0), 0.1) for s in top]
    total = sum(scores)
    probs = [s / total for s in scores]
    
    def pick_parent():
        r = random.random()
        cumsum = 0
        for i, p in enumerate(probs):
            cumsum += p
            if r <= cumsum:
                return top[i]
        return top[0]
    
    roll = random.random()
    
    if roll < 0.35:
        # FINE-TUNE: small Gaussian mutation
        parent = pick_parent()
        child = mutate_strategy(parent, mutation_rate=0.10)
        logger.info(f"FINE-TUNE parent score={parent.get('score',0):.1f}")
        return child
    elif roll < 0.60:
        # CROSSOVER + MUTATE: blend two parents, then small perturbation
        pa = pick_parent()
        pb = pick_parent()
        child = crossover(pa, pb)
        child = mutate_strategy(child, mutation_rate=0.05)
        logger.info(f"CROSSOVER+MUTATE {pa.get('score',0):.1f} x {pb.get('score',0):.1f}")
        return child
    elif roll < 0.75:
        # BIG MUTATION: jump out of local minimum
        parent = pick_parent()
        child = mutate_strategy(parent, mutation_rate=0.40)
        logger.info(f"BIG MUTATE from score={parent.get('score',0):.1f}")
        return child
    else:
        # PURE EXPLORATION: continuous random from wider ranges
        logger.info("EXPLORE random continuous params")
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
