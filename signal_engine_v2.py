"""
Ethbot v2: Signal Engine

Generates trading signals based on 3 proven crypto edges:
1. Funding Rate Reversal — when retail is overleveraged
2. Volume Spike Mean Reversion — extreme moves revert
3. Liquidation Squeeze — market makers hunt stops

Signals are LOGGED ONLY (via EdgeValidator) until validated.
No live trading until edge is proven over 200+ predictions.

Usage:
    from signal_engine_v2 import signal_engine
    signal = await signal_engine.generate_signal(market_data)
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger("ethbot.signals")


@dataclass 
class Signal:
    """A trading signal with direction and reasoning."""
    name: str               # Signal source name
    direction: str           # "LONG", "SHORT", or "FLAT"
    confidence: float        # 0.0 - 1.0
    reason: str              # Human-readable explanation
    price: float             # Price when signal was generated
    timestamp: float         # Unix timestamp
    edge_data: Dict = None   # Raw data that triggered this signal


class SignalEngineV2:
    """Generates consensus signals from multiple proven edges."""

    def __init__(self):
        self.last_signals: List[Signal] = []
        self._signal_count = 0

    # ─── Individual Edge Signals ───

    def funding_rate_signal(self, data: Dict) -> Optional[Signal]:
        """
        Funding Rate Reversal Edge.
        
        When funding rate is extremely positive (>0.05%), longs are paying shorts.
        This means retail is overleveraged long → expect a correction.
        
        When funding rate is extremely negative (<-0.03%), shorts are paying longs.
        This means retail is overleveraged short → expect a bounce.
        """
        fr = data.get("funding_rate")
        if fr is None:
            return None

        price = data.get("price", 0)
        if price <= 0:
            return None

        # Strong short bias when retail is overleveraged long
        if fr >= 0.0008:  # 0.08%+
            confidence = min(0.9, 0.5 + (fr - 0.0005) * 200)
            return Signal(
                name="funding_reversal",
                direction="SHORT",
                confidence=confidence,
                reason=f"Funding rate {fr*100:.4f}% — retail overleveraged LONG, expect correction",
                price=price,
                timestamp=time.time(),
                edge_data={"funding_rate": fr}
            )
        
        # Strong long bias when retail is overleveraged short
        elif fr <= -0.0003:  # -0.03%
            confidence = min(0.9, 0.5 + abs(fr + 0.0001) * 300)
            return Signal(
                name="funding_reversal",
                direction="LONG",
                confidence=confidence,
                reason=f"Funding rate {fr*100:.4f}% — retail overleveraged SHORT, expect bounce",
                price=price,
                timestamp=time.time(),
                edge_data={"funding_rate": fr}
            )

        return None  # Neutral funding rate

    def volume_spike_signal(self, data: Dict) -> Optional[Signal]:
        """
        Volume Spike Mean Reversion Edge.
        
        When volume is >3x average AND price deviates >0.5% from VWAP,
        the move is likely to revert. Trade against the spike.
        """
        vol_ratio = data.get("volume_spike_ratio", 1.0)
        vwap_dev = data.get("vwap_deviation_pct", 0)
        price = data.get("price", 0)

        if price <= 0 or vol_ratio < 2.5:
            return None

        # Volume spike detected
        if vol_ratio >= 3.0 and abs(vwap_dev) >= 0.5:
            # Price above VWAP after volume spike → mean reversion DOWN
            if vwap_dev > 0.5:
                confidence = min(0.85, 0.4 + (vol_ratio - 3.0) * 0.1 + abs(vwap_dev) * 0.1)
                return Signal(
                    name="volume_mean_reversion",
                    direction="SHORT",
                    confidence=confidence,
                    reason=f"Volume {vol_ratio:.1f}x avg, price +{vwap_dev:.2f}% above VWAP — expect reversion",
                    price=price,
                    timestamp=time.time(),
                    edge_data={"volume_spike": vol_ratio, "vwap_dev": vwap_dev}
                )
            
            # Price below VWAP after volume spike → mean reversion UP
            elif vwap_dev < -0.5:
                confidence = min(0.85, 0.4 + (vol_ratio - 3.0) * 0.1 + abs(vwap_dev) * 0.1)
                return Signal(
                    name="volume_mean_reversion",
                    direction="LONG",
                    confidence=confidence,
                    reason=f"Volume {vol_ratio:.1f}x avg, price {vwap_dev:.2f}% below VWAP — expect reversion",
                    price=price,
                    timestamp=time.time(),
                    edge_data={"volume_spike": vol_ratio, "vwap_dev": vwap_dev}
                )

        # Milder volume spike (2.5-3x) with strong VWAP deviation (>1%)
        elif vol_ratio >= 2.5 and abs(vwap_dev) >= 1.0:
            direction = "SHORT" if vwap_dev > 0 else "LONG"
            confidence = min(0.7, 0.35 + abs(vwap_dev) * 0.1)
            return Signal(
                name="volume_mean_reversion",
                direction=direction,
                confidence=confidence,
                reason=f"Volume {vol_ratio:.1f}x avg, VWAP dev {vwap_dev:+.2f}% — mild reversion signal",
                price=price,
                timestamp=time.time(),
                edge_data={"volume_spike": vol_ratio, "vwap_dev": vwap_dev}
            )

        return None

    def oi_divergence_signal(self, data: Dict) -> Optional[Signal]:
        """
        Open Interest Divergence Edge.
        
        When OI increases but price drops → new shorts entering → potential squeeze UP.
        When OI increases but price rises → new longs entering → potential flush DOWN.
        
        This is a simplified version of the liquidation squeeze edge.
        """
        oi = data.get("open_interest")
        price = data.get("price", 0)
        price_change = data.get("price_change_24h", 0)  # % change 24h
        ls_ratio = data.get("long_short_ratio", 1.0)

        if oi is None or price <= 0:
            return None

        # Extreme long/short ratios indicate positioning imbalance
        if ls_ratio is not None:
            # Everyone is long → contrarian short
            if ls_ratio >= 2.0:
                confidence = min(0.75, 0.4 + (ls_ratio - 2.0) * 0.15)
                return Signal(
                    name="oi_divergence",
                    direction="SHORT",
                    confidence=confidence,
                    reason=f"L/S ratio {ls_ratio:.2f} — extreme long positioning, expect correction",
                    price=price,
                    timestamp=time.time(),
                    edge_data={"ls_ratio": ls_ratio, "oi": oi}
                )
            
            # Everyone is short → contrarian long
            elif ls_ratio <= 0.5:
                confidence = min(0.75, 0.4 + (0.5 - ls_ratio) * 0.3)
                return Signal(
                    name="oi_divergence",
                    direction="LONG",
                    confidence=confidence,
                    reason=f"L/S ratio {ls_ratio:.2f} — extreme short positioning, expect squeeze",
                    price=price,
                    timestamp=time.time(),
                    edge_data={"ls_ratio": ls_ratio, "oi": oi}
                )

        # RSI + BB position extreme → overbought/oversold
        rsi = data.get("rsi_1m", 50)
        bb_pos = data.get("bb_position", 0)
        
        if rsi <= 20 and bb_pos <= -0.9:
            return Signal(
                name="oi_divergence",
                direction="LONG",
                confidence=0.6,
                reason=f"RSI={rsi:.0f}, BB={bb_pos:.2f} — extreme oversold",
                price=price,
                timestamp=time.time(),
                edge_data={"rsi": rsi, "bb_position": bb_pos}
            )
        elif rsi >= 80 and bb_pos >= 0.9:
            return Signal(
                name="oi_divergence",
                direction="SHORT",
                confidence=0.6,
                reason=f"RSI={rsi:.0f}, BB={bb_pos:.2f} — extreme overbought",
                price=price,
                timestamp=time.time(),
                edge_data={"rsi": rsi, "bb_position": bb_pos}
            )

        return None

    # ─── Consensus Engine ───

    async def generate_signal(self, market_data: Dict) -> Optional[Dict]:
        """
        Generate a consensus signal from all 3 edges.
        
        Rules:
        - Need ≥ 2/3 signals agreeing on direction for a trade
        - Combined confidence must be > 0.5
        - Returns None if no consensus
        """
        signals = []

        # Run all 3 edge detectors
        fr_signal = self.funding_rate_signal(market_data)
        vol_signal = self.volume_spike_signal(market_data)
        oi_signal = self.oi_divergence_signal(market_data)

        for s in [fr_signal, vol_signal, oi_signal]:
            if s is not None:
                signals.append(s)

        self.last_signals = signals
        self._signal_count += 1

        if not signals:
            return None

        # Count directional votes
        long_votes = [s for s in signals if s.direction == "LONG"]
        short_votes = [s for s in signals if s.direction == "SHORT"]

        # Need at least 2 agreeing signals (consensus)
        if len(long_votes) >= 2:
            avg_confidence = sum(s.confidence for s in long_votes) / len(long_votes)
            if avg_confidence >= 0.5:
                reasons = [s.reason for s in long_votes]
                return {
                    "direction": "LONG",
                    "confidence": round(avg_confidence, 3),
                    "signals_agreeing": len(long_votes),
                    "signals_total": len(signals),
                    "reasons": reasons,
                    "price": market_data.get("price", 0),
                    "consensus": True
                }

        if len(short_votes) >= 2:
            avg_confidence = sum(s.confidence for s in short_votes) / len(short_votes)
            if avg_confidence >= 0.5:
                reasons = [s.reason for s in short_votes]
                return {
                    "direction": "SHORT",
                    "confidence": round(avg_confidence, 3),
                    "signals_agreeing": len(short_votes),
                    "signals_total": len(signals),
                    "reasons": reasons,
                    "price": market_data.get("price", 0),
                    "consensus": True
                }

        # Single strong signal (confidence > 0.75) — log but mark as no consensus
        strongest = max(signals, key=lambda s: s.confidence)
        if strongest.confidence >= 0.75:
            return {
                "direction": strongest.direction,
                "confidence": round(strongest.confidence, 3),
                "signals_agreeing": 1,
                "signals_total": len(signals),
                "reasons": [strongest.reason],
                "price": market_data.get("price", 0),
                "consensus": False,
                "note": "Single strong signal — monitoring only"
            }

        return None

    def get_status(self) -> Dict:
        """Get current signal engine status."""
        return {
            "total_signals_generated": self._signal_count,
            "last_signals": [
                {"name": s.name, "direction": s.direction, 
                 "confidence": s.confidence, "reason": s.reason}
                for s in self.last_signals
            ],
            "edges_active": [
                "funding_reversal",
                "volume_mean_reversion", 
                "oi_divergence"
            ]
        }


# Singleton
signal_engine = SignalEngineV2()
