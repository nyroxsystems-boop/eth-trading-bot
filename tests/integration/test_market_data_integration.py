"""
Integration tests for market data provider
"""
import pytest
import pandas as pd


@pytest.mark.integration
class TestMarketDataIntegration:
    """Integration tests for MarketDataProvider"""
    
    def test_fetch_klines_from_binance(self):
        """Test fetching real data from Binance API"""
        from src.core.market_data import MarketDataProvider
        
        provider = MarketDataProvider()
        
        # Fetch small amount of data
        df = provider.fetch_klines(lookback=10)
        
        assert len(df) > 0
        assert "time" in df.columns
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns
        assert "volume" in df.columns
    
    def test_add_indicators_integration(self):
        """Test adding indicators to real data"""
        from src.core.market_data import MarketDataProvider
        
        provider = MarketDataProvider()
        
        # Fetch data
        df = provider.fetch_klines(lookback=100)
        
        # Add indicators
        df_with_indicators = provider.add_indicators(df)
        
        # Check all indicators were added
        required_indicators = [
            "ret1", "ema20", "ema50", "macd", "macd_sig",
            "rsi14", "atr", "bb_hi", "bb_lo", "hh20", "ll20"
        ]
        
        for indicator in required_indicators:
            assert indicator in df_with_indicators.columns
        
        # Check no NaN in final rows
        assert not df_with_indicators.iloc[-1].isna().any()
    
    def test_get_last_price_integration(self):
        """Test getting last price from Binance"""
        from src.core.market_data import MarketDataProvider
        
        provider = MarketDataProvider()
        
        price = provider.get_last_price()
        
        assert price is not None
        assert price > 0
        assert 1000 < price < 10000  # Reasonable ETH price range
    
    def test_calculate_adx_integration(self):
        """Test ADX calculation on real data"""
        from src.core.market_data import MarketDataProvider
        
        provider = MarketDataProvider()
        
        df = provider.fetch_klines(lookback=100)
        df_with_indicators = provider.add_indicators(df)
        
        adx = provider.calculate_adx(df_with_indicators)
        
        assert 0 <= adx <= 100
        assert adx == adx  # Not NaN
