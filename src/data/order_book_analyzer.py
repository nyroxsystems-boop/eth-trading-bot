"""
Order Book Depth Analysis Module
Analyzes Binance L2 order book for market microstructure signals.
Features:
- Bid/Ask Wall Detection
- Order Imbalance Calculation
- Absorption Rate Analysis
- Large Order Detection
"""

import os
import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Configuration
BINANCE_API_URL = "https://api.binance.com"
ORDER_BOOK_DEPTH = 100  # Number of levels to analyze


@dataclass
class OrderBookSignal:
    """Order book analysis result"""
    timestamp: str
    symbol: str
    
    # Imbalance metrics (-1 to 1, positive = more bids/bullish)
    imbalance_ratio: float
    imbalance_signal: str  # "bullish", "bearish", "neutral"
    
    # Wall detection
    bid_wall_price: Optional[float]
    bid_wall_size: Optional[float]
    ask_wall_price: Optional[float]
    ask_wall_size: Optional[float]
    
    # Spread analysis
    spread_bps: float  # Spread in basis points
    mid_price: float
    
    # Large order detection
    large_bids_count: int
    large_asks_count: int
    
    # Overall signal strength (0 to 1)
    signal_strength: float


class OrderBookAnalyzer:
    """
    Analyzes order book depth for trading signals.
    Professional market makers use this for edge.
    """
    
    def __init__(self, symbol: str = "ETHUSDT"):
        self.symbol = symbol
        self.wall_threshold_multiplier = 5.0  # Wall = 5x average size
        self.large_order_multiplier = 3.0  # Large = 3x average
        self._cache: Dict[str, OrderBookSignal] = {}
        self._cache_ttl_seconds = 5  # Cache for 5 seconds
    
    async def fetch_order_book(self, limit: int = ORDER_BOOK_DEPTH) -> Optional[Dict]:
        """Fetch L2 order book from Binance"""
        try:
            url = f"{BINANCE_API_URL}/api/v3/depth"
            params = {"symbol": self.symbol, "limit": limit}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=5) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Order book fetch failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Order book fetch error: {e}")
            return None
    
    def calculate_imbalance(self, bids: List, asks: List, levels: int = 20) -> float:
        """
        Calculate order book imbalance.
        Positive = more bid volume (bullish pressure)
        Negative = more ask volume (bearish pressure)
        """
        # Sum up bid and ask volumes for top N levels
        bid_volume = sum(float(bid[1]) for bid in bids[:levels])
        ask_volume = sum(float(ask[1]) for ask in asks[:levels])
        
        total = bid_volume + ask_volume
        if total == 0:
            return 0.0
        
        # Imbalance ratio: -1 (all asks) to +1 (all bids)
        imbalance = (bid_volume - ask_volume) / total
        return round(imbalance, 4)
    
    def detect_walls(self, orders: List, is_bid: bool) -> Tuple[Optional[float], Optional[float]]:
        """
        Detect large walls (support/resistance clusters).
        Returns (price, size) of the largest wall within reasonable distance.
        """
        if not orders:
            return None, None
        
        sizes = [float(o[1]) for o in orders[:50]]
        if not sizes:
            return None, None
        
        avg_size = np.mean(sizes)
        threshold = avg_size * self.wall_threshold_multiplier
        
        # Find the first wall
        for order in orders[:50]:
            price = float(order[0])
            size = float(order[1])
            
            if size >= threshold:
                return price, size
        
        return None, None
    
    def count_large_orders(self, orders: List) -> int:
        """Count number of orders significantly larger than average"""
        if not orders:
            return 0
        
        sizes = [float(o[1]) for o in orders[:50]]
        if not sizes:
            return 0
        
        avg_size = np.mean(sizes)
        threshold = avg_size * self.large_order_multiplier
        
        return sum(1 for o in orders[:50] if float(o[1]) >= threshold)
    
    async def analyze(self) -> Optional[OrderBookSignal]:
        """
        Full order book analysis.
        Returns comprehensive signal with all metrics.
        """
        # Check cache
        cache_key = self.symbol
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            cached_time = datetime.fromisoformat(cached.timestamp)
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl_seconds:
                return cached
        
        # Fetch fresh data
        order_book = await self.fetch_order_book()
        if not order_book:
            return None
        
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])
        
        if not bids or not asks:
            return None
        
        # Calculate metrics
        imbalance = self.calculate_imbalance(bids, asks)
        
        # Imbalance signal interpretation
        if imbalance > 0.15:
            imbalance_signal = "bullish"
        elif imbalance < -0.15:
            imbalance_signal = "bearish"
        else:
            imbalance_signal = "neutral"
        
        # Wall detection
        bid_wall_price, bid_wall_size = self.detect_walls(bids, is_bid=True)
        ask_wall_price, ask_wall_size = self.detect_walls(asks, is_bid=False)
        
        # Spread calculation
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid_price = (best_bid + best_ask) / 2
        spread_bps = ((best_ask - best_bid) / mid_price) * 10000
        
        # Large order counts
        large_bids = self.count_large_orders(bids)
        large_asks = self.count_large_orders(asks)
        
        # Signal strength (0 to 1)
        # Higher imbalance = stronger signal
        signal_strength = min(abs(imbalance) * 2, 1.0)
        
        # Boost signal if walls align with imbalance
        if imbalance > 0 and bid_wall_size and (ask_wall_size is None or bid_wall_size > ask_wall_size):
            signal_strength = min(signal_strength * 1.3, 1.0)
        elif imbalance < 0 and ask_wall_size and (bid_wall_size is None or ask_wall_size > bid_wall_size):
            signal_strength = min(signal_strength * 1.3, 1.0)
        
        signal = OrderBookSignal(
            timestamp=datetime.now().isoformat(),
            symbol=self.symbol,
            imbalance_ratio=imbalance,
            imbalance_signal=imbalance_signal,
            bid_wall_price=bid_wall_price,
            bid_wall_size=bid_wall_size,
            ask_wall_price=ask_wall_price,
            ask_wall_size=ask_wall_size,
            spread_bps=round(spread_bps, 2),
            mid_price=round(mid_price, 2),
            large_bids_count=large_bids,
            large_asks_count=large_asks,
            signal_strength=round(signal_strength, 3)
        )
        
        # Cache result
        self._cache[cache_key] = signal
        
        logger.info(f"Order Book: imbalance={imbalance:+.2f} ({imbalance_signal}) | "
                   f"strength={signal_strength:.1%} | spread={spread_bps:.1f}bps")
        
        return signal
    
    def get_trading_bias(self, signal: OrderBookSignal) -> Dict:
        """
        Convert order book signal to trading bias.
        Returns adjustment factors for the main strategy.
        """
        bias = {
            "direction": 0,  # -1 to 1
            "confidence": signal.signal_strength,
            "should_trade": True,
            "reason": ""
        }
        
        if signal.imbalance_signal == "bullish":
            bias["direction"] = signal.imbalance_ratio
            bias["reason"] = f"Order book bullish (imbalance: {signal.imbalance_ratio:+.2f})"
        elif signal.imbalance_signal == "bearish":
            bias["direction"] = signal.imbalance_ratio
            bias["reason"] = f"Order book bearish (imbalance: {signal.imbalance_ratio:+.2f})"
        else:
            bias["direction"] = 0
            bias["reason"] = "Order book neutral"
        
        # Wide spread = low liquidity = be careful
        if signal.spread_bps > 10:
            bias["confidence"] *= 0.7
            bias["reason"] += " | Wide spread warning"
        
        return bias


