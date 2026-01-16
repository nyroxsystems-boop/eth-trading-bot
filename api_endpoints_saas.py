"""
Additional API endpoints for Test Phase and Subscription Management
Append to dashboard_api.py
"""

# Add these imports at the top of dashboard_api.py:
# from test_phase_manager import test_phase_manager
# from subscription_manager import SubscriptionManager

# Add these endpoints at the end of dashboard_api.py:

# ==================== TEST PHASE ENDPOINTS ====================

@app.get("/api/test-phase/{symbol}")
async def get_test_phase(symbol: str, current_user: Dict = Depends(get_current_user)):
    """Get test phase status for a specific cryptocurrency"""
    try:
        phase = test_phase_manager.get_test_phase(current_user['user_id'], symbol)
        if not phase:
            return {"error": "No test phase found for this symbol"}
        return phase
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test-phase/{symbol}/start")
async def start_test_phase(symbol: str, current_user: Dict = Depends(get_current_user)):
    """Start a new 30-day test phase for a cryptocurrency"""
    try:
        # Check subscription limits
        sub_mgr = SubscriptionManager()
        tier = sub_mgr.get_user_tier(current_user['user_id'])
        
        # Get existing test phases
        all_phases = test_phase_manager.get_all_test_phases(current_user['user_id'])
        
        # Check if user can add more coins
        tier_info = sub_mgr.get_tier_info(tier)
        if len(all_phases) >= tier_info['max_trading_pairs']:
            raise HTTPException(
                status_code=403,
                detail=f"Maximum {tier_info['max_trading_pairs']} coins allowed on {tier} tier"
            )
        
        phase = test_phase_manager.start_test_phase(current_user['user_id'], symbol)
        return {
            "success": True,
            "message": f"30-day test phase started for {symbol}",
            "phase": phase
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/test-phases")
async def get_all_test_phases(current_user: Dict = Depends(get_current_user)):
    """Get all test phases for the current user"""
    try:
        phases = test_phase_manager.get_all_test_phases(current_user['user_id'])
        return {"test_phases": phases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test-phase/{symbol}/update")
async def update_test_phase_metrics(
    symbol: str,
    metrics: Dict,
    current_user: Dict = Depends(get_current_user)
):
    """Update test phase with new performance metrics"""
    try:
        phase = test_phase_manager.update_test_phase(
            current_user['user_id'],
            symbol,
            metrics
        )
        return {
            "success": True,
            "phase": phase
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SUBSCRIPTION ENDPOINTS ====================

@app.get("/api/subscription")
async def get_subscription(current_user: Dict = Depends(get_current_user)):
    """Get user's current subscription"""
    try:
        sub_mgr = SubscriptionManager()
        tier = sub_mgr.get_user_tier(current_user['user_id'])
        tier_info = sub_mgr.get_tier_info(tier)
        usage = sub_mgr.get_usage_stats(current_user['user_id'])
        
        return {
            "tier": tier,
            "tier_name": tier_info['name'],
            "price": tier_info['price'],
            "features": tier_info['features'],
            "usage": usage,
            "can_upgrade": tier == 'free'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/subscription/upgrade")
async def upgrade_subscription(current_user: Dict = Depends(get_current_user)):
    """Upgrade user to premium subscription"""
    try:
        sub_mgr = SubscriptionManager()
        
        # Check if already premium
        current_tier = sub_mgr.get_user_tier(current_user['user_id'])
        if current_tier == 'premium':
            raise HTTPException(status_code=400, detail="Already on premium tier")
        
        # Upgrade to premium
        success = sub_mgr.upgrade_user(current_user['user_id'], 'premium')
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to upgrade subscription")
        
        return {
            "success": True,
            "message": "Successfully upgraded to Premium",
            "tier": "premium"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/subscription/tiers")
async def get_subscription_tiers():
    """Get all available subscription tiers"""
    try:
        from subscription_manager import TIERS
        return {"tiers": TIERS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ENHANCED TRADING MODE ENDPOINTS ====================

@app.post("/api/trading/mode/toggle")
async def toggle_trading_mode(current_user: Dict = Depends(get_current_user)):
    """Toggle between paper and live trading with safety checks"""
    try:
        settings = load_settings()
        current_mode = "paper" if settings.get('dry_run', True) else "live"
        new_mode = "live" if current_mode == "paper" else "paper"
        
        # Safety checks for enabling live trading
        if new_mode == "live":
            # Check subscription tier
            sub_mgr = SubscriptionManager()
            tier = sub_mgr.get_user_tier(current_user['user_id'])
            tier_info = sub_mgr.get_tier_info(tier)
            
            if not tier_info['live_trading']:
                raise HTTPException(
                    status_code=403,
                    detail="Live trading requires Premium subscription"
                )
            
            # Check if any test phase is completed and ready
            all_phases = test_phase_manager.get_all_test_phases(current_user['user_id'])
            
            if not all_phases:
                raise HTTPException(
                    status_code=400,
                    detail="No test phases found. Start a 30-day test phase first."
                )
            
            # Check if at least one coin is ready for live trading
            ready_coins = [
                symbol for symbol, phase in all_phases.items()
                if phase.get('ready_for_live', False)
            ]
            
            if not ready_coins and tier_info.get('test_phase_required', True):
                raise HTTPException(
                    status_code=400,
                    detail="Complete a 30-day test phase before enabling live trading"
                )
        
        # Update settings
        settings['dry_run'] = (new_mode == "paper")
        save_settings(settings)
        
        # Log the change
        print(f"User {current_user['user_id']} switched to {new_mode} mode")
        
        return {
            "success": True,
            "mode": new_mode,
            "dry_run": settings['dry_run'],
            "message": f"Switched to {new_mode.upper()} trading mode"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/mode/status")
async def get_trading_mode_status(current_user: Dict = Depends(get_current_user)):
    """Get comprehensive trading mode status including test phases"""
    try:
        settings = load_settings()
        is_paper = settings.get('dry_run', True)
        
        # Get subscription info
        sub_mgr = SubscriptionManager()
        tier = sub_mgr.get_user_tier(current_user['user_id'])
        tier_info = sub_mgr.get_tier_info(tier)
        
        # Get test phases
        all_phases = test_phase_manager.get_all_test_phases(current_user['user_id'])
        
        # Calculate readiness
        ready_coins = [
            symbol for symbol, phase in all_phases.items()
            if phase.get('ready_for_live', False)
        ]
        
        can_enable_live = (
            tier_info['live_trading'] and
            (len(ready_coins) > 0 or not tier_info.get('test_phase_required', True))
        )
        
        return {
            "mode": "paper" if is_paper else "live",
            "dry_run": is_paper,
            "can_enable_live": can_enable_live,
            "subscription_tier": tier,
            "live_trading_allowed": tier_info['live_trading'],
            "test_phases": all_phases,
            "ready_coins": ready_coins,
            "requires_upgrade": not tier_info['live_trading']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
