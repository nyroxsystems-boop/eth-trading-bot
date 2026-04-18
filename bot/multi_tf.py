"""
Multi-Timeframe Analyzer — v3 adaptation.

Checks 5m, 15m, 1h timeframes to confirm trend alignment.
Returns a score boost/penalty (-0.2 to +0.2) for the main signal.
"""
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from bot.executor import fetch_klines
from bot.signals import add_indicators

logger = logging.getLogger("ethbot.mtf")


@dataclass
class TimeframeSignal:
    timeframe: str
    trend: bool       # True if bullish
    strength: float   # 0.0 to 1.0
    rsi: float
    ema_aligned: bool # EMA20 > EMA50
    score: float


# Module-level cache
_cache: Dict[str, pd.DataFrame] = {}
_cache_ts: Dict[str, float] = {}
_CACHE_TTL = 120  # 2 minutes


def analyze_timeframe(df: pd.DataFrame, tf: str) -> TimeframeSignal:
    """Analyze a single timeframe."""
    if len(df) < 20:
        return TimeframeSignal(tf, False, 0.0, 50.0, False, 0.0)

    row = df.iloc[-1]
    close = float(row["close"])
    ema20 = float(row["ema20"])
    ema50 = float(row["ema50"])
    rsi = float(row["rsi14"])

    ema_aligned = ema20 > ema50
    trend = close > ema20 and ema_aligned
    strength = min(1.0, max(0, (ema20 - ema50) / ema50 * 10)) if ema_aligned else 0.0

    score = 0.0
    if trend:
        score += 0.4
    if ema_aligned:
        score += 0.2
    if 35 <= rsi <= 70:
        score += 0.2
    if close > float(row.get("hh20", close)):
        score += 0.2

    return TimeframeSignal(tf, trend, strength, rsi, ema_aligned, score)


def get_mtf_boost(pair: str = "ETHUSDT", timeframes: List[str] = None) -> float:
    """
    Get multi-timeframe alignment boost.

    Returns: float in [-0.2, +0.2]
        +0.2 = all timeframes bullish (strong confirmation)
        -0.2 = all timeframes bearish (avoid entry)
         0.0 = mixed signals
    """
    timeframes = timeframes or ["5m", "15m", "1h"]
    weights = {"5m": 0.40, "15m": 0.35, "1h": 0.25}

    signals: Dict[str, TimeframeSignal] = {}

    for tf in timeframes:
        key = f"{pair}_{tf}"
        now = time.time()

        # Check cache
        if key in _cache and (now - _cache_ts.get(key, 0)) < _CACHE_TTL:
            df = _cache[key]
        else:
            try:
                df = fetch_klines(pair, tf, lookback=200)
                df = add_indicators(df)
                _cache[key] = df
                _cache_ts[key] = now
            except Exception as e:
                logger.warning(f"MTF {tf} fetch failed: {e}")
                if key in _cache:
                    df = _cache[key]  # Stale cache
                else:
                    continue

        signals[tf] = analyze_timeframe(df, tf)

    if not signals:
        return 0.0

    # Weighted average
    weighted = sum(signals[tf].score * weights.get(tf, 0.3) for tf in signals)
    total_w = sum(weights.get(tf, 0.3) for tf in signals)
    avg = weighted / total_w if total_w > 0 else 0.5

    # Alignment bonus
    all_bull = all(s.trend for s in signals.values())
    all_bear = all(not s.trend for s in signals.values())

    if all_bull:
        boost = 0.2
    elif all_bear:
        boost = -0.2
    else:
        bull_count = sum(1 for s in signals.values() if s.trend)
        boost = 0.1 if bull_count >= 2 else -0.1

    final = (avg - 0.5) * 0.4 + boost
    final = max(-0.2, min(0.2, final))

    summary = " | ".join(f"{tf}:{'↑' if s.trend else '↓'}({s.score:.2f})" for tf, s in signals.items())
    logger.info(f"MTF: {summary} → boost={final:+.3f}")

    return round(final, 4)
