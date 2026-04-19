from __future__ import annotations
"""
Walk-Forward Backtester — Honest strategy validation.

FIXES from old backtester (src/ml/ml_backtester.py):
  1. NO synthetic data fallback — real data or fail
  2. Walk-forward: Train on window N, test on N+1, roll
  3. Deterministic fees (not random.uniform)
  4. Market impact model (size-dependent slippage)
  5. Regime segmentation (Bull/Bear/Range/Volatile separate)
  6. Out-of-sample performance tracking

Usage:
  from bot.backtester import run_walk_forward
  results = run_walk_forward(strategy_fn, pairs=["ETHUSDT"], months=6)
"""
import logging
import time
import numpy as np
import pandas as pd
import requests
from dataclasses import dataclass, field
from typing import Callable, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("ethbot.backtester")


@dataclass
class TradeResult:
    """A single backtest trade."""
    pair: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    side: str           # 'LONG' or 'SHORT'
    qty: float
    pnl_pct: float
    pnl_usd: float
    fees_usd: float
    slippage_usd: float
    bars_held: int
    regime: str


@dataclass
class WalkForwardResult:
    """Results from one walk-forward window."""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    trades: list[TradeResult] = field(default_factory=list)
    sharpe: float = 0.0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    max_dd: float = 0.0
    regime_breakdown: dict = field(default_factory=dict)


@dataclass
class BacktestSummary:
    """Full backtest summary."""
    windows: list[WalkForwardResult] = field(default_factory=list)
    total_trades: int = 0
    overall_sharpe: float = 0.0
    overall_win_rate: float = 0.0
    overall_pnl_pct: float = 0.0
    max_drawdown: float = 0.0
    out_of_sample_ratio: float = 0.0  # OOS Sharpe / IS Sharpe
    regime_stats: dict = field(default_factory=dict)
    passed_quality_gates: list[str] = field(default_factory=list)
    failed_quality_gates: list[str] = field(default_factory=list)


# ── Fee Model ──

def calculate_fees(notional: float, is_maker: bool = False) -> float:
    """
    Deterministic fee model based on Binance VIP0.
    NOT random — this is a known, fixed cost.
    """
    rate = 0.0002 if is_maker else 0.0004  # 0.02% maker / 0.04% taker
    return notional * rate


def calculate_slippage(notional: float, daily_volume: float) -> float:
    """
    Market impact model: slippage proportional to order size.
    Based on Kyle's Lambda model (simplified).
    """
    if daily_volume <= 0:
        return notional * 0.001  # Default 0.1%

    # Impact = sqrt(notional / daily_volume) * constant
    impact_pct = 0.1 * (notional / daily_volume) ** 0.5
    # Cap at 0.5%
    impact_pct = min(impact_pct, 0.005)
    return notional * impact_pct


# ── Data Fetching ──

