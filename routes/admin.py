"""
Admin Dashboard API Router
Extracted from dashboard_api.py — handles all /api/admin/* endpoints.

Endpoints:
- Strategy cleanup
- User management (list, get, toggle, subscription, delete)
- Revenue dashboard (Stripe)
- Platform analytics
- Emergency stop/resume
- System health
- Jarvis monitoring (status, workers, alerts, anomalies, manual check)
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from datetime import datetime
from pathlib import Path
import os

from auth_deps import get_current_user, get_current_admin
from db_adapter import get_db_connection, USE_POSTGRES
from user_manager import UserManager

import learning_store

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Shared state — injected from dashboard_api on startup
EMERGENCY_TRADING_STOPPED = False


def _get_user_mgr() -> UserManager:
    from auth_deps import get_user_manager
    return get_user_manager()


# ═══════════════════════════════════════════
# Strategy Cleanup
# ═══════════════════════════════════════════

@router.post("/strategies/cleanup")
async def admin_cleanup_strategies(current_user: Dict = Depends(get_current_user)):
    """Delete fake/simulated strategies, keep only real Binance-data ones"""
    try:
        if not USE_POSTGRES:
            return {"status": "error", "message": "No PostgreSQL connection"}

        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM learning_strategies")
            total_before = cursor.fetchone()[0]

            cursor.execute("SELECT data_source, COUNT(*) FROM learning_strategies GROUP BY data_source")
            breakdown = {(row[0] or "NULL"): row[1] for row in cursor.fetchall()}

            cursor.execute("""
                DELETE FROM learning_strategies 
                WHERE data_source = 'simulated' 
                   OR data_source IS NULL 
                   OR data_source = ''
            """)
            deleted = cursor.rowcount

            cursor.execute("SELECT COUNT(*) FROM learning_strategies")
            total_after = cursor.fetchone()[0]

            try:
                cursor.execute("""
                    UPDATE kv_store SET value = %s 
                    WHERE key = 'total_strategies_tested'
                """, (str(total_after),))
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO kv_store (key, value) VALUES ('total_strategies_tested', %s)
                    """, (str(total_after),))
                cursor.execute("""
                    DELETE FROM kv_store WHERE key LIKE 'daily_tested_%'
                """)
            except Exception as e:
                print(f"⚠️ kv_store reset error: {e}")

            return {
                "status": "success",
                "deleted": deleted,
                "before": total_before,
                "after": total_after,
                "counter_reset_to": total_after,
                "breakdown_before": breakdown
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════
# User Management
# ═══════════════════════════════════════════

@router.get("/users")
async def admin_list_users(current_user: Dict = Depends(get_current_admin)):
    """List all users with trading stats"""
    user_mgr = _get_user_mgr()
    try:
        users = user_mgr.list_users()
        enriched_users = []

        for user in users:
            has_keys = user_mgr.has_api_keys(user['id'])
            enriched_users.append({
                **user,
                'has_api_keys': has_keys,
                'trading_enabled': has_keys,
                'created_at': str(user.get('created_at', '')),
                'last_login': str(user.get('last_login', '')) if user.get('last_login') else None
            })

        return {"status": "success", "total_users": len(users), "users": enriched_users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}")
async def admin_get_user(user_id: int, current_user: Dict = Depends(get_current_admin)):
    """Get detailed user info"""
    user_mgr = _get_user_mgr()
    user = user_mgr.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    api_keys = user_mgr.get_api_keys(user_id, decrypt=False) or {}
    return {
        "status": "success",
        "user": {**user, 'has_binance_keys': api_keys.get('has_binance_keys', False),
                 'has_telegram': api_keys.get('has_telegram', False),
                 'trading_enabled': api_keys.get('trading_enabled', False)}
    }


@router.post("/users/{user_id}/toggle")
async def admin_toggle_user(user_id: int, current_user: Dict = Depends(get_current_admin)):
    """Enable/disable a user account"""
    user_mgr = _get_user_mgr()
    user = user_mgr.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_status = not user.get('active', True)
    user_mgr.update_user(user_id, active=new_status)
    return {"status": "success", "active": new_status}


@router.post("/users/{user_id}/subscription")
async def admin_update_subscription(user_id: int, tier: str, current_user: Dict = Depends(get_current_admin)):
    """Update user subscription tier"""
    if tier not in ['free', 'basic', 'pro', 'enterprise']:
        raise HTTPException(status_code=400, detail="Invalid tier")
    user_mgr = _get_user_mgr()
    user_mgr.update_user(user_id, subscription_tier=tier)
    return {"status": "success", "tier": tier}


@router.delete("/users/{user_id}")
async def admin_delete_user(user_id: int, current_user: Dict = Depends(get_current_admin)):
    """Delete a user account"""
    user_mgr = _get_user_mgr()
    if user_id == current_user.get('id'):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    if not user_mgr.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "success"}


