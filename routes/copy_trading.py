"""
Copy Trading & Revenue API Router
Extracted from dashboard_api.py — handles:
- /api/copy-trading/* (leaderboard, follow, unfollow, following, stats)
- /api/revenue/* (leader earnings, follower spending, commissions, payouts)
"""

from fastapi import APIRouter, Depends
from typing import Dict, Optional

from auth_deps import get_current_user, get_current_user_optional

router = APIRouter(tags=["copy-trading"])


def _get_copy_engine():
    """Lazy import copy trading engine."""
    from src.social.copy_trading import get_copy_trading_engine
    return get_copy_trading_engine()


def _get_revenue_engine():
    """Lazy import revenue engine."""
    from src.social.revenue_engine import get_revenue_engine
    return get_revenue_engine()


# ═══════════════════════════════════════════
# Copy Trading
# ═══════════════════════════════════════════

@router.get("/api/copy-trading/leaderboard")
async def get_leaderboard(limit: int = 50):
    """Get top traders leaderboard"""
    try:
        from dataclasses import asdict
        engine = _get_copy_engine()
        traders = engine.get_leaderboard(limit)
        return {"status": "success", "traders": [asdict(t) for t in traders], "total": len(traders)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/copy-trading/follow")
async def follow_trader(data: dict, current_user: Dict = Depends(get_current_user)):
    """Follow a trader to copy their trades"""
    try:
        engine = _get_copy_engine()
        result = engine.follow_trader(
            follower_id=current_user["id"],
            leader_id=data.get("leader_id"),
            copy_percentage=data.get("copy_percentage", 1.0),
            max_position_size=data.get("max_position_size", 1000.0)
        )
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/copy-trading/unfollow")
async def unfollow_trader(data: dict, current_user: Dict = Depends(get_current_user)):
    """Stop following a trader"""
    try:
        engine = _get_copy_engine()
        result = engine.unfollow_trader(
            follower_id=current_user["id"],
            leader_id=data.get("leader_id")
        )
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/copy-trading/following")
async def get_following(current_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get list of traders the user is following"""
    if not current_user:
        return {"status": "success", "following": []}
    try:
        engine = _get_copy_engine()
        following = engine.get_following(current_user["id"])
        return {"status": "success", "following": following}
    except Exception as e:
        return {"status": "success", "following": []}


@router.get("/api/copy-trading/stats")
async def get_copy_trading_stats(current_user: Dict = Depends(get_current_user)):
    """Get copy trading statistics for the user"""
    try:
        engine = _get_copy_engine()
        stats = engine.get_copy_trading_stats(current_user["id"])
        return {"status": "success", **stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════
# Revenue
# ═══════════════════════════════════════════

@router.get("/api/revenue/leader-earnings")
async def get_leader_earnings(current_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get earnings for the current user as a leader"""
    demo_earnings = {
        "leader_id": 0, "total_earned": 1250.50, "pending_earnings": 340.25,
        "paid_earnings": 910.25, "total_copied_trades": 156, "profitable_trades": 98,
        "total_profit_generated": 12500.00, "win_rate": 62.8
    }
    if not current_user:
        return {"status": "success", "earnings": demo_earnings}
    try:
        engine = _get_revenue_engine()
        earnings = engine.get_leader_earnings(current_user["id"])
        return {"status": "success", "earnings": earnings}
    except Exception as e:
        return {"status": "success", "earnings": demo_earnings}


@router.get("/api/revenue/follower-spending")
async def get_follower_spending(current_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get spending summary for the current user as a copier"""
    demo_spending = {
        "follower_id": 0, "total_fees_paid": 125.00, "total_profit_from_copying": 1250.00,
        "net_result": 1125.00, "total_copied_trades": 45, "roi": 900
    }
    if not current_user:
        return {"status": "success", "spending": demo_spending}
    try:
        engine = _get_revenue_engine()
        spending = engine.get_follower_spending(current_user["id"])
        return {"status": "success", "spending": spending}
    except Exception as e:
        return {"status": "success", "spending": demo_spending}


@router.post("/api/revenue/record-commission")
async def record_trade_commission(data: dict, current_user: Dict = Depends(get_current_user)):
    """Record a commission when a copied trade is closed"""
    try:
        from dataclasses import asdict
        engine = _get_revenue_engine()
        commission = engine.record_commission(
            trade_id=data.get("trade_id"),
            leader_id=data.get("leader_id"),
            follower_id=current_user["id"],
            symbol=data.get("symbol", "ETHUSDT"),
            entry_price=data.get("entry_price", 0),
            exit_price=data.get("exit_price", 0),
            quantity=data.get("quantity", 0),
            is_verified_leader=data.get("is_verified", False),
            follower_tier=data.get("tier", "free")
        )
        return {"status": "success", "commission": asdict(commission)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/revenue/commissions")
async def get_recent_commissions(current_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get recent commissions for the user"""
    if not current_user:
        return {"status": "success", "commissions": []}
    try:
        engine = _get_revenue_engine()
        commissions = engine.get_recent_commissions(limit=50)
        user_commissions = [
            c for c in commissions
            if c["leader_id"] == current_user["id"] or c["follower_id"] == current_user["id"]
        ]
        return {"status": "success", "commissions": user_commissions}
    except Exception as e:
        return {"status": "success", "commissions": []}


@router.get("/api/revenue/platform-stats")
async def get_platform_revenue_stats(current_user: Dict = Depends(get_current_user)):
    """Get platform revenue statistics (admin only)"""
    try:
        if current_user.get("role") != "admin":
            return {"status": "error", "message": "Admin access required"}
        engine = _get_revenue_engine()
        stats = engine.get_platform_revenue(days=30)
        return {"status": "success", "revenue": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/revenue/request-payout")
async def request_leader_payout(current_user: Dict = Depends(get_current_user)):
    """Request payout of pending earnings"""
    try:
        engine = _get_revenue_engine()
        result = engine.process_payout(current_user["id"])
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}
