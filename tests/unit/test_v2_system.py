"""
Tests for Ethbot v2 Edge-First System.

Tests:
- EdgeValidator: prediction logging, outcome evaluation, report generation
- SignalEngineV2: individual edge signals, consensus logic
- RiskManagerV2: Kelly sizing, drawdown limits, circuit breakers
- DataCollector: derived indicator calculations
"""

import pytest
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════
# EDGE VALIDATOR TESTS
# ═══════════════════════════════════════════════════════

class TestEdgeValidator:
    """Test the edge validation system."""

    def _make_validator(self):
        from edge_validator import EdgeValidator
        return EdgeValidator()

    def test_log_prediction(self):
        v = self._make_validator()
        pid = v.log_prediction("funding_reversal", "LONG", 0.7, 3200.0)
        assert pid == 1
        assert len(v._predictions) == 1
        assert v._predictions[0].direction == "LONG"
        assert v._predictions[0].signal_name == "funding_reversal"

    def test_multiple_predictions(self):
        v = self._make_validator()
        v.log_prediction("funding_reversal", "LONG", 0.7, 3200.0)
        v.log_prediction("volume_mean_reversion", "SHORT", 0.6, 3250.0)
        v.log_prediction("oi_divergence", "LONG", 0.8, 3180.0)
        assert len(v._predictions) == 3
        assert v._next_id == 4

    def test_evaluate_outcome_win(self):
        v = self._make_validator()
        v.log_prediction("test", "LONG", 0.7, 3200.0)
        # Force timestamp to be old enough
        v._predictions[0].timestamp = time.time() - 3700  # 61 minutes ago
        v.evaluate_outcomes(3250.0)  # Price went up → WIN for LONG
        assert v._predictions[0].outcome == "WIN"
        assert v._predictions[0].pnl_pct > 0

    def test_evaluate_outcome_loss(self):
        v = self._make_validator()
        v.log_prediction("test", "LONG", 0.7, 3200.0)
        v._predictions[0].timestamp = time.time() - 3700
        v.evaluate_outcomes(3150.0)  # Price went down → LOSS for LONG
        assert v._predictions[0].outcome == "LOSS"
        assert v._predictions[0].pnl_pct < 0

    def test_short_direction_evaluation(self):
        v = self._make_validator()
        v.log_prediction("test", "SHORT", 0.7, 3200.0)
        v._predictions[0].timestamp = time.time() - 3700
        v.evaluate_outcomes(3150.0)  # Price went down → WIN for SHORT
        assert v._predictions[0].outcome == "WIN"

    def test_pending_prediction_not_evaluated(self):
        v = self._make_validator()
        v.log_prediction("test", "LONG", 0.7, 3200.0)
        # Don't adjust timestamp — it's too recent
        v.evaluate_outcomes(3250.0)
        assert v._predictions[0].outcome is None  # Still pending

    def test_report_collecting_status(self):
        v = self._make_validator()
        report = v.get_report()
        assert report["status"] == "COLLECTING"
        assert report["total_predictions"] == 0

    def test_report_with_evaluated_predictions(self):
        v = self._make_validator()
        # Create 10 predictions with outcomes
        for i in range(10):
            v.log_prediction("test", "LONG", 0.7, 3200.0)
            v._predictions[-1].timestamp = time.time() - 7200  # 2h ago
        v.evaluate_outcomes(3250.0)  # All should be wins
        
        report = v.get_report()
        assert report["status"] == "COLLECTING"  # Need 200 for validation
        assert report["evaluated"] == 10
        assert report["win_rate"] == 100.0

    def test_report_no_edge(self):
        v = self._make_validator()
        # Create 200+ losing predictions
        for i in range(201):
            v.log_prediction("test", "LONG", 0.7, 3200.0)
            v._predictions[-1].timestamp = time.time() - 7200
        v.evaluate_outcomes(3100.0)  # All losses
        
        report = v.get_report()
        assert report["status"] == "NO_EDGE"
        assert report["win_rate"] == 0.0


# ═══════════════════════════════════════════════════════
# SIGNAL ENGINE TESTS
# ═══════════════════════════════════════════════════════

