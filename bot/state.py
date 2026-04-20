"""
Bot State — All mutable trading state in one place.
No more scattered globals. Everything serializable for persistence.
"""
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Position:
    """An open trading position."""
    entry_price: float
    quantity: float
    atr_at_entry: float
    entry_time: str  # ISO format
    peak_pnl: float = 0.0
    trailing_active: bool = False
    partial_taken: bool = False
    bars_held: int = 0
    direction: str = "LONG"  # "LONG" or "SHORT"

    @property
    def entry_value(self) -> float:
        return self.entry_price * self.quantity

    def unrealized_pnl(self, current_price: float) -> float:
        if self.entry_price <= 0:
            return 0.0
        if self.direction == "SHORT":
            return (self.entry_price / current_price - 1.0)  # Inverted for shorts
        return (current_price / self.entry_price - 1.0)

    def unrealized_pnl_usd(self, current_price: float) -> float:
        if self.direction == "SHORT":
            return (self.entry_price - current_price) * self.quantity
        return (current_price - self.entry_price) * self.quantity


@dataclass
class BotState:
    """Complete bot state — serializable, restorable."""

    # --- Position ---
    position: Optional[Position] = None

    # --- Daily counters ---
    today_trades: int = 0
    today_date: str = ""
    daily_pnl: float = 0.0
    daily_trade_results: list = field(default_factory=list)

    # --- Streaks ---
    win_streak: int = 0
    loss_streak: int = 0

    # --- Cooldown ---
    cooldown_until: float = 0.0  # Unix timestamp
    circuit_breaker: bool = False

    # --- Paper trading ---
    paper_balance: float = 100_000.0
    paper_locked: float = 0.0  # Capital locked in open position

    # --- Last trade ---
    last_trade_ts: float = 0.0

    def reset_day(self):
        """Reset daily counters. Called at midnight UTC."""
        self.today_trades = 0
        self.today_date = datetime.now(timezone.utc).date().isoformat()
        self.daily_pnl = 0.0
        self.daily_trade_results = []
        self.circuit_breaker = False

    def check_new_day(self):
        """Auto-reset if it's a new day."""
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.today_date:
            self.reset_day()

    @property
    def is_in_position(self) -> bool:
        return self.position is not None

    @property
    def is_cooled_down(self) -> bool:
        return time.time() >= self.cooldown_until

    @property
    def available_balance(self) -> float:
        return max(0, self.paper_balance - self.paper_locked)

    def open_position(self, price: float, qty: float, atr: float):
        """Open a new position."""
        self.position = Position(
            entry_price=price,
            quantity=qty,
            atr_at_entry=atr,
            entry_time=datetime.now(timezone.utc).isoformat(),
        )
        self.paper_locked = price * qty
        self.today_trades += 1
        self.last_trade_ts = time.time()

    def close_position(self, exit_price: float) -> float:
        """Close position and return PnL in USD."""
        if not self.position:
            return 0.0

        pnl = (exit_price - self.position.entry_price) * self.position.quantity
        self.paper_balance += pnl
        self.paper_locked = 0.0
        self.daily_pnl += pnl
        self.daily_trade_results.append(pnl)

        # Update streaks
        if pnl > 0:
            self.win_streak += 1
            self.loss_streak = 0
        else:
            self.loss_streak += 1
            self.win_streak = 0

        self.position = None
        return pnl

    def trigger_cooldown(self, minutes: int):
        """Enter cooldown after loss streak."""
        self.cooldown_until = time.time() + minutes * 60
        self.loss_streak = 0  # Reset after triggering

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        d = {
            "today_trades": self.today_trades,
            "today_date": self.today_date,
            "daily_pnl": self.daily_pnl,
            "daily_trade_results": self.daily_trade_results,
            "win_streak": self.win_streak,
            "loss_streak": self.loss_streak,
            "cooldown_until": self.cooldown_until,
            "circuit_breaker": self.circuit_breaker,
            "paper_balance": self.paper_balance,
            "paper_locked": self.paper_locked,
            "last_trade_ts": self.last_trade_ts,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.position:
            d["position"] = {
                "entry_price": self.position.entry_price,
                "quantity": self.position.quantity,
                "atr_at_entry": self.position.atr_at_entry,
                "entry_time": self.position.entry_time,
                "peak_pnl": self.position.peak_pnl,
                "trailing_active": self.position.trailing_active,
                "partial_taken": self.position.partial_taken,
                "bars_held": self.position.bars_held,
            }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BotState":
        """Restore from persisted dict."""
        state = cls(
            today_trades=d.get("today_trades", 0),
            today_date=d.get("today_date", ""),
            daily_pnl=d.get("daily_pnl", 0.0),
            daily_trade_results=d.get("daily_trade_results", []),
            win_streak=d.get("win_streak", 0),
            loss_streak=d.get("loss_streak", 0),
            cooldown_until=d.get("cooldown_until", 0.0),
            circuit_breaker=d.get("circuit_breaker", False),
            paper_balance=d.get("paper_balance", 100_000.0),
            paper_locked=d.get("paper_locked", 0.0),
            last_trade_ts=d.get("last_trade_ts", 0.0),
        )
        pos = d.get("position")
        if pos and pos.get("entry_price"):
            state.position = Position(
                entry_price=pos["entry_price"],
                quantity=pos.get("quantity", 0),
                atr_at_entry=pos.get("atr_at_entry", 0),
                entry_time=pos.get("entry_time", ""),
                peak_pnl=pos.get("peak_pnl", 0.0),
                trailing_active=pos.get("trailing_active", False),
                partial_taken=pos.get("partial_taken", False),
                bars_held=pos.get("bars_held", 0),
            )
            state.paper_locked = pos["entry_price"] * pos.get("quantity", 0)
        return state

    def save(self, path: str = "logs/bot_state.json"):
        """Save state to JSON file (atomic write)."""
        import os
        import tempfile
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # Write to temp file first, then atomic replace
        dir_name = os.path.dirname(path) or "."
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            os.replace(tmp_path, path)  # Atomic on all OS
        except Exception:
            # Fallback: direct write if temp fails
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            with open(path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str = "logs/bot_state.json") -> "BotState":
        """Load state from JSON file. Returns fresh state if file doesn't exist."""
        try:
            with open(path, "r") as f:
                return cls.from_dict(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()
