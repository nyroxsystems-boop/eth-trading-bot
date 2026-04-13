#!/usr/bin/env python3
"""
Database Setup Script - Initializes all databases and seeds default data
Run this once to set up: Users, Accounts, and verify training works
"""

import os
import sys
from pathlib import Path

# Ensure we're in the right directory
os.chdir(Path(__file__).parent)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(".env.bot")
except ImportError:
    # Manual loading if dotenv not available
    env_file = Path(".env.bot")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

print("=" * 60)
print("ETH Trading Bot - Database Setup")
print("=" * 60)

# 1. Initialize User Database
print("\n📦 Step 1: Initializing User Database...")
try:
    from user_manager import UserManager, seed_initial_users
    user_mgr = UserManager()
    seed_initial_users()
    
    # Verify users
    users = user_mgr.list_users()
    print(f"   ✅ Users in database: {len(users)}")
    for u in users:
        print(f"      - {u['username']} (ID: {u['id']}, Role: {u.get('role', 'user')})")
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# 2. Initialize Account Database
print("\n📦 Step 2: Initializing Account Database...")
try:
    from account_manager import AccountManager
    account_mgr = AccountManager()
    
    # Check env vars
    api_key = os.getenv("BINANCE_API_KEY", "")
    # Check both possible env var names
    api_secret = os.getenv("BINANCE_API_SECRET", "") or os.getenv("BINANCE_SECRET_KEY", "")
    
    if api_key and api_secret:
        print(f"   🔑 Found Binance API Key: {api_key[:10]}...{api_key[-4:]}")
        
        # Set the expected env var name for migrate_legacy_account
        os.environ["BINANCE_API_SECRET"] = api_secret
        
        # Try to create account
        result = account_mgr.migrate_legacy_account()
        if result and result > 0:
            print(f"   ✅ Created Default Account (ID: {result})")
        elif result == -1:
            print(f"   ℹ️ Default Account already exists")
            existing = account_mgr.get_account_by_name("Default Account")
            if existing:
                print(f"      Account ID: {existing['id']}, Active: {existing['active']}")
        else:
            print(f"   ⚠️ Account creation returned: {result}")
    else:
        print("   ⚠️ No BINANCE_API_KEY/BINANCE_SECRET_KEY found in environment")
        print("   ℹ️ Add these to .env.bot to auto-create account")
    
    # List all accounts
    accounts = account_mgr.list_accounts()
    print(f"\n   📊 Total accounts: {len(accounts)}")
    for acc in accounts:
        print(f"      - {acc['name']} (ID: {acc['id']}, Mode: {'Paper' if acc['dry_run'] else 'Live'}, Active: {acc['active']})")

except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# 3. Initialize Learning Database
print("\n📦 Step 3: Initializing Learning Database...")
try:
    from src.ml.strategy_backtester import ensure_db
    ensure_db()
    print("   ✅ Learning database initialized")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 4. Verify ML Models
print("\n📦 Step 4: Checking ML Model Files...")
log_dir = Path(os.getenv("LOG_DIR", "./logs"))
model_files = {
    "DQN Agent": log_dir / "dqn_agent.pt",
    "Gradient Boosting": log_dir / "ml_model.pkl",
    "LSTM Predictor": log_dir / "neural_model.pt"
}

for name, path in model_files.items():
    if path.exists():
        size_kb = path.stat().st_size / 1024
        print(f"   ✅ {name}: {size_kb:.1f} KB")
    else:
        print(f"   ⚠️ {name}: Not trained yet")

# 5. Summary
print("\n" + "=" * 60)
print("Setup Complete!")
print("=" * 60)
print("\nNext steps:")
print("1. Restart the API: python dashboard_api.py")
print("2. Login to dashboard with credentials from ADMIN_PASSWORD / USER_PASSWORD env vars")
print("3. Check Accounts page - should show Default Account")
print("4. Start Training from ML Learning section")
