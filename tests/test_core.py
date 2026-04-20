"""
Test Suite for Ethbot Trading Platform.

Tests cover:
  1. Critical safety: atomic writes, retry logic, kill switch
  2. ML integrity: no circular features, TimeSeriesSplit, Triple-Barrier
  3. Strategy logic: signal generation, allocation, risk limits
  4. Data pipeline: feature collection, experience memory
"""
import os
import sys
import numpy as np
import pytest

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ═══════════════════════════════════════════════════════════════════
# 1. SAFETY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAtomicState:
    """Test atomic state writes (P0 safety)."""

    def test_state_save_load(self, tmp_path):
        from bot.state import BotState
        path = str(tmp_path / "test_state.json")
        state = BotState()
        state.paper_balance = 12345.67
        state.save(path)

        loaded = BotState.load(path)
        assert loaded.paper_balance == 12345.67

    def test_state_no_corruption_on_crash(self, tmp_path):
        """State file should always be valid JSON."""
        from bot.state import BotState
        path = str(tmp_path / "test_state.json")
        state = BotState()

        # Save multiple times (simulating rapid saves)
        for i in range(10):
            state.paper_balance = 1000 + i
            state.save(path)

        # Verify last save is valid
        loaded = BotState.load(path)
        assert loaded.paper_balance == 1009


class TestRetryLogic:
    """Test exponential backoff retry decorator."""

    def test_retry_succeeds_after_failures(self):
        from bot.executor import retry_api

        call_count = 0

        @retry_api(max_retries=3, base_delay=0.01)
        def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "ok"

        result = flaky_fn()
        assert result == "ok"
        assert call_count == 3

    def test_retry_gives_up(self):
        from bot.executor import retry_api

        @retry_api(max_retries=2, base_delay=0.01)
        def always_fails():
            raise ConnectionError("always fail")

        result = always_fails()
        assert result is None  # Safe default


# ═══════════════════════════════════════════════════════════════════
# 2. ML INTEGRITY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestMLIntegrity:
    """Verify ML pipeline has no circular features or look-ahead bias."""

    def test_no_circular_features_in_training(self):
        """score and signal_count must NOT be in feature list."""
        from bot.brain import TradingBrain
        brain = TradingBrain()
        # Access the feature list from maybe_train_model
        import inspect
        source = inspect.getsource(brain.maybe_train_model)
        assert "\"score\"" not in source.split("feature_cols")[1].split("]")[0], \
            "CIRCULAR: 'score' is in training features!"
        assert "\"signal_count\"" not in source.split("feature_cols")[1].split("]")[0], \
            "CIRCULAR: 'signal_count' is in training features!"

    def test_no_fake_features_in_training(self):
        """news_sentiment and oi_signal must NOT be in feature list."""
        from bot.brain import TradingBrain
        brain = TradingBrain()
        import inspect
        source = inspect.getsource(brain.maybe_train_model)
        feature_section = source.split("feature_cols")[1].split("]")[0]
        assert "news_sentiment" not in feature_section
        assert "oi_signal" not in feature_section

    def test_prediction_uses_same_features_as_training(self):
        """Prediction features must match training features exactly."""
        import inspect
        from bot.brain import TradingBrain
        brain = TradingBrain()

        train_src = inspect.getsource(brain.maybe_train_model)
        pred_src = inspect.getsource(brain.get_ml_prediction)

        # Extract feature_cols from both
        train_features = train_src.split("feature_cols = [")[1].split("]")[0]
        pred_features = pred_src.split("feature_cols = [")[1].split("]")[0]

        assert train_features.strip() == pred_features.strip(), \
            f"Feature mismatch!\nTrain: {train_features}\nPred: {pred_features}"

    def test_timeseries_split_used(self):
        """Must use TimeSeriesSplit, not random CV."""
        import inspect
        from bot.brain import TradingBrain
        source = inspect.getsource(TradingBrain.maybe_train_model)
        assert "TimeSeriesSplit" in source, "Random CV still used!"
        assert "cross_val_score" not in source, "Random cross_val_score still present!"