# Singleton instance
_order_book_analyzer: Optional[OrderBookAnalyzer] = None

def get_order_book_analyzer(symbol: str = "ETHUSDT") -> OrderBookAnalyzer:
    """Get or create order book analyzer instance"""
    global _order_book_analyzer
    if _order_book_analyzer is None or _order_book_analyzer.symbol != symbol:
        _order_book_analyzer = OrderBookAnalyzer(symbol)
    return _order_book_analyzer


# Quick test
if __name__ == "__main__":
    async def test():
        analyzer = get_order_book_analyzer("ETHUSDT")
        signal = await analyzer.analyze()
        
        if signal:
            print(f"\n📊 Order Book Analysis ({signal.symbol}):")
            print(f"   Imbalance: {signal.imbalance_ratio:+.2f} ({signal.imbalance_signal})")
            print(f"   Strength: {signal.signal_strength:.1%}")
            print(f"   Mid Price: ${signal.mid_price:,.2f}")
            print(f"   Spread: {signal.spread_bps:.1f} bps")
            print(f"   Bid Wall: ${signal.bid_wall_price:,.2f} ({signal.bid_wall_size:.2f})" if signal.bid_wall_price else "   Bid Wall: None")
            print(f"   Ask Wall: ${signal.ask_wall_price:,.2f} ({signal.ask_wall_size:.2f})" if signal.ask_wall_price else "   Ask Wall: None")
            print(f"   Large Bids: {signal.large_bids_count}, Large Asks: {signal.large_asks_count}")
            
            bias = analyzer.get_trading_bias(signal)
            print(f"\n   Trading Bias: {bias}")
    
    asyncio.run(test())
