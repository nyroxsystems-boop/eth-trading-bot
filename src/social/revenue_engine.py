"""
Copy-Trading Revenue System
Performance fees, commission tracking, and leader earnings
"""

import os
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum
import uuid


class FeeType(str, Enum):
    """Types of fees"""
    PERFORMANCE_FEE = "performance_fee"  # % of profits from copied trades
    SUBSCRIPTION_FEE = "subscription_fee"  # Monthly fee to follow a trader
    PLATFORM_FEE = "platform_fee"  # Platform's cut


@dataclass
class FeeConfig:
    """Fee configuration for the platform"""
    # Performance fee settings
    performance_fee_rate: float = 0.10  # 10% of profits
    min_profit_for_fee: float = 1.0  # Minimum $1 profit to charge fee
    
    # Fee split
    leader_share: float = 0.70  # 70% goes to leader
    platform_share: float = 0.30  # 30% goes to platform
    
    # Tier-based adjustments
    verified_leader_share: float = 0.80  # Verified traders get 80%
    elite_copier_discount: float = 0.20  # 20% discount for Elite tier


@dataclass
class Commission:
    """A commission record"""
    commission_id: str
    trade_id: str
    leader_id: int
    follower_id: int
    
    # Trade details
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    trade_pnl: float  # Profit/loss of the copied trade
    
    # Fee calculation
    gross_fee: float  # Total fee amount
    leader_amount: float  # Amount going to leader
    platform_amount: float  # Amount going to platform
    fee_rate: float  # Rate applied
    
    # Status
    status: str  # "pending", "paid", "cancelled"
    created_at: str
    paid_at: Optional[str] = None


@dataclass
class LeaderEarnings:
    """Earnings summary for a leader"""
    leader_id: int
    total_earned: float = 0.0
    pending_earnings: float = 0.0
    paid_earnings: float = 0.0
    total_copied_trades: int = 0
    profitable_trades: int = 0
    total_profit_generated: float = 0.0
    last_updated: str = ""


@dataclass
class FollowerSpending:
    """Spending summary for a follower"""
    follower_id: int
    total_fees_paid: float = 0.0
    total_profit_from_copying: float = 0.0
    net_result: float = 0.0  # profit - fees
    total_copied_trades: int = 0


