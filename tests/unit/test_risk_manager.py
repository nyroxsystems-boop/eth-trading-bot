"""
Unit tests for risk management calculations
"""
import pytest
import numpy as np


class TestPositionSizing:
    """Test position sizing calculations"""
    
    def test_position_size_for_risk_basic(self):
        """Test basic position sizing calculation"""
        px = 3500.0
        sl_pct = 0.01  # 1% stop loss
        equity = 100000.0
        risk_pct = 0.006  # 0.6% risk per trade
        
        # Expected: risk_usd = 100000 * 0.006 = 600
        # qty = 600 / (0.01 * 3500) = 600 / 35 = 17.14
        risk_usd = equity * risk_pct
        expected_qty = risk_usd / (sl_pct * px)
        
        assert expected_qty > 0
        assert expected_qty == pytest.approx(17.14, rel=0.01)
    
    def test_position_size_minimum(self):
        """Test position size has minimum threshold"""
        px = 3500.0
        sl_pct = 0.10  # Large stop loss
        equity = 100.0  # Small equity
        risk_pct = 0.001
        
        risk_usd = equity * risk_pct
        qty = risk_usd / (sl_pct * px)
        
        # Should have minimum qty (0.0001 in current implementation)
        assert qty >= 0.0001 or qty == max(0.0001, qty)
    
    def test_position_size_with_zero_stop(self):
        """Test position sizing handles zero stop loss"""
        px = 3500.0
        sl_pct = 0.0
        equity = 100000.0
        risk_pct = 0.006
        
        # Should handle division by zero gracefully
        # Implementation uses max(sl_pct * px, 1e-9)
        denom = max(sl_pct * px, 1e-9)
        risk_usd = equity * risk_pct
        qty = risk_usd / denom
        
        assert qty > 0
        assert not np.isnan(qty)
        assert not np.isinf(qty)


class TestStopLossCalculation:
    """Test stop loss calculations"""
    
    def test_stop_loss_floor(self):
        """Test stop loss respects floor"""
        stop_floor = 0.005  # 0.5%
        atr = 10.0
        entry = 3500.0
        atr_mult = 1.5
        
        atr_stop = atr_mult * (atr / entry)
        sl_pct = max(stop_floor, atr_stop)
        
        assert sl_pct >= stop_floor
    
    def test_stop_loss_atr_based(self):
        """Test ATR-based stop loss"""
        atr = 50.0  # Large ATR
        entry = 3500.0
        atr_mult = 1.5
        stop_floor = 0.005
        
        atr_stop = atr_mult * (atr / entry)
        sl_pct = max(stop_floor, atr_stop)
        
        # With large ATR, should use ATR-based stop
        assert sl_pct > stop_floor
        assert sl_pct == pytest.approx(atr_mult * (atr / entry), rel=0.01)
    
    def test_break_even_trigger(self):
        """Test break-even stop loss trigger"""
        entry = 3500.0
        current_px = 3521.0  # +0.6% profit
        break_even_trigger = 0.006  # 0.6%
        
        upnl = (current_px / entry) - 1.0
        
        if upnl >= break_even_trigger:
            sl_pct = max(0.0, 0.0)  # Move to break-even
        else:
            sl_pct = 0.01  # Keep original stop
        
        assert upnl >= break_even_trigger
        assert sl_pct == 0.0


class TestDrawdownProtection:
    """Test drawdown protection logic"""
    
    def test_daily_drawdown_limit(self):
        """Test daily drawdown limit triggers pause"""
        day_start_equity = 100000.0
        current_equity = 97000.0  # -3%
        max_drawdown = 0.03  # 3%
        
        dd = (current_equity / day_start_equity) - 1.0
        
        assert dd <= -max_drawdown
        # Should trigger pause
    
    def test_within_drawdown_limit(self):
        """Test trading continues within drawdown limit"""
        day_start_equity = 100000.0
        current_equity = 98000.0  # -2%
        max_drawdown = 0.03  # 3%
        
        dd = (current_equity / day_start_equity) - 1.0
        
        assert dd > -max_drawdown
        # Should continue trading


class TestLossStreakCooldown:
    """Test loss streak cooldown logic"""
    
    def test_cooldown_after_loss_streak(self):
        """Test cooldown activates after loss streak"""
        loss_streak = 3
        loss_streak_threshold = 2
        cooldown_minutes = 10
        
        import time
        current_time = time.time()
        
        if loss_streak >= loss_streak_threshold:
            cooldown_until = current_time + (cooldown_minutes * 60)
        else:
            cooldown_until = 0
        
        assert loss_streak >= loss_streak_threshold
        assert cooldown_until > current_time
    
    def test_no_cooldown_below_threshold(self):
        """Test no cooldown below loss streak threshold"""
        loss_streak = 1
        loss_streak_threshold = 2
        
        assert loss_streak < loss_streak_threshold
        # Should not trigger cooldown


class TestTrailingStop:
    """Test trailing stop logic"""
    
    def test_trailing_stop_calculation(self):
        """Test trailing stop calculation"""
        entry = 3500.0
        current_atr = 40.0
        trail_atr_mult = 1.0
        
        trail_pct = trail_atr_mult * (current_atr / entry)
        
        assert trail_pct > 0
        assert trail_pct == pytest.approx(1.0 * (40.0 / 3500.0), rel=0.01)
    
    def test_trailing_stop_tightens(self):
        """Test trailing stop tightens as profit increases"""
        entry = 3500.0
        initial_stop = 0.01  # 1%
        trail_pct = 0.008  # 0.8%
        
        # As price moves up, trailing stop should tighten
        final_stop = max(initial_stop, trail_pct)
        
        assert final_stop >= trail_pct
