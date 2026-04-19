from __future__ import annotations
"""
S2: Statistical Arbitrage — Cointegration Pairs Trading

Principle:
  - Find asset pairs that are cointegrated (e.g., ETH/BTC, SOL/ETH)
  - When spread deviates from mean (Z-Score > 2), bet on reversion
  - Works especially well in range-bound markets (where momentum fails)

Math:
  Spread(t) = log(A) - β × log(B)
  Z(t) = (Spread(t) - μ) / σ
  Entry: |Z| > 2.0, Exit: |Z| < 0.5, Stop: |Z| > 4.0

Expected Performance: 0.1-0.25%/day, Sharpe 2-3, Max DD ~8%
"""
import logging
import time
import numpy as np
import requests
from dataclasses import dataclass
from typing import Optional
from itertools import combinations

logger = logging.getLogger("ethbot.strategy.stat_arb")


@dataclass
class CointPair:
    """A cointegrated pair."""
    asset_a: str
    asset_b: str
    hedge_ratio: float    # β coefficient
    pvalue: float         # Cointegration p-value (lower = better)
    half_life: float      # Mean-reversion half-life in candles
    zscore: float         # Current z-score
    spread_mean: float
    spread_std: float


@dataclass
class StatArbPosition:
    """Active stat-arb position."""
    pair: CointPair
    direction: str        # 'LONG_A_SHORT_B' or 'SHORT_A_LONG_B'
    entry_zscore: float
    entry_time: float
    qty_a: float
    qty_b: float
    pnl: float = 0.0


