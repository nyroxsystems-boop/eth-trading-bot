"""
Integration tests for complete trading workflow
"""
import pytest


@pytest.mark.integration
class TestTradingWorkflow:
    """Integration tests for complete trading workflow"""
    
    def test_complete_signal_generation_workflow(self):
        """Test complete workflow from data fetch to signal generation"""
        from src.core.market_data import MarketDataProvider
        from src.core.ml_engine import MLEngine
        from src.core.strategy import TradingStrategy
        
        # Initialize components
        market_data = MarketDataProvider()
        ml_engine = MLEngine()
        strategy = TradingStrategy(market_data, ml_engine)
        
        # Fetch data
        df = market_data.fetch_klines(lookback=300)
        df_with_indicators = market_data.add_indicators(df)
        
        assert len(df_with_indicators) > 100
        
        # Train ML model
        ml_engine.train_initial(df_with_indicators)
        
        assert ml_engine.is_warm()
        
        # Compute regime
        regime = strategy.compute_regime(df_with_indicators)
        
        assert 0 <= regime.adx <= 100
        assert isinstance(regime.trend_ok, bool)
        assert isinstance(regime.vol_ok, bool)
        
        # Calculate signal
        current_row = df_with_indicators.iloc[-1]
        previous_row = df_with_indicators.iloc[-2]
        
        signal = strategy.calculate_entry_signal(current_row, previous_row, regime)
        
        assert -1.0 <= signal.score <= 2.0  # Score can be negative with bearish boosts
        assert 0 <= signal.ml_prob <= 1.0
        
        # Check entry decision
        should_enter, reason = strategy.should_enter_long(signal, regime)
        
        assert isinstance(should_enter, bool)
        assert isinstance(reason, str)
        assert len(reason) > 0
    
    def test_risk_management_workflow(self):
        """Test risk management workflow"""
        from src.core.risk_manager import RiskManager, Position
        
        risk_manager = RiskManager()
        
        # Test position sizing
        price = 3500.0
        equity = 100000.0
        stop_loss_pct = 0.01
        
        qty = risk_manager.position_size_for_risk(price, stop_loss_pct, equity)
        
        assert qty > 0
        assert qty * price < equity  # Position size should be less than total equity
        
        # Test stop loss calculation
        entry = 3500.0
        atr = 40.0
        
        sl_pct = risk_manager.calculate_stop_loss(entry, atr)
        
        assert sl_pct > 0
        assert sl_pct < 0.1  # Stop loss should be reasonable (<10%)
        
        # Test exit logic
        position = Position(entry=3500.0, qty=10.0, atr=40.0)
        current_price = 3550.0  # +1.4% profit
        
        should_exit, reason = risk_manager.should_exit_position(
            position=position,
            current_price=current_price,
            current_atr=40.0,
            bars_in_position=10,
            rsi=65.0
        )
        
        assert isinstance(should_exit, bool)
        if should_exit:
            assert reason in ["TP", "SL", "TIME"]
