#!/usr/bin/env python3
"""
Mock Binance Client for Testing
Provides realistic test data when real API keys are not available
"""

import random
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List

class MockBinanceClient:
    """Mock Binance client that generates realistic test data"""
    
    def __init__(self):
        self.base_price = 2500.0  # ETH base price
        self.price_volatility = 0.02  # 2% volatility
        self.balance_usdt = 100000.0
        self.balance_eth = 0.0
        
    def get_symbol_ticker(self, symbol: str = "ETHUSDT") -> Dict:
        """Get current price"""
        # Simulate price movement
        change = random.uniform(-self.price_volatility, self.price_volatility)
        current_price = self.base_price * (1 + change)
        
        return {
            "symbol": symbol,
            "price": str(current_price)
        }
    
    def get_klines(self, symbol: str, interval: str, limit: int = 500, **kwargs) -> List:
        """Generate mock kline data"""
        klines = []
        now = int(time.time() * 1000)
        
        # Interval to milliseconds
        interval_ms = {
            "1m": 60000,
            "5m": 300000,
            "15m": 900000,
            "1h": 3600000,
            "4h": 14400000,
            "1d": 86400000
        }.get(interval, 300000)
        
        base_price = self.base_price
        
        for i in range(limit):
            timestamp = now - (limit - i) * interval_ms
            
            # Generate OHLCV with realistic movement
            open_price = base_price
            high_price = open_price * (1 + random.uniform(0, 0.01))
            low_price = open_price * (1 - random.uniform(0, 0.01))
            close_price = random.uniform(low_price, high_price)
            volume = random.uniform(100, 1000)
            
            klines.append([
                timestamp,
                str(open_price),
                str(high_price),
                str(low_price),
                str(close_price),
                str(volume),
                timestamp + interval_ms - 1,
                str(volume * close_price),  # Quote volume
                random.randint(50, 200),  # Number of trades
                str(volume * 0.5),  # Taker buy base
                str(volume * close_price * 0.5),  # Taker buy quote
                "0"
            ])
            
            # Update base price for next candle
            base_price = close_price * (1 + random.uniform(-0.005, 0.005))
        
        return klines
    
    def get_account(self) -> Dict:
        """Get account balances"""
        return {
            "balances": [
                {
                    "asset": "USDT",
                    "free": str(self.balance_usdt),
                    "locked": "0.0"
                },
                {
                    "asset": "ETH",
                    "free": str(self.balance_eth),
                    "locked": "0.0"
                }
            ]
        }
    
    def create_order(self, symbol: str, side: str, type: str, **kwargs) -> Dict:
        """Simulate order creation"""
        quantity = float(kwargs.get("quantity", 0))
        price = float(kwargs.get("price", self.base_price))
        
        # Update mock balances
        if side == "BUY":
            cost = quantity * price
            if cost <= self.balance_usdt:
                self.balance_usdt -= cost
                self.balance_eth += quantity
        elif side == "SELL":
            if quantity <= self.balance_eth:
                self.balance_eth -= quantity
                self.balance_usdt += quantity * price
        
        return {
            "symbol": symbol,
            "orderId": random.randint(1000000, 9999999),
            "clientOrderId": f"mock_{int(time.time())}",
            "transactTime": int(time.time() * 1000),
            "price": str(price),
            "origQty": str(quantity),
            "executedQty": str(quantity),
            "status": "FILLED",
            "type": type,
            "side": side
        }

def get_binance_client():
    """Get Binance client (real or mock)"""
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    
    # Use mock if no real credentials or placeholder
    if not api_key or not api_secret or "PLACEHOLDER" in api_key:
        print("[MOCK] Using mock Binance client for testing")
        return MockBinanceClient()
    
    # Use real client
    try:
        from binance.client import Client
        return Client(api_key, api_secret)
    except Exception as e:
        print(f"[MOCK] Failed to create real client: {e}, using mock")
        return MockBinanceClient()

if __name__ == "__main__":
    import os
    # Test mock client
    client = get_binance_client()
    
    print("Testing mock Binance client...")
    print(f"Ticker: {client.get_symbol_ticker()}")
    print(f"Account: {client.get_account()}")
    print(f"Klines: {len(client.get_klines('ETHUSDT', '5m', limit=10))} candles")
