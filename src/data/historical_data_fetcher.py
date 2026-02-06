#!/usr/bin/env python3
"""
Historical Data Fetcher for Binance
Fetches and caches long-term historical OHLCV data from Binance API.
Supports fetching data since ETH listing (August 2017).
"""

import os
import sqlite3
import requests
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
CACHE_DB = LOG_DIR / "historical_data.db"
BINANCE_API = "https://api.binance.com/api/v3"

# ETH was listed on Binance in August 2017
ETH_LISTING_DATE = datetime(2017, 8, 17)


class HistoricalDataFetcher:
    """
    Fetches and caches historical OHLCV data from Binance.
    Uses pagination to fetch data beyond the 1000 candle limit.
    """
    
    def __init__(self):
        self.session = requests.Session()
        self._ensure_db()
    
    def _ensure_db(self):
        """Create cache database and tables"""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                close_time INTEGER NOT NULL,
                PRIMARY KEY (symbol, interval, open_time)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_candles_lookup 
            ON candles (symbol, interval, open_time)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fetch_log (
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                last_fetch TEXT NOT NULL,
                candle_count INTEGER DEFAULT 0,
                PRIMARY KEY (symbol, interval)
            )
        """)
        conn.commit()
        conn.close()
    
    def fetch_klines(
        self,
        symbol: str = "ETHUSDT",
        interval: str = "4h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Fetch klines from Binance API.
        
        Args:
            symbol: Trading pair
            interval: Timeframe (1m, 5m, 15m, 1h, 4h, 1d, etc.)
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            limit: Max candles per request (max 1000)
            
        Returns:
            List of candle dicts
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000)
        }
        
        if start_time:
            params["startTime"] = int(start_time)
        if end_time:
            params["endTime"] = int(end_time)
        
        try:
            response = self.session.get(
                f"{BINANCE_API}/klines",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            candles = []
            for k in response.json():
                candles.append({
                    "open_time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": k[6]
                })
            
            return candles
            
        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            return []
    
    def fetch_all_historical(
        self,
        symbol: str = "ETHUSDT",
        interval: str = "4h",
        years_back: int = 7,
        progress_callback=None
    ) -> List[Dict]:
        """
        Fetch all historical data using pagination.
        
        Args:
            symbol: Trading pair
            interval: Timeframe
            years_back: How many years of data to fetch (max ~7 for ETH)
            progress_callback: Optional callback(current, total) for progress
            
        Returns:
            List of all candles
        """
        # Calculate start time
        start_date = max(
            ETH_LISTING_DATE,
            datetime.now() - timedelta(days=years_back * 365)
        )
        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(datetime.now().timestamp() * 1000)
        
        # Estimate total candles
        interval_ms = self._interval_to_ms(interval)
        if interval_ms == 0:
            interval_ms = 4 * 60 * 60 * 1000  # Default 4h
        
        estimated_candles = (end_ms - start_ms) // interval_ms
        
        logger.info(f"📊 Fetching ~{estimated_candles} candles from Binance ({years_back} years)...")
        
        all_candles = []
        current_start = start_ms
        request_count = 0
        
        while current_start < end_ms:
            candles = self.fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time=current_start,
                end_time=end_ms,
                limit=1000
            )
            
            if not candles:
                break
            
            all_candles.extend(candles)
            request_count += 1
            
            # Progress callback
            if progress_callback:
                progress_callback(len(all_candles), estimated_candles)
            
            # Log progress every 10 requests
            if request_count % 10 == 0:
                logger.info(f"   Fetched {len(all_candles)} candles...")
            
            # Move to next batch
            current_start = candles[-1]["close_time"] + 1
            
            # Rate limiting (1200 requests/min limit)
            time.sleep(0.1)
        
        logger.info(f"✅ Fetched {len(all_candles)} total candles")
        return all_candles
    
    def cache_candles(self, symbol: str, interval: str, candles: List[Dict]):
        """Save candles to SQLite cache"""
        if not candles:
            return
        
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        
        # Insert or replace candles
        cursor.executemany("""
            INSERT OR REPLACE INTO candles 
            (symbol, interval, open_time, open, high, low, close, volume, close_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (symbol, interval, c["open_time"], c["open"], c["high"], 
             c["low"], c["close"], c["volume"], c["close_time"])
            for c in candles
        ])
        
        # Update fetch log
        cursor.execute("""
            INSERT OR REPLACE INTO fetch_log (symbol, interval, last_fetch, candle_count)
            VALUES (?, ?, ?, ?)
        """, (symbol, interval, datetime.now().isoformat(), len(candles)))
        
        conn.commit()
        conn.close()
        
        logger.info(f"💾 Cached {len(candles)} candles for {symbol}/{interval}")
    
    def get_cached_candles(
        self,
        symbol: str = "ETHUSDT",
        interval: str = "4h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict]:
        """Retrieve candles from cache"""
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        
        query = "SELECT * FROM candles WHERE symbol = ? AND interval = ?"
        params = [symbol, interval]
        
        if start_time:
            query += " AND open_time >= ?"
            params.append(start_time)
        if end_time:
            query += " AND open_time <= ?"
            params.append(end_time)
        
        query += " ORDER BY open_time ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "symbol": r[0],
                "interval": r[1],
                "open_time": r[2],
                "open": r[3],
                "high": r[4],
                "low": r[5],
                "close": r[6],
                "volume": r[7],
                "close_time": r[8]
            }
            for r in rows
        ]
    
    def get_prices_array(
        self,
        symbol: str = "ETHUSDT",
        interval: str = "4h",
        days: int = 60
    ) -> List[float]:
        """Get closing prices as numpy-compatible array for training"""
        start_ms = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        candles = self.get_cached_candles(symbol, interval, start_time=start_ms)
        
        if not candles:
            # Fetch if not cached
            logger.info(f"Cache miss - fetching {days} days of data...")
            candles = self.fetch_klines(symbol, interval, start_time=start_ms)
            self.cache_candles(symbol, interval, candles)
        
        return [c["close"] for c in candles]
    
    def update_cache_incremental(self, symbol: str = "ETHUSDT", interval: str = "4h"):
        """Incrementally update cache with latest data"""
        # Get last cached timestamp
        cached = self.get_cached_candles(symbol, interval)
        
        if cached:
            last_time = cached[-1]["close_time"] + 1
        else:
            # No cache, fetch last 60 days
            last_time = int((datetime.now() - timedelta(days=60)).timestamp() * 1000)
        
        # Fetch new candles
        new_candles = self.fetch_klines(
            symbol, interval, start_time=last_time
        )
        
        if new_candles:
            self.cache_candles(symbol, interval, new_candles)
            logger.info(f"📥 Added {len(new_candles)} new candles to cache")
        
        return new_candles
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        
        cursor.execute("SELECT symbol, interval, candle_count, last_fetch FROM fetch_log")
        logs = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) FROM candles")
        total = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_candles": total,
            "datasets": [
                {
                    "symbol": l[0],
                    "interval": l[1],
                    "candle_count": l[2],
                    "last_fetch": l[3]
                }
                for l in logs
            ]
        }
    
    def _interval_to_ms(self, interval: str) -> int:
        """Convert interval string to milliseconds"""
        multipliers = {
            "m": 60 * 1000,
            "h": 60 * 60 * 1000,
            "d": 24 * 60 * 60 * 1000,
            "w": 7 * 24 * 60 * 60 * 1000
        }
        
        try:
            value = int(interval[:-1])
            unit = interval[-1]
            return value * multipliers.get(unit, 0)
        except:
            return 0


