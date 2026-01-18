"""
On-Chain Metrics Analyzer
Fetches and analyzes blockchain data for trading signals
"""

import os
import asyncio
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import aiohttp

# Configuration
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
GLASSNODE_API_KEY = os.getenv("GLASSNODE_API_KEY", "")


@dataclass
class WhaleTransaction:
    """Large transaction on-chain"""
    tx_hash: str
    from_address: str
    to_address: str
    value_eth: float
    value_usd: float
    timestamp: str
    transaction_type: str  # "accumulation" or "distribution"


@dataclass
class OnChainMetrics:
    """Aggregated on-chain metrics"""
    gas_price_gwei: float
    gas_price_trend: str  # "rising", "falling", "stable"
    active_addresses_24h: int
    active_addresses_change: float  # % change vs 7d avg
    exchange_inflow_eth: float
    exchange_outflow_eth: float
    net_flow: float  # negative = accumulation (bullish)
    whale_transactions: List[WhaleTransaction]
    whale_sentiment: str  # "accumulating", "distributing", "neutral"
    overall_signal: str  # "bullish", "bearish", "neutral"
    signal_strength: float  # 0.0 to 1.0
    timestamp: str


class OnChainAnalyzer:
    """
    Analyze on-chain metrics for trading signals
    - Gas prices (network activity)
    - Whale movements
    - Exchange flows
    - Active addresses
    """
    
    def __init__(self):
        self.etherscan_base = "https://api.etherscan.io/api"
        self._cache: Dict[str, any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)
    
    async def get_gas_price(self) -> Dict:
        """Get current gas price from Etherscan"""
        if not ETHERSCAN_API_KEY:
            return self._mock_gas_data()
        
        try:
            params = {
                "module": "gastracker",
                "action": "gasoracle",
                "apikey": ETHERSCAN_API_KEY
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.etherscan_base, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data["status"] == "1":
                            result = data["result"]
                            return {
                                "low": float(result.get("SafeGasPrice", 20)),
                                "average": float(result.get("ProposeGasPrice", 25)),
                                "high": float(result.get("FastGasPrice", 35)),
                                "base_fee": float(result.get("suggestBaseFee", 20))
                            }
            
            return self._mock_gas_data()
            
        except Exception as e:
            print(f"❌ Gas price error: {e}")
            return self._mock_gas_data()
    
    def _mock_gas_data(self) -> Dict:
        """Mock gas data for testing"""
        import random
        base = random.uniform(15, 45)
        return {
            "low": round(base * 0.8, 1),
            "average": round(base, 1),
            "high": round(base * 1.3, 1),
            "base_fee": round(base * 0.9, 1)
        }
    
    async def get_whale_transactions(self, min_value_eth: float = 1000) -> List[WhaleTransaction]:
        """
        Get recent large ETH transactions
        In production: Use Etherscan internal transactions API or Whale Alert
        """
        # Mock data for demonstration
        import random
        
        transactions = []
        num_txs = random.randint(3, 8)
        
        for i in range(num_txs):
            value = random.uniform(min_value_eth, min_value_eth * 10)
            is_accumulation = random.random() > 0.5
            
            transactions.append(WhaleTransaction(
                tx_hash=f"0x{''.join(random.choices('0123456789abcdef', k=64))}",
                from_address=f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                to_address=f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                value_eth=round(value, 2),
                value_usd=round(value * 3200, 2),  # Approximate USD
                timestamp=datetime.now().isoformat(),
                transaction_type="accumulation" if is_accumulation else "distribution"
            ))
        
        return transactions
    
    async def get_exchange_flows(self) -> Dict:
        """
        Get exchange inflow/outflow data
        In production: Use Glassnode or CryptoQuant API
        """
        # Mock realistic exchange flow data
        import random
        
        inflow = random.uniform(5000, 25000)  # ETH
        outflow = random.uniform(5000, 25000)  # ETH
        
        return {
            "inflow_eth": round(inflow, 2),
            "outflow_eth": round(outflow, 2),
            "net_flow": round(inflow - outflow, 2),
            "top_exchanges": ["Binance", "Coinbase", "Kraken"]
        }
    
    async def get_active_addresses(self) -> Dict:
        """
        Get active address count
        In production: Use Etherscan or Glassnode
        """
        import random
        
        base_count = 500000
        daily_variation = random.uniform(-10, 15)  # %
        
        return {
            "count_24h": int(base_count * (1 + daily_variation / 100)),
            "change_vs_7d": round(daily_variation, 1),
            "trend": "increasing" if daily_variation > 0 else "decreasing"
        }
    
    async def analyze(self) -> OnChainMetrics:
        """
        Perform full on-chain analysis and return aggregated metrics
        """
        # Check cache
        if self._cache_time and datetime.now() - self._cache_time < self._cache_ttl:
            if "metrics" in self._cache:
                return self._cache["metrics"]
        
        # Fetch all data concurrently
        gas_data, whales, flows, addresses = await asyncio.gather(
            self.get_gas_price(),
            self.get_whale_transactions(),
            self.get_exchange_flows(),
            self.get_active_addresses()
        )
        
        # Analyze gas trend
        avg_gas = gas_data["average"]
        if avg_gas < 20:
            gas_trend = "low"
        elif avg_gas > 50:
            gas_trend = "high"
        else:
            gas_trend = "normal"
        
        # Analyze whale sentiment
        accumulation = sum(1 for w in whales if w.transaction_type == "accumulation")
        distribution = sum(1 for w in whales if w.transaction_type == "distribution")
        
        if accumulation > distribution * 1.5:
            whale_sentiment = "accumulating"
        elif distribution > accumulation * 1.5:
            whale_sentiment = "distributing"
        else:
            whale_sentiment = "neutral"
        
        # Calculate overall signal
        signal_score = 0.0
        
        # Net flow analysis (negative = coins leaving exchanges = bullish)
        if flows["net_flow"] < -5000:
            signal_score += 0.3
        elif flows["net_flow"] > 5000:
            signal_score -= 0.3
        
        # Whale sentiment
        if whale_sentiment == "accumulating":
            signal_score += 0.3
        elif whale_sentiment == "distributing":
            signal_score -= 0.3
        
        # Active addresses
        if addresses["change_vs_7d"] > 5:
            signal_score += 0.2
        elif addresses["change_vs_7d"] < -5:
            signal_score -= 0.2
        
        # Gas price (high gas = high activity, can be bullish)
        if gas_trend == "high":
            signal_score += 0.1
        
        # Determine overall signal
        if signal_score > 0.3:
            overall_signal = "bullish"
        elif signal_score < -0.3:
            overall_signal = "bearish"
        else:
            overall_signal = "neutral"
        
        signal_strength = min(abs(signal_score), 1.0)
        
        metrics = OnChainMetrics(
            gas_price_gwei=gas_data["average"],
            gas_price_trend=gas_trend,
            active_addresses_24h=addresses["count_24h"],
            active_addresses_change=addresses["change_vs_7d"],
            exchange_inflow_eth=flows["inflow_eth"],
            exchange_outflow_eth=flows["outflow_eth"],
            net_flow=flows["net_flow"],
            whale_transactions=whales,
            whale_sentiment=whale_sentiment,
            overall_signal=overall_signal,
            signal_strength=signal_strength,
            timestamp=datetime.now().isoformat()
        )
        
        # Cache result
        self._cache["metrics"] = metrics
        self._cache_time = datetime.now()
        
        return metrics
    
    def get_trading_signal(self, metrics: OnChainMetrics) -> Dict:
        """
        Convert on-chain metrics to a trading signal
        """
        signal_map = {
            "bullish": 1,
            "bearish": -1,
            "neutral": 0
        }
        
        return {
            "direction": signal_map.get(metrics.overall_signal, 0),
            "strength": metrics.signal_strength,
            "confidence": min(0.4 + metrics.signal_strength * 0.4, 0.8),
            "reasoning": self._build_reasoning(metrics)
        }
    
    def _build_reasoning(self, metrics: OnChainMetrics) -> str:
        """Build human-readable reasoning for the signal"""
        reasons = []
        
        if metrics.net_flow < -5000:
            reasons.append(f"Net exchange outflow of {abs(metrics.net_flow):,.0f} ETH (accumulation)")
        elif metrics.net_flow > 5000:
            reasons.append(f"Net exchange inflow of {metrics.net_flow:,.0f} ETH (selling pressure)")
        
        if metrics.whale_sentiment == "accumulating":
            reasons.append("Whales are accumulating")
        elif metrics.whale_sentiment == "distributing":
            reasons.append("Whales are distributing")
        
        if metrics.active_addresses_change > 5:
            reasons.append(f"Active addresses up {metrics.active_addresses_change:.1f}%")
        elif metrics.active_addresses_change < -5:
            reasons.append(f"Active addresses down {abs(metrics.active_addresses_change):.1f}%")
        
        return "; ".join(reasons) if reasons else "Mixed on-chain signals"


# Singleton instance
_onchain_analyzer: Optional[OnChainAnalyzer] = None

def get_onchain_analyzer() -> OnChainAnalyzer:
    """Get or create on-chain analyzer instance"""
    global _onchain_analyzer
    if _onchain_analyzer is None:
        _onchain_analyzer = OnChainAnalyzer()
    return _onchain_analyzer


# Quick test
if __name__ == "__main__":
    async def test():
        analyzer = get_onchain_analyzer()
        metrics = await analyzer.analyze()
        signal = analyzer.get_trading_signal(metrics)
        
        print(f"\n📊 On-Chain Analysis:")
        print(f"   Gas Price: {metrics.gas_price_gwei:.1f} Gwei ({metrics.gas_price_trend})")
        print(f"   Active Addresses: {metrics.active_addresses_24h:,} ({metrics.active_addresses_change:+.1f}%)")
        print(f"   Exchange Flow: {metrics.net_flow:+,.0f} ETH net")
        print(f"   Whale Sentiment: {metrics.whale_sentiment}")
        print(f"   Whale Txs: {len(metrics.whale_transactions)}")
        print(f"\n📈 Trading Signal:")
        print(f"   Direction: {metrics.overall_signal.upper()}")
        print(f"   Strength: {signal['strength']:.0%}")
        print(f"   Confidence: {signal['confidence']:.0%}")
        print(f"   Reasoning: {signal['reasoning']}")
    
    asyncio.run(test())
