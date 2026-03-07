"""
ML Backtester - Simulates ML trading signals on historical data with realistic slippage.
"""
import os
import json
import random
import numpy as np
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Slippage/fee constants (same as order_executor)
SPREAD_PCT = 0.0005       # 0.05% bid-ask spread
FEE_PCT = 0.001           # 0.1% Binance taker fee
MAX_SLIPPAGE_PCT = 0.0005 # 0-0.05% random slippage
TOTAL_COST_PER_TRADE = SPREAD_PCT + FEE_PCT + MAX_SLIPPAGE_PCT / 2  # ~0.175% avg per side


@dataclass
class BacktestTrade:
    """Represents a single backtest trade"""
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    signal: str
    pnl_pct: float
    model: str
    confidence: float


@dataclass
class BacktestResult:
    """Complete backtest results"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    avg_trade_duration: float
    model: str
    start_date: str
    end_date: str
    trades: List[Dict]


class MLBacktester:
    """
    Backtests ML trading signals on historical price data.
    Includes realistic slippage and fee simulation.
    Calculates Sharpe ratio, win rate, drawdown, and other metrics.
    """
    
    def __init__(self, initial_capital: float = 10000.0, risk_per_trade: float = 0.02):
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        self.results_path = log_dir / "backtest_results.json"
        
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[float] = [initial_capital]
    
    @staticmethod
    def _apply_slippage(price: float, side: str) -> float:
        """Apply realistic slippage + fees to a trade price."""
        slip = random.uniform(0, MAX_SLIPPAGE_PCT)
        total = SPREAD_PCT + FEE_PCT + slip
        if side == "BUY":
            return price * (1 + total)  # Pay more
        else:
            return price * (1 - total)  # Receive less
    
    def load_price_data(self, days: int = 60) -> np.ndarray:
        """
        Load historical price data. Tries real Binance klines first,
        then local files, then synthetic as last resort.
        """
        # 1. Try fetching real Binance klines
        try:
            logger.info(f"Fetching {days} days of Binance ETHUSDT klines...")
            url = "https://api.binance.com/api/v3/klines"
            end_ms = int(datetime.now().timestamp() * 1000)
            start_ms = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            
            all_prices = []
            current_start = start_ms
            
            while current_start < end_ms:
                params = {
                    "symbol": "ETHUSDT",
                    "interval": "5m",
                    "startTime": current_start,
                    "limit": 1000
                }
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                
                if not data:
                    break
                
                all_prices.extend([float(candle[4]) for candle in data])  # Close price
                current_start = int(data[-1][6]) + 1  # Next after last close_time
                
                if len(data) < 1000:
                    break
            
            if len(all_prices) > 100:
                logger.info(f"Loaded {len(all_prices)} real price points from Binance")
                return np.array(all_prices)
        except Exception as e:
            logger.warning(f"Binance klines fetch failed: {e}")
        
        # 2. Try local files
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        for pf in [log_dir / "price_history.json", log_dir / "trades.json"]:
            if pf.exists():
                try:
                    with open(pf) as f:
                        data = json.load(f)
                        if isinstance(data, list) and len(data) > 100:
                            if "price" in data[0]:
                                return np.array([d["price"] for d in data])
                except Exception:
                    pass
        
        # 3. Synthetic fallback
        logger.warning("No historical data found, using synthetic prices")
        np.random.seed(42)
        num_points = days * 24 * 12
        prices = [3200.0]
        for _ in range(num_points - 1):
            change = np.random.normal(0, 0.002)
            trend = np.sin(len(prices) / 500) * 0.0005
            prices.append(prices[-1] * (1 + change + trend))
        return np.array(prices)
    
    def get_ml_signal(self, prices: np.ndarray, model: str = "ensemble") -> Dict[str, Any]:
        """
        Get ML signal for given price window
        
        Args:
            prices: Recent price array
            model: Model to use (dqn, gradient_boosting, lstm, ensemble)
            
        Returns:
            Signal dict with action and confidence
        """
        try:
            if model == "dqn":
                from src.ml.dqn_ensemble_adapter import DQNEnsembleAdapter
                adapter = DQNEnsembleAdapter()
                return adapter.get_signal(prices)
            
            elif model == "ensemble":
                from src.ml.dqn_ensemble_adapter import UnifiedEnsemble
                ensemble = UnifiedEnsemble()
                return ensemble.predict(prices)
            
            else:
                # Simple momentum signal as fallback
                if len(prices) < 20:
                    return {"signal": "HOLD", "confidence": 0.5}
                
                returns = np.diff(prices[-20:]) / prices[-21:-1]
                momentum = np.mean(returns)
                
                if momentum > 0.001:
                    return {"signal": "BUY", "confidence": min(abs(momentum) * 100, 1.0)}
                elif momentum < -0.001:
                    return {"signal": "SELL", "confidence": min(abs(momentum) * 100, 1.0)}
                else:
                    return {"signal": "HOLD", "confidence": 0.5}
                    
        except Exception as e:
            logger.debug(f"ML signal error: {e}")
            return {"signal": "HOLD", "confidence": 0.5}
    
    def run_backtest(
        self, 
        prices: np.ndarray, 
        model: str = "ensemble",
        hold_periods: int = 12,
        min_confidence: float = 0.6
    ) -> BacktestResult:
        """
        Run backtest simulation
        
        Args:
            prices: Historical price array
            model: ML model to test
            hold_periods: Periods to hold each trade
            min_confidence: Minimum confidence to enter trade
            
        Returns:
            BacktestResult with metrics
        """
        logger.info(f"Running {model} backtest on {len(prices)} price points...")
        
        self.trades = []
        self.equity_curve = [self.initial_capital]
        
        position = None
        capital = self.initial_capital
        window_size = 30
        
        for i in range(window_size, len(prices) - hold_periods, hold_periods):
            price_window = prices[i - window_size:i]
            current_price = prices[i]
            
            # Get ML signal
            signal = self.get_ml_signal(price_window, model)
            action = signal.get("signal", "HOLD")
            confidence = signal.get("confidence", 0.5)
            
            # Skip if in position or low confidence
            if position is not None or confidence < min_confidence:
                if position is not None:
                    # Check exit after hold period
                    exit_idx = min(i + hold_periods, len(prices) - 1)
                    exit_price = prices[exit_idx]
                    
                    # Apply slippage to entry and exit
                    entry_with_slip = self._apply_slippage(position["entry"], position["signal"])
                    exit_side = "SELL" if position["signal"] == "BUY" else "BUY"
                    exit_with_slip = self._apply_slippage(exit_price, exit_side)
                    
                    # Calculate PnL with realistic costs
                    if position["signal"] == "BUY":
                        pnl_pct = (exit_with_slip - entry_with_slip) / entry_with_slip
                    else:
                        pnl_pct = (entry_with_slip - exit_with_slip) / entry_with_slip
                    
                    # Update capital
                    position_size = capital * self.risk_per_trade
                    profit = position_size * pnl_pct
                    capital += profit
                    
                    # Record trade
                    trade = BacktestTrade(
                        entry_time=f"bar_{position['bar']}",
                        exit_time=f"bar_{exit_idx}",
                        entry_price=position["entry"],
                        exit_price=exit_price,
                        signal=position["signal"],
                        pnl_pct=pnl_pct * 100,
                        model=model,
                        confidence=position["confidence"]
                    )
                    self.trades.append(trade)
                    
                    position = None
                
                self.equity_curve.append(capital)
                continue
            
            # Enter position
            if action in ["BUY", "SELL"]:
                position = {
                    "entry": current_price,
                    "signal": action,
                    "bar": i,
                    "confidence": confidence
                }
            
            self.equity_curve.append(capital)
        
        # Calculate metrics
        return self._calculate_metrics(model, prices)
    
    def _calculate_metrics(self, model: str, prices: np.ndarray) -> BacktestResult:
        """Calculate backtest performance metrics"""
        if not self.trades:
            return BacktestResult(
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0.0, total_return=0.0, avg_return=0.0,
                sharpe_ratio=0.0, max_drawdown=0.0, profit_factor=0.0,
                avg_trade_duration=0.0, model=model,
                start_date="", end_date="", trades=[]
            )
        
        pnls = [t.pnl_pct for t in self.trades]
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p < 0]
        
        # Win rate
        win_rate = len(winning) / len(self.trades) if self.trades else 0.0
        
        # Total return
        final_capital = self.equity_curve[-1]
        total_return = (final_capital - self.initial_capital) / self.initial_capital * 100
        
        # Average return
        avg_return = np.mean(pnls) if pnls else 0.0
        
        # Sharpe ratio (annualized)
        if len(pnls) > 1:
            daily_returns = np.array(pnls) / 100
            sharpe = np.mean(daily_returns) / np.std(daily_returns) if np.std(daily_returns) > 0 else 0
            sharpe_ratio = sharpe * np.sqrt(252)  # Annualize
        else:
            sharpe_ratio = 0.0
        
        # Max drawdown
        peak = self.equity_curve[0]
        max_dd = 0.0
        for val in self.equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak
            max_dd = max(max_dd, dd)
        
        # Profit factor
        gross_profit = sum(winning) if winning else 0.0
        gross_loss = abs(sum(losing)) if losing else 1.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        
        result = BacktestResult(
            total_trades=len(self.trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=round(win_rate * 100, 2),
            total_return=round(total_return, 2),
            avg_return=round(avg_return, 4),
            sharpe_ratio=round(sharpe_ratio, 2),
            max_drawdown=round(max_dd * 100, 2),
            profit_factor=round(profit_factor, 2),
            avg_trade_duration=12.0,  # Fixed hold period
            model=model,
            start_date="bar_0",
            end_date=f"bar_{len(prices)}",
            trades=[asdict(t) for t in self.trades[:50]]  # First 50 trades
        )
        
        # Save results
        self._save_results(result)
        
        return result
    
    def _save_results(self, result: BacktestResult):
        """Save backtest results to disk"""
        try:
            # Load existing
            existing = []
            if self.results_path.exists():
                with open(self.results_path) as f:
                    existing = json.load(f)
            
            # Add new result
            result_dict = asdict(result)
            result_dict["timestamp"] = datetime.now().isoformat()
            existing.append(result_dict)
            
            # Keep last 20
            existing = existing[-20:]
            
            with open(self.results_path, "w") as f:
                json.dump(existing, f, indent=2)
            
            logger.info(f"Saved backtest results to {self.results_path}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
    
    def run_all_models(self, days: int = 60) -> Dict[str, BacktestResult]:
        """Run backtest for all available models"""
        prices = self.load_price_data(days)
        
        results = {}
        for model in ["dqn", "ensemble"]:
            try:
                result = self.run_backtest(prices, model=model)
                results[model] = result
                logger.info(f"{model}: {result.total_trades} trades, {result.win_rate}% win rate, {result.total_return}% return")
            except Exception as e:
                logger.error(f"Backtest failed for {model}: {e}")
        
        return results
    
    def get_latest_results(self) -> List[Dict]:
        """Get most recent backtest results"""
        if self.results_path.exists():
            with open(self.results_path) as f:
                return json.load(f)
        return []


if __name__ == "__main__":
    print("🔬 Running ML Backtester...")
    
    backtester = MLBacktester(initial_capital=10000)
    
    # Load data
    prices = backtester.load_price_data(days=30)
    print(f"Loaded {len(prices)} price points")
    
    # Run backtest
    result = backtester.run_backtest(prices, model="ensemble")
    
    print(f"\n📊 Backtest Results:")
    print(f"   Model: {result.model}")
    print(f"   Trades: {result.total_trades}")
    print(f"   Win Rate: {result.win_rate}%")
    print(f"   Total Return: {result.total_return}%")
    print(f"   Sharpe Ratio: {result.sharpe_ratio}")
    print(f"   Max Drawdown: {result.max_drawdown}%")
    print(f"   Profit Factor: {result.profit_factor}")