class RevenueEngine:
    """
    Handles all revenue-related functionality for copy-trading:
    - Performance fee calculation
    - Commission tracking
    - Leader earnings
    - Platform revenue
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir or os.getenv("DATA_DIR", "data/copy_trading"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Data files
        self.commissions_file = self.data_dir / "commissions.json"
        self.earnings_file = self.data_dir / "leader_earnings.json"
        self.spending_file = self.data_dir / "follower_spending.json"
        
        # Configuration
        self.fee_config = FeeConfig()
        
        # Data stores
        self._commissions: List[Commission] = []
        self._leader_earnings: Dict[int, LeaderEarnings] = {}
        self._follower_spending: Dict[int, FollowerSpending] = {}
        
        self._load_data()
    
    def _load_data(self):
        """Load data from disk"""
        if self.commissions_file.exists():
            data = json.loads(self.commissions_file.read_text())
            self._commissions = [Commission(**c) for c in data]
        
        if self.earnings_file.exists():
            data = json.loads(self.earnings_file.read_text())
            self._leader_earnings = {
                int(k): LeaderEarnings(**v) for k, v in data.items()
            }
        
        if self.spending_file.exists():
            data = json.loads(self.spending_file.read_text())
            self._follower_spending = {
                int(k): FollowerSpending(**v) for k, v in data.items()
            }
    
    def _save_data(self):
        """Save data to disk"""
        self.commissions_file.write_text(json.dumps(
            [asdict(c) for c in self._commissions], indent=2
        ))
        
        self.earnings_file.write_text(json.dumps(
            {str(k): asdict(v) for k, v in self._leader_earnings.items()}, indent=2
        ))
        
        self.spending_file.write_text(json.dumps(
            {str(k): asdict(v) for k, v in self._follower_spending.items()}, indent=2
        ))
    
    # === Fee Calculation ===
    
    def calculate_performance_fee(
        self,
        trade_pnl: float,
        leader_id: int,
        follower_id: int,
        is_verified_leader: bool = False,
        follower_tier: str = "free"
    ) -> Dict[str, float]:
        """
        Calculate the performance fee for a closed copied trade.
        Only charges fees on profitable trades.
        """
        # No fee if trade was not profitable
        if trade_pnl <= self.fee_config.min_profit_for_fee:
            return {
                "gross_fee": 0.0,
                "leader_amount": 0.0,
                "platform_amount": 0.0,
                "fee_rate": 0.0,
                "reason": "no_profit" if trade_pnl <= 0 else "below_minimum"
            }
        
        # Calculate base fee
        fee_rate = self.fee_config.performance_fee_rate
        
        # Apply tier discount for Elite followers
        if follower_tier == "elite":
            fee_rate *= (1 - self.fee_config.elite_copier_discount)
        
        gross_fee = trade_pnl * fee_rate
        
        # Split between leader and platform
        leader_share = self.fee_config.verified_leader_share if is_verified_leader else self.fee_config.leader_share
        
        leader_amount = gross_fee * leader_share
        platform_amount = gross_fee * (1 - leader_share)
        
        return {
            "gross_fee": round(gross_fee, 4),
            "leader_amount": round(leader_amount, 4),
            "platform_amount": round(platform_amount, 4),
            "fee_rate": round(fee_rate, 4),
            "leader_share": leader_share
        }
    
    def record_commission(
        self,
        trade_id: str,
        leader_id: int,
        follower_id: int,
        symbol: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        is_verified_leader: bool = False,
        follower_tier: str = "free"
    ) -> Commission:
        """
        Record a commission when a copied trade is closed.
        Automatically calculates and splits the fee.
        """
        # Calculate PnL
        trade_pnl = (exit_price - entry_price) * quantity
        
        # Calculate fees
        fee_info = self.calculate_performance_fee(
            trade_pnl=trade_pnl,
            leader_id=leader_id,
            follower_id=follower_id,
            is_verified_leader=is_verified_leader,
            follower_tier=follower_tier
        )
        
        # Create commission record
        commission = Commission(
            commission_id=str(uuid.uuid4()),
            trade_id=trade_id,
            leader_id=leader_id,
            follower_id=follower_id,
            symbol=symbol,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            trade_pnl=round(trade_pnl, 4),
            gross_fee=fee_info["gross_fee"],
            leader_amount=fee_info["leader_amount"],
            platform_amount=fee_info["platform_amount"],
            fee_rate=fee_info["fee_rate"],
            status="pending" if fee_info["gross_fee"] > 0 else "no_fee",
            created_at=datetime.now().isoformat()
        )
        
        self._commissions.append(commission)
        
        # Update leader earnings
        self._update_leader_earnings(leader_id, commission)
        
        # Update follower spending
        self._update_follower_spending(follower_id, commission)
        
        self._save_data()
        return commission
    
    def _update_leader_earnings(self, leader_id: int, commission: Commission):
        """Update leader's earnings after a commission"""
        if leader_id not in self._leader_earnings:
            self._leader_earnings[leader_id] = LeaderEarnings(
                leader_id=leader_id,
                last_updated=datetime.now().isoformat()
            )
        
        earnings = self._leader_earnings[leader_id]
        earnings.total_copied_trades += 1
        
        if commission.trade_pnl > 0:
            earnings.profitable_trades += 1
            earnings.total_profit_generated += commission.trade_pnl
        
        if commission.status == "pending":
            earnings.pending_earnings += commission.leader_amount
            earnings.total_earned += commission.leader_amount
        
        earnings.last_updated = datetime.now().isoformat()
    
    def _update_follower_spending(self, follower_id: int, commission: Commission):
        """Update follower's spending after a commission"""
        if follower_id not in self._follower_spending:
            self._follower_spending[follower_id] = FollowerSpending(
                follower_id=follower_id
            )
        
        spending = self._follower_spending[follower_id]
        spending.total_copied_trades += 1
        spending.total_profit_from_copying += commission.trade_pnl
        spending.total_fees_paid += commission.gross_fee
        spending.net_result = spending.total_profit_from_copying - spending.total_fees_paid
    
    # === Payouts ===
    
    def mark_commission_paid(self, commission_id: str) -> bool:
        """Mark a commission as paid"""
        for commission in self._commissions:
            if commission.commission_id == commission_id:
                if commission.status == "pending":
                    commission.status = "paid"
                    commission.paid_at = datetime.now().isoformat()
                    
                    # Update leader earnings
                    if commission.leader_id in self._leader_earnings:
                        earnings = self._leader_earnings[commission.leader_id]
                        earnings.pending_earnings -= commission.leader_amount
                        earnings.paid_earnings += commission.leader_amount
                    
                    self._save_data()
                    return True
        return False
    
    def get_pending_payouts(self, min_amount: float = 10.0) -> Dict[int, float]:
        """
        Get leaders with pending earnings above threshold.
        Returns dict of {leader_id: pending_amount}
        """
        pending = {}
        for leader_id, earnings in self._leader_earnings.items():
            if earnings.pending_earnings >= min_amount:
                pending[leader_id] = round(earnings.pending_earnings, 2)
        return pending
    
    def process_payout(self, leader_id: int) -> Dict[str, Any]:
        """
        Process payout for a leader.
        Marks all pending commissions as paid.
        """
        if leader_id not in self._leader_earnings:
            return {"success": False, "error": "Leader not found"}
        
        earnings = self._leader_earnings[leader_id]
        payout_amount = earnings.pending_earnings
        
        if payout_amount <= 0:
            return {"success": False, "error": "No pending earnings"}
        
        # Mark all pending commissions for this leader as paid
        paid_count = 0
        for commission in self._commissions:
            if commission.leader_id == leader_id and commission.status == "pending":
                commission.status = "paid"
                commission.paid_at = datetime.now().isoformat()
                paid_count += 1
        
        # Update earnings
        earnings.paid_earnings += payout_amount
        earnings.pending_earnings = 0
        
        self._save_data()
        
        return {
            "success": True,
            "payout_amount": round(payout_amount, 2),
            "commissions_paid": paid_count,
            "leader_id": leader_id
        }
    
    # === Reporting ===
    
    def get_leader_earnings(self, leader_id: int) -> Dict[str, Any]:
        """Get earnings summary for a leader"""
        if leader_id not in self._leader_earnings:
            return {
                "leader_id": leader_id,
                "total_earned": 0,
                "pending_earnings": 0,
                "paid_earnings": 0,
                "total_copied_trades": 0,
                "profitable_trades": 0,
                "win_rate": 0,
                "total_profit_generated": 0
            }
        
        earnings = self._leader_earnings[leader_id]
        win_rate = (earnings.profitable_trades / earnings.total_copied_trades * 100) if earnings.total_copied_trades > 0 else 0
        
        return {
            **asdict(earnings),
            "win_rate": round(win_rate, 1)
        }
    
    def get_follower_spending(self, follower_id: int) -> Dict[str, Any]:
        """Get spending summary for a follower"""
        if follower_id not in self._follower_spending:
            return {
                "follower_id": follower_id,
                "total_fees_paid": 0,
                "total_profit_from_copying": 0,
                "net_result": 0,
                "total_copied_trades": 0,
                "roi": 0
            }
        
        spending = self._follower_spending[follower_id]
        roi = ((spending.net_result / spending.total_fees_paid) * 100) if spending.total_fees_paid > 0 else 0
        
        return {
            **asdict(spending),
            "roi": round(roi, 1)
        }
    
    def get_platform_revenue(self, days: int = 30) -> Dict[str, Any]:
        """Get platform revenue summary"""
        cutoff = datetime.now() - timedelta(days=days)
        
        total_revenue = 0
        total_trades = 0
        
        for commission in self._commissions:
            created = datetime.fromisoformat(commission.created_at)
            if created >= cutoff:
                total_revenue += commission.platform_amount
                total_trades += 1
        
        # All-time stats
        all_time_revenue = sum(c.platform_amount for c in self._commissions)
        all_time_leader_payouts = sum(c.leader_amount for c in self._commissions)
        
        return {
            "period_days": days,
            "period_revenue": round(total_revenue, 2),
            "period_trades": total_trades,
            "all_time_revenue": round(all_time_revenue, 2),
            "all_time_leader_payouts": round(all_time_leader_payouts, 2),
            "total_commissions": len(self._commissions),
            "active_leaders": len(self._leader_earnings),
            "active_copiers": len(self._follower_spending)
        }
    
    def get_recent_commissions(self, limit: int = 50) -> List[Dict]:
        """Get recent commissions"""
        sorted_commissions = sorted(
            self._commissions, 
            key=lambda c: c.created_at, 
            reverse=True
        )[:limit]
        
        return [asdict(c) for c in sorted_commissions]
    
    def get_commissions(
        self, 
        user_id: int, 
        as_leader: bool = True, 
        limit: int = 50
    ) -> List[Dict]:
        """Get commissions for a user, either as leader or follower"""
        filtered = []
        
        for commission in self._commissions:
            if as_leader and commission.leader_id == user_id:
                filtered.append(commission)
            elif not as_leader and commission.follower_id == user_id:
                filtered.append(commission)
        
        # Sort by date, most recent first
        filtered = sorted(filtered, key=lambda c: c.created_at, reverse=True)[:limit]
        
        return [asdict(c) for c in filtered]


