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
    "ml_threshold":       (0.35, 0.65),    # v7: tightened to match bot floor=0.42
    "risk_per_trade":     (0.005, 0.020),   # v7: min 0.5% (was 0.2% = too tiny)
    "tp_min":             (0.012, 0.025),   # v7: ALIGNED with bot clamp min 1.2% (was 0.4%!)
    "tp_max":             (0.020, 0.050),   # v7: min 2% (was 1% = overlapped tp_min)
    "stop_floor":         (0.008, 0.025),   # v7: max 2.5% (was 3.5% = terrible R:R)
    "rsi_oversold":       (15, 40),
    "rsi_overbought":     (60, 85),
    "max_trades_per_day": (5, 25),          # v7: min 5 (was 3)
    "entry_score_min":    (0.15, 0.35),     # v7: tightened to match bot reality
    "breakout_weight":    (0.10, 0.50),
    "trend_weight":       (0.05, 0.40),
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


# v10: Multi-period cache to avoid testing everything on same candles
_cached_candles_multi = {}  # {days: (candles, timestamp)}

def fetch_historical_data(days: int = 7) -> List[Dict]:
    """
    Fetch historical OHLCV data from Binance with per-period caching.
    v10: Supports multiple periods (7/14/30/60 days) cached independently.
    Uses 5m candles to MATCH the bot's trading timeframe.
    Returns list of candles with: time, open, high, low, close, volume
    """
    global _cached_candles, _cache_time, _cached_candles_multi
    import time as _time
    
    # Return cached data for this specific period if fresh
    if days in _cached_candles_multi:
        cached, cache_ts = _cached_candles_multi[days]
        if cached and (_time.time() - cache_ts) < CACHE_TTL:
            return cached
    
    import requests
    
    try:
        # Binance API - 5m candles to match bot's INTERVAL
        url = "https://api.binance.com/api/v3/klines"
        all_candles = []
        candles_needed = min(days * 288, 4000)  # v10: allow more candles for longer periods
        
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
        
        _cached_candles_multi[days] = (all_candles, _time.time())
        # Also update legacy cache for backward compat
        _cached_candles = all_candles
        _cache_time = _time.time()
        logger.info(f"Fetched {len(all_candles)} 5m candles ({days} days)")
        return all_candles
    except Exception as e:
        logger.error(f"Failed to fetch historical data: {e}")
        if days in _cached_candles_multi:
            return _cached_candles_multi[days][0]
        return _cached_candles or []