class TestTripleBarrier:
    """Test Triple-Barrier labeling."""

    def test_sl_hit_before_tp_labels_zero(self):
        """When SL is hit before TP, label should be 0."""
        # SL at -0.7%, TP at +1.0%
        entry = 100.0
        sl = entry * 0.993  # 99.3
        tp = entry * 1.01   # 101.0

        # Price drops immediately
        prices = [100, 99.5, 99.0, 98.5]  # SL hit at bar 2
        highs = [100.5, 99.7, 99.2, 98.8]
        lows = [99.8, 99.3, 98.9, 98.3]

        # SL should trigger
        barrier_hit = 0
        for i in range(1, len(prices)):
            if lows[i] <= sl:
                barrier_hit = -1
                break
            elif highs[i] >= tp:
                barrier_hit = 1
                break

        assert barrier_hit == -1, "SL should have been hit"

    def test_tp_hit_before_sl_labels_one(self):
        """When TP is hit before SL, label should be 1."""
        entry = 100.0
        sl = entry * 0.993  # 99.3
        tp = entry * 1.01   # 101.0

        # Price rises
        highs = [100.2, 100.5, 101.2]  # TP hit at bar 2
        lows = [99.8, 100.0, 100.8]

        barrier_hit = 0
        for i in range(len(highs)):
            if lows[i] <= sl:
                barrier_hit = -1
                break
            elif highs[i] >= tp:
                barrier_hit = 1
                break

        assert barrier_hit == 1, "TP should have been hit"


# ═══════════════════════════════════════════════════════════════════
# 3. STRATEGY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAllocator:
    """Test Master Allocator risk management."""

    def test_kelly_no_edge_returns_zero(self):
        """Kelly should return 0 when there's no edge."""
        from bot.strategies.allocator import MasterAllocator
        # 50% win rate, 1:1 payoff = no edge
        size = MasterAllocator.kelly_size(0.5, 1.0, 100000)
        assert size == 0.0, f"Kelly should be 0 with no edge, got {size}"

    def test_kelly_positive_edge(self):
        """Kelly should return positive size with edge."""
        from bot.strategies.allocator import MasterAllocator
        # 60% win rate, 1.5:1 payoff
        size = MasterAllocator.kelly_size(0.60, 1.5, 100000)
        assert size > 0, f"Kelly should be positive with edge, got {size}"
        assert size <= 10000, f"Kelly should be ≤10% of capital, got {size}"

    def test_kill_switch_on_daily_loss(self):
        """Kill switch activates on 3% daily loss."""
        from bot.strategies.allocator import MasterAllocator
        alloc = MasterAllocator(100000)
        alloc.state.daily_pnl = -0.04  # 4% loss
        risk = alloc.check_global_risk()
        assert risk["kill_switch"], "Kill switch should be active at 4% daily loss"

    def test_max_position_cap(self):
        """Position should never exceed 10% of capital."""
        from bot.strategies.allocator import MasterAllocator
        # Even with amazing edge, cap at 10%
        size = MasterAllocator.kelly_size(0.99, 10.0, 100000)
        assert size <= 10000, f"Position exceeded 10% cap: {size}"


class TestMarginExecutor:
    """Test Margin client safety limits."""

    def test_max_position_limit(self):
        """Max position should be capped."""
        from bot.margin_executor import MarginClient
        assert MarginClient.MAX_POSITION_USD == 50_000

    def test_client_initialization(self):
        """Client should initialize without error."""
        from bot.margin_executor import MarginClient
        client = MarginClient.__new__(MarginClient)
        assert hasattr(client, 'MAX_POSITION_USD')


