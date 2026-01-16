"""
Unit tests for multi-timeframe analysis
"""
import pytest
import pandas as pd
import numpy as np


class TestMultiTimeframeAnalyzer:
    """Test multi-timeframe analysis"""
    
    def test_analyzer_initialization(self):
        """Test analyzer initializes with correct timeframes"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer
        
        analyzer = MultiTimeframeAnalyzer()
        
        assert analyzer.timeframes == ["5m", "15m", "1h"]
        assert analyzer.weights["5m"] == 0.40
        assert analyzer.weights["15m"] == 0.35
        assert analyzer.weights["1h"] == 0.25
    
    def test_analyze_timeframe_bullish(self, sample_df_features):
        """Test timeframe analysis detects bullish signal"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer
        
        analyzer = MultiTimeframeAnalyzer()
        
        # Create bullish scenario
        df = sample_df_features.copy()
        df.loc[df.index[-1], "close"] = 3600  # Above EMA
        df.loc[df.index[-1], "ema20"] = 3550
        df.loc[df.index[-1], "ema50"] = 3500
        df.loc[df.index[-1], "rsi14"] = 60
        
        signal = analyzer.analyze_timeframe(df, "5m")
        
        assert signal.timeframe == "5m"
        assert signal.trend is True
        assert signal.ema_alignment is True
        assert signal.score > 0.5
    
    def test_analyze_timeframe_bearish(self, sample_df_features):
        """Test timeframe analysis detects bearish signal"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer
        
        analyzer = MultiTimeframeAnalyzer()
        
        # Create bearish scenario
        df = sample_df_features.copy()
        df.loc[df.index[-1], "close"] = 3400  # Below EMA
        df.loc[df.index[-1], "ema20"] = 3450
        df.loc[df.index[-1], "ema50"] = 3500
        df.loc[df.index[-1], "rsi14"] = 35
        
        signal = analyzer.analyze_timeframe(df, "5m")
        
        assert signal.timeframe == "5m"
        assert signal.trend is False
        assert signal.ema_alignment is False
    
    def test_aggregate_signals_all_bullish(self):
        """Test signal aggregation with all bullish timeframes"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer, TimeframeSignal
        
        analyzer = MultiTimeframeAnalyzer()
        
        signals = {
            "5m": TimeframeSignal("5m", True, 0.8, 65, True, True, 0.8),
            "15m": TimeframeSignal("15m", True, 0.7, 62, True, False, 0.7),
            "1h": TimeframeSignal("1h", True, 0.6, 60, True, False, 0.6)
        }
        
        boost = analyzer.aggregate_signals(signals)
        
        # All bullish should give positive boost
        assert boost > 0.1
        assert boost <= 0.2
    
    def test_aggregate_signals_all_bearish(self):
        """Test signal aggregation with all bearish timeframes"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer, TimeframeSignal
        
        analyzer = MultiTimeframeAnalyzer()
        
        signals = {
            "5m": TimeframeSignal("5m", False, 0.2, 35, False, False, 0.2),
            "15m": TimeframeSignal("15m", False, 0.1, 32, False, False, 0.1),
            "1h": TimeframeSignal("1h", False, 0.0, 30, False, False, 0.0)
        }
        
        boost = analyzer.aggregate_signals(signals)
        
        # All bearish should give negative boost
        assert boost < -0.1
        assert boost >= -0.2
    
    def test_aggregate_signals_mixed(self):
        """Test signal aggregation with mixed timeframes"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer, TimeframeSignal
        
        analyzer = MultiTimeframeAnalyzer()
        
        signals = {
            "5m": TimeframeSignal("5m", True, 0.7, 62, True, True, 0.7),
            "15m": TimeframeSignal("15m", True, 0.6, 58, True, False, 0.6),
            "1h": TimeframeSignal("1h", False, 0.3, 45, False, False, 0.3)
        }
        
        boost = analyzer.aggregate_signals(signals)
        
        # Mixed signals should give moderate boost
        assert -0.1 <= boost <= 0.15
    
    def test_should_block_entry_all_bearish(self):
        """Test entry blocking when all timeframes bearish"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer, TimeframeSignal
        
        analyzer = MultiTimeframeAnalyzer()
        
        signals = {
            "5m": TimeframeSignal("5m", False, 0.2, 35, False, False, 0.2),
            "15m": TimeframeSignal("15m", False, 0.1, 32, False, False, 0.1),
            "1h": TimeframeSignal("1h", False, 0.0, 30, False, False, 0.0)
        }
        
        should_block = analyzer.should_block_entry(signals)
        
        assert should_block is True
    
    def test_should_not_block_entry_bullish(self):
        """Test entry not blocked when timeframes bullish"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer, TimeframeSignal
        
        analyzer = MultiTimeframeAnalyzer()
        
        signals = {
            "5m": TimeframeSignal("5m", True, 0.7, 62, True, True, 0.7),
            "15m": TimeframeSignal("15m", True, 0.6, 58, True, False, 0.6),
            "1h": TimeframeSignal("1h", True, 0.5, 55, True, False, 0.5)
        }
        
        should_block = analyzer.should_block_entry(signals)
        
        assert should_block is False
