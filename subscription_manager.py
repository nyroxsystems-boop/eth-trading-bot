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

# Subscription tier definitions - Comprehensive 4-Tier System
TIERS = {
    'free': {
        'name': 'Free',
        'display_name': 'Starter',
        'max_accounts': 1,
        'max_trading_pairs': 1,
        'max_trades_per_day': 10,
        'live_trading': False,
        'ml_training': False,
        'api_access': False,
        'priority_support': False,
        'custom_strategies': False,
        'telegram_notifications': False,
        'price': 0,
        'price_yearly': 0,
        'stripe_price_id': None,
        'color': '#64748B',
        'features': [
            'Paper Trading Only',
            '1 Trading Pair (ETH)',
            '10 Trades/Day Limit',
            'Basic Dashboard',
            'Community Support'
        ],
        'limitations': [
            'No Live Trading',
            'No ML Features',
            'No API Access'
        ]
    },
    'basic': {
        'name': 'Basic',
        'display_name': 'Trader',
        'max_accounts': 1,
        'max_trading_pairs': 3,
        'max_trades_per_day': 50,
        'live_trading': True,
        'ml_training': False,
        'api_access': False,
        'priority_support': False,
        'custom_strategies': False,
        'telegram_notifications': True,
        'price': 29,
        'price_yearly': 290,  # ~17% discount
        'stripe_price_id': 'price_basic_monthly',
        'color': '#06B6D4',
        'features': [
            'Live Trading Enabled',
            '3 Trading Pairs',
            '50 Trades/Day',
            'Telegram Notifications',
            'Email Support',
            'Basic Analytics'
        ],
        'limitations': [
            'No ML Training',
            'No API Access'
        ]
    },
    'pro': {
        'name': 'Pro',
        'display_name': 'Professional',
        'max_accounts': 5,
        'max_trading_pairs': 10,
        'max_trades_per_day': None,  # Unlimited
        'live_trading': True,
        'ml_training': True,
        'api_access': True,
        'priority_support': True,
        'custom_strategies': False,
        'telegram_notifications': True,
        'price': 99,
        'price_yearly': 990,  # ~17% discount
        'stripe_price_id': 'price_pro_monthly',
        'color': '#8B5CF6',
        'features': [
            'Unlimited Trades',
            '10 Trading Pairs',
            '5 Bot Instances',
            'ML Model Training',
            'REST API Access',
            'Priority Support',
            'Advanced Analytics',
            'Custom Alerts'
        ],
        'limitations': []
    },
    'enterprise': {
        'name': 'Enterprise',
        'display_name': 'Enterprise',
        'max_accounts': None,  # Unlimited
        'max_trading_pairs': None,  # Unlimited
        'max_trades_per_day': None,  # Unlimited
        'live_trading': True,
        'ml_training': True,
        'api_access': True,
        'priority_support': True,
        'custom_strategies': True,
        'telegram_notifications': True,
        'price': 299,
        'price_yearly': 2990,  # ~17% discount
        'stripe_price_id': 'price_enterprise_monthly',
        'color': '#F59E0B',
        'features': [
            'Everything in Pro',
            'Unlimited Accounts',
            'Unlimited Trading Pairs',
            'Custom Strategy Builder',
            'White-Label Option',
            'Dedicated Account Manager',
            'SLA Guarantee',
            'On-Call Support'
        ],
        'limitations': []
    }
}

# Legacy mapping for backwards compatibility
LEGACY_TIER_MAPPING = {
    'premium': 'pro'  # Old 'premium' tier maps to new 'pro'
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
        
        # Count user's enabled trading pairs
        # Note: Currently returns True as trading pairs are not yet in database
        # In future, query trading_pairs table filtered by user_id
        enabled_pairs = 1  # Default: 1 pair (ETHUSDT)
        return enabled_pairs < limits['max_trading_pairs']
    
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
                'used': 1,  # Default: 1 pair (ETHUSDT), will be dynamic when trading_pairs table is added
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