def fetch_historical_klines(pair: str, interval: str = "5m",
                             start_date: str = None, end_date: str = None,
                             limit: int = 1000) -> Optional[pd.DataFrame]:
    """
    Fetch historical klines from Binance.
    NO synthetic fallback — real data or None.
    """
    try:
        params = {"symbol": pair, "interval": interval, "limit": limit}
        if start_date:
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            params["startTime"] = int(dt.timestamp() * 1000)
        if end_date:
            dt = datetime.strptime(end_date, "%Y-%m-%d")
            params["endTime"] = int(dt.timestamp() * 1000)

        all_data = []
        while True:
            resp = requests.get(
                "https://api.binance.com/api/v3/klines",
                params=params, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            all_data.extend(data)

            if len(data) < limit:
                break

            # Paginate
            params["startTime"] = int(data[-1][0]) + 1
            time.sleep(0.5)  # Rate limit

        if not all_data:
            logger.warning(f"No data for {pair} {start_date}→{end_date}")
            return None

        df = pd.DataFrame(all_data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qv", "trades", "taker_base", "taker_quote", "ignore"
        ])

        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)

        df["time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df[["time", "open", "high", "low", "close", "volume"]]
        df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

        logger.info(f"Fetched {len(df)} candles for {pair} ({df['time'].iloc[0]} → {df['time'].iloc[-1]})")
        return df

    except Exception as e:
        logger.error(f"Historical data fetch failed: {e}")
        return None


# ── Regime Detection ──

def detect_regime(df: pd.DataFrame, lookback: int = 100) -> str:
    """
    Classify market regime for a window of data.
    Returns: 'bull', 'bear', 'range', 'volatile'
    """
    if len(df) < lookback:
        return "unknown"

    close = df["close"].values[-lookback:]
    returns = np.diff(close) / close[:-1]

    # Trend: cumulative return
    total_return = (close[-1] / close[0]) - 1
    # Volatility: annualized std
    vol = np.std(returns) * np.sqrt(288 * 365)  # 5-min candles
    # Range: high-low range / avg price
    high = np.max(close)
    low = np.min(close)
    range_pct = (high - low) / np.mean(close)

    if vol > 0.8:
        return "volatile"
    elif total_return > 0.05:
        return "bull"
    elif total_return < -0.05:
        return "bear"
    else:
        return "range"


# ── Walk-Forward Engine ──

def run_walk_forward(
    strategy_fn: Callable,
    pairs: list[str] = None,
    months: int = 6,
    train_months: int = 2,
    test_months: int = 1,
    initial_capital: float = 100_000.0,
    max_position_pct: float = 0.10,
) -> BacktestSummary:
    """
    Run walk-forward backtest.

    Args:
        strategy_fn: Function(df, pair) → list of signals
                     Each signal: {side, entry_idx, stop, target}
        pairs: Symbols to test
        months: Total months of data
        train_months: Training window size
        test_months: Testing window size
        initial_capital: Starting capital
        max_position_pct: Max position as % of capital

    Returns:
        BacktestSummary with quality gate checks
    """
    if pairs is None:
        pairs = ["ETHUSDT", "BTCUSDT", "SOLUSDT"]

    summary = BacktestSummary()
    all_returns = []

    # Calculate date windows
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=months * 30)

    # Generate walk-forward windows
    window_size = timedelta(days=(train_months + test_months) * 30)
    step_size = timedelta(days=test_months * 30)
    train_size = timedelta(days=train_months * 30)

    window_start = start_date
    window_id = 0

    while window_start + window_size <= end_date:
        train_end = window_start + train_size
        test_end = train_end + timedelta(days=test_months * 30)

        wf_result = WalkForwardResult(
            window_id=window_id,
            train_start=window_start.strftime("%Y-%m-%d"),
            train_end=train_end.strftime("%Y-%m-%d"),
            test_start=train_end.strftime("%Y-%m-%d"),
            test_end=test_end.strftime("%Y-%m-%d"),
        )

        logger.info(
            f"📊 Walk-Forward Window #{window_id}: "
            f"Train {wf_result.train_start}→{wf_result.train_end} | "
            f"Test {wf_result.test_start}→{wf_result.test_end}"
        )

        for pair in pairs:
            # Fetch test data only (we don't actually retrain — strategy is rule-based)
            test_df = fetch_historical_klines(
                pair, "5m",
                start_date=wf_result.test_start,
                end_date=wf_result.test_end,
            )

            if test_df is None or len(test_df) < 100:
                continue

            regime = detect_regime(test_df)
            daily_volume = float(test_df["volume"].mean()) * 288  # 5-min → daily

            # Run strategy on test data
            try:
                signals = strategy_fn(test_df, pair)
            except Exception as e:
                logger.warning(f"Strategy error on {pair}: {e}")
                continue

            # Execute signals with realistic costs
            capital = initial_capital
            for sig in signals:
                entry_idx = sig.get("entry_idx", 0)
                if entry_idx >= len(test_df) - 1:
                    continue

                entry_price = float(test_df.iloc[entry_idx]["close"])
                position_size = capital * max_position_pct
                qty = position_size / entry_price

                # Calculate costs
                fees = calculate_fees(position_size) * 2  # Entry + exit
                slippage = calculate_slippage(position_size, daily_volume) * 2

                # Simulate trade with Triple-Barrier
                stop = sig.get("stop", entry_price * 0.98)
                target = sig.get("target", entry_price * 1.02)
                max_bars = sig.get("max_bars", 60)
                side = sig.get("side", "LONG")

                exit_price, bars_held = _simulate_trade(
                    test_df, entry_idx, entry_price,
                    stop, target, max_bars, side
                )

                # PnL calculation
                if side == "LONG":
                    raw_pnl_pct = (exit_price / entry_price - 1) * 100
                else:
                    raw_pnl_pct = (1 - exit_price / entry_price) * 100

                cost_pct = (fees + slippage) / position_size * 100
                net_pnl_pct = raw_pnl_pct - cost_pct
                net_pnl_usd = position_size * net_pnl_pct / 100

                trade = TradeResult(
                    pair=pair,
                    entry_time=str(test_df.iloc[entry_idx]["time"]),
                    exit_time=str(test_df.iloc[min(entry_idx + bars_held, len(test_df)-1)]["time"]),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    side=side,
                    qty=qty,
                    pnl_pct=net_pnl_pct,
                    pnl_usd=net_pnl_usd,
                    fees_usd=fees,
                    slippage_usd=slippage,
                    bars_held=bars_held,
                    regime=regime,
                )
                wf_result.trades.append(trade)
                all_returns.append(net_pnl_pct)

        # Window stats
        if wf_result.trades:
            pnls = [t.pnl_pct for t in wf_result.trades]
            wf_result.win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
            wf_result.avg_pnl = np.mean(pnls)
            wf_result.sharpe = _sharpe(np.array(pnls))
            wf_result.max_dd = _max_drawdown(pnls)

            # Regime breakdown
            for regime in ["bull", "bear", "range", "volatile"]:
                regime_trades = [t for t in wf_result.trades if t.regime == regime]
                if regime_trades:
                    regime_pnls = [t.pnl_pct for t in regime_trades]
                    wf_result.regime_breakdown[regime] = {
                        "trades": len(regime_trades),
                        "win_rate": sum(1 for p in regime_pnls if p > 0) / len(regime_pnls),
                        "avg_pnl": float(np.mean(regime_pnls)),
                        "sharpe": _sharpe(np.array(regime_pnls)),
                    }

        summary.windows.append(wf_result)
        window_start += step_size
        window_id += 1

    # ── Overall Summary ──
    all_trades = [t for w in summary.windows for t in w.trades]
    summary.total_trades = len(all_trades)

    if all_returns:
        returns = np.array(all_returns)
        summary.overall_sharpe = _sharpe(returns)
        summary.overall_win_rate = sum(1 for r in returns if r > 0) / len(returns)
        summary.overall_pnl_pct = float(np.sum(returns))
        summary.max_drawdown = _max_drawdown(all_returns)

        # Regime stats
        for regime in ["bull", "bear", "range", "volatile"]:
            regime_trades = [t for t in all_trades if t.regime == regime]
            if regime_trades:
                regime_pnls = [t.pnl_pct for t in regime_trades]
                summary.regime_stats[regime] = {
                    "trades": len(regime_trades),
                    "win_rate": sum(1 for p in regime_pnls if p > 0) / len(regime_pnls),
                    "total_pnl": float(np.sum(regime_pnls)),
                    "sharpe": _sharpe(np.array(regime_pnls)),
                }

    # ── Quality Gate Checks ──
    _check_quality_gates(summary)

    return summary


