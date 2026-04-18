"""
Signal Engine — Clean signal calculation.
Takes OHLCV data, computes indicators, returns a clear BUY/HOLD decision.
No globals, no side effects, pure functions.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List

from ta.volatility import AverageTrueRange, BollingerBands
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator


@dataclass
class Signal:
    """Result of signal computation."""
    score: float           # 0.0 - 1.0  (higher = stronger buy)
    should_buy: bool       # Final decision
    signals: List[str]     # Active signal names
    ml_confidence: float   # ML prediction (0-1)
    rsi: float
    atr: float
    atr_pct: float         # ATR as % of price
    adx: float
    price: float
    regime: str            # "trending" | "ranging" | "volatile"


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicators to OHLCV DataFrame."""
    out = df.copy()

    # Returns
    out["ret1"] = out["close"].pct_change()

    # EMAs
    out["ema20"] = EMAIndicator(out["close"], 20).ema_indicator()
    out["ema50"] = EMAIndicator(out["close"], 50).ema_indicator()

    # MACD
    macd = MACD(out["close"], window_slow=26, window_fast=12, window_sign=9)
    out["macd"] = macd.macd()
    out["macd_sig"] = macd.macd_signal()

    # RSI
    out["rsi14"] = RSIIndicator(out["close"], 14).rsi()

    # ATR
    atr = AverageTrueRange(out["high"], out["low"], out["close"], window=14)
    out["atr"] = atr.average_true_range()

    # Bollinger Bands
    bb = BollingerBands(out["close"], window=20, window_dev=2)
    out["bb_hi"] = bb.bollinger_hband()
    out["bb_lo"] = bb.bollinger_lband()

    # High/Low channels
    out["hh20"] = out["high"].rolling(20).max()
    out["ll20"] = out["low"].rolling(20).min()

    # Volume ratio
    vol_med = out["volume"].rolling(20).median()
    out["volume_ratio"] = out["volume"] / vol_med.clip(lower=1e-9)

    # ADX
    try:
        out["adx14"] = ADXIndicator(out["high"], out["low"], out["close"], window=14).adx()
    except Exception:
        out["adx14"] = 25.0

    # VWAP (session-anchored: rolling 48-bar ≈ 4h on 5m)
    typical_price = (out["high"] + out["low"] + out["close"]) / 3.0
    cum_vol = out["volume"].rolling(48).sum()
    cum_tp_vol = (typical_price * out["volume"]).rolling(48).sum()
    out["vwap"] = cum_tp_vol / cum_vol.clip(lower=1e-9)
    out["vwap_dev"] = (out["close"] - out["vwap"]) / out["vwap"].clip(lower=1e-9)  # % deviation

    out.dropna(inplace=True)
    return out


def detect_regime(adx: float, atr_pct: float) -> str:
    """Classify market regime from ADX and ATR."""
    if atr_pct > 0.015:  # ATR > 1.5% of price
        return "volatile"
    elif adx >= 25:
        return "trending"
    else:
        return "ranging"


def compute_tp(regime: str, rsi: float, atr_pct: float, tp_min: float, tp_max: float) -> float:
    """Compute take-profit based on regime."""
    if regime == "trending":
        base = tp_max * 1.3 if rsi < 70 else tp_max * 1.5
    elif regime == "ranging":
        base = tp_min
    elif regime == "volatile":
        base = max(tp_max, atr_pct * 1.5)
    else:
        base = tp_max if rsi >= 70 else tp_min

    return max(tp_min * 0.8, min(base, 0.06))


