"""
Copy-Trading Engine
Allows users to follow and automatically copy trades from top performers
"""

import os
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class TraderStats:
    """Statistics for a trader"""
    user_id: int
    username: str
    total_pnl: float
    win_rate: float
    total_trades: int
    avg_trade_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    followers_count: int
    is_verified: bool
    rank: int
    performance_30d: float  # % return in last 30 days
    created_at: str


@dataclass
class FollowRelation:
    """Follower-Leader relationship"""
    follower_id: int
    leader_id: int
    copy_percentage: float  # What % of leader's position size to copy
    max_position_size: float  # Maximum position size for copies
    created_at: str
    is_active: bool


@dataclass
class CopiedTrade:
    """A trade that was copied from a leader"""
    trade_id: str
    leader_id: int
    follower_id: int
    original_trade_id: str
    symbol: str
    side: str
    entry_price: float
    quantity: float
    timestamp: str
    status: str  # "pending", "executed", "failed"


class CopyTradingEngine:
    """
    Engine for social copy-trading functionality.
    Allows users to follow top performers and automatically
    mirror their trades with configurable parameters.
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir or os.getenv("DATA_DIR", "data/copy_trading"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Data files
        self.follows_file = self.data_dir / "follows.json"
        self.trades_file = self.data_dir / "copied_trades.json"
        self.stats_cache_file = self.data_dir / "stats_cache.json"
        
        # Initialize data
        self._follows: Dict[str, FollowRelation] = {}
        self._copied_trades: List[CopiedTrade] = []
        self._stats_cache: Dict[int, TraderStats] = {}
        
        self._load_data()
    
    def _load_data(self):
        """Load data from disk"""
        if self.follows_file.exists():
            data = json.loads(self.follows_file.read_text())
            self._follows = {
                k: FollowRelation(**v) for k, v in data.items()
            }
        
        if self.trades_file.exists():
            data = json.loads(self.trades_file.read_text())
            self._copied_trades = [CopiedTrade(**t) for t in data]
    
    def _save_data(self):
        """Save data to disk"""
        self.follows_file.write_text(json.dumps(
            {k: asdict(v) for k, v in self._follows.items()}, indent=2
        ))
        
        self.trades_file.write_text(json.dumps(
            [asdict(t) for t in self._copied_trades], indent=2
        ))
    
    # === Leaderboard ===
    
    def get_leaderboard(self, limit: int = 50) -> List[TraderStats]:
        """
        Get the top traders ranked by performance.
        In production: Query from database with actual trade data.
        """
        # For demo: Generate mock leaderboard data
        mock_traders = self._generate_mock_leaderboard(limit)
        return mock_traders
    
    def _generate_mock_leaderboard(self, limit: int) -> List[TraderStats]:
        """Generate mock leaderboard data for demo"""
        import random
        
        traders = []
        for i in range(limit):
            # Higher ranks have better stats
            rank_factor = 1 - (i / limit)
            
            win_rate = 0.45 + (rank_factor * 0.25) + random.uniform(-0.05, 0.05)
            total_pnl = (rank_factor * 50000) + random.uniform(-5000, 5000)
            
            traders.append(TraderStats(
                user_id=1000 + i,
                username=f"Trader_{1000 + i}",
                total_pnl=round(total_pnl, 2),
                win_rate=round(min(0.85, max(0.35, win_rate)), 3),
                total_trades=random.randint(50, 500),
                avg_trade_pnl=round(total_pnl / random.randint(100, 300), 2),
                max_drawdown=round(random.uniform(0.05, 0.25), 3),
                sharpe_ratio=round(1.5 + (rank_factor * 2) + random.uniform(-0.5, 0.5), 2),
                followers_count=int((rank_factor ** 2) * 1000) + random.randint(0, 100),
                is_verified=i < 10,  # Top 10 are verified
                rank=i + 1,
                performance_30d=round((rank_factor * 15) + random.uniform(-5, 5), 2),
                created_at=datetime.now().isoformat()
            ))
        
        return traders
    
    def get_trader_stats(self, user_id: int) -> Optional[TraderStats]:
        """Get stats for a specific trader"""
        leaderboard = self.get_leaderboard(100)
        for trader in leaderboard:
            if trader.user_id == user_id:
                return trader
        return None
    
    # === Following ===
    
    def follow_trader(
        self,
        follower_id: int,
        leader_id: int,
        copy_percentage: float = 1.0,
        max_position_size: float = 1000.0
    ) -> Dict[str, Any]:
        """
        Start following a trader.
        Returns success status and follow details.
        """
        # Validate
        if follower_id == leader_id:
            return {"success": False, "error": "Cannot follow yourself"}
        
        if copy_percentage <= 0 or copy_percentage > 2.0:
            return {"success": False, "error": "Copy percentage must be between 0 and 2.0"}
        
        # Check if already following
        follow_key = f"{follower_id}_{leader_id}"
        if follow_key in self._follows:
            return {"success": False, "error": "Already following this trader"}
        
        # Create follow relation
        follow = FollowRelation(
            follower_id=follower_id,
            leader_id=leader_id,
            copy_percentage=copy_percentage,
            max_position_size=max_position_size,
            created_at=datetime.now().isoformat(),
            is_active=True
        )
        
        self._follows[follow_key] = follow
        self._save_data()
        
        return {
            "success": True,
            "message": f"Now following trader {leader_id}",
            "follow": asdict(follow)
        }
    
    def unfollow_trader(self, follower_id: int, leader_id: int) -> Dict[str, Any]:
        """Stop following a trader"""
        follow_key = f"{follower_id}_{leader_id}"
        
        if follow_key not in self._follows:
            return {"success": False, "error": "Not following this trader"}
        
        del self._follows[follow_key]
        self._save_data()
        
        return {
            "success": True,
            "message": f"Unfollowed trader {leader_id}"
        }
    
    def get_following(self, follower_id: int) -> List[Dict]:
        """Get list of traders the user is following"""
        following = []
        for key, follow in self._follows.items():
            if follow.follower_id == follower_id and follow.is_active:
                leader_stats = self.get_trader_stats(follow.leader_id)
                following.append({
                    **asdict(follow),
                    "leader_stats": asdict(leader_stats) if leader_stats else None
                })
        return following
    
    def get_followers(self, leader_id: int) -> List[FollowRelation]:
        """Get list of users following this trader"""
        return [
            follow for follow in self._follows.values()
            if follow.leader_id == leader_id and follow.is_active
        ]
    
    def update_follow_settings(
        self,
        follower_id: int,
        leader_id: int,
        copy_percentage: Optional[float] = None,
        max_position_size: Optional[float] = None,
        is_active: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update follow settings"""
        follow_key = f"{follower_id}_{leader_id}"
        
        if follow_key not in self._follows:
            return {"success": False, "error": "Not following this trader"}
        
        follow = self._follows[follow_key]
        
        if copy_percentage is not None:
            follow.copy_percentage = copy_percentage
        if max_position_size is not None:
            follow.max_position_size = max_position_size
        if is_active is not None:
            follow.is_active = is_active
        
        self._save_data()
        
        return {
            "success": True,
            "follow": asdict(follow)
        }
    
    # === Trade Copying ===
    
    def mirror_trade(
        self,
        leader_trade: Dict,
        leader_id: int
    ) -> List[CopiedTrade]:
        """
        Mirror a leader's trade to all followers.
        Called when a leader executes a trade.
        """
        copied_trades = []
        followers = self.get_followers(leader_id)
        
        for follow in followers:
            # Calculate position size based on follower settings
            original_qty = leader_trade.get("quantity", 0)
            copied_qty = min(
                original_qty * follow.copy_percentage,
                follow.max_position_size / leader_trade.get("price", 1)
            )
            
            if copied_qty <= 0:
                continue
            
            # Create copied trade record
            import uuid
            copied_trade = CopiedTrade(
                trade_id=str(uuid.uuid4()),
                leader_id=leader_id,
                follower_id=follow.follower_id,
                original_trade_id=leader_trade.get("trade_id", ""),
                symbol=leader_trade.get("symbol", "ETHUSDT"),
                side=leader_trade.get("side", "BUY"),
                entry_price=leader_trade.get("price", 0),
                quantity=round(copied_qty, 6),
                timestamp=datetime.now().isoformat(),
                status="pending"
            )
            
            copied_trades.append(copied_trade)
            self._copied_trades.append(copied_trade)
        
        self._save_data()
        return copied_trades
    
    def get_copied_trades(
        self,
        follower_id: Optional[int] = None,
        leader_id: Optional[int] = None,
        limit: int = 50
    ) -> List[CopiedTrade]:
        """Get copied trades with optional filters"""
        trades = self._copied_trades
        
        if follower_id:
            trades = [t for t in trades if t.follower_id == follower_id]
        if leader_id:
            trades = [t for t in trades if t.leader_id == leader_id]
        
        return sorted(trades, key=lambda t: t.timestamp, reverse=True)[:limit]
    
    def execute_copied_trade(self, trade_id: str, status: str = "executed") -> bool:
        """Update status of a copied trade after execution"""
        for trade in self._copied_trades:
            if trade.trade_id == trade_id:
                trade.status = status
                self._save_data()
                return True
        return False
    
    # === Statistics ===
    
    def get_copy_trading_stats(self, user_id: int) -> Dict:
        """Get copy trading statistics for a user"""
        # As follower
        following = self.get_following(user_id)
        copied = self.get_copied_trades(follower_id=user_id)
        
        # As leader
        followers = self.get_followers(user_id)
        
        return {
            "as_follower": {
                "following_count": len(following),
                "total_copied_trades": len(copied),
                "active_positions": len([c for c in copied if c.status == "executed"])
            },
            "as_leader": {
                "followers_count": len(followers),
                "total_copied_from_me": len([t for t in self._copied_trades if t.leader_id == user_id])
            }
        }