def _simulate_trade(df: pd.DataFrame, entry_idx: int, entry_price: float,
                    stop: float, target: float, max_bars: int,
                    side: str) -> tuple[float, int]:
    """
    Simulate a trade using Triple-Barrier on historical data.
    Returns (exit_price, bars_held).
    """
    for bar in range(1, max_bars + 1):
        idx = entry_idx + bar
        if idx >= len(df):
            break

        high = float(df.iloc[idx]["high"])
        low = float(df.iloc[idx]["low"])

        if side == "LONG":
            # SL check first (conservative)
            if low <= stop:
                return stop, bar
            if high >= target:
                return target, bar
        else:  # SHORT
            if high >= stop:
                return stop, bar
            if low <= target:
                return target, bar

    # Timeout — exit at close
    exit_idx = min(entry_idx + max_bars, len(df) - 1)
    return float(df.iloc[exit_idx]["close"]), max_bars


def _sharpe(returns: np.ndarray, risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio."""
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free
    std = np.std(excess)
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(365))


def _max_drawdown(returns: list[float]) -> float:
    """Calculate maximum drawdown from returns series."""
    if not returns:
        return 0.0
    cumulative = np.cumsum(returns)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    return float(np.max(drawdown)) if len(drawdown) > 0 else 0.0


def _check_quality_gates(summary: BacktestSummary):
    """Run quality gate checks on backtest results."""
    gates = [
        ("Sharpe >= 1.0", summary.overall_sharpe >= 1.0),
        ("Win Rate >= 45%", summary.overall_win_rate >= 0.45),
        ("Max DD <= 20%", summary.max_drawdown <= 20.0),
        ("Total trades >= 50", summary.total_trades >= 50),
        ("Profitable in >= 3 regimes", sum(
            1 for r in summary.regime_stats.values()
            if r.get("total_pnl", 0) > 0
        ) >= 3),
        ("Consistent across windows", all(
            w.sharpe > 0 for w in summary.windows if w.trades
        )),
    ]

    for name, passed in gates:
        if passed:
            summary.passed_quality_gates.append(f"✅ {name}")
        else:
            summary.failed_quality_gates.append(f"❌ {name}")

    total = len(gates)
    passed = len(summary.passed_quality_gates)
    logger.info(
        f"📊 Quality Gates: {passed}/{total} passed | "
        f"Sharpe: {summary.overall_sharpe:.2f} | "
        f"WR: {summary.overall_win_rate:.1%} | "
        f"DD: {summary.max_drawdown:.1f}% | "
        f"Trades: {summary.total_trades}"
    )