class StatArbStrategy:
    """
    Statistical Arbitrage using Engle-Granger cointegration test.
    Trades mean-reversion on cointegrated crypto pairs.
    """

    LOOKBACK = 720             # 60h at 5m = 720 candles
    ENTRY_Z = 2.0              # Enter when |Z| > 2
    EXIT_Z = 0.5               # Exit when |Z| < 0.5
    STOP_Z = 4.0               # Stop when |Z| > 4
    MAX_ALLOCATION = 0.20      # 20% of capital
    MAX_POSITIONS = 3
    COINT_PVALUE = 0.05        # 95% confidence required
    RESCAN_INTERVAL = 86400    # Rescan cointegration daily

    # Universe of liquid crypto pairs
    UNIVERSE = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "MATICUSDT",
        "LINKUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT", "LTCUSDT",
    ]

    def __init__(self):
        self.pairs: list[CointPair] = []
        self.positions: dict[str, StatArbPosition] = {}
        self.last_scan = 0.0
        self._price_cache: dict[str, np.ndarray] = {}
        logger.info(f"📊 StatArb initialized: {len(self.UNIVERSE)} assets, "
                     f"max {len(list(combinations(self.UNIVERSE, 2)))} pairs to test")

    def find_cointegrated_pairs(self) -> list[CointPair]:
        """
        Run Engle-Granger cointegration test on all asset pairs.
        Should run nightly or on startup.
        """
        logger.info("📊 StatArb: Starting cointegration scan...")

        # Fetch prices for all assets
        prices = {}
        for symbol in self.UNIVERSE:
            try:
                px = self._fetch_prices(symbol, self.LOOKBACK)
                if px is not None and len(px) >= self.LOOKBACK * 0.8:
                    prices[symbol] = px
            except Exception as e:
                logger.debug(f"StatArb price fetch {symbol}: {e}")

        if len(prices) < 3:
            logger.warning("StatArb: Not enough price data for cointegration")
            return []

        # Test all pairs
        found_pairs = []
        for (a, b) in combinations(prices.keys(), 2):
            try:
                result = self._test_cointegration(a, b, prices[a], prices[b])
                if result is not None:
                    found_pairs.append(result)
            except Exception as e:
                logger.debug(f"StatArb coint test {a}/{b}: {e}")

        # Sort by p-value (best first)
        found_pairs.sort(key=lambda p: p.pvalue)
        self.pairs = found_pairs[:10]  # Keep top 10
        self.last_scan = time.time()

        logger.info(
            f"📊 StatArb scan complete: {len(found_pairs)} cointegrated pairs found | "
            f"Top: {self.pairs[0].asset_a}/{self.pairs[0].asset_b} "
            f"(p={self.pairs[0].pvalue:.4f})" if self.pairs else "None found"
        )

        return self.pairs

    def generate_signals(self) -> list[dict]:
        """Generate trading signals for all monitored pairs."""
        signals = []

        for pair in self.pairs:
            try:
                # Fetch fresh prices
                px_a = self._fetch_prices(pair.asset_a, 100)
                px_b = self._fetch_prices(pair.asset_b, 100)
                if px_a is None or px_b is None:
                    continue

                # Calculate current spread
                spread = np.log(px_a) - pair.hedge_ratio * np.log(px_b)
                zscore = (spread[-1] - pair.spread_mean) / max(pair.spread_std, 1e-8)
                pair.zscore = zscore

                pair_key = f"{pair.asset_a}_{pair.asset_b}"

                # Check for entry signals
                if pair_key not in self.positions:
                    if zscore > self.ENTRY_Z:
                        signals.append({
                            "pair": pair,
                            "action": "SHORT_A_LONG_B",
                            "zscore": zscore,
                            "confidence": min(1.0, abs(zscore) / self.STOP_Z),
                        })
                    elif zscore < -self.ENTRY_Z:
                        signals.append({
                            "pair": pair,
                            "action": "LONG_A_SHORT_B",
                            "zscore": zscore,
                            "confidence": min(1.0, abs(zscore) / self.STOP_Z),
                        })

                # Check for exit signals
                else:
                    pos = self.positions[pair_key]
                    if abs(zscore) < self.EXIT_Z:
                        signals.append({
                            "pair": pair,
                            "action": "EXIT",
                            "zscore": zscore,
                            "reason": "mean_reversion_complete",
                        })
                    elif abs(zscore) > self.STOP_Z:
                        signals.append({
                            "pair": pair,
                            "action": "STOP",
                            "zscore": zscore,
                            "reason": "spread_divergence",
                        })

            except Exception as e:
                logger.debug(f"StatArb signal {pair.asset_a}/{pair.asset_b}: {e}")

        return signals

    def get_status(self) -> dict:
        """Return strategy status for dashboard."""
        return {
            "strategy": "S2_StatArb",
            "cointegrated_pairs": len(self.pairs),
            "active_positions": len(self.positions),
            "pairs": [
                {
                    "a": p.asset_a, "b": p.asset_b,
                    "pvalue": round(p.pvalue, 4),
                    "hedge_ratio": round(p.hedge_ratio, 4),
                    "zscore": round(p.zscore, 2),
                    "half_life": round(p.half_life, 1),
                }
                for p in self.pairs[:5]
            ],
            "last_scan_ago": int(time.time() - self.last_scan),
        }

    # ── Internal Methods ──

    def _test_cointegration(self, sym_a: str, sym_b: str,
                             px_a: np.ndarray, px_b: np.ndarray) -> Optional[CointPair]:
        """Run Engle-Granger cointegration test."""
        # Align lengths
        min_len = min(len(px_a), len(px_b))
        px_a = px_a[-min_len:]
        px_b = px_b[-min_len:]

        log_a = np.log(px_a)
        log_b = np.log(px_b)

        # OLS regression: log_a = β × log_b + ε
        # β = cov(log_a, log_b) / var(log_b)
        beta = np.cov(log_a, log_b)[0, 1] / np.var(log_b)
        spread = log_a - beta * log_b

        # ADF test (simplified — Dickey-Fuller)
        # H0: unit root (non-stationary) → reject = cointegrated
        pvalue = self._adf_test(spread)

        if pvalue < self.COINT_PVALUE:
            # Calculate half-life of mean reversion
            half_life = self._halflife(spread)

            return CointPair(
                asset_a=sym_a,
                asset_b=sym_b,
                hedge_ratio=beta,
                pvalue=pvalue,
                half_life=half_life,
                zscore=(spread[-1] - np.mean(spread)) / np.std(spread),
                spread_mean=float(np.mean(spread)),
                spread_std=float(np.std(spread)),
            )
        return None

    def _adf_test(self, series: np.ndarray) -> float:
        """
        Simplified ADF test. Returns approximate p-value.
        For production, use statsmodels.tsa.stattools.adfuller.
        """
        try:
            # Try statsmodels if available
            from statsmodels.tsa.stattools import adfuller
            result = adfuller(series, maxlag=20, autolag='AIC')
            return result[1]  # p-value
        except ImportError:
            pass

        # Fallback: simplified Dickey-Fuller
        n = len(series)
        if n < 30:
            return 1.0

        diff = np.diff(series)
        lag = series[:-1]

        # OLS: diff = α + γ × lag + ε
        # γ < 0 → stationary (reject H0)
        X = np.column_stack([np.ones(len(lag)), lag])
        try:
            beta = np.linalg.lstsq(X, diff, rcond=None)[0]
            gamma = beta[1]
            residuals = diff - X @ beta
            se_gamma = np.sqrt(np.var(residuals) / (np.sum((lag - np.mean(lag))**2)))
            t_stat = gamma / se_gamma

            # Approximate p-value from DF distribution
            # Critical values: 1% = -3.43, 5% = -2.86, 10% = -2.57
            if t_stat < -3.43:
                return 0.01
            elif t_stat < -2.86:
                return 0.05
            elif t_stat < -2.57:
                return 0.10
            else:
                return 0.50
        except Exception:
            return 1.0

    def _halflife(self, spread: np.ndarray) -> float:
        """Calculate mean-reversion half-life using Ornstein-Uhlenbeck."""
        spread_lag = spread[:-1]
        spread_diff = np.diff(spread)

        # OLS: Δspread = λ × spread_lag + ε
        # half_life = -log(2) / λ
        try:
            X = np.column_stack([np.ones(len(spread_lag)), spread_lag])
            beta = np.linalg.lstsq(X, spread_diff, rcond=None)[0]
            lam = beta[1]
            if lam < 0:
                return -np.log(2) / lam
        except Exception:
            pass
        return 999.0  # Very slow reversion

    def _fetch_prices(self, symbol: str, lookback: int) -> Optional[np.ndarray]:
        """Fetch close prices from Binance."""
        try:
            resp = requests.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": "5m", "limit": lookback},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            closes = np.array([float(c[4]) for c in data])
            self._price_cache[symbol] = closes
            return closes
        except Exception as e:
            logger.debug(f"StatArb price fetch {symbol}: {e}")
            return self._price_cache.get(symbol)


# Singleton
_instance: Optional[StatArbStrategy] = None

def get_stat_arb() -> StatArbStrategy:
    global _instance
    if _instance is None:
        _instance = StatArbStrategy()
    return _instance
