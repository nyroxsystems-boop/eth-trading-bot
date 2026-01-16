"""
Trading Guards Module
Consolidated pre-buy safeguards and risk checks
"""
import csv
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Tuple
from collections import deque

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TradeGuards:
    """Consolidated trading safeguards"""
    
    def __init__(self, trades_csv_path: Optional[str] = None):
        self.trades_csv = trades_csv_path or str(Path.cwd() / "logs" / "trades.csv")
        self.timestamp_format = "%Y-%m-%d %H:%M:%S"
        self.tz = timezone.utc
    
    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse timestamp string to datetime"""
        return datetime.strptime(ts_str, self.timestamp_format).replace(tzinfo=self.tz)
    
    def _load_trades(self) -> List[dict]:
        """Load trades from CSV"""
        try:
            with open(self.trades_csv, "r", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except FileNotFoundError:
            logger.debug(f"Trades CSV not found: {self.trades_csv}")
            return []
        except Exception as e:
            logger.warning(f"Error loading trades CSV: {e}")
            return []
    
    def _get_closed_pairs(self, rows: List[dict], limit: int = 200) -> List[Tuple[dict, dict]]:
        """Get closed trade pairs (BUY-SELL) using FIFO"""
        # Filter valid rows
        rows = [r for r in rows if r.get("price") not in ("", "0", "0.0", "0.00")]
        rows.sort(key=lambda r: r["timestamp"])
        
        pairs = []
        stack = []
        
        for r in rows:
            action = r["action"].upper()
            if action == "BUY":
                stack.append(r)
            elif action == "SELL" and stack:
                buy_row = stack.pop(0)  # FIFO pairing
                pairs.append((buy_row, r))
        
        return pairs[-limit:]
    
    def check_max_consecutive_losses(
        self,
        max_losses: int = 3,
        cooldown_minutes: int = 60
    ) -> Tuple[bool, str]:
        """
        Check if max consecutive losses limit reached
        
        Args:
            max_losses: Maximum consecutive losses allowed
            cooldown_minutes: Cooldown period after max losses
            
        Returns:
            Tuple of (is_blocked, reason)
        """
        rows = self._load_trades()
        if not rows:
            return False, "No trades yet"
        
        pairs = self._get_closed_pairs(rows, 200)
        
        consecutive_losses = 0
        last_sell_ts = None
        
        # Count consecutive losses from most recent
        for buy_row, sell_row in reversed(pairs):
            try:
                buy_price = float(buy_row["price"])
                sell_price = float(sell_row["price"])
                qty = min(float(buy_row["qty"]), float(sell_row["qty"]))
                pnl = (sell_price - buy_price) * qty
                
                last_sell_ts = self._parse_timestamp(sell_row["timestamp"])
                
                if pnl < 0:
                    consecutive_losses += 1
                else:
                    break  # Streak broken
            except (ValueError, KeyError):
                continue
        
        # Check if in cooldown
        if consecutive_losses >= max_losses and last_sell_ts:
            cooldown_until = last_sell_ts + timedelta(minutes=cooldown_minutes)
            if datetime.now(self.tz) < cooldown_until:
                reason = f"{consecutive_losses} consecutive losses - cooldown until {cooldown_until.isoformat()}"
                logger.warning(f"[GUARD] Max losses: {reason}")
                return True, reason
        
        return False, f"{consecutive_losses} consecutive losses (OK)"
    
    def check_daily_target_reached(
        self,
        target_pct: float = 0.02,
        equity: float = 100000.0
    ) -> Tuple[bool, str]:
        """
        Check if daily profit target reached
        
        Args:
            target_pct: Daily target percentage (e.g., 0.02 for 2%)
            equity: Total equity
            
        Returns:
            Tuple of (is_blocked, reason)
        """
        rows = self._load_trades()
        if not rows:
            return False, "No trades yet"
        
        # Calculate today's PnL using FIFO
        today_start = datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
        fifo_queue = deque()
        realized_pnl = 0.0
        
        for row in rows:
            try:
                ts = self._parse_timestamp(row["timestamp"])
                if ts < today_start:
                    continue
                
                action = row["action"].upper()
                qty = float(row["qty"])
                price = float(row["price"])
                
                if price <= 0:
                    continue
                
                if action == "BUY":
                    fifo_queue.append([qty, price])
                elif action == "SELL":
                    remaining = qty
                    while remaining > 1e-12 and fifo_queue:
                        buy_qty, buy_price = fifo_queue[0]
                        take = min(buy_qty, remaining)
                        realized_pnl += (price - buy_price) * take
                        buy_qty -= take
                        remaining -= take
                        
                        if buy_qty <= 1e-12:
                            fifo_queue.popleft()
                        else:
                            fifo_queue[0] = [buy_qty, buy_price]
            except (ValueError, KeyError):
                continue
        
        target_usd = equity * target_pct
        
        if realized_pnl >= target_usd:
            reason = f"Daily target reached: ${realized_pnl:.2f} >= ${target_usd:.2f}"
            logger.info(f"[GUARD] {reason}")
            return True, reason
        
        return False, f"PnL ${realized_pnl:.2f} < target ${target_usd:.2f}"
    
    def check_all_guards(
        self,
        max_losses: int = 3,
        cooldown_minutes: int = 60,
        target_pct: float = 0.02,
        equity: float = 100000.0
    ) -> Tuple[bool, List[str]]:
        """
        Run all pre-buy guards
        
        Returns:
            Tuple of (is_blocked, reasons)
        """
        reasons = []
        
        # Check max losses
        blocked, reason = self.check_max_consecutive_losses(max_losses, cooldown_minutes)
        if blocked:
            return True, [f"Max losses: {reason}"]
        reasons.append(f"✓ {reason}")
        
        # Check daily target
        blocked, reason = self.check_daily_target_reached(target_pct, equity)
        if blocked:
            return True, [f"Daily target: {reason}"]
        reasons.append(f"✓ {reason}")
        
        return False, reasons


# Standalone functions for backward compatibility with subprocess calls
def max_losses_guard_main():
    """Standalone max losses guard (for subprocess compatibility)"""
    max_losses = int(os.getenv("MAX_CONSEC_LOSSES", "3"))
    cooldown = int(os.getenv("COOLDOWN_AFTER_MAX_LOSSES_MIN", "60"))
    
    guards = TradeGuards()
    blocked, reason = guards.check_max_consecutive_losses(max_losses, cooldown)
    
    print(f"[MAXLOSS] {reason}")
    sys.exit(2 if blocked else 0)


def daily_target_guard_main():
    """Standalone daily target guard (for subprocess compatibility)"""
    target_pct = float(os.getenv("DAILY_TARGET_PCT", "0.02"))
    equity = float(os.getenv("EQUITY_USDT", os.getenv("PAPER_BASE_USDT", "100000")))
    
    guards = TradeGuards()
    blocked, reason = guards.check_daily_target_reached(target_pct, equity)
    
    print(f"[DAILY_TARGET] {reason}")
    sys.exit(2 if blocked else 0)
