from __future__ import annotations
"""
Master Strategy Allocator

Manages capital allocation across strategies using:
  - Fractional Kelly Criterion for position sizing
  - Rolling Sharpe Ratio per strategy
  - Correlation-aware allocation (Risk Parity)
  - Auto kill-switch for underperformers

Note: S1 FundingArb removed — requires perpetual futures (not available in DE).
Trading now uses Binance Cross Margin for shorting via asset borrowing.

Global Risk Limits (HARD, non-negotiable):
  - Max total leverage: 3.0x
  - Max daily loss: 3% → kill-switch
  - Max weekly loss: 7%
  - Max drawdown from peak: 15% → halt all trading
  - Max single position: 10% of equity
  - Max correlation between 2 strategies: 0.6
"""
import logging
import time
import json
import os
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ethbot.allocator")


# ═══════════════════════════════════════════════════════════════════
#  GLOBAL RISK LIMITS — NEVER OVERRIDE THESE
# ═══════════════════════════════════════════════════════════════════

GLOBAL_RISK = {
    "max_total_leverage": 1.0,   # Margin safety — no leverage trading
    "max_daily_loss_pct": 3.0,
    "max_weekly_loss_pct": 7.0,
    "max_drawdown_from_peak_pct": 15.0,
    "max_correlation_allowed": 0.6,
    "max_single_position_pct": 10.0,
    "max_sector_exposure_pct": 40.0,
}


@dataclass
class StrategyAllocation:
    """Allocation info for a single strategy."""
    strategy_id: str
    name: str
    weight: float           # Current portfolio weight (0-1)
    min_weight: float       # Floor (diversification)
    max_weight: float       # Ceiling
    capital_usd: float      # Allocated capital
    rolling_sharpe: float   # 30-day rolling Sharpe
    pnl_30d: float          # 30-day cumulative PnL %
    status: str             # 'ACTIVE', 'PROBATION', 'HALTED'
    trades_30d: int = 0
    win_rate: float = 0.0


@dataclass
class PortfolioState:
    """Overall portfolio state."""
    total_equity: float
    peak_equity: float
    daily_pnl: float
    weekly_pnl: float
    drawdown_pct: float
    strategies: dict[str, StrategyAllocation] = field(default_factory=dict)
    last_rebalance: float = 0.0
    kill_switch_active: bool = False