# Singleton instance
_revenue_engine: Optional[RevenueEngine] = None

def get_revenue_engine() -> RevenueEngine:
    """Get or create revenue engine instance"""
    global _revenue_engine
    if _revenue_engine is None:
        _revenue_engine = RevenueEngine()
    return _revenue_engine


if __name__ == "__main__":
    engine = get_revenue_engine()
    
    # Test fee calculation
    print("\n💰 Fee Calculation Test:")
    fee = engine.calculate_performance_fee(
        trade_pnl=100.0,
        leader_id=1001,
        follower_id=1,
        is_verified_leader=True,
        follower_tier="pro"
    )
    print(f"   Trade Profit: $100")
    print(f"   Gross Fee: ${fee['gross_fee']}")
    print(f"   Leader Gets: ${fee['leader_amount']}")
    print(f"   Platform Gets: ${fee['platform_amount']}")
    
    # Test commission recording
    print("\n📊 Commission Recording Test:")
    commission = engine.record_commission(
        trade_id="test_trade_1",
        leader_id=1001,
        follower_id=1,
        symbol="ETHUSDT",
        entry_price=3200.0,
        exit_price=3280.0,
        quantity=0.5,
        is_verified_leader=True
    )
    print(f"   Commission ID: {commission.commission_id[:8]}...")
    print(f"   Trade P&L: ${commission.trade_pnl}")
    print(f"   Fee Collected: ${commission.gross_fee}")
    
    # Test platform revenue
    print("\n📈 Platform Revenue:")
    revenue = engine.get_platform_revenue()
    print(f"   30-Day Revenue: ${revenue['period_revenue']}")
    print(f"   All-Time Revenue: ${revenue['all_time_revenue']}")