# ═══════════════════════════════════════════
# Revenue Dashboard
# ═══════════════════════════════════════════

@router.get("/revenue")
async def admin_get_revenue(current_user: Dict = Depends(get_current_admin)):
    """Get revenue overview from Stripe"""
    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        if not stripe.api_key:
            return {"status": "warning", "message": "Stripe not configured", "mrr": 0, "active_subscriptions": 0}
        subs = stripe.Subscription.list(status='active', limit=100)
        mrr = sum(item['price']['unit_amount']/100 for sub in subs.data for item in sub['items']['data'])
        return {"status": "success", "mrr": mrr, "active_subscriptions": len(subs.data)}
    except Exception as e:
        return {"status": "error", "message": str(e), "mrr": 0}


# ═══════════════════════════════════════════
# Platform Analytics
# ═══════════════════════════════════════════

@router.get("/analytics")
async def admin_get_analytics(current_user: Dict = Depends(get_current_admin)):
    """Get platform-wide analytics"""
    user_mgr = _get_user_mgr()
    users = user_mgr.list_users()
    return {
        "status": "success",
        "total_users": len(users),
        "active_users": len([u for u in users if u.get('active', True)]),
        "users_with_api_keys": len([u for u in users if user_mgr.has_api_keys(u['id'])]),
        "subscription_breakdown": {}
    }


# ═══════════════════════════════════════════
# Emergency Controls
# ═══════════════════════════════════════════

@router.get("/emergency/status")
async def admin_emergency_status(current_user: Dict = Depends(get_current_admin)):
    global EMERGENCY_TRADING_STOPPED
    flag_file = Path(os.getenv("LOG_DIR", "./logs")) / "EMERGENCY_STOP"
    if flag_file.exists():
        EMERGENCY_TRADING_STOPPED = True
    return {"trading_stopped": EMERGENCY_TRADING_STOPPED}


@router.post("/emergency/stop-all")
async def admin_emergency_stop(current_user: Dict = Depends(get_current_admin)):
    global EMERGENCY_TRADING_STOPPED
    EMERGENCY_TRADING_STOPPED = True

    try:
        flag_file = Path(os.getenv("LOG_DIR", "./logs")) / "EMERGENCY_STOP"
        flag_file.parent.mkdir(parents=True, exist_ok=True)
        flag_file.write_text(f"STOPPED by {current_user.get('username')} at {datetime.now().isoformat()}")
    except Exception as e:
        print(f"⚠️ Flag file write failed: {e}")

    try:
        learning_store.set_kv("emergency_trading_stopped", "true")
    except Exception as e:
        print(f"⚠️ KV store write failed: {e}")

    try:
        import requests
        token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if token and chat:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": f"🚨 EMERGENCY STOP by {current_user.get('username')}"})
    except: pass
    return {"status": "success", "trading_stopped": True}


