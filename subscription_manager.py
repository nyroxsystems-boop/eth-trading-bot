"""
Subscription Manager for SaaS Platform
Manages subscription tiers, limits, and enforcement
"""

import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# Import database adapter
from db_adapter import get_db_connection, USE_POSTGRES

# Subscription tier definitions
TIERS = {
    'free': {
        'name': 'Free',
        'max_accounts': 1,
        'max_trading_pairs': 1,
        'live_trading': False,
        'price': 0,
        'features': [
            '1 Binance Account',
            '1 Trading Pair (ETH only)',
            'Paper Trading Only',
            'Basic Support'
        ]
    },
    'premium': {
        'name': 'Premium',
        'max_accounts': 5,
        'max_trading_pairs': 10,
        'live_trading': True,
        'price': 29,  # USD/month
        'features': [
            '5 Binance Accounts',
            '10 Trading Pairs',
            'Live Trading Enabled',
            'Priority Support',
            'Advanced Analytics'
        ]
    }
}


class SubscriptionManager:
    """Manages user subscriptions and tier limits"""
    
    def __init__(self):
        pass
    
    def get_tier_info(self, tier: str) -> Dict:
        """Get tier information"""
        return TIERS.get(tier, TIERS['free'])
    
    def get_user_tier(self, user_id: int) -> str:
        """Get user's current subscription tier"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT subscription_tier FROM users WHERE id = %s
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT subscription_tier FROM users WHERE id = ?
                """, (user_id,))
            
            result = cursor.fetchone()
        
        return result[0] if result else 'free'
    
    def check_account_limit(self, user_id: int) -> bool:
        """Check if user can add more accounts"""
        from account_manager import AccountManager
        
        tier = self.get_user_tier(user_id)
        limits = TIERS[tier]
        
        account_mgr = AccountManager()
        # Note: This will need user_id filtering after migration
        accounts = account_mgr.list_accounts()
        user_accounts = [a for a in accounts if a.get('user_id') == user_id]
        
        return len(user_accounts) < limits['max_accounts']
    
    def check_trading_pair_limit(self, user_id: int) -> bool:
        """Check if user can enable more trading pairs"""
        tier = self.get_user_tier(user_id)
        limits = TIERS[tier]
        
        # TODO: Count user's enabled trading pairs
        # For now, return True
        return True
    
    def check_live_trading_allowed(self, user_id: int) -> bool:
        """Check if user can enable live trading"""
        tier = self.get_user_tier(user_id)
        return TIERS[tier]['live_trading']
    
    def upgrade_user(self, user_id: int, new_tier: str) -> bool:
        """Upgrade user to new tier"""
        if new_tier not in TIERS:
            return False
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    UPDATE users SET subscription_tier = %s WHERE id = %s
                """, (new_tier, user_id))
            else:
                cursor.execute("""
                    UPDATE users SET subscription_tier = ? WHERE id = ?
                """, (new_tier, user_id))
            
            success = cursor.rowcount > 0
        
        return success
    
    def get_usage_stats(self, user_id: int) -> Dict:
        """Get user's current usage vs limits"""
        from account_manager import AccountManager
        
        tier = self.get_user_tier(user_id)
        limits = TIERS[tier]
        
        account_mgr = AccountManager()
        accounts = account_mgr.list_accounts()
        user_accounts = [a for a in accounts if a.get('user_id') == user_id]
        
        return {
            'tier': tier,
            'tier_name': limits['name'],
            'accounts': {
                'used': len(user_accounts),
                'limit': limits['max_accounts'],
                'remaining': limits['max_accounts'] - len(user_accounts)
            },
            'trading_pairs': {
                'used': 1,  # TODO: Count actual pairs
                'limit': limits['max_trading_pairs'],
                'remaining': limits['max_trading_pairs'] - 1
            },
            'live_trading': {
                'allowed': limits['live_trading'],
                'enabled': any(not a['dry_run'] for a in user_accounts)
            }
        }


# Middleware for tier enforcement
def enforce_tier_limits(user_id: int, action: str) -> tuple[bool, str]:
    """
    Enforce subscription tier limits
    Returns: (allowed: bool, message: str)
    """
    sub_mgr = SubscriptionManager()
    
    if action == 'add_account':
        if not sub_mgr.check_account_limit(user_id):
            tier = sub_mgr.get_user_tier(user_id)
            limit = TIERS[tier]['max_accounts']
            return False, f"Account limit reached ({limit}). Upgrade to Premium for more accounts."
        return True, ""
    
    elif action == 'enable_live_trading':
        if not sub_mgr.check_live_trading_allowed(user_id):
            return False, "Live trading requires Premium subscription."
        return True, ""
    
    elif action == 'add_trading_pair':
        if not sub_mgr.check_trading_pair_limit(user_id):
            tier = sub_mgr.get_user_tier(user_id)
            limit = TIERS[tier]['max_trading_pairs']
            return False, f"Trading pair limit reached ({limit}). Upgrade to Premium."
        return True, ""
    
    return True, ""


if __name__ == "__main__":
    # Test subscription manager
    sub_mgr = SubscriptionManager()
    
    print("📊 Subscription Tiers:")
    for tier_name, tier_info in TIERS.items():
        print(f"\n{tier_info['name']} (${tier_info['price']}/month):")
        for feature in tier_info['features']:
            print(f"  ✓ {feature}")