def get_random_backtest_period() -> int:
    """v10: Return a random backtest period to avoid all strategies being scored on identical data."""
    return random.choice([7, 14, 14, 30, 30, 60])


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
    ALIGNED WITH LIVE BOT: includes trailing TP, break-even, partial exit, time exit.
    Returns performance metrics including losses (no more hiding bad strategies).
    """
    if len(candles) < 60:
        return None
    
    # Extract params
    ml_threshold = params.get("ml_threshold", 0.5)
    risk_pct = params.get("risk_per_trade", 0.01)
    tp_min = params.get("tp_min", 0.01)
    tp_max = params.get("tp_max", 0.02)
    stop_floor = params.get("stop_floor", 0.012)
    rsi_oversold = params.get("rsi_oversold", 30)
    rsi_overbought = params.get("rsi_overbought", 70)
    max_trades = params.get("max_trades_per_day", 10)
    break_even_trigger = 0.012  # Match live bot: +1.2% → move SL to break-even
    max_hold_bars = 60  # Match live bot: ~5h max hold time
    
    # Simulation state
    equity = 100000.0
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
        
        # ═══ POSITION MANAGEMENT (aligned with live bot) ═══
        if position:
            entry = position["entry"]
            pnl_pct = (price - entry) / entry
            pos_size = position.get("size", equity * risk_pct / max(stop_floor, 0.001))
            bars_held = i - position.get("entry_idx", i)
            peak_pnl = position.get("peak_pnl", 0.0)
            trailing_active = position.get("trailing_active", False)
            sl_pct = stop_floor  # Dynamic SL starts at stop_floor
            
            # Track peak PnL
            if pnl_pct > peak_pnl:
                position["peak_pnl"] = pnl_pct
                peak_pnl = pnl_pct
            
            exit_reason = None
            
            # === TIME EXIT (match live bot MAX_HOLD_BARS) ===
            if bars_held >= max_hold_bars:
                exit_reason = "TIME"
            
            # === BREAK-EVEN: after +1.2%, move SL to 0 ===
            if pnl_pct >= break_even_trigger:
                sl_pct = 0.001  # Break-even + tiny buffer
            
            # === TRAILING TP SYSTEM (match live bot exactly) ===
            if peak_pnl >= tp_max and not trailing_active:
                position["trailing_active"] = True
                trailing_active = True
            
            if trailing_active:
                # Lock in 60% of peak gains (match live bot)
                trail_floor = peak_pnl * 0.60
                trail_sl = max(trail_floor, tp_max * 0.50)
                
                if pnl_pct <= trail_sl and peak_pnl > tp_max * 0.8:
                    exit_reason = "TRAIL_TP"
                
                # Hard cap at 3x TP
                if pnl_pct >= tp_max * 3.0:
                    exit_reason = "TRAIL_CAP"
            else:
                # Standard TP (not trailing yet)
                if pnl_pct >= tp_max:
                    exit_reason = "TP"
                elif pnl_pct >= tp_min and rsi > rsi_overbought:
                    exit_reason = "TP_RSI"
            
            # === STOP LOSS ===
            if pnl_pct <= -sl_pct and not exit_reason:
                exit_reason = "SL"
            
            # === EXECUTE EXIT ===
            if exit_reason:
                is_win = pnl_pct > 0
                position["exit"] = price
                position["pnl"] = pnl_pct
                position["win"] = is_win
                position["exit_reason"] = exit_reason
                position["bars_held"] = bars_held
                trades.append(position)
                equity += pos_size * pnl_pct * (0.999 if is_win else 1.0)  # Fee only on wins
                position = None
            
            # Update max drawdown
            if equity > max_equity:
                max_equity = equity
            dd = (max_equity - equity) / max_equity
            if dd > max_drawdown:
                max_drawdown = dd
        
        # ═══ ENTRY LOGIC (aligned with live bot) ═══
        if not position and daily_trades < max_trades:
            entry_min = params.get("entry_score_min", 0.25)
            brk_w = params.get("breakout_weight", 0.30)
            trn_w = params.get("trend_weight", 0.20)
            
            # --- 1H CONTEXT SIMULATION ---
            hourly_bias = "NEUTRAL"
            if i >= 168:
                h1_closes = [candles[j]["close"] for j in range(i - 167, i + 1, 12)]
                if len(h1_closes) >= 14:
                    h1_gains, h1_losses = [], []
                    for k in range(1, len(h1_closes)):
                        chg = h1_closes[k] - h1_closes[k-1]
                        h1_gains.append(max(0, chg))
                        h1_losses.append(max(0, -chg))
                    ag = sum(h1_gains[-14:]) / 14
                    al = sum(h1_losses[-14:]) / 14
                    h1_rsi = 100 - 100 / (1 + ag / max(al, 1e-9)) if al > 0 else 100
                    h1_ema20 = sum(h1_closes[-min(20, len(h1_closes)):]) / min(20, len(h1_closes))
                    h1_ema50 = sum(h1_closes[-min(len(h1_closes), 14):]) / min(len(h1_closes), 14)
                    
                    if h1_rsi < 35 and price < h1_ema20:
                        hourly_bias = "OVERSOLD_BOUNCE"
                    elif price > h1_ema20 and h1_ema20 > h1_ema50:
                        hourly_bias = "TREND_UP"
                    elif price < h1_ema20 and h1_ema20 < h1_ema50:
                        hourly_bias = "TREND_DOWN"
            
            # Penalty for 1h downtrend (match live bot: -0.15 penalty, not hard block)
            bias_penalty = -0.15 if hourly_bias == "TREND_DOWN" else 0.0
            
            # --- TA-based signal components ---
            trend_ok = price > sma20 and (sma50 is None or sma20 > sma50)
            rsi_ok = rsi_oversold < rsi < rsi_overbought
            oversold = rsi <= rsi_oversold + 5
            recent_high = max(c["high"] for c in candles[max(0,i-20):i])
            breakout = price > recent_high * 1.0001
            vol_spike = vol > avg_volume * 1.5 if avg_volume > 0 else False
            momentum = price > candles[i-3]["close"] if i >= 3 else False
            
            # EMA bounce (match live bot)
            ema_bounce = (price > sma20) and (candle["low"] <= sma20 * 1.002) and (rsi > 40)
            
            # MACD crossover (simplified)
            macd_cross = False
            if i >= 2:
                prev_mom = candles[i-1]["close"] - candles[i-2]["close"]
                curr_mom = candle["close"] - candles[i-1]["close"]
                macd_cross = curr_mom > 0 and prev_mom <= 0
            
            # Composite TA score (aligned with live bot weights)
            ta_score = (
                0.18 * (1.0 if breakout else 0.0) +
                0.10 * (1.0 if trend_ok else 0.0) +
                0.12 * (1.0 if oversold else 0.0) +
                0.10 * (1.0 if ema_bounce else 0.0) +
                0.10 * (1.0 if macd_cross else 0.0) +
                0.08 * (1.0 if vol_spike else 0.0) +
                0.08 * (1.0 if momentum else 0.0) +
                0.06 * (1.0 if rsi_ok else 0.0) +
                bias_penalty
            )
            
            # 1h bias bonuses
            if hourly_bias == "OVERSOLD_BOUNCE":
                ta_score += 0.15
                entry_min *= 0.75  # Match live bot: modest reduction (was 0.60)
            elif hourly_bias == "TREND_UP":
                ta_score += 0.10
            
            # Entry gate: score must pass both entry_min AND ml_threshold
            if ta_score >= entry_min and ta_score >= ml_threshold * 0.7:
                position = {
                    "entry": price,
                    "time": candle["time"],
                    "entry_idx": i,
                    "size": equity * risk_pct / max(stop_floor, 0.001),
                    "peak_pnl": 0.0,
                    "trailing_active": False
                }
                daily_trades += 1
    
    # ═══ CALCULATE METRICS (no more hiding bad strategies!) ═══
    if len(trades) < 3:
        return None  # Not enough trades for any valid assessment
    
    wins = [t for t in trades if t["win"]]
    losses = [t for t in trades if not t["win"]]
    win_rate = len(wins) / len(trades) * 100
    
    # FIX: DON'T delete strategies with WR < 50%!
    # Return ALL results honestly so the scoring system can rank them properly.
    # The old filter was hiding failures → only 100% WR strategies survived → misleading dashboard.
    
    roi = (equity - initial_equity) / initial_equity * 100
    
    # Profit factor
    gross_wins = sum(t["pnl"] for t in wins) if wins else 0
    gross_losses = abs(sum(t["pnl"] for t in losses)) if losses else 0.0001
    profit_factor = gross_wins / max(gross_losses, 0.0001)
    
    # Sharpe ratio
    pnls = [t["pnl"] for t in trades]
    avg_pnl = sum(pnls) / len(pnls)
    std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)) ** 0.5
    sharpe = (avg_pnl / std_pnl * (len(trades) ** 0.5)) if std_pnl > 0 else 0
    
    # === SCORING: v7 PROFITABILITY-FIRST (ROI + R:R dominant) ===
    n_trades = len(trades)
    
    # FAKE GATES: reject unrealistically perfect strategies
    if win_rate >= 99.5:
        score = 0.0  # No real strategy has 100% WR
    elif win_rate >= 90.0 and n_trades < 20:
        score = 0.0  # Need at least 20 trades for 90%+ WR to be credible
    elif win_rate >= 80.0 and n_trades < 10:
        score = 0.0  # Way too few samples for such high WR
    # KILL GATE: WR < 55% = score 0 (lowered from 60% — was too restrictive)
    elif win_rate < 55.0:
        score = 0.0
    else:
        # BASE: WR contribution (v7: HALVED dominance — was *10, now *5)
        score = win_rate * 5.0
        # Tier bonuses (v7: recalibrated)
        if win_rate > 65: score += 100.0
        if win_rate > 70: score += 200.0
        if win_rate > 75: score += 300.0
        if win_rate > 80: score += 500.0
        if win_rate > 85: score += 800.0   # NEW tier for 85%+ target
        # ROI — MASSIVELY weighted (v7: 100x — was 15x!)
        # 15% ROI = 1500pts, making ROI the PRIMARY driver
        score += roi * 100.0
        # R:R RATIO BONUS (v7 NEW — rewards better risk management)
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.001
        rr_ratio = avg_win / max(avg_loss, 0.001)
        if rr_ratio >= 2.0: score += 500.0      # Excellent R:R
        elif rr_ratio >= 1.5: score += 300.0    # Good R:R
        elif rr_ratio >= 1.0: score += 100.0    # Fair R:R
        elif rr_ratio < 0.5: score *= 0.3       # Terrible R:R → heavy penalty
        # PROFIT FACTOR (v7: boosted tiers)
        if profit_factor >= 2.0:
            score += 300.0
        elif profit_factor >= 1.5:
            score += 200.0
        elif profit_factor >= 1.2:
            score += 100.0
        elif profit_factor < 0.8:
            score *= 0.3  # v7: harsher penalty (was 0.5)
        # ROI FLOOR (v7 NEW): low ROI = heavy penalty
        if roi < 5.0:
            score *= 0.5   # Below 5% ROI — not worth it
        if roi < 0:
            score *= 0.2   # Losing money → near-zero
        # Sharpe (kept at 5.0)
        score += min(sharpe, 3.0) * 5.0
        # Drawdown penalty (kept at 5.0)
        score -= max_drawdown * 5.0
        # Trade count bonus (need ≥20 trades for full credit)
        score += min(n_trades / 20, 1.0) * 50
        # Reliability gate: <10 trades = divide by 10
        if n_trades < 10:
            score *= 0.1
    
    # Exit reason breakdown for debugging
    exit_reasons = {}
    for t in trades:
        r = t.get("exit_reason", "unknown")
        exit_reasons[r] = exit_reasons.get(r, 0) + 1
    
    return {
        "total_trades": n_trades,
        "win_rate": round(win_rate, 1),
        "roi": round(roi, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "profit_factor": round(profit_factor, 2),
        "score": round(score, 2),
        "exit_reasons": exit_reasons
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
    # v7: Enforce minimum R:R ratio — tp_min must be >= 50% of stop_floor
    if p["tp_min"] < p["stop_floor"] * 0.5:
        p["tp_min"] = round(p["stop_floor"] * 0.5, 6)
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
    # v7: Enforce minimum R:R ratio
    if child["tp_min"] < child["stop_floor"] * 0.5:
        child["tp_min"] = round(child["stop_floor"] * 0.5, 6)
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


def _detect_convergence(top: List[Dict]) -> bool:
    """v10: Detect if evolution has converged (top strategies too similar).
    Returns True if all top strategies are within 5% score spread."""
    if len(top) < 3:
        return False
    scores = [s.get("score", 0) for s in top if s.get("score", 0) > 0]
    if not scores:
        return True  # All zeros = definitely converged
    max_s = max(scores)
    min_s = min(scores)
    if max_s == 0:
        return True
    spread = (max_s - min_s) / max_s
    is_converged = spread < 0.05  # Less than 5% spread = converged
    if is_converged:
        logger.warning(f"⚠️ CONVERGENCE DETECTED: spread={spread:.3f} (max={max_s:.1f}, min={min_s:.1f}) → forcing 100% exploration")
    return is_converged


def generate_evolved_params() -> Dict:
    """
    v10 Bayesian-inspired evolutionary optimization — ANTI-STAGNATION:
    
    If convergence detected (top-10 within 5% spread):
    → 100% pure random exploration to escape local minimum
    
    Normal mode:
    - 15% Fine-tune: small Gaussian mutation of top parent
    - 10% Crossover + mutate: blend two parents
    - 20% Big mutation: large perturbation to escape local minimum  
    - 55% Pure exploration: random (v10: up from 45%)
    
    Score-proportional parent selection (roulette wheel).
    """
    top = get_top_strategies(10)
    
    if len(top) < 3:
        return generate_random_params()
    
    # v10: CONVERGENCE ESCAPE — if top strategies are too similar, go full random
    if _detect_convergence(top):
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
    
    if roll < 0.15:
        # FINE-TUNE: small Gaussian mutation
        parent = pick_parent()
        child = mutate_strategy(parent, mutation_rate=0.10)
        logger.info(f"FINE-TUNE parent score={parent.get('score',0):.1f}")
        return child
    elif roll < 0.25:
        # CROSSOVER + MUTATE: blend two parents, then small perturbation
        pa = pick_parent()
        pb = pick_parent()
        child = crossover(pa, pb)
        child = mutate_strategy(child, mutation_rate=0.08)
        logger.info(f"CROSSOVER+MUTATE {pa.get('score',0):.1f} x {pb.get('score',0):.1f}")
        return child
    elif roll < 0.45:
        # BIG MUTATION: jump out of local minimum
        parent = pick_parent()
        child = mutate_strategy(parent, mutation_rate=0.50)  # v10: bigger jump (was 0.40)
        logger.info(f"BIG MUTATE from score={parent.get('score',0):.1f}")
        return child
    else:
        # PURE EXPLORATION: v10 55% (was 45%)
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
        
        # v10: Random backtest period to diversify strategy scoring
        period = get_random_backtest_period()
        candles = fetch_historical_data(period)
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
        # CRITICAL: if kill-gate zeroed the test score, keep it at 0!
        # Don't let a high train score rescue a dead test strategy.
        if test_metrics["score"] <= 0:
            oos_score = 0.0  # Kill-gate says NO → final answer is NO
        else:
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
