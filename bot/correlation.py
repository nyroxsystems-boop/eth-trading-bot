"""
Correlation Guard — Prevents taking multiple correlated positions.

Problem: BTC long + ETH long + SOL long = basically the same trade 3x.
If BTC dumps, ALL positions lose simultaneously → max drawdown.

Solution: Rolling correlation matrix between all pairs.
If correlation > 0.75 → block the 3rd correlated position.

This is what DE Shaw and Citadel do — portfolio-level risk management.
"""
import logging
import numpy as np
from typing import Optional
from collections import defaultdict

logger = logging.getLogger("ethbot.correlation")


class CorrelationGuard:
    """
    Prevents excessive exposure to correlated assets.
    
    Maintains a rolling window of returns for each pair
    and computes a correlation matrix to detect highly
    correlated positions.
    """

    MAX_CORRELATED_POSITIONS = 2   # Max positions with correlation > threshold
    CORRELATION_THRESHOLD = 0.75   # Above this = "same trade"
    WINDOW_SIZE = 50               # Rolling window (50 bars = ~4h at 5m)

    def __init__(self):
        self._returns: dict[str, list[float]] = defaultdict(list)
        self._open_positions: dict[str, str] = {}  # pair → direction
        logger.info(
            f"🔗 Correlation Guard: max {self.MAX_CORRELATED_POSITIONS} correlated, "
            f"threshold {self.CORRELATION_THRESHOLD}"
        )

    def update_price(self, pair: str, price: float):
        """Update price data for correlation calculation."""
        history = self._returns[pair]
        if history:
            prev = history[-1]
            if prev > 0:
                ret = (price - prev) / prev
                history.append(price)
            else:
                history.append(price)
                return
        else:
            history.append(price)
            return

        # Trim to window
        if len(history) > self.WINDOW_SIZE + 10:
            self._returns[pair] = history[-self.WINDOW_SIZE:]

    def register_position(self, pair: str, direction: str = "LONG"):
        """Register an open position."""
        self._open_positions[pair] = direction

    def close_position(self, pair: str):
        """Remove a closed position."""
        self._open_positions.pop(pair, None)

    def can_open_position(self, new_pair: str, direction: str = "LONG") -> tuple[bool, str]:
        """
        Check if opening a new position would create excessive correlation.
        
        Returns:
            (allowed, reason)
        """
        if not self._open_positions:
            return True, "No open positions"

        if new_pair in self._open_positions:
            return False, f"{new_pair} already has an open position"

        # Count how many existing positions are highly correlated with new_pair
        correlated_count = 0
        correlated_pairs = []

        for open_pair, open_dir in self._open_positions.items():
            # Same direction + high correlation = correlated trade
            if open_dir == direction:
                corr = self._get_correlation(new_pair, open_pair)
                if corr is not None and corr > self.CORRELATION_THRESHOLD:
                    correlated_count += 1
                    correlated_pairs.append(f"{open_pair}({corr:.0%})")

        if correlated_count >= self.MAX_CORRELATED_POSITIONS:
            return False, (
                f"Correlated with {correlated_count} open positions: "
                f"{', '.join(correlated_pairs)}"
            )

        return True, "OK"

    def _get_correlation(self, pair_a: str, pair_b: str) -> Optional[float]:
        """Compute Pearson correlation between two pairs."""
        prices_a = self._returns.get(pair_a, [])
        prices_b = self._returns.get(pair_b, [])

        # Need at least 20 data points
        min_len = min(len(prices_a), len(prices_b))
        if min_len < 20:
            return 0.5  # Default: assume moderate correlation

        # Align and compute returns
        a = np.array(prices_a[-min_len:])
        b = np.array(prices_b[-min_len:])

        # Convert prices to returns
        ret_a = np.diff(a) / a[:-1]
        ret_b = np.diff(b) / b[:-1]

        if len(ret_a) < 10:
            return 0.5

        # Pearson correlation
        try:
            corr = np.corrcoef(ret_a, ret_b)[0, 1]
            if np.isnan(corr):
                return 0.5
            return float(corr)
        except Exception:
            return 0.5

    def get_matrix(self) -> dict:
        """Get the full correlation matrix for API/Dashboard."""
        pairs = list(self._returns.keys())
        matrix = {}

        for i, p1 in enumerate(pairs):
            for p2 in pairs[i+1:]:
                corr = self._get_correlation(p1, p2)
                if corr is not None:
                    key = f"{p1}|{p2}"
                    matrix[key] = round(corr, 3)

        return {
            "pairs_tracked": len(pairs),
            "open_positions": dict(self._open_positions),
            "max_correlated": self.MAX_CORRELATED_POSITIONS,
            "threshold": self.CORRELATION_THRESHOLD,
            "correlations": matrix,
        }


# Singleton
_instance: Optional[CorrelationGuard] = None

def get_correlation_guard() -> CorrelationGuard:
    global _instance
    if _instance is None:
        _instance = CorrelationGuard()
    return _instance
