from __future__ import annotations
"""
S1: Funding Rate Arbitrage (Cash & Carry)

Principle:
  - When Funding Rate on Perpetual > threshold, Longs pay Shorts every 8h
  - Go Long Spot + Short Perp → price-hedged, collect funding
  - Historically ETH Funding avg 0.01-0.03% per 8h = 0.03-0.09%/day
  - In bull runs: 0.1-0.5%/day possible
  - Risk: Near-zero market risk, only exchange risk + funding flip risk

Expected Performance: 0.05-0.15%/day, Sharpe 3-5, Max DD <3%
"""
import logging
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ethbot.strategy.funding_arb")


@dataclass
class FundingOpp:
    """A funding rate arbitrage opportunity."""
    symbol: str
    funding_rate: float           # Current 8h rate (e.g., 0.001 = 0.1%)
    annualized: float             # Extrapolated annual rate
    predicted_rate: float         # Predicted next funding
    oi_usd: float                 # Open interest in USD
    entry_cost_pct: float         # Estimated slippage cost to enter
    net_edge_per_8h: float        # funding_rate - entry_cost / hold_periods


@dataclass
class FundingPosition:
    """Active funding arb position."""
    symbol: str
    spot_qty: float
    perp_qty: float
    entry_funding_rate: float
    entry_time: float
    total_funding_collected: float = 0.0
    rebalance_count: int = 0


