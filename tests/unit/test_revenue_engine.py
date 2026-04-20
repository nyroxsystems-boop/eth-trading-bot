"""
Unit tests for Revenue Engine (copy trading performance fees)
"""
import pytest
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def fresh_engine():
    """Create a fresh engine with isolated temp directory"""
    from src.social.revenue_engine import RevenueEngine
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    engine = RevenueEngine(data_dir=temp_dir)
    
    yield engine
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestFeeCalculation:
    """Test performance fee calculations"""
    
    def test_fee_on_profitable_trade(self, fresh_engine):
        """Test fee is charged only on profitable trades"""
        engine = fresh_engine
        
        # Profitable trade: $100 profit
        result = engine.calculate_performance_fee(
            trade_pnl=100.0,
            leader_id=1,
            follower_id=2
        )
        
        # 10% fee = $10
        assert result["gross_fee"] == 10.0
        assert result["leader_amount"] == 7.0  # 70% of $10
        assert result["platform_amount"] == 3.0  # 30% of $10
    
    def test_no_fee_on_loss(self, fresh_engine):
        """Test no fee charged on losing trades"""
        engine = fresh_engine
        
        # Losing trade
        result = engine.calculate_performance_fee(
            trade_pnl=-50.0,
            leader_id=1,
            follower_id=2
        )
        
        assert result["gross_fee"] == 0.0
        assert result["leader_amount"] == 0.0
        assert result["platform_amount"] == 0.0
        assert result["reason"] == "no_profit"
    
    def test_no_fee_below_minimum(self, fresh_engine):
        """Test no fee when profit below minimum threshold"""
        engine = fresh_engine
        
        # Tiny profit below $1 minimum
        result = engine.calculate_performance_fee(
            trade_pnl=0.50,
            leader_id=1,
            follower_id=2
        )
        
        assert result["gross_fee"] == 0.0
        assert result["reason"] == "below_minimum"
    
    def test_verified_leader_higher_share(self, fresh_engine):
        """Test verified leaders get 80% instead of 70%"""
        engine = fresh_engine
        
        result = engine.calculate_performance_fee(
            trade_pnl=100.0,
            leader_id=1,
            follower_id=2,
            is_verified_leader=True
        )
        
        # Verified: 80% to leader
        assert result["leader_amount"] == 8.0
        assert result["platform_amount"] == 2.0
    
    def test_elite_copier_discount(self, fresh_engine):
        """Test elite copiers get 20% fee discount"""
        engine = fresh_engine
        
        result = engine.calculate_performance_fee(
            trade_pnl=100.0,
            leader_id=1,
            follower_id=2,
            follower_tier="elite"
        )
        
        # 20% discount: 10% * 0.8 = 8% fee = $8
        assert result["gross_fee"] == 8.0


class TestCommissionRecording:
    """Test commission recording and tracking"""
    
    def test_record_commission_creates_entry(self, fresh_engine):
        """Test recording a commission creates proper entry"""
        engine = fresh_engine
        
        commission = engine.record_commission(
            trade_id="trade_001",
            leader_id=1,
            follower_id=2,
            symbol="ETHUSDT",
            entry_price=3000.0,
            exit_price=3100.0,
            quantity=1.0
        )
        
        # $100 profit, 10% fee = $10
        assert commission.trade_pnl == 100.0
        assert commission.gross_fee == 10.0
        assert commission.leader_amount == 7.0
        assert commission.platform_amount == 3.0
        assert commission.status == "pending"
    
    def test_record_commission_losing_trade(self, fresh_engine):
        """Test recording losing trade has no fee"""
        engine = fresh_engine
        
        commission = engine.record_commission(
            trade_id="trade_002",
            leader_id=1,
            follower_id=2,
            symbol="ETHUSDT",
            entry_price=3100.0,
            exit_price=3000.0,
            quantity=1.0
        )
        
        assert commission.trade_pnl == -100.0
        assert commission.gross_fee == 0.0
        assert commission.status == "no_fee"