@router.post("/emergency/resume")
async def admin_emergency_resume(current_user: Dict = Depends(get_current_admin)):
    global EMERGENCY_TRADING_STOPPED
    EMERGENCY_TRADING_STOPPED = False

    try:
        flag_file = Path(os.getenv("LOG_DIR", "./logs")) / "EMERGENCY_STOP"
        if flag_file.exists():
            flag_file.unlink()
    except Exception as e:
        print(f"⚠️ Flag file remove failed: {e}")

    try:
        learning_store.set_kv("emergency_trading_stopped", "false")
    except Exception as e:
        print(f"⚠️ KV store clear failed: {e}")

    try:
        import requests
        token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if token and chat:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": f"✅ Trading RESUMED by {current_user.get('username')}"})
    except: pass
    return {"status": "success", "trading_stopped": False}


# ═══════════════════════════════════════════
# System Health
# ═══════════════════════════════════════════

@router.get("/system/health")
async def admin_system_health(current_user: Dict = Depends(get_current_admin)):
    health = {"status": "success", "timestamp": datetime.now().isoformat(), "services": {}}
    try:
        with get_db_connection() as conn:
            conn.cursor().execute("SELECT 1")
        health["services"]["database"] = {"status": "healthy", "type": "PostgreSQL" if USE_POSTGRES else "SQLite"}
    except Exception as e:
        health["services"]["database"] = {"status": "unhealthy", "error": str(e)}
    health["services"]["api"] = {"status": "healthy"}
    health["emergency_stop_active"] = EMERGENCY_TRADING_STOPPED
    return health


# ═══════════════════════════════════════════
# Jarvis Monitoring System
# ═══════════════════════════════════════════

@router.get("/jarvis/status")
async def get_jarvis_status(current_user: Dict = Depends(get_current_admin)):
    """Get full Jarvis system status"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        import asyncio
        asyncio.create_task(jarvis.check_all_services())
        return {"status": "success", **jarvis.get_status()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/jarvis/workers")
async def get_jarvis_workers(current_user: Dict = Depends(get_current_admin)):
    """Get all monitored workers/services"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        workers = []
        for name, health in jarvis.services.items():
            workers.append({
                "name": name,
                "status": health.status.value,
                "last_check": health.last_check.isoformat() if health.last_check else None,
                "response_time_ms": health.response_time_ms,
                "error": health.error_message,
                "consecutive_failures": health.consecutive_failures,
                "metadata": health.metadata
            })
        return {"status": "success", "workers": workers}
    except Exception as e:
        return {"status": "error", "message": str(e), "workers": []}


@router.get("/jarvis/alerts")
async def get_jarvis_alerts(
    limit: int = 20,
    unresolved_only: bool = False,
    current_user: Dict = Depends(get_current_admin)
):
    """Get recent Jarvis alerts"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        return {"status": "success", "alerts": jarvis.get_alerts(limit=limit, unresolved_only=unresolved_only)}
    except Exception as e:
        return {"status": "error", "message": str(e), "alerts": []}


@router.post("/jarvis/alerts/{alert_id}/resolve")
async def resolve_jarvis_alert(alert_id: str, current_user: Dict = Depends(get_current_admin)):
    """Mark an alert as resolved"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        if jarvis.resolve_alert(alert_id):
            return {"status": "success", "message": f"Alert {alert_id} resolved"}
        else:
            raise HTTPException(status_code=404, detail="Alert not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jarvis/anomalies")
async def get_jarvis_anomalies(limit: int = 20, current_user: Dict = Depends(get_current_admin)):
    """Get detected anomalies"""
    try:
        from jarvis import get_anomaly_detector
        detector = get_anomaly_detector()
        return {"status": "success", "anomalies": detector.get_recent_anomalies(limit=limit), "summary": detector.get_summary()}
    except Exception as e:
        return {"status": "error", "message": str(e), "anomalies": []}


@router.post("/jarvis/check")
async def trigger_jarvis_check(current_user: Dict = Depends(get_current_admin)):
    """Manually trigger a full health check"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        results = await jarvis.check_all_services()
        return {
            "status": "success",
            "message": "Health check completed",
            "results": {
                name: {"status": health.status.value, "response_time_ms": health.response_time_ms}
                for name, health in results.items()
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
