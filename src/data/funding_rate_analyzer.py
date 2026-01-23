"""
Funding Rate Signal Module
Tracks Binance Futures perpetual funding rate as a contrarian indicator.
- Negative funding = Shorts pay Longs = Shorts overcrowded = BULLISH
- Positive funding = Longs pay Shorts = Longs overcrowded = BEARISH
"""

import os
import asyncio
import aiohttp
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Binance Futures API
BINANCE_FUTURES_URL = "https://fapi.binance.com"


@dataclass
class FundingSignal:
    """Funding rate analysis result"""
    timestamp: str
    symbol: str
    
    # Current funding
    current_rate: float  # e.g., 0.0001 = 0.01%
    current_rate_pct: float  # Percentage format
    
    # Historical context
    avg_rate_8h: float  # Average over last 8 hours
    avg_rate_24h: float  # Average over last 24 hours
    
    # Signal interpretation
    signal: str  # "bullish", "bearish", "neutral"
    signal_strength: float  # 0 to 1
    
    # Derived metrics
    funding_sentiment: str  # "shorts_crowded", "longs_crowded", "balanced"
    next_funding_time: str
    
    # Trading adjustment
    long_bias: float  # -1 to 1 (positive = favor longs)


class FundingRateAnalyzer:
    """
    Analyzes perpetual futures funding rate for sentiment.
    Funding rate is a contrarian indicator!
    """
    
    def __init__(self, symbol: str = "ETHUSDT"):
        self.symbol = symbol
        self._cache: Dict[str, FundingSignal] = {}
        self._cache_ttl_seconds = 60  # Cache for 1 minute
        
        # Thresholds for signals
        self.extreme_negative = -0.0003  # -0.03% = very shorts crowded
        self.negative_threshold = -0.0001  # -0.01% = shorts crowded
        self.positive_threshold = 0.0001  # +0.01% = longs crowded
        self.extreme_positive = 0.0003  # +0.03% = very longs crowded
    
    async def fetch_current_funding(self) -> Optional[Dict]:
        """Fetch current funding rate from Binance Futures"""
        try:
            url = f"{BINANCE_FUTURES_URL}/fapi/v1/premiumIndex"
            params = {"symbol": self.symbol}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=5) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Funding rate fetch failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Funding rate fetch error: {e}")
            return None
    
    async def fetch_funding_history(self, limit: int = 24) -> Optional[List]:
        """Fetch historical funding rates (each 8h = 3 per day)"""
        try:
            url = f"{BINANCE_FUTURES_URL}/fapi/v1/fundingRate"
            params = {"symbol": self.symbol, "limit": limit}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=5) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return None
        except Exception as e:
            logger.error(f"Funding history fetch error: {e}")
            return None
    
    def interpret_funding(self, rate: float) -> tuple:
        """
        Interpret funding rate as contrarian signal.
        Returns (signal, sentiment, strength)
        """
        if rate <= self.extreme_negative:
            return "bullish", "shorts_crowded", 1.0
        elif rate <= self.negative_threshold:
            return "bullish", "shorts_crowded", 0.6
        elif rate >= self.extreme_positive:
            return "bearish", "longs_crowded", 1.0
        elif rate >= self.positive_threshold:
            return "bearish", "longs_crowded", 0.6
        else:
            return "neutral", "balanced", 0.3
    
    async def analyze(self) -> Optional[FundingSignal]:
        """
        Full funding rate analysis.
        Returns signal with historical context.
        """
        # Check cache
        cache_key = self.symbol
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            cached_time = datetime.fromisoformat(cached.timestamp)
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl_seconds:
                return cached
        
        # Fetch current and historical data
        current_data = await self.fetch_current_funding()
        history = await self.fetch_funding_history(limit=9)  # 3 days
        
        if not current_data:
            return None
        
        current_rate = float(current_data.get("lastFundingRate", 0))
        next_funding = current_data.get("nextFundingTime", 0)
        
        # Calculate historical averages
        if history and len(history) >= 3:
            rates = [float(h.get("fundingRate", 0)) for h in history]
            avg_8h = rates[0] if len(rates) >= 1 else current_rate  # Last rate
            avg_24h = np.mean(rates[:3]) if len(rates) >= 3 else current_rate  # Last 3 periods
        else:
            avg_8h = current_rate
            avg_24h = current_rate
        
        # Interpret signal
        signal, sentiment, strength = self.interpret_funding(current_rate)
        
        # Calculate long bias (-1 to 1)
        # Negative funding = bullish for longs
        long_bias = -current_rate * 1000  # Scale: -0.001 becomes +1.0
        long_bias = max(min(long_bias, 1.0), -1.0)  # Clamp
        
        # Next funding time
        next_time = datetime.fromtimestamp(next_funding / 1000).isoformat() if next_funding else "unknown"
        
        funding_signal = FundingSignal(
            timestamp=datetime.now().isoformat(),
            symbol=self.symbol,
            current_rate=current_rate,
            current_rate_pct=round(current_rate * 100, 4),
            avg_rate_8h=round(avg_8h, 6),
            avg_rate_24h=round(avg_24h, 6),
            signal=signal,
            signal_strength=strength,
            funding_sentiment=sentiment,
            next_funding_time=next_time,
            long_bias=round(long_bias, 3)
        )
        
        # Cache result
        self._cache[cache_key] = funding_signal
        
        logger.info(f"Funding: {current_rate*100:+.4f}% ({sentiment}) | signal={signal} | bias={long_bias:+.2f}")
        
        return funding_signal
    
    def get_trading_adjustment(self, signal: FundingSignal) -> Dict:
        """
        Get trading adjustment based on funding.
        Returns multipliers for the main strategy.
        """
        adjustment = {
            "long_multiplier": 1.0,  # Multiply long signal by this
            "short_multiplier": 1.0,  # For future short capability
            "confidence_boost": 0.0,
            "reason": ""
        }
        
        if signal.signal == "bullish":
            # Shorts crowded = boost long signals
            adjustment["long_multiplier"] = 1.0 + (signal.signal_strength * 0.3)
            adjustment["confidence_boost"] = signal.signal_strength * 0.1
            adjustment["reason"] = f"Funding bullish ({signal.current_rate_pct:+.3f}%) - shorts crowded"
        
        elif signal.signal == "bearish":
            # Longs crowded = reduce long signals
            adjustment["long_multiplier"] = 1.0 - (signal.signal_strength * 0.2)
            adjustment["confidence_boost"] = -signal.signal_strength * 0.1
            adjustment["reason"] = f"Funding bearish ({signal.current_rate_pct:+.3f}%) - longs crowded"
        
        else:
            adjustment["reason"] = "Funding neutral"
        
        return adjustment