class TestLeaderEarnings:
    """Test leader earnings aggregation"""
    
    def test_leader_earnings_accumulate(self, fresh_engine):
        """Test earnings accumulate across multiple trades"""
        engine = fresh_engine
        
        # Record two profitable trades
        engine.record_commission(
            trade_id="trade_001",
            leader_id=1,
            follower_id=2,
            symbol="ETHUSDT",
            entry_price=3000.0,
            exit_price=3100.0,  # $100 profit
            quantity=1.0
        )
        
        engine.record_commission(
            trade_id="trade_002",
            leader_id=1,
            follower_id=3,
            symbol="ETHUSDT",
            entry_price=3000.0,
            exit_price=3200.0,  # $200 profit
            quantity=1.0
        )
        
        earnings = engine.get_leader_earnings(1)
        
        # $100 + $200 profit, 10% fee, 70% to leader
        # = $10 * 0.7 + $20 * 0.7 = $7 + $14 = $21
        assert earnings["total_earned"] == 21.0
        assert earnings["pending_earnings"] == 21.0
        assert earnings["total_copied_trades"] == 2
    
    def test_leader_not_found_returns_default(self, fresh_engine):
        """Test querying unknown leader returns default values"""
        engine = fresh_engine
        earnings = engine.get_leader_earnings(999)
        
        assert earnings["total_earned"] == 0
        assert earnings["pending_earnings"] == 0


class TestFollowerSpending:
    """Test follower spending tracking"""
    
    def test_follower_spending_tracked(self, fresh_engine):
        """Test follower spending is properly tracked"""
        engine = fresh_engine
        
        # Follower copies a trade
        engine.record_commission(
            trade_id="trade_001",
            leader_id=1,
            follower_id=2,
            symbol="ETHUSDT",
            entry_price=3000.0,
            exit_price=3100.0,  # $100 profit
            quantity=1.0
        )
        
        spending = engine.get_follower_spending(2)
        
        # $10 fee for $100 profit
        assert spending["total_fees_paid"] == 10.0
        assert spending["net_result"] == 90.0  # $100 - $10


class TestPayoutProcessing:
    """Test leader payout processing"""
    
    def test_payout_clears_pending(self, fresh_engine):
        """Test payout clears pending earnings"""
        engine = fresh_engine
        
        # Record profitable trade
        engine.record_commission(
            trade_id="trade_001",
            leader_id=1,
            follower_id=2,
            symbol="ETHUSDT",
            entry_price=3000.0,
            exit_price=3100.0,
            quantity=1.0
        )
        
        # Process payout
        result = engine.process_payout(1)
        
        assert result["success"] is True
        assert result["payout_amount"] == 7.0  # 70% of $10 fee
        
        # Check pending is now 0
        earnings = engine.get_leader_earnings(1)
        assert earnings["pending_earnings"] == 0
        assert earnings["paid_earnings"] == 7.0
    
    def test_payout_fails_with_no_earnings(self, fresh_engine):
        """Test payout fails when no pending earnings"""
        engine = fresh_engine
        
        result = engine.process_payout(999)
        
        assert result["success"] is False


class TestPlatformRevenue:
    """Test platform revenue reporting"""
    
    def test_platform_revenue_calculated(self, fresh_engine):
        """Test platform revenue is properly calculated"""
        engine = fresh_engine
        
        # Record some trades
        for i in range(5):
            engine.record_commission(
                trade_id=f"trade_{i}",
                leader_id=1,
                follower_id=2,
                symbol="ETHUSDT",
                entry_price=3000.0,
                exit_price=3100.0,  # $100 profit each
                quantity=1.0
            )
        
        stats = engine.get_platform_revenue(days=30)
        
        # 5 trades * $10 fee * 30% platform = $15
        assert stats["all_time_revenue"] == 15.0
        assert stats["total_commissions"] == 5
        assert stats["active_leaders"] == 1


class TestCommissionHistory:
    """Test commission history retrieval"""
    
    def test_get_user_commissions(self, fresh_engine):
        """Test retrieving user's commission history"""
        engine = fresh_engine
        
        # Record trades for different users
        engine.record_commission(
            trade_id="trade_001",
            leader_id=1,
            follower_id=2,
            symbol="ETHUSDT",
            entry_price=3000.0,
            exit_price=3100.0,
            quantity=1.0
        )
        
        engine.record_commission(
            trade_id="trade_002",
            leader_id=3,
            follower_id=4,
            symbol="BTCUSDT",
            entry_price=50000.0,
            exit_price=51000.0,
            quantity=1.0
        )
        
        # Get commissions for leader 1
        leader_commissions = engine.get_commissions(user_id=1, as_leader=True)
        assert len(leader_commissions) == 1
        assert leader_commissions[0]["trade_id"] == "trade_001"
        
        # Get commissions for follower 2
        follower_commissions = engine.get_commissions(user_id=2, as_leader=False)
        assert len(follower_commissions) == 1
        assert follower_commissions[0]["trade_id"] == "trade_001"
