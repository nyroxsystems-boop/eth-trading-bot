"""
Ultra Signal Aggregator
Combines all advanced signals into a unified trading recommendation:
- Order Book Depth (Market Microstructure)
- Funding Rate (Contrarian Sentiment)
- Multi-Agent Ensemble (DQN Voting)
- Traditional Strategy Signals
"""

import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class UltraSignal:
    """Combined signal from all sources"""
    timestamp: str
    
    # Individual signals
    order_book_bias: float  # -1 to 1
    order_book_signal: str
    funding_bias: float  # -1 to 1
    funding_signal: str
    ensemble_action: str
    ensemble_confidence: float
    
    # Combined metrics
    combined_score: float  # -1 (strong sell) to 1 (strong buy)
    signal_agreement: float  # 0 to 1 (how aligned are signals)
    
    # Final decision
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float
    should_trade: bool
    reason: str


class UltraSignalAggregator:
    """
    Aggregates all advanced signals for the ultimate trading decision.
    Weights can be tuned based on backtest performance.
    """
    
    def __init__(self):
        # Signal weights (should sum to 1.0)
        self.weights = {
            "order_book": 0.25,
            "funding": 0.15,
            "ensemble": 0.40,
            "traditional": 0.20
        }
        
        self.confidence_threshold = 0.5
        self.score_threshold = 0.3  # Minimum score to trade
    
    async def get_all_signals(self) -> Dict:
        """Fetch all signals concurrently"""
        from src.data.order_book_analyzer import get_order_book_analyzer
        from src.data.funding_rate_analyzer import get_funding_analyzer
        from src.ml.multi_agent_ensemble import get_multi_agent_ensemble
        import numpy as np
        
        # Initialize analyzers
        ob_analyzer = get_order_book_analyzer("ETHUSDT")
        funding_analyzer = get_funding_analyzer("ETHUSDT")
        ensemble = get_multi_agent_ensemble()
        
        # Fetch order book and funding concurrently
        ob_signal, funding_signal = await asyncio.gather(
            ob_analyzer.analyze(),
            funding_analyzer.analyze(),
            return_exceptions=True
        )
        
        # Get ensemble vote (needs state - use random for now, should use real state)
        test_state = np.random.randn(26).astype(np.float32)
        ensemble_decision = ensemble.vote(test_state)
        
        return {
            "order_book": ob_signal if not isinstance(ob_signal, Exception) else None,
            "funding": funding_signal if not isinstance(funding_signal, Exception) else None,
            "ensemble": ensemble_decision
        }
    
    async def generate_signal(self, traditional_score: float = 0.0) -> UltraSignal:
        """
        Generate the ultimate combined signal.
        
        Args:
            traditional_score: Score from traditional strategy (-1 to 1)
        """
        signals = await self.get_all_signals()
        
        # Extract values with fallbacks
        ob = signals.get("order_book")
        funding = signals.get("funding")
        ensemble = signals.get("ensemble")
        
        # Order book bias
        ob_bias = ob.imbalance_ratio if ob else 0.0
        ob_signal_str = ob.imbalance_signal if ob else "neutral"
        
        # Funding bias
        funding_bias = funding.long_bias if funding else 0.0
        funding_signal_str = funding.signal if funding else "neutral"
        
        # Ensemble
        ensemble_action = ensemble.final_action if ensemble else "HOLD"
        ensemble_conf = ensemble.final_confidence if ensemble else 0.0
        
        # Convert ensemble action to numeric
        ensemble_score = {
            "BUY": 1.0,
            "SELL": -1.0,
            "HOLD": 0.0
        }.get(ensemble_action, 0.0) * ensemble_conf
        
        # Calculate combined score (weighted average)
        combined_score = (
            ob_bias * self.weights["order_book"] +
            funding_bias * self.weights["funding"] +
            ensemble_score * self.weights["ensemble"] +
            traditional_score * self.weights["traditional"]
        )
        
        # Signal agreement (do signals point same direction?)
        signs = [
            1 if ob_bias > 0.1 else (-1 if ob_bias < -0.1 else 0),
            1 if funding_bias > 0.1 else (-1 if funding_bias < -0.1 else 0),
            1 if ensemble_score > 0.2 else (-1 if ensemble_score < -0.2 else 0),
            1 if traditional_score > 0.2 else (-1 if traditional_score < -0.2 else 0)
        ]
        non_zero_signs = [s for s in signs if s != 0]
        if len(non_zero_signs) >= 2:
            agreement = abs(sum(non_zero_signs)) / len(non_zero_signs)
        else:
            agreement = 0.5
        
        # Determine final action
        if combined_score > self.score_threshold:
            action = "BUY"
        elif combined_score < -self.score_threshold:
            action = "SELL"
        else:
            action = "HOLD"
        
        # Confidence based on agreement and individual confidences
        confidence = agreement * (0.5 + ensemble_conf * 0.5)
        
        # Should trade?
        should_trade = (
            action != "HOLD" and
            confidence >= self.confidence_threshold and
            abs(combined_score) >= self.score_threshold
        )
        
        # Build reason
        components = []
        if ob_signal_str != "neutral":
            components.append(f"OB:{ob_signal_str}")
        if funding_signal_str != "neutral":
            components.append(f"FR:{funding_signal_str}")
        if ensemble_action != "HOLD":
            components.append(f"AI:{ensemble_action}")
        
        reason = " + ".join(components) if components else "No strong signals"
        if should_trade:
            reason = f"{action}: {reason} (score={combined_score:.2f})"
        
        return UltraSignal(
            timestamp=datetime.now().isoformat(),
            order_book_bias=round(ob_bias, 3),
            order_book_signal=ob_signal_str,
            funding_bias=round(funding_bias, 3),
            funding_signal=funding_signal_str,
            ensemble_action=ensemble_action,
            ensemble_confidence=round(ensemble_conf, 3),
            combined_score=round(combined_score, 3),
            signal_agreement=round(agreement, 3),
            action=action,
            confidence=round(confidence, 3),
            should_trade=should_trade,
            reason=reason
        )
    
    def to_dict(self, signal: UltraSignal) -> Dict:
        """Convert signal to dictionary for API/display"""
        return asdict(signal)


# Singleton
_aggregator: Optional[UltraSignalAggregator] = None

def get_ultra_signal_aggregator() -> UltraSignalAggregator:
    """Get or create signal aggregator"""
    global _aggregator
    if _aggregator is None:
        _aggregator = UltraSignalAggregator()
    return _aggregator


# Quick test
if __name__ == "__main__":
    async def test():
        aggregator = get_ultra_signal_aggregator()
        signal = await aggregator.generate_signal(traditional_score=0.3)
        
        print(f"\n🚀 ULTRA SIGNAL:")
        print(f"   Order Book: {signal.order_book_signal} ({signal.order_book_bias:+.2f})")
        print(f"   Funding: {signal.funding_signal} ({signal.funding_bias:+.2f})")
        print(f"   Ensemble: {signal.ensemble_action} ({signal.ensemble_confidence:.0%})")
        print(f"   ---")
        print(f"   Combined Score: {signal.combined_score:+.2f}")
        print(f"   Agreement: {signal.signal_agreement:.0%}")
        print(f"   ---")
        print(f"   ACTION: {signal.action}")
        print(f"   Confidence: {signal.confidence:.0%}")
        print(f"   Should Trade: {'YES' if signal.should_trade else 'NO'}")
        print(f"   Reason: {signal.reason}")
    
    asyncio.run(test())