class FundingArbStrategy:
    """
    Funding Rate Arbitrage: Long Spot + Short Perp = delta-neutral.
    Collect funding payments every 8 hours.
    """

    # Entry: funding rate must exceed this per 8h (0.01% = ~11% p.a.)
    THRESHOLD_ENTRY = 0.0001      # 0.01% per 8h
    # Exit: close when funding drops below this
    THRESHOLD_EXIT = 0.00003      # 0.003% per 8h
    # Max allocation of total capital
    MAX_ALLOCATION = 0.30         # 30%
    # Max positions simultaneously
    MAX_POSITIONS = 3
    # Max drift before rebalance
    MAX_DRIFT_PCT = 0.02          # 2% qty mismatch triggers rebalance

    # Futures pairs to monitor
    UNIVERSE = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
        "DOGEUSDT", "AVAXUSDT", "ADAUSDT", "DOTUSDT", "MATICUSDT",
        "LINKUSDT", "ATOMUSDT", "LTCUSDT", "NEARUSDT", "APTUSDT",
    ]

    def __init__(self):
        self.positions: dict[str, FundingPosition] = {}
        self.last_scan = 0.0
        self.scan_interval = 3600  # Scan every hour
        self._funding_cache: dict[str, float] = {}
        logger.info(f"💰 FundingArb initialized: {len(self.UNIVERSE)} pairs monitored")

    def scan_opportunities(self) -> list[FundingOpp]:
        """
        Scan all perpetual pairs for high funding rates.
        Returns sorted list of opportunities (best first).
        """
        opps = []
        for symbol in self.UNIVERSE:
            try:
                fr = self._fetch_funding_rate(symbol)
                if fr is None:
                    continue

                oi = self._fetch_open_interest(symbol)
                predicted = self._predict_next_funding(symbol, fr)

                # Net edge = funding collected - entry/exit costs
                entry_cost = 0.0012  # ~0.12% round-trip (maker fees + slippage)
                hold_periods = 30    # Expect to hold ~30 funding periods (10 days)
                net_edge = fr - (entry_cost / hold_periods)

                if fr >= self.THRESHOLD_ENTRY and net_edge > 0:
                    opps.append(FundingOpp(
                        symbol=symbol,
                        funding_rate=fr,
                        annualized=fr * 3 * 365,  # 3 funding periods/day
                        predicted_rate=predicted,
                        oi_usd=oi,
                        entry_cost_pct=entry_cost,
                        net_edge_per_8h=net_edge,
                    ))

            except Exception as e:
                logger.debug(f"FundingArb scan {symbol}: {e}")

        # Sort by net edge (best first)
        opps.sort(key=lambda o: o.net_edge_per_8h, reverse=True)
        self.last_scan = time.time()

        if opps:
            logger.info(
                f"💰 Funding scan: {len(opps)} opportunities | "
                f"Best: {opps[0].symbol} @ {opps[0].funding_rate:.4%}/8h "
                f"({opps[0].annualized:.1%} p.a.)"
            )

        return opps[:self.MAX_POSITIONS]

    def should_enter(self, opp: FundingOpp) -> bool:
        """Check if we should open a new funding arb position."""
        if opp.symbol in self.positions:
            return False
        if len(self.positions) >= self.MAX_POSITIONS:
            return False
        if opp.net_edge_per_8h <= 0:
            return False
        # OI check: don't arb illiquid markets
        if opp.oi_usd < 10_000_000:
            return False
        return True

    def should_exit(self, symbol: str) -> bool:
        """Check if we should close a funding arb position."""
        if symbol not in self.positions:
            return False
        current_fr = self._fetch_funding_rate(symbol)
        if current_fr is None:
            return False
        # Exit if funding flipped or dropped below threshold
        if current_fr < self.THRESHOLD_EXIT:
            logger.info(f"💰 FundingArb EXIT signal: {symbol} funding dropped to {current_fr:.4%}")
            return True
        # Exit if funding went negative (we'd be PAYING)
        if current_fr < 0:
            logger.warning(f"💰 FundingArb EMERGENCY EXIT: {symbol} funding negative {current_fr:.4%}")
            return True
        return False

    def check_rebalance(self, symbol: str, spot_qty: float, perp_qty: float) -> Optional[dict]:
        """
        Check if spot/perp quantities have drifted too far and need rebalancing.
        Returns rebalance instructions or None.
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        drift = abs(spot_qty - perp_qty) / max(spot_qty, perp_qty, 0.001)

        if drift > self.MAX_DRIFT_PCT:
            # Determine which side to adjust
            if spot_qty > perp_qty:
                return {"action": "increase_short", "qty_delta": spot_qty - perp_qty}
            else:
                return {"action": "increase_spot", "qty_delta": perp_qty - spot_qty}
        return None

    def get_status(self) -> dict:
        """Return strategy status for dashboard."""
        return {
            "strategy": "S1_FundingArb",
            "active_positions": len(self.positions),
            "positions": {
                sym: {
                    "funding_rate": self._funding_cache.get(sym, 0),
                    "total_collected": pos.total_funding_collected,
                    "rebalances": pos.rebalance_count,
                    "age_hours": (time.time() - pos.entry_time) / 3600,
                }
                for sym, pos in self.positions.items()
            },
            "universe_size": len(self.UNIVERSE),
            "last_scan_ago": int(time.time() - self.last_scan),
        }

    # ── Data Fetching ──

    def _fetch_funding_rate(self, symbol: str) -> Optional[float]:
        """Fetch current funding rate from Binance Futures."""
        try:
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                params={"symbol": symbol, "limit": 1},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                rate = float(data[0]["fundingRate"])
                self._funding_cache[symbol] = rate
                return rate
        except Exception as e:
            logger.debug(f"Funding rate fetch {symbol}: {e}")
        return None

    def _fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest in USD."""
        try:
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/openInterest",
                params={"symbol": symbol},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            # OI is in contracts, multiply by mark price
            oi = float(data.get("openInterest", 0))
            # Rough USD estimate (not exact but good enough for filtering)
            mark_resp = requests.get(
                "https://fapi.binance.com/fapi/v1/premiumIndex",
                params={"symbol": symbol},
                timeout=5,
            )
            mark_resp.raise_for_status()
            mark_price = float(mark_resp.json().get("markPrice", 0))
            return oi * mark_price
        except Exception:
            return 0.0

    def _predict_next_funding(self, symbol: str, current_rate: float) -> float:
        """Simple prediction: exponential moving average of last 10 rates."""
        try:
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                params={"symbol": symbol, "limit": 10},
                timeout=5,
            )
            resp.raise_for_status()
            rates = [float(r["fundingRate"]) for r in resp.json()]
            if len(rates) >= 3:
                # EMA with alpha=0.3
                ema = rates[0]
                for r in rates[1:]:
                    ema = 0.3 * r + 0.7 * ema
                return ema
        except Exception:
            pass
        return current_rate


# Singleton
_instance: Optional[FundingArbStrategy] = None

def get_funding_arb() -> FundingArbStrategy:
    global _instance
    if _instance is None:
        _instance = FundingArbStrategy()
    return _instance
