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
    
    # Jarvis BotState (external LLM control)
    state.jarvis_ml_threshold = 0.50
    state.jarvis_emergency_stop = True
"""

import threading
import time
import logging
from typing import List

logger = logging.getLogger("ethbot.state")


# ═══════════════════════════════════════════════════════════════
# Default Jarvis BotState values
# These are the "factory defaults" — Jarvis overrides live on top.
# ═══════════════════════════════════════════════════════════════
JARVIS_DEFAULTS = {
    "ml_confidence_threshold": 0.42,
    "active_edges": ["BREAKOUT", "DRAWDOWN", "OS-FAST", "NORMAL", "BB_BOUNCE", "MACD_CROSS", "RANGE_SUP"],
    "emergency_stop": False,
    "risk_multiplier": 1.0,
}


class StateManager:
    """Thread-safe runtime state container with TTL cache support."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict = {}
        self._cache: dict = {}       # {key: (data, timestamp)}
        self._cache_ttl: dict = {}   # {key: ttl_seconds}
        
        # Initialize Jarvis defaults
        for key, val in JARVIS_DEFAULTS.items():
            self._data[f"jarvis_{key}"] = val
        self._data["jarvis_override_active"] = False
        self._data["jarvis_last_update"] = 0.0

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

    # ═══════════════════════════════════════════════════════════
    # Jarvis BotState Properties
    # ═══════════════════════════════════════════════════════════

    @property
    def jarvis_override_active(self) -> bool:
        """True if Jarvis has sent at least one override AND it hasn't expired."""
        return self.get("jarvis_override_active", False)
    
    @jarvis_override_active.setter
    def jarvis_override_active(self, value: bool):
        self.set("jarvis_override_active", value)

    @property
    def jarvis_ml_threshold(self) -> float:
        """ML confidence threshold set by Jarvis (default: 0.42)."""
        return self.get("jarvis_ml_confidence_threshold", JARVIS_DEFAULTS["ml_confidence_threshold"])
    
    @jarvis_ml_threshold.setter
    def jarvis_ml_threshold(self, value: float):
        self.set("jarvis_ml_confidence_threshold", value)

    @property
    def jarvis_active_edges(self) -> List[str]:
        """List of active strategy edges set by Jarvis."""
        return self.get("jarvis_active_edges", JARVIS_DEFAULTS["active_edges"])
    
    @jarvis_active_edges.setter
    def jarvis_active_edges(self, value: List[str]):
        self.set("jarvis_active_edges", value)

    @property
    def jarvis_emergency_stop(self) -> bool:
        """Emergency stop flag set by Jarvis."""
        return self.get("jarvis_emergency_stop", False)
    
    @jarvis_emergency_stop.setter
    def jarvis_emergency_stop(self, value: bool):
        self.set("jarvis_emergency_stop", value)

    @property
    def jarvis_risk_multiplier(self) -> float:
        """Risk multiplier for Kelly sizing (default: 1.0)."""
        return self.get("jarvis_risk_multiplier", JARVIS_DEFAULTS["risk_multiplier"])
    
    @jarvis_risk_multiplier.setter
    def jarvis_risk_multiplier(self, value: float):
        self.set("jarvis_risk_multiplier", value)

    @property
    def jarvis_last_update(self) -> float:
        """Timestamp of last Jarvis webhook update."""
        return self.get("jarvis_last_update", 0.0)
    
    @jarvis_last_update.setter
    def jarvis_last_update(self, value: float):
        self.set("jarvis_last_update", value)

    def apply_jarvis_update(self, payload: dict) -> dict:
        """
        Apply a Jarvis webhook payload to the state.
        Only updates fields present in the payload.
        Returns a dict of what was changed.
        """
        changes = {}
        
        if "ml_confidence_threshold" in payload:
            val = max(0.30, min(0.90, float(payload["ml_confidence_threshold"])))
            self.jarvis_ml_threshold = val
            changes["ml_confidence_threshold"] = val
        
        if "active_edges" in payload:
            edges = [str(e).upper() for e in payload["active_edges"]]
            self.jarvis_active_edges = edges
            changes["active_edges"] = edges
        
        if "emergency_stop" in payload:
            val = bool(payload["emergency_stop"])
            self.jarvis_emergency_stop = val
            changes["emergency_stop"] = val
        
        if "risk_multiplier" in payload:
            val = max(0.1, min(5.0, float(payload["risk_multiplier"])))
            self.jarvis_risk_multiplier = val
            changes["risk_multiplier"] = val
        
        if changes:
            self.jarvis_override_active = True
            self.jarvis_last_update = time.time()
            changes["timestamp"] = self.jarvis_last_update
            logger.info(f"Jarvis BotState updated: {changes}")
        
        return changes

    def get_jarvis_state(self) -> dict:
        """Return full Jarvis BotState as a serializable dict."""
        return {
            "override_active": self.jarvis_override_active,
            "ml_confidence_threshold": self.jarvis_ml_threshold,
            "active_edges": self.jarvis_active_edges,
            "emergency_stop": self.jarvis_emergency_stop,
            "risk_multiplier": self.jarvis_risk_multiplier,
            "last_update": self.jarvis_last_update,
            "last_update_iso": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.jarvis_last_update))
                if self.jarvis_last_update > 0 else None
            ),
        }

    def __repr__(self):
        with self._lock:
            keys = list(self._data.keys())
        return f"StateManager(keys={keys})"


# Singleton
state = StateManager()
