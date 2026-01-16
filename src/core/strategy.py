"""
Trading Strategy Module
Handles entry/exit signals, scoring, and regime detection
"""
import pandas as pd
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

from src.utils.config import get_config
from src.utils.logger import get_logger
from src.core.market_data import MarketDataProvider
from src.core.ml_engine import MLEngine

logger = get_logger(__name__)


@dataclass
class RegimeInfo:
    """Market regime information"""
    adx: float
    trend_ok: bool
    vol_ok: bool


@dataclass
class SignalInfo:
    """Trading signal information"""
    score: float
    breakout: bool
    drawdown: bool
    trend: bool
    rsi_ok: bool
    oversold: bool
    secondary: bool
    ml_prob: float


class TradingStrategy:
    """Trading strategy for entry/exit signals"""
    
    def __init__(self, market_data: MarketDataProvider, ml_engine: MLEngine):
        self.config = get_config()
        self.market_data = market_data
        self.ml_engine = ml_engine
        self.sentiment_score = 0.0
    
    def compute_regime(self, df: pd.DataFrame) -> RegimeInfo:
        """
        Compute market regime (trend strength, volatility)
        
        Args:
            df: DataFrame with indicators
            
        Returns:
            RegimeInfo with regime characteristics
        """
        # Calculate ADX for trend strength
        adx_value = self.market_data.calculate_adx(df)
        
        # Volatility regime: current ATR vs median
        atr_series = df["atr"].iloc[-200:] if len(df) >= 200 else df["atr"]
        atr_median = float(atr_series.median()) if len(atr_series) > 0 else 0.0
        atr_current = float(df["atr"].iloc[-1]) if len(df) > 0 else 0.0
        
        vol_ok = atr_current >= atr_median if atr_median > 0 else True
        trend_ok = (adx_value >= self.config.regime.adx_min_trend) if self.config.regime.use_adx_filter else True
        
        return RegimeInfo(
            adx=adx_value,
            trend_ok=trend_ok,
            vol_ok=vol_ok
        )
    
    def calculate_entry_signal(
        self,
        current_row: pd.Series,
        previous_row: pd.Series,
        regime: RegimeInfo,
        use_mtf: bool = True
    ) -> SignalInfo:
        """
        Calculate entry signal score and components
        
        Args:
            current_row: Current candle data with indicators
            previous_row: Previous candle data
            regime: Current market regime
            use_mtf: Use multi-timeframe analysis (default: True)
            
        Returns:
            SignalInfo with signal components and score
        """
        # Extract values
        px = float(current_row["close"])
        ema20 = float(current_row["ema20"])
        ema50 = float(current_row["ema50"])
        rsi14 = float(current_row["rsi14"])
        hh20 = float(current_row["hh20"])
        bb_lo = float(current_row["bb_lo"])
        
        # Signal components
        drawdown_ok = self.market_data.is_drawdown_candle(previous_row)
        breakout_ok = px > hh20 * (1.0 + self.config.trading.breakout_pct)
        trend_ok = (px > ema20) and (ema20 > ema50)
        rsi_ok = (self.config.trading.rsi_min <= rsi14 <= self.config.trading.rsi_max)
        
        # Oversold rebound signal
        oversold_ok = (
            rsi14 <= max(40.0, self.config.trading.rsi_min) and
            drawdown_ok and
            px >= bb_lo * 1.0005
        )
        
        # ML prediction
        ml_prob = self.ml_engine.predict(current_row)
        
        # Secondary confirmation
        secondary_ok = (
            trend_ok and
            rsi14 >= self.config.trading.rsi_min and
            ml_prob >= self.config.trading.sec_pml_min and
            px > ema20
        )
        
        # ADX bonus for strong trends
        adx_bonus = 0.0
        if regime.trend_ok:
            adx_bonus = max(0.0, min((regime.adx - 20.0) / 400.0, 0.15))
        
        # Sentiment and ML boost
        boost = (ml_prob - 0.5) * 0.4 + (self.sentiment_score * 0.1) + adx_bonus
        
        # Multi-timeframe boost (NEW!)
        mtf_boost = 0.0
        if use_mtf:
            try:
                from src.core.multi_timeframe import MultiTimeframeAnalyzer
                
                mtf_analyzer = MultiTimeframeAnalyzer()
                mtf_data = mtf_analyzer.fetch_all_timeframes()
                
                if mtf_data:
                    mtf_signals = {
                        tf: mtf_analyzer.analyze_timeframe(df, tf)
                        for tf, df in mtf_data.items()
                    }
                    mtf_boost = mtf_analyzer.aggregate_signals(mtf_signals)
                    
                    logger.debug(f"MTF boost: {mtf_boost:+.3f} | {mtf_analyzer.get_signal_summary(mtf_signals)}")
            except Exception as e:
                logger.warning(f"MTF analysis failed: {e}")
        
        # Calculate weighted score
        score = (
            0.32 * (1.0 if breakout_ok else 0.0) +
            0.18 * (1.0 if drawdown_ok else 0.0) +
            0.16 * (1.0 if trend_ok else 0.0) +
            0.06 * (1.0 if rsi_ok else 0.0) +
            0.18 * (1.0 if oversold_ok else 0.0) +
            0.05 * (1.0 if secondary_ok else 0.0) +
            0.05 * (1.0 if regime.vol_ok else 0.0) +
            boost +
            mtf_boost  # Add MTF boost
        )
        
        return SignalInfo(
            score=score,
            breakout=breakout_ok,
            drawdown=drawdown_ok,
            trend=trend_ok,
            rsi_ok=rsi_ok,
            oversold=oversold_ok,
            secondary=secondary_ok,
            ml_prob=ml_prob
        )
    
    def should_enter_long(
        self,
        signal: SignalInfo,
        regime: RegimeInfo
    ) -> Tuple[bool, str]:
        """
        Determine if should enter long position
        
        Args:
            signal: Signal information
            regime: Regime information
            
        Returns:
            Tuple of (should_enter, reason)
        """
        # Check regime filters
        if not (regime.trend_ok or regime.vol_ok):
            return False, f"regime_filter (adx={regime.adx:.1f})"
        
        # Oversold fast-lane entry (lower threshold)
        if signal.oversold and signal.score >= 0.32:
            return True, "oversold_fast_lane"
        
        # Standard entry
        if signal.score >= self.config.trading.entry_score_min:
            return True, "standard_entry"
        
        return False, f"score_too_low ({signal.score:.2f})"
    
    def update_sentiment(self, score: float):
        """Update sentiment score from external source"""
        self.sentiment_score = max(min(score, 0.5), -0.5)
    
    def get_signal_description(self, signal: SignalInfo) -> str:
        """Get human-readable signal description"""
        components = []
        if signal.breakout:
            components.append("breakout")
        if signal.drawdown:
            components.append("drawdown")
        if signal.trend:
            components.append("trend")
        if signal.oversold:
            components.append("oversold")
        if signal.secondary:
            components.append("secondary")
        
        return f"score={signal.score:.2f} ml={signal.ml_prob:.2f} [{', '.join(components)}]"
