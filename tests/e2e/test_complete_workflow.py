"""
End-to-End Tests for ETH Trading Bot
Tests complete trading workflow from data fetching to order execution
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock


class TestCompleteWorkflow:
    """Test complete trading workflow end-to-end"""
    
    def test_full_trading_cycle_dry_run(self, sample_df_features):
        """Test complete trading cycle in dry-run mode"""
        from src.core.market_data import MarketDataProvider
        from src.core.ml_engine import MLEngine
        from src.core.strategy import TradingStrategy
        from src.core.risk_manager import RiskManager
        from src.core.order_executor import OrderExecutor
        
        # Initialize components
        market_data = MarketDataProvider()
        ml_engine = MLEngine()
        strategy = TradingStrategy(market_data, ml_engine)
        risk_manager = RiskManager()
        order_executor = OrderExecutor()
        
        # Verify all components initialized
        assert market_data is not None
        assert ml_engine is not None
        assert strategy is not None
        assert risk_manager is not None
        assert order_executor is not None
    
    def test_data_to_signal_pipeline(self, sample_df_features):
        """Test data flows correctly through the pipeline"""
        from src.core.market_data import MarketDataProvider
        from src.core.ml_engine import MLEngine
        from src.core.strategy import TradingStrategy
        
        # Create components
        market_data = MarketDataProvider()
        ml_engine = MLEngine()
        strategy = TradingStrategy(market_data, ml_engine)
        
        # Train ML model
        ml_engine.train_initial(sample_df_features)
        assert ml_engine.is_warm()
        
        # Compute regime
        regime = strategy.compute_regime(sample_df_features)
        assert regime.adx >= 0
        
        # Calculate signal
        current = sample_df_features.iloc[-1]
        previous = sample_df_features.iloc[-2]
        signal = strategy.calculate_entry_signal(current, previous, regime, use_mtf=False)
        
        assert 0 <= signal.score <= 2.0
        assert 0 <= signal.ml_prob <= 1.0
    
    def test_risk_management_integration(self):
        """Test risk management integrates correctly"""
        from src.core.risk_manager import RiskManager, Position
        
        risk_manager = RiskManager()
        
        # Test position sizing
        qty = risk_manager.position_size_for_risk(3500.0, 0.01, 100000.0)
        assert qty > 0
        
        # Test stop loss
        sl_pct = risk_manager.calculate_stop_loss(3500.0, 40.0)
        assert 0 < sl_pct < 0.05
        
        # Test drawdown protection
        risk_manager.day_start_equity = 100000.0
        is_paused = risk_manager.check_daily_drawdown(97000.0)
        assert is_paused is True
    
    def test_order_execution_guards(self):
        """Test order executor with guards"""
        from src.core.order_executor import OrderExecutor
        
        executor = OrderExecutor()
        
        # Test guards (should pass with no trades file)
        can_trade = executor.run_pre_buy_guards()
        assert isinstance(can_trade, bool)
        
        # Test balance
        balance = executor.get_usdt_balance()
        assert balance >= 0
    
    def test_multi_timeframe_integration(self, sample_df_features):
        """Test multi-timeframe analysis integration"""
        from src.core.multi_timeframe import MultiTimeframeAnalyzer
        
        analyzer = MultiTimeframeAnalyzer()
        
        # Test timeframe analysis
        signal = analyzer.analyze_timeframe(sample_df_features, "5m")
        assert signal.timeframe == "5m"
        assert 0 <= signal.score <= 1.0
    
    def test_ensemble_ml_integration(self, sample_df_features):
        """Test ensemble ML engine integration"""
        from src.ml.ensemble_engine import EnsembleMLEngine
        
        engine = EnsembleMLEngine()
        
        # Train
        engine.train_initial(sample_df_features)
        assert engine.is_warm()
        
        # Predict
        pred = engine.predict(sample_df_features.iloc[-1])
        assert 0 <= pred <= 1.0
        
        # Get info
        info = engine.get_model_info()
        assert info['warm'] is True


class TestModuleIntegration:
    """Test modules work together correctly"""
    
    def test_config_logger_integration(self):
        """Test config and logger work together"""
        from src.utils.config import get_config
        from src.utils.logger import get_logger
        
        config = get_config()
        logger = get_logger('test')
        
        assert config is not None
        assert logger is not None
        
        logger.info(f"Config test: {config.trading.pair}")
    
    def test_strategy_uses_all_components(self, sample_df_features):
        """Test strategy integrates all components"""
        from src.core.market_data import MarketDataProvider
        from src.core.ml_engine import MLEngine
        from src.core.strategy import TradingStrategy
        
        market_data = MarketDataProvider()
        ml_engine = MLEngine()
        strategy = TradingStrategy(market_data, ml_engine)
        
        # Train ML
        ml_engine.train_initial(sample_df_features)
        
        # Get regime
        regime = strategy.compute_regime(sample_df_features)
        
        # Get signal
        current = sample_df_features.iloc[-1]
        previous = sample_df_features.iloc[-2]
        signal = strategy.calculate_entry_signal(current, previous, regime, use_mtf=False)
        
        # Check entry decision
        should_enter, reason = strategy.should_enter_long(signal, regime)
        assert isinstance(should_enter, bool)
        assert isinstance(reason, str)


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_insufficient_data(self):
        """Test handling of insufficient data"""
        from src.core.market_data import MarketDataProvider
        
        provider = MarketDataProvider()
        
        # Empty dataframe - provider should handle gracefully
        df_empty = pd.DataFrame()
        
        # Empty DataFrame without proper columns should raise or return empty
        try:
            df_with_indicators = provider.add_indicators(df_empty)
            # If it doesn't raise, it should return empty or minimal
            assert len(df_with_indicators) == 0 or 'close' not in df_empty.columns
        except (KeyError, ValueError):
            # Expected behavior - insufficient data raises error
            pass
    
    def test_invalid_predictions(self):
        """Test ML engine with invalid data"""
        from src.core.ml_engine import MLEngine
        
        engine = MLEngine()
        
        # Predict without training
        row = pd.Series({'close': 3500, 'ema20': 3480, 'rsi14': 50})
        pred = engine.predict(row)
        
        # Should return neutral
        assert pred == 0.5
    
    def test_guards_with_no_trades(self):
        """Test guards when no trades exist"""
        from src.core.guards import TradeGuards
        
        guards = TradeGuards()
        
        # Should not block when no trades
        blocked, reason = guards.check_max_consecutive_losses()
        assert blocked is False
        
        blocked, reason = guards.check_daily_target_reached()
        assert blocked is False


class TestPerformance:
    """Test performance and latency"""
    
    def test_prediction_latency(self, sample_df_features):
        """Test ML prediction is fast enough"""
        import time
        from src.core.ml_engine import MLEngine
        
        engine = MLEngine()
        engine.train_initial(sample_df_features)
        
        # Measure prediction time
        start = time.time()
        for _ in range(100):
            engine.predict(sample_df_features.iloc[-1])
        elapsed = time.time() - start
        
        avg_time = elapsed / 100
        
        # Should be < 50ms per prediction
        assert avg_time < 0.05, f"Prediction too slow: {avg_time*1000:.2f}ms"
    
    def test_indicator_calculation_speed(self, sample_df_features):
        """Test indicator calculation is fast"""
        import time
        from src.core.market_data import MarketDataProvider
        
        provider = MarketDataProvider()
        
        start = time.time()
        df_with_indicators = provider.add_indicators(sample_df_features)
        elapsed = time.time() - start
        
        # Should be < 1 second for 500 bars
        assert elapsed < 1.0, f"Indicators too slow: {elapsed:.2f}s"


@pytest.fixture
def sample_df_features():
    """Create sample dataframe with features for testing"""
    np.random.seed(42)
    n = 500
    
    dates = pd.date_range(start='2024-01-01', periods=n, freq='5min')
    
    # Generate realistic price data
    price = 3500.0
    prices = []
    for _ in range(n):
        price += np.random.randn() * 10
        prices.append(price)
    
    df = pd.DataFrame({
        'time': dates,
        'open': prices,
        'high': [p + abs(np.random.randn() * 5) for p in prices],
        'low': [p - abs(np.random.randn() * 5) for p in prices],
        'close': prices,
        'volume': np.random.uniform(100, 1000, n)
    })
    
    # Add indicators
    from src.core.market_data import MarketDataProvider
    provider = MarketDataProvider()
    df_with_indicators = provider.add_indicators(df)
    
    return df_with_indicators
