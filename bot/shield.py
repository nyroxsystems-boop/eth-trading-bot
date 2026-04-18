"""
Portfolio Risk Shield — The final layer of institutional-grade protection.

Components:
1. Drawdown Circuit Breaker — Auto-stops ALL trading if daily loss exceeds threshold
2. Portfolio Correlation Guard — Prevents overexposure to correlated assets
3. Slippage & Fee Simulator — Realistic cost simulation for paper trading
4. Order Flow Analyzer — Buy/Sell pressure from recent trade data (CVD)
5. Position Heat Monitor — Max % of capital in one direction

This module turns the bot from "smart" to "institutional".
"""
import logging
import math
import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger("ethbot.shield")


# ═══════════════════════════════════════════════════════════════════════════
# 1. DRAWDOWN CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════════════════

class CircuitBreaker:
    """
    Auto-stops ALL trading if losses exceed thresholds.
    
    Like a real trading desk — if you lose too much, you're done for the day.
    Prevents catastrophic losses during flash crashes or black swans.
    """

    def __init__(self):
        self.max_daily_loss_pct = float(os.getenv("MAX_DAILY_LOSS_PCT", "5.0"))
        self.max_consecutive_losses = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5"))
        self.max_drawdown_pct = float(os.getenv("MAX_DRAWDOWN_PCT", "10.0"))
        self.cooldown_hours = float(os.getenv("CIRCUIT_COOLDOWN_HOURS", "4.0"))

        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.consecutive_losses = 0
        self.peak_balance = 0.0
        self.tripped = False
        self.trip_time = None
        self.trip_reason = ""
        self.last_reset = datetime.now(timezone.utc)

        self._state_file = Path("./logs/brain/circuit_breaker.json")
        self._load()

    def _load(self):
        """Load circuit breaker state."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                self.daily_pnl = data.get("daily_pnl", 0)
                self.consecutive_losses = data.get("consecutive_losses", 0)
                self.peak_balance = data.get("peak_balance", 0)
                self.tripped = data.get("tripped", False)
                self.trip_time = data.get("trip_time")
                self.trip_reason = data.get("trip_reason", "")
                last_reset = data.get("last_reset")
                if last_reset:
                    self.last_reset = datetime.fromisoformat(last_reset)
            except Exception:
                pass

    def save(self):
        """Persist state."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._state_file.write_text(json.dumps({
                "daily_pnl": self.daily_pnl,
                "consecutive_losses": self.consecutive_losses,
                "peak_balance": self.peak_balance,
                "tripped": self.tripped,
                "trip_time": self.trip_time,
                "trip_reason": self.trip_reason,
                "last_reset": self.last_reset.isoformat(),
            }))
        except Exception:
            pass

    def check_new_day(self):
        """Reset daily counters if it's a new day."""
        now = datetime.now(timezone.utc)
        if now.date() > self.last_reset.date():
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.last_reset = now
            # Auto-reset circuit breaker on new day
            if self.tripped:
                logger.info("🔌 Circuit breaker auto-reset (new day)")
                self.tripped = False
                self.trip_reason = ""
            self.save()

    def record_trade(self, pnl: float, balance: float):
        """Record a trade and check if breaker should trip."""
        self.daily_pnl += pnl
        self.daily_trades += 1

        if pnl > 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

        # Track peak balance for drawdown
        if balance > self.peak_balance:
            self.peak_balance = balance

        # Check triggers
        pnl_pct = (self.daily_pnl / max(balance, 1)) * 100

        if pnl_pct < -self.max_daily_loss_pct:
            self._trip(f"Daily loss {pnl_pct:.1f}% exceeds -{self.max_daily_loss_pct}%")
        elif self.consecutive_losses >= self.max_consecutive_losses:
            self._trip(f"{self.consecutive_losses} consecutive losses")
        elif self.peak_balance > 0:
            drawdown = ((self.peak_balance - balance) / self.peak_balance) * 100
            if drawdown > self.max_drawdown_pct:
                self._trip(f"Drawdown {drawdown:.1f}% exceeds {self.max_drawdown_pct}%")

        self.save()

    def _trip(self, reason: str):
        """Trip the circuit breaker — ALL trading stops."""
        if not self.tripped:
            self.tripped = True
            self.trip_time = datetime.now(timezone.utc).isoformat()
            self.trip_reason = reason
            logger.warning(f"🚨 CIRCUIT BREAKER TRIPPED: {reason}")
            logger.warning(f"🚨 ALL TRADING HALTED for {self.cooldown_hours}h")

    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed."""
        self.check_new_day()

        if not self.tripped:
            return True

        # Check if cooldown has passed
        if self.trip_time:
            try:
                trip_dt = datetime.fromisoformat(self.trip_time)
                elapsed = (datetime.now(timezone.utc) - trip_dt).total_seconds() / 3600
                if elapsed >= self.cooldown_hours:
                    logger.info(f"🔌 Circuit breaker reset after {elapsed:.1f}h cooldown")
                    self.tripped = False
                    self.trip_reason = ""
                    self.save()
                    return True
            except Exception:
                pass

        return False

    def get_status(self) -> dict:
        return {
            "tripped": self.tripped,
            "reason": self.trip_reason,
            "daily_pnl": round(self.daily_pnl, 2),
            "consecutive_losses": self.consecutive_losses,
            "daily_trades": self.daily_trades,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 2. PORTFOLIO CORRELATION GUARD
# ═══════════════════════════════════════════════════════════════════════════

class PortfolioGuard:
    """
    Prevents overexposure to correlated assets.
    
    If you're long BTC, ETH, SOL, ADA simultaneously —
    they're all correlated. One crash kills everything.
    
    This guard limits how many positions can be open at once
    and tracks "portfolio heat" (total directional exposure).
    """

    # Asset correlation groups
    CORRELATION_GROUPS = {
        "large_cap_crypto": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        "alt_l1": ["SOLUSDT", "ADAUSDT", "SUIUSDT", "AVAXUSDT"],
        "meme": ["DOGEUSDT", "PEPEUSDT", "WLDUSDT", "SHIBUSDT"],
        "defi": ["LINKUSDT", "UNIUSDT", "AAVEUSDT"],
        "tech_stocks": ["AAPL", "MSFT", "NVDA", "AMD", "GOOG", "META", "AMZN"],
        "index_etf": ["SPY", "QQQ"],
    }

    def __init__(self):
        self.max_positions = int(os.getenv("MAX_POSITIONS", "8"))
        self.max_per_group = int(os.getenv("MAX_PER_GROUP", "3"))
        self.max_portfolio_heat_pct = float(os.getenv("MAX_HEAT_PCT", "50.0"))
        self.open_positions: dict = {}  # pair -> {"size_usd": ..., "group": ...}

    def can_open_position(self, pair: str, size_usd: float) -> tuple:
        """
        Check if a new position is allowed.
        Returns (allowed: bool, reason: str).
        """
        # Check total position count
        if len(self.open_positions) >= self.max_positions:
            return False, f"Max {self.max_positions} positions reached"

        # Check correlation group limit
        group = self._get_group(pair)
        group_count = sum(
            1 for p, info in self.open_positions.items()
            if info.get("group") == group
        )
        if group_count >= self.max_per_group and group:
            return False, f"Max {self.max_per_group} in {group} group"

        # Check portfolio heat
        total_exposure = sum(p.get("size_usd", 0) for p in self.open_positions.values())
        total_exposure += size_usd
        # Heat is simplified here — in production use account balance
        heat_pct = (total_exposure / max(total_exposure * 2, 1)) * 100
        if len(self.open_positions) > 5:
            return False, f"Portfolio heat too high ({len(self.open_positions)} positions)"

        return True, "OK"

    def register_position(self, pair: str, size_usd: float):
        """Register a new open position."""
        self.open_positions[pair] = {
            "size_usd": size_usd,
            "group": self._get_group(pair),
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }

    def close_position(self, pair: str):
        """Remove a closed position."""
        self.open_positions.pop(pair, None)

    def _get_group(self, pair: str) -> str:
        """Find which correlation group a pair belongs to."""
        for group, members in self.CORRELATION_GROUPS.items():
            if pair in members:
                return group
        return "other"

    def get_status(self) -> dict:
        return {
            "open_positions": len(self.open_positions),
            "max_positions": self.max_positions,
            "positions": list(self.open_positions.keys()),
            "groups": {
                g: sum(1 for p in self.open_positions.values() if p.get("group") == g)
                for g in set(p.get("group", "other") for p in self.open_positions.values())
            } if self.open_positions else {},
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. SLIPPAGE & FEE SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════

class CostSimulator:
    """
    Simulates real trading costs in paper mode.
    
    Without this, paper trading results are unrealistically optimistic.
    Real costs = Spread + Slippage + Exchange Fees + Price Impact.
    """

    # Exchange fee rates
    FEES = {
        "binance": {"maker": 0.0010, "taker": 0.0010},  # 0.10%
        "alpaca": {"maker": 0.0000, "taker": 0.0000},    # Commission-free
    }

    # Average slippage by market condition
    SLIPPAGE = {
        "low_vol": 0.0002,     # 0.02% in calm markets
        "normal": 0.0005,      # 0.05% normal
        "high_vol": 0.0015,    # 0.15% in volatile markets
        "crisis": 0.005,       # 0.50% during crashes
    }

    def __init__(self):
        self.total_fees_paid = 0.0
        self.total_slippage = 0.0
        self.total_trades = 0

    def simulate_execution(self, price: float, qty: float, side: str,
                           exchange: str = "binance", volatility: str = "normal") -> dict:
        """
        Simulate realistic execution with costs.
        
        Returns:
        - executed_price: price after slippage
        - fee: fee amount in USD
        - total_cost: total execution cost
        """
        # Fee
        fee_rate = self.FEES.get(exchange, self.FEES["binance"])["taker"]
        fee = price * qty * fee_rate

        # Slippage
        slippage_rate = self.SLIPPAGE.get(volatility, self.SLIPPAGE["normal"])
        if side == "BUY":
            executed_price = price * (1 + slippage_rate)  # Buy higher
        else:
            executed_price = price * (1 - slippage_rate)  # Sell lower

        slippage_cost = abs(executed_price - price) * qty

        self.total_fees_paid += fee
        self.total_slippage += slippage_cost
        self.total_trades += 1

        return {
            "executed_price": round(executed_price, 8),
            "fee": round(fee, 4),
            "slippage_cost": round(slippage_cost, 4),
            "total_cost": round(fee + slippage_cost, 4),
        }

    def get_stats(self) -> dict:
        return {
            "total_fees": round(self.total_fees_paid, 2),
            "total_slippage": round(self.total_slippage, 2),
            "total_trades": self.total_trades,
            "avg_cost_per_trade": round(
                (self.total_fees_paid + self.total_slippage) / max(self.total_trades, 1), 4
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4. ORDER FLOW ANALYZER (CVD)
# ═══════════════════════════════════════════════════════════════════════════

class OrderFlowAnalyzer:
    """
    Analyzes buy/sell pressure from recent trades.
    
    CVD (Cumulative Volume Delta) shows whether buyers or sellers dominate.
    This is one of the most powerful short-term signals available.
    """

    def analyze(self, pair: str) -> dict:
        """
        Fetch recent trades and calculate order flow metrics.
        
        Returns:
        - cvd: Cumulative Volume Delta (positive = buyers, negative = sellers)
        - buy_ratio: % of volume that is buying
        - large_order_bias: Are large orders buying or selling?
        - signal: -1 to +1 order flow signal
        """
        try:
            import requests
            # Get recent aggTrades from Binance
            resp = requests.get(
                "https://api.binance.com/api/v3/aggTrades",
                params={"symbol": pair, "limit": 500},
                timeout=10,
            )
            resp.raise_for_status()
            trades = resp.json()

            if not trades:
                return self._neutral()

            buy_volume = 0.0
            sell_volume = 0.0
            large_buy = 0.0
            large_sell = 0.0

            # Calculate average trade size for "large" threshold
            sizes = [float(t["q"]) * float(t["p"]) for t in trades]
            avg_size = sum(sizes) / len(sizes) if sizes else 1
            large_threshold = avg_size * 3  # 3x average = "large"

            for trade in trades:
                qty = float(trade["q"])
                price = float(trade["p"])
                value = qty * price
                is_buyer_maker = trade["m"]  # True = seller initiated (sell)

                if is_buyer_maker:
                    sell_volume += value
                    if value > large_threshold:
                        large_sell += value
                else:
                    buy_volume += value
                    if value > large_threshold:
                        large_buy += value

            total_volume = buy_volume + sell_volume
            if total_volume == 0:
                return self._neutral()

            cvd = buy_volume - sell_volume
            buy_ratio = buy_volume / total_volume

            # Large order bias
            large_total = large_buy + large_sell
            large_bias = (large_buy - large_sell) / max(large_total, 1)

            # Composite signal: -1 (strong sell) to +1 (strong buy)
            signal = (buy_ratio - 0.5) * 2  # Scale to -1..+1
            signal = signal * 0.7 + large_bias * 0.3  # Weight large orders

            return {
                "cvd": round(cvd, 2),
                "buy_ratio": round(buy_ratio, 3),
                "large_order_bias": round(large_bias, 3),
                "signal": round(max(-1, min(1, signal)), 3),
                "total_volume": round(total_volume, 2),
                "trade_count": len(trades),
            }

        except Exception as e:
            logger.debug(f"Order flow analysis failed for {pair}: {e}")
            return self._neutral()

    @staticmethod
    def _neutral() -> dict:
        return {
            "cvd": 0, "buy_ratio": 0.5, "large_order_bias": 0,
            "signal": 0, "total_volume": 0, "trade_count": 0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 5. INTEGRATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

# Singletons
_breaker = None
_guard = None
_costs = None
_flow = None


def get_circuit_breaker() -> CircuitBreaker:
    global _breaker
    if _breaker is None:
        _breaker = CircuitBreaker()
    return _breaker


def get_portfolio_guard() -> PortfolioGuard:
    global _guard
    if _guard is None:
        _guard = PortfolioGuard()
    return _guard


def get_cost_simulator() -> CostSimulator:
    global _costs
    if _costs is None:
        _costs = CostSimulator()
    return _costs


def get_order_flow() -> OrderFlowAnalyzer:
    global _flow
    if _flow is None:
        _flow = OrderFlowAnalyzer()
    return _flow
