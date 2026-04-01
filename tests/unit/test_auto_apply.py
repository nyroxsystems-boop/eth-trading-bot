#!/usr/bin/env python3
"""
Unit tests for auto_apply.py strategy application safety logic.

Tests the should_apply_strategy() method which gates strategy promotion:
- Min win rate threshold (55%)
- Max drawdown threshold (15%)
- Min ROI threshold (1.0%)  
- Score improvement requirement (0.5%)
- Win rate regression protection (±0.5%)
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from auto_apply import AutoApply


@pytest.fixture
def applier():
    """Create AutoApply instance with default safety thresholds."""
    aa = AutoApply.__new__(AutoApply)
    aa.min_score_improvement = 1.005  # 0.5% improvement
    aa.min_win_rate = 55.0
    aa.max_drawdown = 15.0
    aa.min_roi = 1.0
    return aa


# =================== SAFETY GATE TESTS ===================

class TestSafetyGates:
    """Strategies that don't meet thresholds must be rejected"""
    
    def test_reject_low_win_rate(self, applier):
        new = {"win_rate": 50.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        assert not applier.should_apply_strategy(new, None), \
            "WR < 55% should be rejected"
    
    def test_reject_high_drawdown(self, applier):
        new = {"win_rate": 65.0, "max_drawdown": 20.0, "roi": 10.0, "score": 500}
        assert not applier.should_apply_strategy(new, None), \
            "Drawdown > 15% should be rejected"
    
    def test_reject_low_roi(self, applier):
        new = {"win_rate": 65.0, "max_drawdown": 5.0, "roi": 0.5, "score": 500}
        assert not applier.should_apply_strategy(new, None), \
            "ROI < 1.0% should be rejected"
    
    def test_accept_first_good_strategy(self, applier):
        new = {"win_rate": 65.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        assert applier.should_apply_strategy(new, None), \
            "First good strategy (no current) should be accepted"
    
    def test_accept_exactly_at_thresholds(self, applier):
        new = {"win_rate": 55.0, "max_drawdown": 15.0, "roi": 1.0, "score": 500}
        assert applier.should_apply_strategy(new, None), \
            "Strategy exactly at thresholds should be accepted"


# =================== SCORE IMPROVEMENT TESTS ===================

class TestScoreImprovement:
    """New strategy must be at least 0.5% better than current"""
    
    def test_reject_same_score(self, applier):
        current = {"win_rate": 65.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        new = {"win_rate": 65.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        assert not applier.should_apply_strategy(new, current), \
            "Same score should be rejected (need 0.5% improvement)"
    
    def test_reject_marginal_improvement(self, applier):
        current = {"win_rate": 65.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        new = {"win_rate": 65.1, "max_drawdown": 5.0, "roi": 10.0, "score": 501}  # 0.2% better
        assert not applier.should_apply_strategy(new, current), \
            "0.2% improvement should be rejected (need 0.5%)"
    
    def test_accept_sufficient_improvement(self, applier):
        current = {"win_rate": 65.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        new = {"win_rate": 66.0, "max_drawdown": 5.0, "roi": 10.0, "score": 510}  # 2% better
        assert applier.should_apply_strategy(new, current), \
            "2% improvement should be accepted"
    
    def test_accept_when_current_score_zero(self, applier):
        current = {"win_rate": 55.0, "max_drawdown": 5.0, "roi": 10.0, "score": 0}
        new = {"win_rate": 65.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        assert applier.should_apply_strategy(new, current), \
            "Any good strategy should replace a score-0 current"


# =================== WIN RATE REGRESSION TESTS ===================

class TestWRRegression:
    """New strategy must not regress WR by more than 0.5%"""
    
    def test_reject_wr_regression(self, applier):
        current = {"win_rate": 68.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        new = {"win_rate": 65.0, "max_drawdown": 3.0, "roi": 15.0, "score": 600}  # Better score, but WR dropped 3%
        assert not applier.should_apply_strategy(new, current), \
            "WR drop of 3% should be rejected despite higher score"
    
    def test_accept_tiny_wr_regression(self, applier):
        current = {"win_rate": 68.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        new = {"win_rate": 67.6, "max_drawdown": 3.0, "roi": 15.0, "score": 600}  # WR only dropped 0.4%
        assert applier.should_apply_strategy(new, current), \
            "WR drop of 0.4% should be accepted (within 0.5% tolerance)"
    
    def test_accept_wr_improvement(self, applier):
        current = {"win_rate": 65.0, "max_drawdown": 5.0, "roi": 10.0, "score": 500}
        new = {"win_rate": 70.0, "max_drawdown": 5.0, "roi": 10.0, "score": 600}
        assert applier.should_apply_strategy(new, current), \
            "WR improvement should always be accepted (if score also better)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
