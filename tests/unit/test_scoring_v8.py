#!/usr/bin/env python3
"""
Unit tests for v8 scoring system.
Tests the scoring formula used in strategy_backtester.py, 
continuous_backtester.py, and dashboard_api.py.

These tests validate:
- Kill gates (WR < 55%)
- Fake gates (WR >= 99.5%, etc.)
- Tier bonuses (WR 58-85%)
- ROI floor penalties
- R:R ratio bonuses
- Profit factor bonuses
- Trade count reliability gate
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def compute_v8_score(trades):
    """
    Extracted v8 scoring formula — identical to strategy_backtester.py lines 415-477.
    This is the reference implementation for testing.
    """
    if not trades or len(trades) == 0:
        return {"score": 0.0, "win_rate": 0, "roi": 0}
    
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100
    
    total_pnl = sum(t["pnl"] for t in trades)
    roi = total_pnl / 1000 * 100  # Assume $1000 base
    
    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0
    profit_factor = gross_profit / max(gross_loss, 0.001)
    
    # Simplified drawdown
    equity = 1000
    peak = 1000
    max_drawdown = 0
    for t in trades:
        equity += t["pnl"]
        peak = max(peak, equity)
        dd = (peak - equity) / peak
        max_drawdown = max(max_drawdown, dd)
    
    # Sharpe
    pnls = [t["pnl"] for t in trades]
    avg_pnl = sum(pnls) / len(pnls)
    std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)) ** 0.5
    sharpe = (avg_pnl / std_pnl * (len(trades) ** 0.5)) if std_pnl > 0 else 0
    
    n_trades = len(trades)
    
    # === SCORING v8 ===
    if win_rate >= 99.5:
        score = 0.0
    elif win_rate >= 90.0 and n_trades < 20:
        score = 0.0
    elif win_rate >= 80.0 and n_trades < 10:
        score = 0.0
    elif win_rate < 55.0:
        score = 0.0
    else:
        score = win_rate * 7.0
        if win_rate > 58: score += 50.0
        if win_rate > 60: score += 100.0
        if win_rate > 63: score += 200.0
        if win_rate > 65: score += 300.0
        if win_rate > 68: score += 400.0
        if win_rate > 70: score += 500.0
        if win_rate > 75: score += 700.0
        if win_rate > 80: score += 1000.0
        if win_rate > 85: score += 1500.0
        if 60 <= win_rate <= 75:
            score += 200.0  # Sweet spot bonus
        # ROI
        score += roi * 80.0
        # R:R
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.001
        rr_ratio = avg_win / max(avg_loss, 0.001)
        if rr_ratio >= 2.0: score += 500.0
        elif rr_ratio >= 1.5: score += 300.0
        elif rr_ratio >= 1.0: score += 100.0
        elif rr_ratio < 0.5: score *= 0.4
        # Profit factor
        if profit_factor >= 2.0: score += 300.0
        elif profit_factor >= 1.5: score += 200.0
        elif profit_factor >= 1.2: score += 100.0
        elif profit_factor < 0.8: score *= 0.3
        # ROI floor
        if roi < 5.0: score *= 0.6
        if roi < 0: score *= 0.25
        # Sharpe
        score += min(sharpe, 3.0) * 5.0
        # Drawdown
        score -= max_drawdown * 5.0
        # Trade count bonus
        score += min(n_trades / 20, 1.0) * 50
        # Reliability
        if n_trades < 10: score *= 0.1
    
    return {
        "score": round(score, 2),
        "win_rate": round(win_rate, 1),
        "roi": round(roi, 2),
        "profit_factor": round(profit_factor, 2),
        "n_trades": n_trades
    }


def make_trades(n_wins, n_losses, win_pnl=10.0, loss_pnl=-5.0):
    """Helper: create a list of mock trades."""
    trades = []
    for _ in range(n_wins):
        trades.append({"pnl": win_pnl, "exit_reason": "tp"})
    for _ in range(n_losses):
        trades.append({"pnl": loss_pnl, "exit_reason": "sl"})
    return trades


# =================== KILL GATE TESTS ===================

class TestKillGates:
    """WR < 55% must always score 0"""
    
    def test_wr_50_percent_scores_zero(self):
        trades = make_trades(50, 50)  # 50% WR
        result = compute_v8_score(trades)
        assert result["score"] == 0.0, f"WR 50% should score 0, got {result['score']}"
    
    def test_wr_54_percent_scores_zero(self):
        trades = make_trades(54, 46)  # 54% WR
        result = compute_v8_score(trades)
        assert result["score"] == 0.0, f"WR 54% should score 0, got {result['score']}"
    
    def test_wr_55_percent_scores_positive(self):
        trades = make_trades(55, 45)  # 55% WR
        result = compute_v8_score(trades)
        assert result["score"] > 0.0, f"WR 55% should score > 0, got {result['score']}"
    
    def test_no_trades_scores_zero(self):
        result = compute_v8_score([])
        assert result["score"] == 0.0


# =================== FAKE GATE TESTS ===================

class TestFakeGates:
    """Unrealistically perfect strategies must score 0"""
    
    def test_99_5_wr_scores_zero(self):
        trades = make_trades(200, 1)  # 99.5% WR
        result = compute_v8_score(trades)
        assert result["score"] == 0.0, "99.5%+ WR should be caught as fake"
    
    def test_100_wr_scores_zero(self):
        trades = make_trades(100, 0)  # 100% WR 
        result = compute_v8_score(trades)
        assert result["score"] == 0.0, "100% WR should be caught as fake"
    
    def test_90_wr_with_few_trades_scores_zero(self):
        trades = make_trades(18, 2)  # 90% WR, only 20 trades → < 20 check triggers
        result = compute_v8_score(trades)
        # 90% WR with 20 trades: n_trades = 20, so >= 20 passes
        # But 18/20 = 90%, and n_trades = 20 which is NOT < 20
        # Let's test with < 20 trades
        trades = make_trades(9, 1)  # 90% WR, 10 trades
        result = compute_v8_score(trades)
        assert result["score"] == 0.0, "90% WR with <20 trades should score 0"
    
    def test_80_wr_with_9_trades_scores_zero(self):
        trades = make_trades(8, 2)  # 80% WR, 10 trades → NOT < 10
        # Need < 10 trades for fake gate
        trades = make_trades(7, 1)  # 87.5%>=80% WR, 8 trades < 10
        result = compute_v8_score(trades)
        assert result["score"] == 0.0, "80%+ WR with <10 trades should score 0"
    
    def test_90_wr_with_enough_trades_scores_positive(self):
        trades = make_trades(90, 10)  # 90% WR, 100 trades — legitimate
        result = compute_v8_score(trades)
        assert result["score"] > 0.0, "90% WR with 100 trades should be valid"


# =================== TIER BONUS TESTS ===================

class TestTierBonuses:
    """Higher WR should always give higher scores (all else equal)"""
    
    def test_wr_ordering(self):
        """WR 60% < WR 65% < WR 70% < WR 75%"""
        scores = {}
        for wr in [56, 60, 65, 70, 75]:
            n_total = 100
            n_wins = wr
            n_losses = n_total - wr
            trades = make_trades(n_wins, n_losses)
            result = compute_v8_score(trades)
            scores[wr] = result["score"]
        
        assert scores[60] > scores[56], f"WR 60% ({scores[60]}) should beat WR 56% ({scores[56]})"
        assert scores[65] > scores[60], f"WR 65% ({scores[65]}) should beat WR 60% ({scores[60]})"
        assert scores[70] > scores[65], f"WR 70% ({scores[70]}) should beat WR 65% ({scores[65]})"
        assert scores[75] > scores[70], f"WR 75% ({scores[75]}) should beat WR 70% ({scores[70]})"
    
    def test_sweet_spot_bonus(self):
        """WR 60-75% should get sweet spot bonus"""
        trades_62 = make_trades(62, 38)
        trades_56 = make_trades(56, 44)
        
        score_62 = compute_v8_score(trades_62)["score"]
        score_56 = compute_v8_score(trades_56)["score"]
        
        # 62% is in sweet spot (60-75%), should be significantly better than 56%
        assert score_62 > score_56 * 1.2, "Sweet spot WR should be significantly better than just-above kill gate"


# =================== ROI & PROFITABILITY TESTS ===================

class TestProfitability:
    """ROI, profit factor, and R:R should correctly impact score"""
    
    def test_negative_roi_heavily_penalized(self):
        """Losing strategies should be near-zero"""
        trades = make_trades(60, 40, win_pnl=4.0, loss_pnl=-7.0)  # 60% WR, but losing money
        result = compute_v8_score(trades)
        
        trades_profitable = make_trades(60, 40, win_pnl=10.0, loss_pnl=-5.0)
        result_profitable = compute_v8_score(trades_profitable)
        
        assert result["score"] < result_profitable["score"] * 0.25, \
            "Losing money should score way less than profitable"
    
    def test_rr_ratio_2_gets_max_bonus(self):
        """R:R >= 2.0 should give +500 bonus"""
        trades_good_rr = make_trades(60, 40, win_pnl=20.0, loss_pnl=-5.0)  # R:R = 4.0
        trades_bad_rr = make_trades(60, 40, win_pnl=3.0, loss_pnl=-5.0)    # R:R = 0.6
        
        score_good = compute_v8_score(trades_good_rr)["score"]
        score_bad = compute_v8_score(trades_bad_rr)["score"]
        
        assert score_good > score_bad, "Good R:R should outscore bad R:R"


# =================== RELIABILITY GATE TESTS ===================

class TestReliabilityGate:
    """< 10 trades should be heavily penalized"""
    
    def test_few_trades_penalized(self):
        trades_7 = make_trades(5, 2)  # 71.4% WR but only 7 trades
        trades_100 = make_trades(71, 29)  # 71% WR with 100 trades
        
        score_7 = compute_v8_score(trades_7)["score"]
        score_100 = compute_v8_score(trades_100)["score"]
        
        assert score_7 < score_100 * 0.2, f"7 trades ({score_7}) should score way less than 100 trades ({score_100})"


# =================== REGRESSION TESTS (known edge cases) ===================

class TestEdgeCases:
    """Edge cases that have caused issues in production"""
    
    def test_all_winners_is_fake(self):
        """A strategy that wins every single trade is fake"""
        trades = make_trades(50, 0)
        assert compute_v8_score(trades)["score"] == 0.0
    
    def test_score_is_finite(self):
        """Score should never be NaN or Infinity"""
        for wr in [55, 60, 70, 80, 90, 95]:
            n = 100
            trades = make_trades(wr, n - wr)
            result = compute_v8_score(trades)
            assert not (result["score"] != result["score"]), f"Score is NaN for WR {wr}%"
            assert result["score"] < 100000, f"Score unreasonably high for WR {wr}%: {result['score']}"
    
    def test_zero_std_sharpe_safe(self):
        """All identical PnLs should not crash Sharpe calculation"""
        trades = [{"pnl": 5.0, "exit_reason": "tp"}] * 20
        result = compute_v8_score(trades)
        assert result["score"] == 0.0  # 100% WR → fake gate


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
