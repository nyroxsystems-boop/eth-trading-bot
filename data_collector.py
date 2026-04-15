"""
Ethbot v2: Market Data Collector

Collects granular market data every 60 seconds:
- Price, Volume, VWAP
- Funding Rate (Binance Futures)
- Open Interest (Binance Futures)
- Long/Short Ratio
- Volume Spikes
- RSI, Bollinger Band deviation

Stores everything in PostgreSQL for edge validation and signal generation.

Usage:
    from data_collector import MarketCollector
    collector = MarketCollector()
    await collector.run()  # Runs forever, collecting every 60s
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger("ethbot.collector")

# Binance API endpoints
SPOT_BASE = "https://api.binance.com/api/v3"
FUTURES_BASE = "https://fapi.binance.com/fapi/v1"
SYMBOL = "ETHUSDT"


class MarketCollector:
    """Collects and stores granular market data for edge validation."""

    def __init__(self):
        self.has_futures = None  # Auto-detected on first call
        self._price_history: list = []  # Rolling window for indicators
        self._volume_history: list = []  # Rolling window for volume avg
        self._collect_count = 0
        self._errors = 0

    # ─── Data Fetching ───

    async def _fetch_json(self, url: str, params: dict = None, timeout: int = 10) -> Optional[dict]:
        """Fetch JSON from URL using asyncio.to_thread (non-blocking)."""
        import requests
        try:
            resp = await asyncio.to_thread(
                requests.get, url, params=params or {}, timeout=timeout
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.debug(f"HTTP {resp.status_code} from {url}")
                return None
        except Exception as e:
            logger.debug(f"Fetch error {url}: {e}")
            return None

    async def fetch_spot_data(self) -> Dict:
        """Fetch current price, volume, and kline data from Binance Spot."""
        data = {"price": 0.0, "volume_1m": 0.0, "high": 0.0, "low": 0.0, "open": 0.0}

        # Current price
        ticker = await self._fetch_json(f"{SPOT_BASE}/ticker/price", {"symbol": SYMBOL})
        if ticker:
            data["price"] = float(ticker.get("price", 0))

        # 1-minute kline for OHLCV
        klines = await self._fetch_json(f"{SPOT_BASE}/klines", {
            "symbol": SYMBOL, "interval": "1m", "limit": 2
        })
        if klines and len(klines) >= 2:
            last = klines[-2]  # Use completed candle
            data["open"] = float(last[1])
            data["high"] = float(last[2])
            data["low"] = float(last[3])
            data["volume_1m"] = float(last[5])

        # 24h volume for context
        ticker_24h = await self._fetch_json(f"{SPOT_BASE}/ticker/24hr", {"symbol": SYMBOL})
        if ticker_24h:
            data["volume_24h"] = float(ticker_24h.get("volume", 0))
            data["price_change_24h"] = float(ticker_24h.get("priceChangePercent", 0))

        return data

    async def fetch_funding_rate(self) -> Dict:
        """Fetch funding rate from Binance Futures API."""
        data = {"funding_rate": None, "next_funding_time": None}

        result = await self._fetch_json(f"{FUTURES_BASE}/premiumIndex", {"symbol": SYMBOL})
        if result:
            self.has_futures = True
            data["funding_rate"] = float(result.get("lastFundingRate", 0))
            data["next_funding_time"] = int(result.get("nextFundingTime", 0))
            data["mark_price"] = float(result.get("markPrice", 0))
            data["index_price"] = float(result.get("indexPrice", 0))
        elif self.has_futures is None:
            self.has_futures = False
            logger.warning("Futures API not available — funding rate edge disabled")

        return data

    async def fetch_open_interest(self) -> Dict:
        """Fetch open interest from Binance Futures API."""
        data = {"open_interest": None, "open_interest_value": None}

        result = await self._fetch_json(f"{FUTURES_BASE}/openInterest", {"symbol": SYMBOL})
        if result:
            data["open_interest"] = float(result.get("openInterest", 0))

        return data

    async def fetch_long_short_ratio(self) -> Dict:
        """Fetch global long/short ratio from Binance Futures."""
        data = {"long_short_ratio": None, "long_account": None, "short_account": None}

        result = await self._fetch_json(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
            {"symbol": SYMBOL, "period": "5m", "limit": 1}
        )
        if result and len(result) > 0:
            entry = result[0]
            data["long_short_ratio"] = float(entry.get("longShortRatio", 1.0))
            data["long_account"] = float(entry.get("longAccount", 0.5))
            data["short_account"] = float(entry.get("shortAccount", 0.5))

        return data

    # ─── Derived Indicators ───

    def calculate_derived(self, spot: Dict) -> Dict:
        """Calculate VWAP deviation, volume spike, RSI from collected data."""
        derived = {}
        price = spot.get("price", 0)
        volume = spot.get("volume_1m", 0)

        # Track history (rolling 60-bar window = 1 hour at 1m interval)
        self._price_history.append(price)
        self._volume_history.append(volume)
        if len(self._price_history) > 120:
            self._price_history = self._price_history[-120:]
        if len(self._volume_history) > 120:
            self._volume_history = self._volume_history[-120:]

        # Volume spike (vs 1h average)
        if len(self._volume_history) >= 10:
            avg_vol = sum(self._volume_history[-60:]) / min(len(self._volume_history), 60)
            derived["volume_spike_ratio"] = round(volume / max(avg_vol, 1), 2)
        else:
            derived["volume_spike_ratio"] = 1.0

        # Simple VWAP approximation (volume-weighted average price)
        if len(self._price_history) >= 10 and len(self._volume_history) >= 10:
            window = min(60, len(self._price_history))
            prices = self._price_history[-window:]
            volumes = self._volume_history[-window:]
            total_vol = sum(volumes)
            if total_vol > 0:
                vwap = sum(p * v for p, v in zip(prices, volumes)) / total_vol
                derived["vwap"] = round(vwap, 2)
                derived["vwap_deviation_pct"] = round((price - vwap) / max(vwap, 1) * 100, 4)
            else:
                derived["vwap"] = price
                derived["vwap_deviation_pct"] = 0.0
        else:
            derived["vwap"] = price
            derived["vwap_deviation_pct"] = 0.0

        # RSI-14 (on 1m prices)
        if len(self._price_history) >= 15:
            gains, losses = [], []
            for i in range(-14, 0):
                change = self._price_history[i] - self._price_history[i - 1]
                gains.append(max(0, change))
                losses.append(max(0, -change))
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            if avg_loss == 0:
                derived["rsi_1m"] = 100.0
            else:
                rs = avg_gain / avg_loss
                derived["rsi_1m"] = round(100 - 100 / (1 + rs), 1)
        else:
            derived["rsi_1m"] = 50.0

        # Bollinger Band position (2σ)
        if len(self._price_history) >= 20:
            window = self._price_history[-20:]
            mean = sum(window) / 20
            std = (sum((p - mean) ** 2 for p in window) / 20) ** 0.5
            if std > 0:
                derived["bb_position"] = round((price - mean) / (2 * std), 3)  # -1 to +1
            else:
                derived["bb_position"] = 0.0
        else:
            derived["bb_position"] = 0.0

        return derived

    # ─── Storage ───

    async def ensure_table(self):
        """Create the market_data_1m table in PostgreSQL."""
        try:
            from db_adapter import get_db_connection, USE_POSTGRES
            if not USE_POSTGRES:
                logger.info("No PostgreSQL — market data will be stored in memory only")
                return False

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS market_data_1m (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        price FLOAT NOT NULL,
                        open FLOAT,
                        high FLOAT,
                        low FLOAT,
                        volume_1m FLOAT,
                        volume_24h FLOAT,
                        price_change_24h FLOAT,
                        funding_rate FLOAT,
                        next_funding_time BIGINT,
                        mark_price FLOAT,
                        index_price FLOAT,
                        open_interest FLOAT,
                        long_short_ratio FLOAT,
                        long_account FLOAT,
                        short_account FLOAT,
                        vwap FLOAT,
                        vwap_deviation_pct FLOAT,
                        volume_spike_ratio FLOAT,
                        rsi_1m FLOAT,
                        bb_position FLOAT
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_market_data_ts 
                    ON market_data_1m (timestamp DESC);
                """)
            logger.info("✅ market_data_1m table ready")
            return True
        except Exception as e:
            logger.error(f"Table creation error: {e}")
            return False

    async def store(self, data: Dict):
        """Store collected data point in PostgreSQL."""
        try:
            from db_adapter import get_db_connection, USE_POSTGRES
            if not USE_POSTGRES:
                return

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO market_data_1m (
                        price, open, high, low, volume_1m, volume_24h, price_change_24h,
                        funding_rate, next_funding_time, mark_price, index_price,
                        open_interest, long_short_ratio, long_account, short_account,
                        vwap, vwap_deviation_pct, volume_spike_ratio, rsi_1m, bb_position
                    ) VALUES (
                        %(price)s, %(open)s, %(high)s, %(low)s, %(volume_1m)s, 
                        %(volume_24h)s, %(price_change_24h)s,
                        %(funding_rate)s, %(next_funding_time)s, %(mark_price)s, %(index_price)s,
                        %(open_interest)s, %(long_short_ratio)s, %(long_account)s, %(short_account)s,
                        %(vwap)s, %(vwap_deviation_pct)s, %(volume_spike_ratio)s, 
                        %(rsi_1m)s, %(bb_position)s
                    )
                """, data)
        except Exception as e:
            logger.warning(f"Store error: {e}")
            self._errors += 1

    # ─── Main Loop ───

    async def collect_once(self) -> Dict:
        """Collect all data points once."""
        # Fetch all data concurrently
        spot, funding, oi, ls = await asyncio.gather(
            self.fetch_spot_data(),
            self.fetch_funding_rate(),
            self.fetch_open_interest(),
            self.fetch_long_short_ratio(),
            return_exceptions=True
        )

        # Handle exceptions from gather
        if isinstance(spot, Exception):
            spot = {"price": 0, "volume_1m": 0, "high": 0, "low": 0, "open": 0}
        if isinstance(funding, Exception):
            funding = {}
        if isinstance(oi, Exception):
            oi = {}
        if isinstance(ls, Exception):
            ls = {}

        # Calculate derived indicators
        derived = self.calculate_derived(spot)

        # Merge all data
        data = {
            **spot,
            **funding,
            **oi,
            **ls,
            **derived
        }

        # Fill missing keys with None
        all_keys = [
            "price", "open", "high", "low", "volume_1m", "volume_24h", "price_change_24h",
            "funding_rate", "next_funding_time", "mark_price", "index_price",
            "open_interest", "long_short_ratio", "long_account", "short_account",
            "vwap", "vwap_deviation_pct", "volume_spike_ratio", "rsi_1m", "bb_position"
        ]
        for key in all_keys:
            if key not in data:
                data[key] = None

        return data

    async def run(self):
        """Main collection loop — runs forever, collecting every 60 seconds."""
        has_db = await self.ensure_table()
        logger.info(f"📊 Market Data Collector started (DB: {'PostgreSQL' if has_db else 'memory-only'})")

        while True:
            try:
                data = await self.collect_once()
                self._collect_count += 1

                # Store in database
                if data.get("price", 0) > 0:
                    await self.store(data)

                # Log every 5 minutes
                if self._collect_count % 5 == 0:
                    fr = data.get("funding_rate")
                    fr_str = f"{fr*100:.4f}%" if fr is not None else "N/A"
                    oi = data.get("open_interest")
                    oi_str = f"{oi:,.0f}" if oi is not None else "N/A"
                    logger.info(
                        f"📊 Tick #{self._collect_count}: "
                        f"${data['price']:,.2f} | "
                        f"FR={fr_str} | "
                        f"OI={oi_str} | "
                        f"Vol spike={data.get('volume_spike_ratio', 'N/A')}x | "
                        f"VWAP dev={data.get('vwap_deviation_pct', 0):.3f}% | "
                        f"RSI={data.get('rsi_1m', 'N/A')}"
                    )

            except Exception as e:
                logger.error(f"Collection error: {e}")
                self._errors += 1

            await asyncio.sleep(60)

    def get_status(self) -> Dict:
        """Return collector status for dashboard."""
        return {
            "running": True,
            "ticks_collected": self._collect_count,
            "errors": self._errors,
            "has_futures_api": self.has_futures,
            "price_history_len": len(self._price_history),
            "data_points_estimated": self._collect_count,
            "hours_of_data": round(self._collect_count / 60, 1)
        }


# Singleton
collector = MarketCollector()
