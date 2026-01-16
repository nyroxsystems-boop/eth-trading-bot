"""
Multi-Timeframe Analysis Module
Analyzes multiple timeframes to improve signal quality
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
import pandas as pd

from src.core.market_data import MarketDataProvider
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TimeframeSignal:
    """Signal information for a single timeframe"""
    timeframe: str
    trend: bool  # True if bullish
    strength: float  # 0.0 to 1.0
    rsi: float
    ema_alignment: bool  # EMA20 > EMA50
    breakout: bool
    score: float  # Overall signal score


class MultiTimeframeAnalyzer:
    """Analyzes multiple timeframes for better signal quality"""
    
    def __init__(self, timeframes: Optional[List[str]] = None):
        """
        Initialize multi-timeframe analyzer
        
        Args:
            timeframes: List of timeframes to analyze (default: ["5m", "15m", "1h"])
        """
        self.config = get_config()
        self.market_data = MarketDataProvider()
        self.timeframes = timeframes or ["5m", "15m", "1h"]
        
        # Weights for each timeframe
        self.weights = {
            "5m": 0.40,   # Execution timeframe
            "15m": 0.35,  # Trend confirmation
            "1h": 0.25    # Major trend
        }
    
    def fetch_all_timeframes(
        self, 
        symbol: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for all configured timeframes
        
        Args:
            symbol: Trading pair (default from config)
            
        Returns:
            Dict mapping timeframe to DataFrame with indicators
        """
        symbol = symbol or self.config.trading.pair
        data = {}
        
        for tf in self.timeframes:
            try:
                # Fetch klines for this timeframe
                df = self.market_data.fetch_klines(
                    symbol=symbol,
                    interval=tf,
                    lookback=200  # Enough for indicators
                )
                
                # Add indicators
                df_with_indicators = self.market_data.add_indicators(df)
                
                data[tf] = df_with_indicators
                logger.debug(f"Fetched {tf} data: {len(df_with_indicators)} bars")
                
            except Exception as e:
                logger.warning(f"Failed to fetch {tf} data: {e}")
                continue
        
        return data
    
    def analyze_timeframe(
        self, 
        df: pd.DataFrame, 
        timeframe: str
    ) -> TimeframeSignal:
        """
        Analyze a single timeframe
        
        Args:
            df: DataFrame with indicators
            timeframe: Timeframe string (e.g., "5m")
            
        Returns:
            TimeframeSignal with analysis results
        """
        if len(df) < 20:
            logger.warning(f"Insufficient data for {timeframe}")
            return TimeframeSignal(
                timeframe=timeframe,
                trend=False,
                strength=0.0,
                rsi=50.0,
                ema_alignment=False,
                breakout=False,
                score=0.0
            )
        
        # Get latest values
        current = df.iloc[-1]
        
        # Extract indicators
        close = float(current["close"])
        ema20 = float(current["ema20"])
        ema50 = float(current["ema50"])
        rsi = float(current["rsi14"])
        hh20 = float(current["hh20"])
        
        # Trend analysis
        ema_alignment = ema20 > ema50
        trend_bullish = close > ema20 and ema_alignment
        
        # Trend strength (0-1)
        if ema_alignment:
            strength = min(1.0, (ema20 - ema50) / ema50 * 10)  # Normalize
        else:
            strength = 0.0
        
        # Breakout detection
        breakout = close > hh20 * 1.001
        
        # Calculate timeframe score
        score = 0.0
        if trend_bullish:
            score += 0.4
        if ema_alignment:
            score += 0.2
        if 40 <= rsi <= 70:
            score += 0.2
        if breakout:
            score += 0.2
        
        return TimeframeSignal(
            timeframe=timeframe,
            trend=trend_bullish,
            strength=strength,
            rsi=rsi,
            ema_alignment=ema_alignment,
            breakout=breakout,
            score=score
        )
    
    def aggregate_signals(
        self, 
        signals: Dict[str, TimeframeSignal]
    ) -> float:
        """
        Aggregate signals from multiple timeframes
        
        Args:
            signals: Dict mapping timeframe to TimeframeSignal
            
        Returns:
            Aggregated score boost (-0.2 to +0.2)
        """
        if not signals:
            return 0.0
        
        # Calculate weighted score
        weighted_score = 0.0
        total_weight = 0.0
        
        for tf, signal in signals.items():
            weight = self.weights.get(tf, 0.0)
            weighted_score += signal.score * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0
        
        avg_score = weighted_score / total_weight
        
        # Check alignment across timeframes
        all_bullish = all(s.trend for s in signals.values())
        all_bearish = all(not s.trend for s in signals.values())
        
        # Boost/penalty based on alignment
        if all_bullish:
            boost = 0.2  # Strong alignment bonus
        elif all_bearish:
            boost = -0.2  # Strong misalignment penalty
        else:
            # Partial alignment
            bullish_count = sum(1 for s in signals.values() if s.trend)
            if bullish_count >= 2:
                boost = 0.1  # Moderate alignment
            else:
                boost = -0.1  # Misalignment
        
        # Combine weighted score with alignment boost
        final_boost = (avg_score - 0.5) * 0.4 + boost
        
        # Clamp to [-0.2, +0.2]
        return max(-0.2, min(0.2, final_boost))
    
    def get_signal_summary(
        self, 
        signals: Dict[str, TimeframeSignal]
    ) -> str:
        """
        Get human-readable summary of multi-timeframe signals
        
        Args:
            signals: Dict mapping timeframe to TimeframeSignal
            
        Returns:
            Summary string
        """
        parts = []
        for tf, signal in signals.items():
            trend_str = "↑" if signal.trend else "↓"
            parts.append(f"{tf}:{trend_str}({signal.score:.2f})")
        
        return " | ".join(parts)
    
    def should_block_entry(
        self, 
        signals: Dict[str, TimeframeSignal]
    ) -> bool:
        """
        Check if entry should be blocked due to timeframe misalignment
        
        Args:
            signals: Dict mapping timeframe to TimeframeSignal
            
        Returns:
            True if entry should be blocked
        """
        # Block if all timeframes are bearish
        if all(not s.trend for s in signals.values()):
            logger.warning("MTF: All timeframes bearish - blocking entry")
            return True
        
        # Block if higher timeframes strongly bearish
        if "1h" in signals and "15m" in signals:
            if not signals["1h"].trend and not signals["15m"].trend:
                logger.warning("MTF: Higher timeframes bearish - blocking entry")
                return True
        
        return False
