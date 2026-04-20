from __future__ import annotations
"""
S5: Liquidation Hunting

Principle:
  - Monitor Binance Futures liquidation stream (public WebSocket)
  - When cascade liquidation > $5M in <30 sec → trade the bounce
  - Long liquidations → price dropped → bounce LONG
  - Short liquidations → price pumped → fade SHORT
  - Hold 1-5 minutes, take 0.5-2% bounce

Edge: ~63% win rate on large cascades (Coin Metrics 2023), sporadisch aber profitabel.
Expected: 0.3-0.8%/day (but only 5-10 events/month)
"""
import logging
import time
import threading
import requests
from collections import deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("ethbot.strategy.liquidation")


@dataclass
class LiquidationEvent:
    """A liquidation event from the stream."""
    symbol: str
    side: str           # 'BUY' (short liq) or 'SELL' (long liq)
    price: float
    qty: float
    usd_value: float
    timestamp: float


@dataclass
class CascadeSignal:
    """A cascade liquidation signal (tradeable)."""
    symbol: str
    direction: str       # 'LONG' (buy the dip) or 'SHORT' (fade the pump)
    cascade_usd: float   # Total USD liquidated in window
    event_count: int     # Number of liquidation events
    avg_price: float     # Average liquidation price
    entry_price: float   # Suggested entry
    stop_pct: float      # Stop loss percentage
    target_pct: float    # Take profit percentage
    confidence: float    # 0-1
    timestamp: float


class LiquidationHunter:
    """
    Monitors liquidation cascades and trades the bounce.
    Uses REST polling (WebSocket upgrade planned for Phase 3).
    """

    # Cascade detection thresholds
    CASCADE_THRESHOLD_USD = 5_000_000    # $5M in liquidations
    CASCADE_WINDOW_SEC = 30              # Within 30 seconds
    BOUNCE_TARGET_PCT = 0.015            # 1.5% take-profit
    STOP_PCT = 0.010                     # 1.0% stop-loss
    COOLDOWN_SEC = 300                   # 5 min between trades
    MAX_ALLOCATION = 0.10                # 10% of capital (high risk)

    # Symbols to monitor
    MONITOR_SYMBOLS = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    ]

    def __init__(self):
        self.liq_buffer: deque[LiquidationEvent] = deque(maxlen=5000)
        self.last_trade_time: float = 0.0
        self.cascade_count: int = 0
        self.total_usd_captured: float = 0.0
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        logger.info(f"🎯 LiquidationHunter initialized: {len(self.MONITOR_SYMBOLS)} symbols monitored")

    def start_monitoring(self):
        """Start background polling for liquidation data."""
        if self._running:
            return
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("🎯 LiquidationHunter: Monitoring started")

    def stop_monitoring(self):
        """Stop monitoring."""
        self._running = False

    def detect_cascade(self) -> Optional[CascadeSignal]:
        """
        Check if a liquidation cascade is happening right now.
        Returns a CascadeSignal if threshold exceeded.
        """
        now = time.time()

        # Cooldown check
        if now - self.last_trade_time < self.COOLDOWN_SEC:
            return None

        # Check each symbol
        for symbol in self.MONITOR_SYMBOLS:
            recent = [
                e for e in self.liq_buffer
                if e.symbol == symbol and (now - e.timestamp) < self.CASCADE_WINDOW_SEC
            ]

            if not recent:
                continue

            total_usd = sum(e.usd_value for e in recent)

            if total_usd >= self.CASCADE_THRESHOLD_USD:
                # Determine direction: were longs or shorts liquidated?
                long_liqs = sum(e.usd_value for e in recent if e.side == "SELL")   # Sell = long liq
                short_liqs = sum(e.usd_value for e in recent if e.side == "BUY")   # Buy = short liq

                if long_liqs > short_liqs:
                    # Longs were liquidated → price dropped → bounce LONG
                    direction = "LONG"
                else:
                    # Shorts were liquidated → price pumped → fade SHORT
                    direction = "SHORT"

                avg_price = sum(e.price * e.usd_value for e in recent) / total_usd
                confidence = min(1.0, total_usd / (self.CASCADE_THRESHOLD_USD * 3))

                self.cascade_count += 1
                logger.warning(
                    f"🎯 CASCADE DETECTED: {symbol} | "
                    f"${total_usd/1e6:.1f}M in {len(recent)} events | "
                    f"Direction: {direction} | Confidence: {confidence:.0%}"
                )

                # Get current price for entry
                current_price = self._get_price(symbol) or avg_price

                return CascadeSignal(
                    symbol=symbol,
                    direction=direction,
                    cascade_usd=total_usd,
                    event_count=len(recent),
                    avg_price=avg_price,
                    entry_price=current_price,
                    stop_pct=self.STOP_PCT,
                    target_pct=self.BOUNCE_TARGET_PCT,
                    confidence=confidence,
                    timestamp=now,
                )

        return None

    def record_trade(self, pnl: float):
        """Record a completed trade."""
        self.last_trade_time = time.time()
        self.total_usd_captured += pnl

    def get_status(self) -> dict:
        """Return strategy status for dashboard."""
        now = time.time()
        recent_30m = [e for e in self.liq_buffer if (now - e.timestamp) < 1800]
        total_30m_usd = sum(e.usd_value for e in recent_30m)

        return {
            "strategy": "S5_LiquidationHunter",
            "monitoring": self._running,
            "buffer_size": len(self.liq_buffer),
            "cascades_detected": self.cascade_count,
            "total_usd_captured": round(self.total_usd_captured, 2),
            "last_30m_liquidations_usd": round(total_30m_usd, 0),
            "last_30m_events": len(recent_30m),
            "cooldown_remaining": max(0, int(self.COOLDOWN_SEC - (now - self.last_trade_time))),
            "symbols": self.MONITOR_SYMBOLS,
        }

    # ── Internal ──

    def _poll_loop(self):
        """Background poll for liquidation data (REST fallback)."""
        while self._running:
            try:
                self._fetch_recent_liquidations()
            except Exception as e:
                logger.debug(f"LiqHunter poll: {e}")
            time.sleep(5)  # Poll every 5 seconds

    def _fetch_recent_liquidations(self):
        """
        Fetch recent forced liquidations from Binance Futures.
        Uses allForceOrders endpoint.
        """
        for symbol in self.MONITOR_SYMBOLS:
            try:
                resp = requests.get(
                    "https://fapi.binance.com/fapi/v1/allForceOrders",
                    params={"symbol": symbol, "limit": 50},
                    timeout=5,
                )
                if resp.status_code == 200:
                    orders = resp.json()
                    for order in orders:
                        ts = float(order.get("time", 0)) / 1000
                        # Only add recent events (last 2 minutes)
                        if time.time() - ts < 120:
                            price = float(order.get("price", 0))
                            qty = float(order.get("origQty", 0))
                            event = LiquidationEvent(
                                symbol=symbol,
                                side=order.get("side", "SELL"),
                                price=price,
                                qty=qty,
                                usd_value=price * qty,
                                timestamp=ts,
                            )
                            self.liq_buffer.append(event)
            except Exception:
                pass

    def _get_price(self, symbol: str) -> Optional[float]:
        """Get current price."""
        try:
            resp = requests.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": symbol},
                timeout=3,
            )
            return float(resp.json()["price"])
        except Exception:
            return None


# Singleton
_instance: Optional[LiquidationHunter] = None

def get_liq_hunter() -> LiquidationHunter:
    global _instance
    if _instance is None:
        _instance = LiquidationHunter()
    return _instance