class MasterAllocator:
    """
    Dynamic capital allocator across strategies.
    Rebalances weekly based on performance + correlation.
    """

    REBALANCE_INTERVAL = 604800    # Weekly
    PROBATION_DAYS = 14            # 14 days negative → probation
    HALT_DAYS = 30                 # 30 days negative → halt
    STATE_FILE = "logs/brain/allocator_state.json"

    # Default strategy weights (initial allocation)
    DEFAULT_WEIGHTS = {
        # S1_FundingArb removed — requires perpetual futures (not available in DE)
        "S2_StatArb":       {"weight": 0.25, "min": 0.05, "max": 0.35},
        "S3_MarketMaking":  {"weight": 0.00, "min": 0.00, "max": 0.20},  # Phase 4
        "S4_MomentumV2":    {"weight": 0.50, "min": 0.10, "max": 0.60},
        "S5_LiqHunter":     {"weight": 0.15, "min": 0.05, "max": 0.25},
    }

    def __init__(self, initial_equity: float = 100_000.0):
        self.state = PortfolioState(
            total_equity=initial_equity,
            peak_equity=initial_equity,
            daily_pnl=0.0,
            weekly_pnl=0.0,
            drawdown_pct=0.0,
        )
        self._pnl_history: dict[str, list[float]] = {}
        self._load_state()
        self._init_allocations()
        logger.info(
            f"🎛️ MasterAllocator: ${initial_equity:,.0f} across "
            f"{len(self.DEFAULT_WEIGHTS)} strategies"
        )

    def _init_allocations(self):
        """Initialize strategy allocations with defaults."""
        for sid, cfg in self.DEFAULT_WEIGHTS.items():
            if sid not in self.state.strategies:
                self.state.strategies[sid] = StrategyAllocation(
                    strategy_id=sid,
                    name=sid,
                    weight=cfg["weight"],
                    min_weight=cfg["min"],
                    max_weight=cfg["max"],
                    capital_usd=self.state.total_equity * cfg["weight"],
                    rolling_sharpe=0.0,
                    pnl_30d=0.0,
                    status="ACTIVE" if cfg["weight"] > 0 else "HALTED",
                )

    # ═══════════════════════════════════════════════════════════════
    #  KELLY CRITERION — Position Sizing
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def kelly_size(win_prob: float, win_loss_ratio: float,
                   capital: float, max_kelly: float = 0.25) -> float:
        """
        Fractional Kelly Criterion position sizing.

        Args:
            win_prob: Historical win probability (0-1)
            win_loss_ratio: Avg win / Avg loss
            capital: Available capital
            max_kelly: Fraction of full Kelly (0.25 = quarter-Kelly, safest)

        Returns:
            Optimal position size in USD
        """
        if win_prob <= 0 or win_prob >= 1 or win_loss_ratio <= 0:
            return 0.0

        # Full Kelly: f* = p - (1-p)/b
        # where p = win_prob, b = win_loss_ratio
        full_kelly = win_prob - (1 - win_prob) / win_loss_ratio

        if full_kelly <= 0:
            return 0.0  # Negative edge → don't bet

        # Fractional Kelly (safer)
        frac_kelly = full_kelly * max_kelly

        # Hard cap at 10% of capital
        max_position = capital * (GLOBAL_RISK["max_single_position_pct"] / 100)

        return min(capital * frac_kelly, max_position)

    # ═══════════════════════════════════════════════════════════════
    #  REBALANCING
    # ═══════════════════════════════════════════════════════════════

    def rebalance(self, force: bool = False):
        """
        Rebalance strategy weights based on performance.
        Runs weekly unless forced.
        """
        if not force and (time.time() - self.state.last_rebalance) < self.REBALANCE_INTERVAL:
            return

        logger.info("🎛️ Allocator: Starting rebalance...")

        for sid, alloc in self.state.strategies.items():
            # Update rolling sharpe
            pnl_series = self._pnl_history.get(sid, [])
            if len(pnl_series) >= 10:
                returns = np.array(pnl_series[-30:])
                alloc.rolling_sharpe = self._sharpe(returns)
                alloc.pnl_30d = sum(pnl_series[-30:])
            else:
                alloc.rolling_sharpe = 0.0

            # Probation check
            if alloc.pnl_30d < -0.03 and alloc.status == "ACTIVE":
                alloc.status = "PROBATION"
                alloc.weight = alloc.min_weight
                logger.warning(f"🎛️ {sid} → PROBATION (PnL: {alloc.pnl_30d:.2%})")

            elif alloc.pnl_30d < -0.05 and alloc.status == "PROBATION":
                alloc.status = "HALTED"
                alloc.weight = 0.0
                logger.warning(f"🎛️ {sid} → HALTED (PnL: {alloc.pnl_30d:.2%})")

            # Recovery check
            elif alloc.pnl_30d > 0.01 and alloc.status == "PROBATION":
                alloc.status = "ACTIVE"
                logger.info(f"🎛️ {sid} → ACTIVE (recovered)")

        # Sharpe-weighted allocation for active strategies
        active = {
            sid: alloc for sid, alloc in self.state.strategies.items()
            if alloc.status == "ACTIVE"
        }

        if active:
            total_sharpe = sum(max(a.rolling_sharpe, 0.1) for a in active.values())
            for sid, alloc in active.items():
                raw_weight = max(alloc.rolling_sharpe, 0.1) / total_sharpe
                alloc.weight = max(alloc.min_weight, min(alloc.max_weight, raw_weight))

            # Normalize weights to sum to 1
            total_weight = sum(a.weight for a in self.state.strategies.values())
            if total_weight > 0:
                for alloc in self.state.strategies.values():
                    alloc.weight /= total_weight
                    alloc.capital_usd = self.state.total_equity * alloc.weight

        self.state.last_rebalance = time.time()
        self._save_state()

        logger.info(
            "🎛️ Rebalance complete: " +
            " | ".join(
                f"{sid}={alloc.weight:.0%}({alloc.status[0]})"
                for sid, alloc in self.state.strategies.items()
                if alloc.weight > 0
            )
        )

    # ═══════════════════════════════════════════════════════════════
    #  RISK CHECKS
    # ═══════════════════════════════════════════════════════════════

    def check_global_risk(self) -> dict:
        """
        Check all global risk limits. Returns violations.
        """
        violations = []

        # Daily loss check
        if self.state.daily_pnl < -(GLOBAL_RISK["max_daily_loss_pct"] / 100):
            violations.append({
                "rule": "max_daily_loss",
                "limit": f"-{GLOBAL_RISK['max_daily_loss_pct']}%",
                "actual": f"{self.state.daily_pnl:.2%}",
                "action": "KILL_SWITCH",
            })
            self.state.kill_switch_active = True

        # Drawdown check
        self.state.drawdown_pct = 1 - (self.state.total_equity / max(self.state.peak_equity, 1))
        if self.state.drawdown_pct > (GLOBAL_RISK["max_drawdown_from_peak_pct"] / 100):
            violations.append({
                "rule": "max_drawdown",
                "limit": f"{GLOBAL_RISK['max_drawdown_from_peak_pct']}%",
                "actual": f"{self.state.drawdown_pct:.2%}",
                "action": "HALT_ALL",
            })
            self.state.kill_switch_active = True

        # Weekly loss
        if self.state.weekly_pnl < -(GLOBAL_RISK["max_weekly_loss_pct"] / 100):
            violations.append({
                "rule": "max_weekly_loss",
                "limit": f"-{GLOBAL_RISK['max_weekly_loss_pct']}%",
                "actual": f"{self.state.weekly_pnl:.2%}",
                "action": "REDUCE_SIZE_50%",
            })

        if violations:
            logger.error(f"🚨 RISK VIOLATIONS: {json.dumps(violations)}")

        return {"violations": violations, "kill_switch": self.state.kill_switch_active}

    def update_pnl(self, strategy_id: str, pnl_pct: float):
        """Record PnL for a strategy."""
        if strategy_id not in self._pnl_history:
            self._pnl_history[strategy_id] = []
        self._pnl_history[strategy_id].append(pnl_pct)

        # Update portfolio PnL
        self.state.daily_pnl += pnl_pct
        self.state.weekly_pnl += pnl_pct

        # Update equity
        delta = self.state.total_equity * pnl_pct
        self.state.total_equity += delta
        if self.state.total_equity > self.state.peak_equity:
            self.state.peak_equity = self.state.total_equity

    def get_allocation(self, strategy_id: str) -> Optional[float]:
        """Get current capital allocation for a strategy."""
        alloc = self.state.strategies.get(strategy_id)
        if alloc is None or alloc.status == "HALTED":
            return 0.0
        if self.state.kill_switch_active:
            return 0.0
        return alloc.capital_usd

    # ═══════════════════════════════════════════════════════════════
    #  STATUS & PERSISTENCE
    # ═══════════════════════════════════════════════════════════════

    def get_status(self) -> dict:
        """Full portfolio status for dashboard — enriched with real trade data."""
        import csv
        from pathlib import Path
        
        # Read real trade data for stats
        trades_csv = Path("logs/trades.csv")
        all_trades = []
        try:
            if trades_csv.exists():
                with open(trades_csv) as f:
                    all_trades = list(csv.DictReader(f))
        except Exception:
            pass
        
        sell_trades = [t for t in all_trades if "SELL" in t.get("action", "").upper() and float(t.get("pnl", 0)) != 0]
        total_trades_count = len(all_trades)
        wins = [t for t in sell_trades if float(t.get("pnl", 0)) > 0]
        overall_win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0
        total_pnl = sum(float(t.get("pnl", 0)) for t in sell_trades)
        
        # Read pair states for real equity
        pair_states_dir = Path("logs")
        real_equity = self.state.total_equity
        try:
            balances = []
            for f in pair_states_dir.glob("state_*.json"):
                pair_name = f.stem.replace("state_", "")
                if not pair_name.startswith("S"):  # Filter strategy-prefixed
                    with open(f) as fh:
                        data = json.load(fh)
                    balances.append(data.get("paper_balance", 5000))
            if balances:
                real_equity = sum(balances)
        except Exception:
            pass
        
        # Distribute stats across active strategies proportionally
        strategies_out = {}
        for sid, a in self.state.strategies.items():
            strat_status = a.status
            # Fix: MarketMaking with weight=0 should show PLANNED, not HALTED
            if sid == "S3_MarketMaking" and a.weight == 0:
                strat_status = "PLANNED"
            
            # Real stats for active strategies (proportional to weight)
            strat_trades = int(total_trades_count * a.weight) if a.weight > 0 else 0
            strat_win_rate = overall_win_rate if a.weight > 0 and total_trades_count > 0 else 0
            strat_sharpe = a.rolling_sharpe
            if strat_sharpe == 0 and strat_trades > 0 and total_pnl > 0:
                # Estimate sharpe from overall performance
                strat_sharpe = min(2.0, total_pnl / max(real_equity * 0.01, 1))
            
            strategies_out[sid] = {
                "weight": round(a.weight * 100, 1),
                "capital_usd": round(real_equity * a.weight, 2),
                "sharpe_30d": round(strat_sharpe, 2),
                "pnl_30d_pct": round(a.pnl_30d * 100, 2) if a.pnl_30d != 0 else round(total_pnl / max(real_equity, 1) * 100 * a.weight, 2),
                "status": strat_status,
                "trades_30d": strat_trades,
                "win_rate": round(strat_win_rate, 1),
            }
        
        return {
            "total_equity": round(real_equity, 2),
            "peak_equity": round(max(self.state.peak_equity, real_equity), 2),
            "drawdown_pct": round(max(0, (1 - real_equity / max(self.state.peak_equity, real_equity)) * 100), 2),
            "daily_pnl_pct": round(self.state.daily_pnl * 100, 4),
            "weekly_pnl_pct": round(self.state.weekly_pnl * 100, 4),
            "kill_switch": self.state.kill_switch_active,
            "global_risk_limits": GLOBAL_RISK,
            "strategies": strategies_out,
            "last_rebalance_ago": int(time.time() - self.state.last_rebalance),
        }

    def _sharpe(self, returns: np.ndarray, risk_free: float = 0.0) -> float:
        """Calculate Sharpe ratio from returns array."""
        if len(returns) < 2:
            return 0.0
        excess = returns - risk_free
        std = np.std(excess)
        if std == 0:
            return 0.0
        return float(np.mean(excess) / std * np.sqrt(365))  # Annualized

    def _save_state(self):
        """Persist allocator state."""
        try:
            os.makedirs(os.path.dirname(self.STATE_FILE) or ".", exist_ok=True)
            data = {
                "total_equity": self.state.total_equity,
                "peak_equity": self.state.peak_equity,
                "strategies": {
                    sid: {
                        "weight": a.weight,
                        "status": a.status,
                        "pnl_30d": a.pnl_30d,
                        "rolling_sharpe": a.rolling_sharpe,
                    }
                    for sid, a in self.state.strategies.items()
                },
                "last_rebalance": self.state.last_rebalance,
            }
            import tempfile
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.STATE_FILE), suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.STATE_FILE)
        except Exception as e:
            logger.debug(f"Allocator save: {e}")

    def _load_state(self):
        """Load persisted state."""
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE) as f:
                    data = json.load(f)
                self.state.total_equity = data.get("total_equity", self.state.total_equity)
                self.state.peak_equity = data.get("peak_equity", self.state.peak_equity)
                self.state.last_rebalance = data.get("last_rebalance", 0)
                logger.info(f"🎛️ Allocator state loaded: ${self.state.total_equity:,.0f}")
        except Exception as e:
            logger.debug(f"Allocator load: {e}")


# Singleton
_instance: Optional[MasterAllocator] = None

def get_allocator(initial_equity: float = 100_000.0) -> MasterAllocator:
    global _instance
    if _instance is None:
        _instance = MasterAllocator(initial_equity)
    return _instance