# Singleton instance
_funding_analyzer: Optional[FundingRateAnalyzer] = None

def get_funding_analyzer(symbol: str = "ETHUSDT") -> FundingRateAnalyzer:
    """Get or create funding analyzer instance"""
    global _funding_analyzer
    if _funding_analyzer is None or _funding_analyzer.symbol != symbol:
        _funding_analyzer = FundingRateAnalyzer(symbol)
    return _funding_analyzer


# Quick test
if __name__ == "__main__":
    async def test():
        analyzer = get_funding_analyzer("ETHUSDT")
        signal = await analyzer.analyze()
        
        if signal:
            print(f"\n💰 Funding Rate Analysis ({signal.symbol}):")
            print(f"   Current Rate: {signal.current_rate_pct:+.4f}%")
            print(f"   8h Average: {signal.avg_rate_8h*100:+.4f}%")
            print(f"   24h Average: {signal.avg_rate_24h*100:+.4f}%")
            print(f"   Signal: {signal.signal.upper()} ({signal.funding_sentiment})")
            print(f"   Strength: {signal.signal_strength:.0%}")
            print(f"   Long Bias: {signal.long_bias:+.2f}")
            print(f"   Next Funding: {signal.next_funding_time}")
            
            adjustment = analyzer.get_trading_adjustment(signal)
            print(f"\n   Trading Adjustment: {adjustment}")
    
    asyncio.run(test())