def compute_signals(
    df: pd.DataFrame,
    entry_score_min: float = 0.20,
    rsi_min: float = 30.0,
    rsi_max: float = 75.0,
    ml_confidence: float = 0.5,
    ml_threshold: float = 0.52,
    breakout_pct: float = 0.0005,
) -> Signal:
    """
    Compute entry signal from indicator DataFrame.

    This is the CORE decision logic. Clean, readable, debuggable.
    Returns a Signal object with score, decision, and metadata.
    """
    if len(df) < 20:
        return Signal(
            score=0.0, should_buy=False, signals=[], ml_confidence=ml_confidence,
            rsi=50, atr=0, atr_pct=0, adx=20, price=0, regime="unknown"
        )

    row = df.iloc[-1]
    prev = df.iloc[-2]
    px = float(row["close"])
    ema20 = float(row["ema20"])
    ema50 = float(row["ema50"])
    rsi14 = float(row["rsi14"])
    atr = float(row["atr"])
    atr_pct = atr / max(px, 1) if px > 0 else 0
    adx = float(row.get("adx14", 20))
    hh20 = float(row["hh20"])
    bb_lo = float(row["bb_lo"])
    macd_val = float(row["macd"])
    macd_sig_val = float(row["macd_sig"])

    regime = detect_regime(adx, atr_pct)
    active_signals = []
    score = 0.0

    # ===== SIGNAL CHECKS =====

    # 1. Breakout: price above 20-bar high
    breakout = px > hh20 * (1.0 + breakout_pct)
    if breakout:
        score += 0.20
        active_signals.append("BREAKOUT")

    # 2. Trend alignment: price > EMA20 > EMA50
    trend = (px > ema20) and (ema20 > ema50)
    if trend:
        score += 0.15
        active_signals.append("TREND")

    # 3. RSI in range (not overbought, not too oversold)
    rsi_ok = rsi_min <= rsi14 <= rsi_max
    if rsi_ok:
        score += 0.05
        active_signals.append("RSI_OK")

    # 4. Oversold bounce: RSI < 35 + price near lower BB
    oversold = (rsi14 < 35) and (px <= bb_lo * 1.005)
    if oversold:
        score += 0.20
        active_signals.append("OVERSOLD")

    # 5. MACD crossover: MACD just crossed above signal line
    prev_macd = float(prev["macd"]) if "macd" in prev.index else 0
    prev_macd_sig = float(prev["macd_sig"]) if "macd_sig" in prev.index else 0
    macd_cross = (macd_val > macd_sig_val) and (prev_macd <= prev_macd_sig)
    if macd_cross:
        score += 0.15
        active_signals.append("MACD_CROSS")

    # 6. BB bounce: price near lower Bollinger Band
    bb_bounce = (px <= bb_lo * 1.003) and (rsi14 < 45)
    if bb_bounce:
        score += 0.10
        active_signals.append("BB_BOUNCE")

    # 7. Volume confirmation
    vol_ratio = float(row.get("volume_ratio", 1.0))
    vol_ok = vol_ratio >= 1.0
    if vol_ok:
        score += 0.05
        active_signals.append("VOLUME")

    # 8. ML confidence bonus/penalty
    if ml_confidence > ml_threshold:
        ml_bonus = min(0.15, (ml_confidence - 0.5) * 0.3)
        score += ml_bonus
        active_signals.append(f"ML({ml_confidence:.2f})")
    elif ml_confidence < 0.40:
        score -= 0.10  # ML is bearish

    # 9. ADX trend strength bonus
    if adx > 25:
        score += min(0.10, (adx - 20) / 200)
        active_signals.append("ADX_STRONG")

    # 10. VWAP Reversion: price below VWAP → mean reversion buy
    vwap_dev = float(row.get("vwap_dev", 0.0))
    if vwap_dev < -0.005:  # Price > 0.5% below VWAP
        vwap_bonus = min(0.15, abs(vwap_dev) * 10)
        score += vwap_bonus
        active_signals.append(f"VWAP({vwap_dev*100:+.1f}%)")

    # ===== FINAL DECISION =====
    should_buy = score >= entry_score_min and len(active_signals) >= 2

    return Signal(
        score=round(score, 4),
        should_buy=should_buy,
        signals=active_signals,
        ml_confidence=ml_confidence,
        rsi=rsi14,
        atr=atr,
        atr_pct=atr_pct,
        adx=adx,
        price=px,
        regime=regime,
    )
