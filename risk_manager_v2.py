"""
Ethbot v2: Enhanced Risk Manager

Extends the existing RiskManager with:
- Kelly Criterion position sizing (based on validated edge)
- Weekly drawdown limit (-5%)
- Max simultaneous positions (3)
- Gradual capital rollout (10% → 25% → 50% → 100%)
- Circuit breaker (auto-pause after extreme losses)

Usage:
    from risk_manager_v2 import risk_engine
    
    # Check if trading is allowed
    if risk_engine.can_trade():
        size = risk_engine.calculate_position_size(equity, price)
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger("ethbot.risk_v2")


class RiskManagerV2:
    """Production-grade risk management for edge-validated trading."""

    def __init__(self):
        # ─── Hard Limits ───
        self.max_risk_per_trade = 0.01        # 1% of capital per trade
        self.max_daily_drawdown = 0.02         # -2% → pause until midnight
        self.max_weekly_drawdown = 0.05        # -5% → pause until Monday
        self.max_simultaneous_positions = 3
        self.max_consecutive_losses = 6

        # ─── Capital Rollout ───
        self.rollout_stages = {
            0:   0.10,   # Start: 10% of capital
            50:  0.25,   # After 50 trades: 25%
            100: 0.50,   # After 100 trades: 50%
            200: 1.00,   # After 200 trades: 100%
        }

        # ─── State ───
        self._total_trades = 0
        self._consecutive_losses = 0
        self._open_positions = 0
        self._day_start_equity = None
        self._week_start_equity = None
        self._day_start_ts = 0
        self._week_start_ts = 0
        self._paused_until = 0
        self._pause_reason = ""

    # ─── Position Sizing ───

    def kelly_position_size(
        self,
        equity: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        price: float,
        stop_loss_pct: float = 0.012
    ) -> float:
        """
        Calculate position size using Kelly Criterion.
        
        Kelly = (W × B - L) / B
        Where: W = win rate, L = loss rate, B = avg_win / avg_loss
        
        We use HALF-KELLY for safety (never full Kelly).
        """
        if win_rate <= 0 or avg_loss <= 0 or price <= 0:
            return 0.0

        w = win_rate / 100  # Convert to decimal
        l = 1 - w
        b = avg_win / max(avg_loss, 0.001)  # Win/Loss ratio

        kelly_pct = (w * b - l) / max(b, 0.001)

        # Half-Kelly for safety
        kelly_pct *= 0.5

        # Cap at max risk per trade
        kelly_pct = max(0, min(kelly_pct, self.max_risk_per_trade))

        # Apply capital rollout multiplier
        rollout = self._get_rollout_multiplier()
        risk_usd = equity * kelly_pct * rollout

        # Convert to position size
        qty = risk_usd / max(stop_loss_pct * price, 1e-9)

        logger.debug(
            f"Kelly: WR={win_rate:.1f}% B={b:.2f} kelly={kelly_pct*100:.3f}% "
            f"rollout={rollout*100:.0f}% → ${risk_usd:.2f} risk"
        )

        return max(0.0001, qty)

    def fixed_risk_position_size(
        self,
        equity: float,
        price: float,
        stop_loss_pct: float = 0.012
    ) -> float:
        """Fixed 1% risk position sizing (fallback when edge is not yet validated)."""
        rollout = self._get_rollout_multiplier()
        risk_usd = equity * self.max_risk_per_trade * rollout
        qty = risk_usd / max(stop_loss_pct * price, 1e-9)
        return max(0.0001, qty)

    def _get_rollout_multiplier(self) -> float:
        """Get current capital rollout multiplier based on trade count."""
        multiplier = 0.10  # Default: 10%
        for threshold, pct in sorted(self.rollout_stages.items()):
            if self._total_trades >= threshold:
                multiplier = pct
        return multiplier

    # ─── Trading Guards ───

    def can_trade(self, current_equity: float = None) -> tuple:
        """
        Check all risk conditions. Returns (allowed, reason).
        
        Returns:
            (True, "OK") if trading is allowed
            (False, "reason") if blocked
        """
        now = time.time()

        # Circuit breaker — paused?
        if now < self._paused_until:
            remaining = int(self._paused_until - now)
            return False, f"Paused ({self._pause_reason}) — resume in {remaining}s"

        # Max simultaneous positions
        if self._open_positions >= self.max_simultaneous_positions:
            return False, f"Max {self.max_simultaneous_positions} positions reached"

        # Consecutive loss limit
        if self._consecutive_losses >= self.max_consecutive_losses:
            return False, f"Loss streak {self._consecutive_losses} — cooldown active"

        # Daily drawdown check
        if current_equity and self._day_start_equity:
            daily_dd = 1 - (current_equity / max(self._day_start_equity, 1))
            if daily_dd >= self.max_daily_drawdown:
                self._pause("daily_drawdown", self._seconds_until_midnight())
                return False, f"Daily drawdown limit reached ({daily_dd*100:.1f}%)"

        # Weekly drawdown check
        if current_equity and self._week_start_equity:
            weekly_dd = 1 - (current_equity / max(self._week_start_equity, 1))
            if weekly_dd >= self.max_weekly_drawdown:
                self._pause("weekly_drawdown", self._seconds_until_monday())
                return False, f"Weekly drawdown limit reached ({weekly_dd*100:.1f}%)"

        return True, "OK"

    def on_trade_opened(self):
        """Called when a new position is opened."""
        self._open_positions += 1
        self._total_trades += 1

    def on_trade_closed(self, is_win: bool, pnl_pct: float = 0):
        """Called when a position is closed."""
        self._open_positions = max(0, self._open_positions - 1)

        if is_win:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.max_consecutive_losses:
                # Auto-pause for 2 hours after max streak
                self._pause("loss_streak", 7200)
                logger.warning(f"Circuit breaker: {self._consecutive_losses} consecutive losses — 2h cooldown")

    def update_equity_markers(self, equity: float):
        """Update day/week start equity. Call at the start of each session."""
        now = time.time()

        # New day?
        if now - self._day_start_ts > 86400:
            self._day_start_equity = equity
            self._day_start_ts = now
            self._consecutive_losses = 0  # Reset streak on new day

        # New week?
        if now - self._week_start_ts > 604800:
            self._week_start_equity = equity
            self._week_start_ts = now

    # ─── Internal ───

    def _pause(self, reason: str, duration_seconds: int):
        """Pause trading for a specified duration."""
        self._paused_until = time.time() + duration_seconds
        self._pause_reason = reason
        logger.warning(f"🛑 Trading PAUSED: {reason} for {duration_seconds/3600:.1f}h")

    def _seconds_until_midnight(self) -> int:
        """Seconds until UTC midnight."""
        now = datetime.now(timezone.utc)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if now >= midnight:
            from datetime import timedelta
            midnight += timedelta(days=1)
        return int((midnight - now).total_seconds())

    def _seconds_until_monday(self) -> int:
        """Seconds until next Monday 00:00 UTC."""
        now = datetime.now(timezone.utc)
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        from datetime import timedelta
        monday = (now + timedelta(days=days_until_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return int((monday - now).total_seconds())

    def get_status(self) -> Dict:
        """Return current risk status for dashboard."""
        now = time.time()
        paused = now < self._paused_until

        return {
            "can_trade": not paused and self._consecutive_losses < self.max_consecutive_losses,
            "paused": paused,
            "pause_reason": self._pause_reason if paused else None,
            "pause_remaining_s": max(0, int(self._paused_until - now)) if paused else 0,
            "total_trades": self._total_trades,
            "open_positions": self._open_positions,
            "max_positions": self.max_simultaneous_positions,
            "consecutive_losses": self._consecutive_losses,
            "max_consecutive_losses": self.max_consecutive_losses,
            "capital_rollout_pct": self._get_rollout_multiplier() * 100,
            "daily_drawdown_limit": self.max_daily_drawdown * 100,
            "weekly_drawdown_limit": self.max_weekly_drawdown * 100,
        }


# Singleton
risk_engine = RiskManagerV2()
