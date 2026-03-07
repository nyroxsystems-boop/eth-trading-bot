"""
Market Data Module
Handles data fetching, indicator calculation, and technical analysis
"""
import requests
import pandas as pd
import numpy as np
from typing import Optional
from datetime import datetime, timezone

from ta.volatility import AverageTrueRange, BollingerBands
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MarketDataProvider:
    """Provides market data and technical indicators"""
    
    def __init__(self):
        self.config = get_config()
        self.base_url = "https://api.binance.com/api/v3"
    
    def fetch_klines(
        self,
        symbol: Optional[str] = None,
        interval: Optional[str] = None,
        lookback: Optional[int] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch kline/candlestick data from Binance
        
        Args:
            symbol: Trading pair (default from config)
            interval: Timeframe (default from config)
            lookback: Number of candles to fetch (default from config)
            start_ts: Start timestamp in milliseconds
            end_ts: End timestamp in milliseconds
            
        Returns:
            DataFrame with OHLCV data
        """
        symbol = symbol or self.config.trading.pair
        interval = interval or self.config.trading.interval
        lookback = lookback or self.config.trading.lookback
        
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": 1000
        }
        
        if start_ts:
            params["startTime"] = int(start_ts)
        if end_ts:
            params["endTime"] = int(end_ts)
        
        frames = []
        
        while True:
            try:
                response = requests.get(
                    f"{self.base_url}/klines",
                    params=params,
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                
                if not data:
                    break
                
                df = pd.DataFrame(data, columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "qv", "trades", "taker_base", "taker_quote", "ignore"
                ])
                frames.append(df)
                
                if len(data) < 1000:
                    break
                
                params["startTime"] = int(data[-1][6]) + 1
                
            except Exception as e:
                logger.error(f"Error fetching klines: {e}")
                raise
        
        if not frames:
            raise RuntimeError("No klines fetched")
        
        df = pd.concat(frames, ignore_index=True)
        
        # Convert to numeric
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        
        df["time"] = pd.to_datetime(df["open_time"], unit="ms")
        
        return df[["time", "open", "high", "low", "close", "volume"]]
    
    def get_last_price(self, symbol: Optional[str] = None) -> Optional[float]:
        """
        Get the latest price for a symbol.
        Tries WebSocket cache first (sub-second), falls back to REST API.
        
        Args:
            symbol: Trading pair (default from config)
            
        Returns:
            Latest price or None on error
        """
        symbol = symbol or self.config.trading.pair
        
        # Try WebSocket cache first (fastest)
        try:
            from src.data.price_stream import get_live_price
            ws_price = get_live_price(max_age=10.0)
            if ws_price is not None:
                return ws_price
        except ImportError:
            pass
        
        # Fallback to REST API
        try:
            df = self.fetch_klines(symbol=symbol, lookback=2)
            return float(df["close"].iloc[-1])
        except Exception as e:
            logger.error(f"Error getting last price: {e}")
            return None
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add technical indicators to OHLCV dataframe
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
        """
        out = df.copy()
        
        # Returns
        out["ret1"] = out["close"].pct_change()
        
        # EMAs
        out["ema20"] = EMAIndicator(out["close"], 20).ema_indicator()
        out["ema50"] = EMAIndicator(out["close"], 50).ema_indicator()
        
        # MACD
        macd = MACD(out["close"], window_slow=26, window_fast=12, window_sign=9)
        out["macd"] = macd.macd()
        out["macd_sig"] = macd.macd_signal()
        
        # RSI
        out["rsi14"] = RSIIndicator(out["close"], 14).rsi()
        
        # ATR
        atr = AverageTrueRange(out["high"], out["low"], out["close"], window=14)
        out["atr"] = atr.average_true_range()
        
        # Bollinger Bands
        bb = BollingerBands(out["close"], window=20, window_dev=2)
        out["bb_hi"] = bb.bollinger_hband()
        out["bb_lo"] = bb.bollinger_lband()
        
        # High/Low ranges
        out["hh20"] = out["high"].rolling(20).max()
        out["ll20"] = out["low"].rolling(20).min()
        
        # Drop NaN rows
        out.dropna(inplace=True)
        
        return out
    
    def calculate_adx(
        self, 
        df: pd.DataFrame, 
        window: Optional[int] = None
    ) -> float:
        """
        Calculate ADX (Average Directional Index) safely
        
        Args:
            df: DataFrame with OHLCV data
            window: ADX window (default from config)
            
        Returns:
            ADX value or 0.0 on error
        """
        window = window or self.config.regime.adx_window
        
        try:
            # Use tail for performance
            sub = df.tail(max(window * 4, 60)).copy()
            
            if len(sub) < window + 1:
                return 0.0
            
            # Ensure numeric types
            for col in ["high", "low", "close"]:
                sub[col] = pd.to_numeric(sub[col], errors="coerce")
            
            sub = sub.dropna()
            
            if len(sub) < 14:  # Minimum for ADX
                return 0.0
            
            w = min(window, max(14, len(sub) // 2))
            adx = ADXIndicator(sub["high"], sub["low"], sub["close"], window=w).adx()
            
            value = float(adx.iloc[-1])
            
            # Handle NaN
            if value != value:
                return 0.0
            
            return max(0.0, min(100.0, value))
            
        except Exception as e:
            logger.warning(f"ADX calculation failed: {e}")
            return 0.0
    
    def is_drawdown_candle(self, candle: pd.Series) -> bool:
        """
        Detect if a candle is a drawdown/hammer candle
        
        Args:
            candle: Series with open, high, low, close
            
        Returns:
            True if drawdown candle pattern detected
        """
        try:
            body = abs(candle["close"] - candle["open"])
            range_ = candle["high"] - candle["low"]
            lower_wick = min(candle["open"], candle["close"]) - candle["low"]
            
            if range_ <= 0:
                return False
            
            # Long lower wick (>45% of range) and close in upper half
            has_long_wick = (lower_wick / range_) > 0.45
            closes_high = candle["close"] > (candle["low"] + 0.5 * range_)
            
            return has_long_wick and closes_high
            
        except Exception as e:
            logger.warning(f"Drawdown candle check failed: {e}")
            return False