class TestSignalEngine:
    """Test signal generation logic."""

    def _make_engine(self):
        from signal_engine_v2 import SignalEngineV2
        return SignalEngineV2()

    def test_funding_rate_high_gives_short(self):
        engine = self._make_engine()
        signal = engine.funding_rate_signal({
            "funding_rate": 0.001,  # 0.1% — very high
            "price": 3200.0
        })
        assert signal is not None
        assert signal.direction == "SHORT"
        assert signal.confidence > 0.5

    def test_funding_rate_negative_gives_long(self):
        engine = self._make_engine()
        signal = engine.funding_rate_signal({
            "funding_rate": -0.0005,  # -0.05%
            "price": 3200.0
        })
        assert signal is not None
        assert signal.direction == "LONG"

    def test_funding_rate_neutral_gives_none(self):
        engine = self._make_engine()
        signal = engine.funding_rate_signal({
            "funding_rate": 0.0002,  # 0.02% — neutral
            "price": 3200.0
        })
        assert signal is None

    def test_funding_rate_missing_gives_none(self):
        engine = self._make_engine()
        signal = engine.funding_rate_signal({"price": 3200.0})
        assert signal is None

    def test_volume_spike_above_vwap_gives_short(self):
        engine = self._make_engine()
        signal = engine.volume_spike_signal({
            "volume_spike_ratio": 4.0,
            "vwap_deviation_pct": 1.2,
            "price": 3200.0
        })
        assert signal is not None
        assert signal.direction == "SHORT"

    def test_volume_spike_below_vwap_gives_long(self):
        engine = self._make_engine()
        signal = engine.volume_spike_signal({
            "volume_spike_ratio": 3.5,
            "vwap_deviation_pct": -0.8,
            "price": 3200.0
        })
        assert signal is not None
        assert signal.direction == "LONG"

    def test_volume_no_spike_gives_none(self):
        engine = self._make_engine()
        signal = engine.volume_spike_signal({
            "volume_spike_ratio": 1.5,
            "vwap_deviation_pct": 0.1,
            "price": 3200.0
        })
        assert signal is None

    def test_oi_extreme_long_gives_short(self):
        engine = self._make_engine()
        signal = engine.oi_divergence_signal({
            "open_interest": 500000,
            "long_short_ratio": 2.5,
            "price": 3200.0,
            "price_change_24h": 5.0
        })
        assert signal is not None
        assert signal.direction == "SHORT"

    def test_oi_extreme_short_gives_long(self):
        engine = self._make_engine()
        signal = engine.oi_divergence_signal({
            "open_interest": 500000,
            "long_short_ratio": 0.3,
            "price": 3200.0,
            "price_change_24h": -3.0
        })
        assert signal is not None
        assert signal.direction == "LONG"

    def test_consensus_requires_two_signals(self):
        import asyncio
        engine = self._make_engine()
        # Only funding rate fires — no consensus
        result = asyncio.run(engine.generate_signal({
            "funding_rate": 0.001,
            "volume_spike_ratio": 1.0,
            "vwap_deviation_pct": 0.0,
            "price": 3200.0,
            "open_interest": None,
            "long_short_ratio": 1.0,
            "rsi_1m": 50,
            "bb_position": 0,
            "price_change_24h": 0
        }))
        # Single signal — might return with consensus=False or None
        if result:
            assert result.get("consensus", False) == False

    def test_consensus_two_signals_agree(self):
        import asyncio
        engine = self._make_engine()
        # Both funding rate AND OI divergence say SHORT
        result = asyncio.run(engine.generate_signal({
            "funding_rate": 0.001,      # → SHORT (high FR)
            "volume_spike_ratio": 1.0,
            "vwap_deviation_pct": 0.0,
            "price": 3200.0,
            "open_interest": 500000,
            "long_short_ratio": 2.5,    # → SHORT (extreme long positioning)
            "rsi_1m": 50,
            "bb_position": 0,
            "price_change_24h": 5.0
        }))
        assert result is not None
        assert result["direction"] == "SHORT"
        assert result["consensus"] == True
        assert result["signals_agreeing"] >= 2


# ═══════════════════════════════════════════════════════
# RISK MANAGER V2 TESTS
# ═══════════════════════════════════════════════════════