# Singleton instance
_copy_trading_engine: Optional[CopyTradingEngine] = None

def get_copy_trading_engine() -> CopyTradingEngine:
    """Get or create copy trading engine instance"""
    global _copy_trading_engine
    if _copy_trading_engine is None:
        _copy_trading_engine = CopyTradingEngine()
    return _copy_trading_engine


if __name__ == "__main__":
    engine = get_copy_trading_engine()
    
    # Test leaderboard
    print("\n🏆 Top 5 Traders:")
    for trader in engine.get_leaderboard(5):
        print(f"   #{trader.rank} {trader.username}")
        print(f"      Win Rate: {trader.win_rate:.1%}")
        print(f"      Total P&L: ${trader.total_pnl:,.2f}")
        print(f"      Followers: {trader.followers_count}")
    
    # Test following
    print("\n👥 Testing Follow System:")
    result = engine.follow_trader(1, 1001, copy_percentage=0.5)
    print(f"   Follow: {result['success']}")
    
    # Test trade mirroring
    print("\n📋 Testing Trade Mirror:")
    trades = engine.mirror_trade(
        {"trade_id": "test_1", "symbol": "ETHUSDT", "side": "BUY", "price": 3200, "quantity": 0.5},
        leader_id=1001
    )
    print(f"   Created {len(trades)} copied trades")
