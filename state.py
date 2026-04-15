"""
Ethbot State Manager — Thread-safe, centralized runtime state.

Replaces scattered global variables with a single atomic state container.
All modules read/write state through this instead of module-level globals.

Usage:
    from state import state
    
    state.set("training_active", True)
    if state.get("training_active"):
        ...
    
    # Typed shortcuts for common state
    state.training_active = True
    price = state.eth_price
"""

import threading
import time
import logging

logger = logging.getLogger("ethbot.state")


class StateManager:
    """Thread-safe runtime state container with TTL cache support."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict = {}
        self._cache: dict = {}       # {key: (data, timestamp)}
        self._cache_ttl: dict = {}   # {key: ttl_seconds}

    # ─── Generic get/set ───

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            self._data[key] = value

    # ─── Cache (timed) ───

    def cache_get(self, key: str, ttl: int = 30):
        """Return cached value if still fresh, else None."""
        with self._lock:
            if key in self._cache:
                data, ts = self._cache[key]
                if time.time() - ts < ttl:
                    return data
        return None

    def cache_set(self, key: str, data):
        """Store value in cache with current timestamp."""
        with self._lock:
            self._cache[key] = (data, time.time())

    def cache_clear(self, key: str = None):
        """Clear one or all cache entries."""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    # ─── Typed properties for common state ───

    @property
    def training_active(self) -> bool:
        return self.get("training_active", False)

    @training_active.setter
    def training_active(self, value: bool):
        self.set("training_active", value)

    @property
    def training_data(self) -> dict:
        return self.get("training_data", {})

    @training_data.setter
    def training_data(self, value: dict):
        self.set("training_data", value)

    @property
    def ml_stats(self) -> dict:
        return self.get("ml_stats", {})

    @ml_stats.setter
    def ml_stats(self, value: dict):
        self.set("ml_stats", value)

    @property
    def training_process(self):
        return self.get("training_process", None)

    @training_process.setter
    def training_process(self, value):
        self.set("training_process", value)

    @property
    def eth_price(self) -> float:
        return self.get("eth_price", 0.0)

    @eth_price.setter
    def eth_price(self, value: float):
        self.set("eth_price", value)

    @property
    def eth_price_ts(self) -> float:
        return self.get("eth_price_ts", 0.0)

    @eth_price_ts.setter
    def eth_price_ts(self, value: float):
        self.set("eth_price_ts", value)

    def __repr__(self):
        with self._lock:
            keys = list(self._data.keys())
        return f"StateManager(keys={keys})"


# Singleton
state = StateManager()