class TestRiskManagerV2:
    """Test risk management with Kelly sizing and circuit breakers."""

    def _make_risk(self):
        from risk_manager_v2 import RiskManagerV2
        return RiskManagerV2()

    def test_initial_rollout_is_10_percent(self):
        rm = self._make_risk()
        assert rm._get_rollout_multiplier() == 0.10

    def test_rollout_increases_with_trades(self):
        rm = self._make_risk()
        rm._total_trades = 50
        assert rm._get_rollout_multiplier() == 0.25
        rm._total_trades = 100
        assert rm._get_rollout_multiplier() == 0.50
        rm._total_trades = 200
        assert rm._get_rollout_multiplier() == 1.00

    def test_kelly_position_size_positive_edge(self):
        rm = self._make_risk()
        # 60% WR, avg win 1.5%, avg loss 1% → positive Kelly
        size = rm.kelly_position_size(
            equity=100000, win_rate=60, avg_win=1.5, avg_loss=1.0,
            price=3200, stop_loss_pct=0.012
        )
        assert size > 0
        # With 10% rollout, should be conservative
        assert size < 100  # Not absurdly large

    def test_kelly_zero_on_negative_edge(self):
        rm = self._make_risk()
        # 30% WR, avg win 0.5%, avg loss 1% → negative Kelly
        size = rm.kelly_position_size(
            equity=100000, win_rate=30, avg_win=0.5, avg_loss=1.0,
            price=3200, stop_loss_pct=0.012
        )
        assert size == 0.0001  # Minimum (basically zero)

    def test_can_trade_initially(self):
        rm = self._make_risk()
        allowed, reason = rm.can_trade()
        assert allowed == True
        assert reason == "OK"

    def test_max_positions_blocks_trading(self):
        rm = self._make_risk()
        for _ in range(3):
            rm.on_trade_opened()
        allowed, reason = rm.can_trade()
        assert allowed == False
        assert "positions" in reason.lower()

    def test_consecutive_loss_circuit_breaker(self):
        rm = self._make_risk()
        for _ in range(6):
            rm.on_trade_closed(is_win=False)
        allowed, reason = rm.can_trade()
        assert allowed == False
        assert "loss" in reason.lower() or "streak" in reason.lower()

    def test_win_resets_loss_streak(self):
        rm = self._make_risk()
        rm.on_trade_closed(is_win=False)
        rm.on_trade_closed(is_win=False)
        rm.on_trade_closed(is_win=True)
        assert rm._consecutive_losses == 0

    def test_daily_drawdown_pauses_trading(self):
        rm = self._make_risk()
        rm._day_start_equity = 100000
        rm._day_start_ts = time.time()
        # Equity dropped to 97500 → -2.5%
        allowed, reason = rm.can_trade(current_equity=97500)
        assert allowed == False
        assert "daily" in reason.lower()

    def test_weekly_drawdown_pauses_trading(self):
        rm = self._make_risk()
        rm._week_start_equity = 100000
        rm._week_start_ts = time.time()
        # Equity dropped to 94000 → -6%
        allowed, reason = rm.can_trade(current_equity=94000)
        assert allowed == False
        assert "weekly" in reason.lower()

    def test_status_report(self):
        rm = self._make_risk()
        status = rm.get_status()
        assert "can_trade" in status
        assert "capital_rollout_pct" in status
        assert status["capital_rollout_pct"] == 10.0

    def test_fixed_risk_sizing(self):
        rm = self._make_risk()
        size = rm.fixed_risk_position_size(
            equity=100000, price=3200, stop_loss_pct=0.012
        )
        # 1% of 100k × 10% rollout = $100 risk, at 1.2% SL and $3200 price
        assert size > 0
        assert size < 10  # Reasonable ETH quantity


# ═══════════════════════════════════════════════════════
# DATA COLLECTOR TESTS
# ═══════════════════════════════════════════════════════

class TestDataCollector:
    """Test derived indicator calculations."""

    def _make_collector(self):
        from data_collector import MarketCollector
        return MarketCollector()

    def test_volume_spike_ratio_no_history(self):
        c = self._make_collector()
        derived = c.calculate_derived({"price": 3200, "volume_1m": 100})
        assert derived["volume_spike_ratio"] == 1.0

    def test_vwap_calculation_with_data(self):
        c = self._make_collector()
        # Feed some prices
        for i in range(15):
            c.calculate_derived({"price": 3200 + i, "volume_1m": 100})
        derived = c.calculate_derived({"price": 3220, "volume_1m": 100})
        assert "vwap" in derived
        assert derived["vwap"] > 0

    def test_rsi_calculation(self):
        c = self._make_collector()
        # Feed 20 prices (trending up)
        for i in range(20):
            c.calculate_derived({"price": 3200 + i * 2, "volume_1m": 100})
        derived = c.calculate_derived({"price": 3240, "volume_1m": 100})
        assert derived["rsi_1m"] > 50  # Should be bullish

    def test_bb_position(self):
        c = self._make_collector()
        # Feed stable prices, then spike
        for i in range(25):
            c.calculate_derived({"price": 3200, "volume_1m": 100})
        # Spike up
        derived = c.calculate_derived({"price": 3300, "volume_1m": 100})
        assert derived["bb_position"] > 0  # Above upper band

    def test_collector_status(self):
        c = self._make_collector()
        status = c.get_status()
        assert status["running"] == True
        assert status["ticks_collected"] == 0
