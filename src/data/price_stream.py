"""
Price Stream - Binance WebSocket for real-time price updates.

Connects to Binance trade stream for sub-second price updates.
Falls back to REST API if WebSocket is unavailable.
"""

import asyncio
import json
import time
import threading
from typing import Optional, Dict, Callable

# Try websockets library, fall back gracefully
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


class PriceStream:
    """
    Real-time price stream from Binance WebSocket.
    
    Usage:
        stream = PriceStream()
        stream.start()  # Starts background thread
        
        price = stream.get_price()  # Returns latest price instantly
        stream.stop()
    """
    
    BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
    
    def __init__(self, symbol: str = "ethusdt"):
        self.symbol = symbol.lower()
        self._latest_price: Optional[float] = None
        self._latest_time: float = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._on_price_callbacks: list = []
        
        # Stats
        self.messages_received = 0
        self.reconnections = 0
        self.connected_since: Optional[float] = None
    
    @property
    def is_connected(self) -> bool:
        return self._running and self._latest_price is not None
    
    @property
    def price_age_seconds(self) -> float:
        """How old the latest price is in seconds."""
        if self._latest_time == 0:
            return float('inf')
        return time.time() - self._latest_time
    
    def get_price(self, max_age_seconds: float = 10.0) -> Optional[float]:
        """
        Get the latest price if it's fresh enough.
        
        Args:
            max_age_seconds: Maximum age of price data to accept
            
        Returns:
            Latest price, or None if too stale or not connected
        """
        if self._latest_price and self.price_age_seconds <= max_age_seconds:
            return self._latest_price
        return None
    
    def get_status(self) -> Dict:
        """Get stream status for API/dashboard."""
        return {
            "connected": self.is_connected,
            "symbol": self.symbol,
            "latest_price": self._latest_price,
            "price_age_seconds": round(self.price_age_seconds, 1) if self._latest_price else None,
            "messages_received": self.messages_received,
            "reconnections": self.reconnections,
            "uptime_seconds": round(time.time() - self.connected_since, 0) if self.connected_since else 0
        }
    
    def on_price(self, callback: Callable[[float], None]):
        """Register a callback for price updates."""
        self._on_price_callbacks.append(callback)
    
    def start(self):
        """Start the WebSocket stream in a background thread."""
        if not HAS_WEBSOCKETS:
            print("⚠️ PriceStream: 'websockets' library not installed, falling back to REST")
            return
        
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print(f"⚡ PriceStream started for {self.symbol.upper()}")
    
    def stop(self):
        """Stop the WebSocket stream."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        print("⛔ PriceStream stopped")
    
    def _run_loop(self):
        """Run the asyncio event loop in a background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_with_retry())
    
    async def _connect_with_retry(self):
        """Connect to WebSocket with automatic reconnection."""
        while self._running:
            try:
                stream_url = f"{self.BINANCE_WS_URL}/{self.symbol}@trade"
                
                async with websockets.connect(
                    stream_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as ws:
                    self.connected_since = time.time()
                    self._reconnect_delay = 1.0  # Reset on successful connection
                    print(f"🔗 PriceStream connected to {stream_url}")
                    
                    async for message in ws:
                        if not self._running:
                            break
                        
                        try:
                            data = json.loads(message)
                            price = float(data.get('p', 0))
                            
                            if price > 0:
                                self._latest_price = price
                                self._latest_time = time.time()
                                self.messages_received += 1
                                
                                # Notify callbacks (rate-limited to 1/sec)
                                if self.messages_received % 10 == 0:
                                    for cb in self._on_price_callbacks:
                                        try:
                                            cb(price)
                                        except Exception:
                                            pass
                        except (json.JSONDecodeError, ValueError):
                            continue
                            
            except Exception as e:
                if not self._running:
                    break
                    
                self.reconnections += 1
                print(f"⚠️ PriceStream disconnected: {e}. Reconnecting in {self._reconnect_delay}s...")
                
                await asyncio.sleep(self._reconnect_delay)
                # Exponential backoff
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay
                )


# Global singleton
_price_stream: Optional[PriceStream] = None


def get_price_stream(symbol: str = "ethusdt") -> PriceStream:
    """Get or create the global price stream singleton."""
    global _price_stream
    if _price_stream is None:
        _price_stream = PriceStream(symbol=symbol)
    return _price_stream


def start_price_stream(symbol: str = "ethusdt") -> PriceStream:
    """Start the global price stream."""
    stream = get_price_stream(symbol)
    stream.start()
    return stream


def get_live_price(max_age: float = 10.0) -> Optional[float]:
    """Quick helper to get the latest live price."""
    if _price_stream:
        return _price_stream.get_price(max_age)
    return None
