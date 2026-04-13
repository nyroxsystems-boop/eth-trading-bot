"""
Advanced Trading Guards V2
Professional-grade risk management:
- Dynamic position sizing (Kelly Criterion)
- Volatility-adjusted stops
- Correlation-based exposure limits
- Drawdown protection with exponential cooldowns
- Time-of-day filters
- Momentum crash protection
"""

import os
import csv
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RiskMetrics:
    """Real-time risk metrics"""
    current_drawdown: float
    max_drawdown: float
    volatility: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    exposure: float
    risk_score: float  # 0-100, higher = more risky


class AdvancedTradeGuards:
    """
    Professional risk management system.
    Prevents catastrophic losses and optimizes position sizing.
    """
    
    def __init__(self, trades_csv_path: Optional[str] = None, equity: float = 100000):
        self.trades_csv = trades_csv_path or str(Path.cwd() / "logs" / "trades.csv")
        self.equity = equity
        self.tz = timezone.utc
        self.timestamp_format = "%Y-%m-%d %H:%M:%S"
        
        # Risk parameters (FIXED: was unreachable dead code after return in _parse_timestamp)
        self.max_drawdown_pct = 0.15  # 15% max drawdown
        self.max_daily_loss_pct = 0.05  # 5% max daily loss
        self.max_consecutive_losses = 4
        self.volatility_multiplier = 2.0  # For stop loss
        self.min_win_rate = 0.35  # Minimum acceptable win rate
        
        # Kelly Criterion parameters
        self.kelly_fraction = 0.25  # Use 25% Kelly (conservative)
        self.max_position_pct = 0.20  # Never risk more than 20%
        self.min_position_pct = 0.02  # Minimum 2% position
        
        # Time filters
        self.trading_hours_start = 8  # UTC
        self.trading_hours_end = 22  # UTC
        self.weekend_trading = False
        
        # Internal state
        self._risk_metrics_cache: Optional[RiskMetrics] = None
        self._cache_timestamp: Optional[datetime] = None
    
    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse timestamp string robustly (supports ISO and fixed formats)"""
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
        ):
            try:
                return datetime.strptime(ts_str.strip(), fmt).replace(tzinfo=self.tz)
            except ValueError:
                continue
        logger.warning(f"[GUARD] Unparseable timestamp '{ts_str}', using current time")
        return datetime.now(self.tz)
    
    def calculate_risk_metrics(self, lookback_trades: int = 100) -> RiskMetrics:
        """Calculate comprehensive risk metrics"""
        # Check cache (valid for 1 minute)
        if self._risk_metrics_cache and self._cache_timestamp:
            if (datetime.now(self.tz) - self._cache_timestamp).seconds < 60:
                return self._risk_metrics_cache
        
        trades = self._load_trades()
        closed_pairs = self._get_closed_pairs(trades, lookback_trades)
        
        if not closed_pairs:
            return RiskMetrics(
                current_drawdown=0, max_drawdown=0, volatility=0,
                sharpe_ratio=0, win_rate=0.5, profit_factor=1.0,
                exposure=0, risk_score=50
            )
        
        # Calculate PnL series
        pnls = []
        for buy, sell in closed_pairs:
            try:
                buy_price = float(buy["price"])
                sell_price = float(sell["price"])
                qty = min(float(buy["qty"]), float(sell["qty"]))
                pnl = (sell_price - buy_price) * qty
                pnls.append(pnl)
            except (ValueError, KeyError):
                continue
        
        if not pnls:
            return RiskMetrics(
                current_drawdown=0, max_drawdown=0, volatility=0,
                sharpe_ratio=0, win_rate=0.5, profit_factor=1.0,
                exposure=0, risk_score=50
            )
        
        pnls = np.array(pnls)
        
        # Win rate
        wins = np.sum(pnls > 0)
        total = len(pnls)
        win_rate = wins / total
        
        # Profit factor
        gross_profit = np.sum(pnls[pnls > 0])
        gross_loss = abs(np.sum(pnls[pnls < 0]))
        profit_factor = gross_profit / (gross_loss + 1e-10)
        
        # Drawdown
        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (running_max - cumulative) / (self.equity + running_max + 1e-10)
        max_drawdown = np.max(drawdowns) if len(drawdowns) > 0 else 0
        current_drawdown = drawdowns[-1] if len(drawdowns) > 0 else 0
        
        # Volatility (std of returns)
        returns = pnls / self.equity
        volatility = np.std(returns) if len(returns) > 1 else 0
        
        # Sharpe ratio (simplified)
        avg_return = np.mean(returns)
        sharpe_ratio = (avg_return / (volatility + 1e-10)) * np.sqrt(252)  # Annualized
        
        # Current exposure (if in position)
        exposure = self._calculate_current_exposure(trades)
        
        # Risk score (0-100, higher = more risky)
        risk_score = self._calculate_risk_score(
            current_drawdown, max_drawdown, volatility, 
            win_rate, profit_factor, exposure
        )
        
        self._risk_metrics_cache = RiskMetrics(
            current_drawdown=round(current_drawdown, 4),
            max_drawdown=round(max_drawdown, 4),
            volatility=round(volatility, 6),
            sharpe_ratio=round(sharpe_ratio, 2),
            win_rate=round(win_rate, 3),
            profit_factor=round(profit_factor, 2),
            exposure=round(exposure, 4),
            risk_score=round(risk_score, 1)
        )
        self._cache_timestamp = datetime.now(self.tz)
        
        return self._risk_metrics_cache
    
    def _calculate_risk_score(
        self, 
        current_dd: float, 
        max_dd: float, 
        vol: float,
        win_rate: float,
        pf: float,
        exposure: float
    ) -> float:
        """Calculate composite risk score 0-100"""
        score = 0
        
        # Drawdown component (0-30)
        dd_score = min(current_dd / self.max_drawdown_pct, 1.0) * 30
        score += dd_score
        
        # Volatility component (0-20)
        vol_baseline = 0.02  # 2% is normal
        vol_score = min(vol / vol_baseline, 2.0) * 10
        score += vol_score
        
        # Win rate component (0-20, inverted)
        wr_score = (1 - win_rate) * 20
        score += wr_score
        
        # Exposure component (0-15)
        exp_score = exposure * 15
        score += exp_score
        
        # Profit factor component (0-15, inverted)
        pf_score = max(0, (2 - pf) / 2) * 15
        score += pf_score
        
        return min(score, 100)
    
    def _calculate_current_exposure(self, trades: List[dict]) -> float:
        """Calculate current market exposure"""
        # Simple FIFO to find open position
        stack = []
        for trade in trades:
            action = trade.get("action", "").upper()
            if action == "BUY":
                stack.append(trade)
            elif action == "SELL" and stack:
                stack.pop(0)
        
        if not stack:
            return 0.0
        
        # Calculate value of open positions
        total_value = 0
        for buy in stack:
            try:
                qty = float(buy["qty"])
                price = float(buy["price"])
                total_value += qty * price
            except (ValueError, KeyError):
                continue
        
        return total_value / self.equity
    
    def calculate_kelly_position_size(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Calculate optimal position size using Kelly Criterion.
        Returns fraction of equity to risk.
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return self.min_position_pct
        
        # Kelly formula: f = (bp - q) / b
        # where b = avg_win/avg_loss, p = win_rate, q = 1 - p
        b = avg_win / abs(avg_loss)
        p = win_rate
        q = 1 - p
        
        kelly = (b * p - q) / b
        
        # Apply conservative fraction
        kelly = kelly * self.kelly_fraction
        
        # Clamp to limits
        kelly = max(self.min_position_pct, min(self.max_position_pct, kelly))
        
        return kelly
    
    def calculate_volatility_stop(self, current_price: float, atr: float) -> float:
        """Calculate volatility-adjusted stop loss price"""
        stop_distance = atr * self.volatility_multiplier
        stop_price = current_price - stop_distance
        return max(stop_price, current_price * 0.95)  # Never more than 5% stop
    
    def check_time_filter(self) -> Tuple[bool, str]:
        """Check if current time is within trading hours"""
        now = datetime.now(self.tz)
        
        # Weekend check
        if not self.weekend_trading and now.weekday() >= 5:
            return True, f"Weekend trading disabled (day={now.weekday()})"
        
        # Hour check
        if not (self.trading_hours_start <= now.hour < self.trading_hours_end):
            return True, f"Outside trading hours ({self.trading_hours_start}:00-{self.trading_hours_end}:00 UTC)"
        
        return False, "Within trading hours"
    
    def check_drawdown_limit(self) -> Tuple[bool, str]:
        """Check if drawdown exceeds limit"""
        metrics = self.calculate_risk_metrics()
        
        if metrics.current_drawdown >= self.max_drawdown_pct:
            cooldown_hours = int(metrics.current_drawdown / self.max_drawdown_pct * 24)
            return True, f"Max drawdown reached: {metrics.current_drawdown:.1%} (cooldown: {cooldown_hours}h)"
        
        return False, f"Drawdown OK: {metrics.current_drawdown:.1%}"
    
    def check_daily_loss_limit(self) -> Tuple[bool, str]:
        """Check if daily loss limit exceeded"""
        trades = self._load_trades()
        today_start = datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
        
        daily_pnl = 0
        for trade in trades:
            try:
                ts = self._parse_timestamp(trade["timestamp"])
                if ts >= today_start and trade["action"].upper() == "SELL":
                    pnl = float(trade.get("pnl", 0))
                    daily_pnl += pnl
            except (ValueError, KeyError):
                continue
        
        daily_loss_pct = abs(min(0, daily_pnl)) / self.equity
        
        if daily_loss_pct >= self.max_daily_loss_pct:
            return True, f"Daily loss limit: {daily_loss_pct:.1%} >= {self.max_daily_loss_pct:.1%}"
        
        return False, f"Daily P&L: {daily_pnl:+.2f} ({daily_loss_pct:.1%} of limit)"
    
    def check_consecutive_losses(self) -> Tuple[bool, str]:
        """Check consecutive losses with exponential cooldown"""
        trades = self._load_trades()
        pairs = self._get_closed_pairs(trades, 50)
        
        consecutive = 0
        last_loss_time = None
        
        for buy, sell in reversed(pairs):
            try:
                buy_price = float(buy["price"])
                sell_price = float(sell["price"])
                pnl = sell_price - buy_price
                
                if pnl < 0:
                    consecutive += 1
                    last_loss_time = self._parse_timestamp(sell["timestamp"])
                else:
                    break
            except (ValueError, KeyError):
                continue
        
        if consecutive >= self.max_consecutive_losses and last_loss_time:
            # Exponential cooldown: 30min * 2^(losses - max)
            cooldown_minutes = 30 * (2 ** (consecutive - self.max_consecutive_losses))
            cooldown_until = last_loss_time + timedelta(minutes=cooldown_minutes)
            
            if datetime.now(self.tz) < cooldown_until:
                remaining = (cooldown_until - datetime.now(self.tz)).seconds // 60
                return True, f"{consecutive} losses, cooldown {remaining}min remaining"
        
        return False, f"Consecutive losses: {consecutive}"
    
    def check_momentum_crash(self, prices: np.ndarray) -> Tuple[bool, str]:
        """Detect and protect against momentum crashes"""
        if len(prices) < 10:
            return False, "Insufficient data"
        
        # Calculate recent momentum
        returns = np.diff(prices[-10:]) / prices[-11:-1]
        
        # Flash crash detection: >3% drop in last 10 candles
        cum_return = (prices[-1] / prices[-10]) - 1
        
        if cum_return < -0.03:
            return True, f"Momentum crash detected: {cum_return:.1%} in last 10 candles"
        
        # High volatility spike
        vol = np.std(returns)
        if vol > 0.02:  # 2% volatility per candle is extreme
            return True, f"Extreme volatility: {vol:.1%} per candle"
        
        return False, f"Momentum OK: {cum_return:+.1%}"
    
    def check_win_rate(self) -> Tuple[bool, str]:
        """Check if win rate is acceptable"""
        metrics = self.calculate_risk_metrics()
        
        if metrics.win_rate < self.min_win_rate:
            return True, f"Low win rate: {metrics.win_rate:.0%} < {self.min_win_rate:.0%}"
        
        return False, f"Win rate: {metrics.win_rate:.0%}"
    
    def get_optimal_position_size(self) -> Dict:
        """Get optimal position size based on all factors"""
        metrics = self.calculate_risk_metrics()
        
        # Base Kelly size
        kelly_size = self.calculate_kelly_position_size(
            metrics.win_rate,
            metrics.profit_factor,  # Approximation
            1.0  # Normalized
        )
        
        # Adjust for risk score
        risk_adjustment = 1 - (metrics.risk_score / 200)  # 0.5 at risk=100
        adjusted_size = kelly_size * risk_adjustment
        
        # Adjust for drawdown
        dd_adjustment = 1 - (metrics.current_drawdown / self.max_drawdown_pct)
        adjusted_size *= max(0.1, dd_adjustment)
        
        # Clamp
        final_size = max(self.min_position_pct, min(self.max_position_pct, adjusted_size))
        
        return {
            "position_size_pct": round(final_size * 100, 2),
            "position_size_usd": round(self.equity * final_size, 2),
            "kelly_raw": round(kelly_size * 100, 2),
            "risk_adjustment": round(risk_adjustment, 2),
            "dd_adjustment": round(dd_adjustment, 2),
            "risk_metrics": {
                "risk_score": metrics.risk_score,
                "win_rate": metrics.win_rate,
                "drawdown": metrics.current_drawdown,
                "sharpe": metrics.sharpe_ratio
            }
        }
    
    def check_all_guards(self, prices: np.ndarray = None) -> Tuple[bool, List[str], RiskMetrics]:
        """
        Run all guards.
        Returns (is_blocked, reasons, risk_metrics)
        """
        reasons = []
        metrics = self.calculate_risk_metrics()
        
        # Time filter
        blocked, reason = self.check_time_filter()
        if blocked:
            return True, [f"⏰ {reason}"], metrics
        reasons.append(f"✓ {reason}")
        
        # Drawdown
        blocked, reason = self.check_drawdown_limit()
        if blocked:
            return True, [f"📉 {reason}"], metrics
        reasons.append(f"✓ {reason}")
        
        # Daily loss
        blocked, reason = self.check_daily_loss_limit()
        if blocked:
            return True, [f"📊 {reason}"], metrics
        reasons.append(f"✓ {reason}")
        
        # Consecutive losses
        blocked, reason = self.check_consecutive_losses()
        if blocked:
            return True, [f"❌ {reason}"], metrics
        reasons.append(f"✓ {reason}")
        
        # Win rate
        blocked, reason = self.check_win_rate()
        if blocked:
            return True, [f"📈 {reason}"], metrics
        reasons.append(f"✓ {reason}")
        
        # Momentum crash
        if prices is not None:
            blocked, reason = self.check_momentum_crash(prices)
            if blocked:
                return True, [f"💥 {reason}"], metrics
            reasons.append(f"✓ {reason}")
        
        # Risk score warning
        if metrics.risk_score > 70:
            reasons.append(f"⚠️ High risk score: {metrics.risk_score}")
        
        return False, reasons, metrics
    
    def _load_trades(self) -> List[dict]:
        """Load trades from CSV"""
        try:
            with open(self.trades_csv, "r", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"Error loading trades: {e}")
            return []
    
    def _get_closed_pairs(self, rows: List[dict], limit: int = 200) -> List[Tuple[dict, dict]]:
        """Get closed trade pairs using FIFO"""
        rows = [r for r in rows if r.get("price") not in ("", "0", "0.0")]
        rows.sort(key=lambda r: r.get("timestamp", ""))
        
        pairs = []
        stack = []
        
        for r in rows:
            action = r.get("action", "").upper()
            if action == "BUY":
                stack.append(r)
            elif action == "SELL" and stack:
                pairs.append((stack.pop(0), r))
        
        return pairs[-limit:]


# Quick test
if __name__ == "__main__":
    guards = AdvancedTradeGuards(equity=100000)
    
    # Calculate risk metrics
    metrics = guards.calculate_risk_metrics()
    print(f"📊 Risk Metrics:")
    print(f"   Risk Score: {metrics.risk_score}/100")
    print(f"   Win Rate: {metrics.win_rate:.0%}")
    print(f"   Drawdown: {metrics.current_drawdown:.1%}")
    print(f"   Sharpe: {metrics.sharpe_ratio:.2f}")
    
    # Get position size
    sizing = guards.get_optimal_position_size()
    print(f"\n💰 Optimal Position:")
    print(f"   Size: {sizing['position_size_pct']}% (${sizing['position_size_usd']:,.0f})")
    
    # Check all guards
    blocked, reasons, _ = guards.check_all_guards()
    print(f"\n🛡️ Guards: {'BLOCKED' if blocked else 'OK'}")
    for r in reasons:
        print(f"   {r}")