# Singleton instance
_fetcher = None

def get_historical_fetcher() -> HistoricalDataFetcher:
    """Get global historical data fetcher instance"""
    global _fetcher
    if _fetcher is None:
        _fetcher = HistoricalDataFetcher()
    return _fetcher


def fetch_all_historical_data(
    symbol: str = "ETHUSDT",
    interval: str = "4h", 
    years_back: int = 5
) -> List[Dict]:
    """
    Convenience function to fetch all historical data.
    
    Args:
        symbol: Trading pair
        interval: Timeframe
        years_back: Years of history to fetch
        
    Returns:
        List of candle dicts
    """
    fetcher = get_historical_fetcher()
    
    # Check cache first
    cached = fetcher.get_cached_candles(symbol, interval)
    if len(cached) > 1000:  # Good enough cache
        logger.info(f"📂 Using cached data ({len(cached)} candles)")
        return cached
    
    # Fetch fresh data
    candles = fetcher.fetch_all_historical(symbol, interval, years_back)
    fetcher.cache_candles(symbol, interval, candles)
    
    return candles


# CLI for testing
if __name__ == "__main__":
    import sys
    
    fetcher = HistoricalDataFetcher()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        # Fetch full history
        print("🚀 Fetching full historical data (this may take a few minutes)...")
        candles = fetcher.fetch_all_historical("ETHUSDT", "4h", years_back=5)
        fetcher.cache_candles("ETHUSDT", "4h", candles)
        print(f"✅ Done! Cached {len(candles)} candles")
        
    elif len(sys.argv) > 1 and sys.argv[1] == "--stats":
        # Show cache stats
        stats = fetcher.get_cache_stats()
        print(f"\n📊 Cache Statistics:")
        print(f"   Total candles: {stats['total_candles']}")
        for ds in stats['datasets']:
            print(f"   {ds['symbol']}/{ds['interval']}: {ds['candle_count']} (last fetch: {ds['last_fetch']})")
    
    else:
        # Quick test - fetch last 60 days
        print("🧪 Testing historical data fetch (60 days)...")
        candles = fetcher.fetch_klines("ETHUSDT", "4h", limit=360)
        print(f"✅ Fetched {len(candles)} candles")
        if candles:
            print(f"   First: {datetime.fromtimestamp(candles[0]['open_time']/1000)}")
            print(f"   Last:  {datetime.fromtimestamp(candles[-1]['open_time']/1000)}")
            print(f"   Price range: ${candles[0]['close']:.2f} - ${candles[-1]['close']:.2f}")