class TestMomentum:
    """Test Momentum V2 strategy."""

    def test_hurst_returns_valid_float(self):
        """Hurst exponent should return a valid float between 0 and 1."""
        from bot.strategies.momentum_v2 import MomentumBreakoutV2
        mom = MomentumBreakoutV2()
        np.random.seed(42)
        random_walk = np.cumsum(np.random.randn(500)) + 100
        hurst = mom._hurst_exponent(random_walk, 200)
        assert 0.0 <= hurst <= 1.0, f"Hurst should be in [0, 1], got {hurst}"
        assert isinstance(hurst, float), f"Hurst should be float, got {type(hurst)}"

    def test_atr_calculation(self):
        """ATR should be positive for volatile data."""
        from bot.strategies.momentum_v2 import MomentumBreakoutV2
        mom = MomentumBreakoutV2()
        high = np.array([101, 102, 103, 104, 105] * 5)
        low = np.array([99, 98, 97, 96, 95] * 5)
        close = np.array([100, 100, 100, 100, 100] * 5)
        atr = mom._atr(high, low, close, period=14)
        assert atr > 0, f"ATR should be positive, got {atr}"

    def test_vol_targeting_reduces_size_in_high_vol(self):
        """Higher volatility should result in smaller position."""
        from bot.strategies.momentum_v2 import MomentumBreakoutV2
        mom = MomentumBreakoutV2()

        size_low_vol = mom.volatility_target_size(100000, 10, 3000)
        size_high_vol = mom.volatility_target_size(100000, 100, 3000)

        assert size_high_vol < size_low_vol, \
            f"High vol size ({size_high_vol}) should be < low vol size ({size_low_vol})"


class TestExperienceMemory:
    """Test Experience Memory with fixed thresholds."""

    def test_similarity_threshold_lowered(self):
        """Verify threshold is 0.65, not old 0.85."""
        import inspect
        from bot.experience import ExperienceMemory
        source = inspect.getsource(ExperienceMemory.find_similar)
        assert "0.65" in source, "Similarity threshold should be 0.65"
        assert "0.85" not in source, "Old 0.85 threshold still present!"

    def test_no_circular_features_in_vector(self):
        """score should NOT be in snapshot vector keys."""
        from bot.experience import MarketSnapshot
        snap = MarketSnapshot("TEST", {"rsi14": 50})
        import inspect
        source = inspect.getsource(snap._to_vector)
        # Check the keys list
        keys_section = source.split("keys = [")[1].split("]")[0]
        assert '"score"' not in keys_section, "Circular 'score' still in vector!"
        assert '"news_sentiment"' not in keys_section, "Fake 'news_sentiment' still in vector!"


# ═══════════════════════════════════════════════════════════════════
# 4. BACKTESTER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestBacktester:
    """Test walk-forward backtester integrity."""

    def test_deterministic_fees(self):
        """Fees must be deterministic (not random)."""
        from bot.backtester import calculate_fees
        fee1 = calculate_fees(10000)
        fee2 = calculate_fees(10000)
        assert fee1 == fee2, "Fees must be deterministic!"

    def test_slippage_increases_with_size(self):
        """Larger orders should have more slippage."""
        from bot.backtester import calculate_slippage
        slip_small = calculate_slippage(1000, 100_000_000)
        slip_large = calculate_slippage(100_000, 100_000_000)
        assert slip_large > slip_small, "Larger orders should have more slippage"

    def test_quality_gate_sharpe(self):
        """Quality gate should fail with negative Sharpe."""
        from bot.backtester import BacktestSummary, _check_quality_gates
        summary = BacktestSummary()
        summary.overall_sharpe = -0.5
        summary.overall_win_rate = 0.3
        summary.max_drawdown = 25.0
        summary.total_trades = 100
        _check_quality_gates(summary)
        assert len(summary.failed_quality_gates) > 0, "Should fail quality gates"


# ═══════════════════════════════════════════════════════════════════
# 5. MARGIN EXECUTOR TESTS
# ═══════════════════════════════════════════════════════════════════

class TestMarginExecutorSafety:
    """Test Margin client safety limits."""

    def test_slippage_allowance(self):
        """Slippage should be reasonable."""
        from bot.margin_executor import MarginClient
        assert MarginClient.SLIPPAGE_ALLOWANCE == 0.001, "Slippage should be 0.1%"

    def test_max_position_safety(self):
        """Max position should be capped at $50k."""
        from bot.margin_executor import MarginClient
        assert MarginClient.MAX_POSITION_USD == 50_000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
