"""
Risk Management Module
Handles position sizing, stop-loss, drawdown protection, and risk calculations
"""
from typing import Dict, Optional, Tuple
import time
from dataclasses import dataclass

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Position:
    """Represents an open trading position"""
    entry: float
    qty: float
    atr: float
    open_bar_time: Optional[str] = None


class RiskManager:
    """Manages risk for trading operations"""
    
    def __init__(self):
        self.config = get_config()
        self.day_start_equity: Optional[float] = None
        self.loss_streak: int = 0
        self.cooldown_until_ts: float = 0.0
        
    def position_size_for_risk(
        self, 
        price: float, 
        stop_loss_pct: float, 
        equity: float
    ) -> float:
        """
        Calculate position size based on risk per trade
        
        Args:
            price: Current price
            stop_loss_pct: Stop loss percentage (e.g., 0.01 for 1%)
            equity: Current equity
            
        Returns:
            Position size in base asset units
        """
        risk_usd = max(0.0, equity * self.config.risk.risk_pct_per_trade)
        denom = max(stop_loss_pct * price, 1e-9)
        qty = risk_usd / denom
        
        return max(0.0001, qty)
    
    def calculate_stop_loss(
        self, 
        entry: float, 
        atr: float,
        current_upnl: Optional[float] = None
    ) -> float:
        """
        Calculate dynamic stop loss percentage
        
        Args:
            entry: Entry price
            atr: Average True Range
            current_upnl: Current unrealized PnL (optional, for break-even logic)
            
        Returns:
            Stop loss percentage
        """
        # Base stop: max of floor or ATR-based
        sl_pct = max(
            self.config.risk.stop_floor,
            self.config.risk.stop_atr_mult * (atr / max(entry, 1e-9))
        )
        
        # Break-even logic: when profit exceeds trigger, tighten stop to near break-even
        if current_upnl is not None and current_upnl >= self.config.risk.break_even_trigger:
            sl_pct = min(sl_pct, 0.001)  # Move stop to 0.1% (covers fees)
        
        return sl_pct
    
    def calculate_trailing_stop(self, entry: float, current_atr: float) -> float:
        """
        Calculate trailing stop percentage based on ATR
        
        Args:
            entry: Entry price
            current_atr: Current ATR value
            
        Returns:
            Trailing stop percentage
        """
        return self.config.risk.trail_atr_mult * (current_atr / max(entry, 1e-9))
    
    def check_daily_drawdown(self, current_equity: float) -> bool:
        """
        Check if daily drawdown limit has been exceeded
        
        Args:
            current_equity: Current equity value
            
        Returns:
            True if trading should be paused, False otherwise
        """
        if self.day_start_equity is None:
            self.day_start_equity = current_equity
            return False
        
        dd = (current_equity / max(self.day_start_equity, 1e-9)) - 1.0
        
        if dd <= -self.config.risk.max_drawdown_day:
            logger.warning(
                f"Daily max drawdown reached ({dd*100:.2f}%) - pausing trading"
            )
            return True
        
        return False
    
    def check_cooldown(self) -> bool:
        """
        Check if currently in cooldown period
        
        Returns:
            True if in cooldown, False otherwise
        """
        return time.time() < self.cooldown_until_ts
    
    def trigger_cooldown(self):
        """Trigger cooldown after loss streak"""
        self.cooldown_until_ts = time.time() + (self.config.risk.cooldown_min * 60)
        logger.info(
            f"Cooldown triggered for {self.config.risk.cooldown_min} minutes "
            f"after {self.loss_streak} consecutive losses"
        )
    
    def update_loss_streak(self, is_loss: bool):
        """
        Update loss streak counter
        
        Args:
            is_loss: True if last trade was a loss
        """
        if is_loss:
            self.loss_streak += 1
            if self.loss_streak >= self.config.risk.loss_streak_cool:
                self.trigger_cooldown()
        else:
            self.loss_streak = 0
    
    def reset_daily_state(self, current_equity: float):
        """
        Reset daily risk state (call at start of new trading day)
        
        Args:
            current_equity: Current equity value
        """
        self.day_start_equity = current_equity
        self.loss_streak = 0
        self.cooldown_until_ts = 0.0
        logger.info(f"Daily risk state reset - starting equity: {current_equity:.2f}")
    
    def calculate_take_profit(
        self, 
        rsi: float, 
        adx: Optional[float] = None
    ) -> float:
        """
        Calculate dynamic take profit target
        
        Args:
            rsi: Current RSI value
            adx: Current ADX value (optional, for stretch targets)
            
        Returns:
            Take profit percentage
        """
        # Base TP: use max if RSI is high (overbought)
        base_tp = self.config.risk.tp_max if rsi >= 70 else self.config.risk.tp_min
        
        # Stretch TP in strong trends
        if adx is not None and adx >= 22.0:
            return max(base_tp, 0.02)  # 2% in strong trends
        
        return base_tp
    
    def should_exit_position(
        self,
        position: Position,
        current_price: float,
        current_atr: float,
        bars_in_position: int,
        rsi: float,
        adx: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if position should be exited
        
        Args:
            position: Current position
            current_price: Current market price
            current_atr: Current ATR
            bars_in_position: Number of bars since entry
            rsi: Current RSI
            adx: Current ADX (optional)
            
        Returns:
            Tuple of (should_exit, exit_reason)
        """
        entry = position.entry
        upnl = (current_price / entry) - 1.0
        
        # Calculate dynamic stops and targets
        sl_pct = self.calculate_stop_loss(entry, position.atr, upnl)
        trail_pct = self.calculate_trailing_stop(entry, current_atr)
        sl_pct = min(sl_pct, trail_pct)  # Trailing should TIGHTEN the stop
        
        tp_pct = self.calculate_take_profit(rsi, adx)
        
        # Check exit conditions
        if upnl >= tp_pct:
            return True, "TP"
        
        if upnl <= -sl_pct:
            return True, "SL"
        
        if bars_in_position >= self.config.risk.max_hold_bars:
            return True, "TIME"
        
        return False, None
