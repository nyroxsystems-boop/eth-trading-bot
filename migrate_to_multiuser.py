"""
Database Migration Script - Add User Support to Accounts
Migrates single-user system to multi-user SaaS platform
"""

import sqlite3
import os
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "/root/ethbot/logs"))
ACCOUNTS_DB = LOG_DIR / "accounts.db"
USERS_DB = LOG_DIR / "users.db"


def migrate_accounts_for_multi_user():
    """Add user_id column to accounts table and migrate existing accounts"""
    
    print("🔄 Starting database migration for multi-user support...")
    
    # Connect to both databases
    accounts_conn = sqlite3.connect(ACCOUNTS_DB)
    users_conn = sqlite3.connect(USERS_DB)
    
    accounts_cursor = accounts_conn.cursor()
    users_cursor = users_conn.cursor()
    
    try:
        # Step 1: Check if user_id column already exists
        accounts_cursor.execute("PRAGMA table_info(accounts)")
        columns = [col[1] for col in accounts_cursor.fetchall()]
        
        if 'user_id' in columns:
            print("✅ user_id column already exists, skipping migration")
            return
        
        # Step 2: Get or create admin user
        users_cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin = users_cursor.fetchone()
        
        if not admin:
            print("⚠️ No admin user found, creating default admin...")
            from user_manager import UserManager
            user_mgr = UserManager()
            admin_id = user_mgr.create_admin(
                email="admin@ethbot.com",
                username="admin",
                password="ChangeMe123!"  # User should change this!
            )
            print(f"✅ Created admin user (ID: {admin_id})")
        else:
            admin_id = admin[0]
            print(f"✅ Found existing admin user (ID: {admin_id})")
        
        # Step 3: Add user_id column to accounts table
        print("📝 Adding user_id column to accounts table...")
        accounts_cursor.execute("""
            ALTER TABLE accounts ADD COLUMN user_id INTEGER DEFAULT 1
        """)
        
        # Step 4: Set all existing accounts to admin user
        print(f"📝 Assigning all existing accounts to admin user (ID: {admin_id})...")
        accounts_cursor.execute("""
            UPDATE accounts SET user_id = ?
        """, (admin_id,))
        
        # Step 5: Add user_id to account_trades table
        accounts_cursor.execute("PRAGMA table_info(account_trades)")
        trade_columns = [col[1] for col in accounts_cursor.fetchall()]
        
        if 'user_id' not in trade_columns:
            print("📝 Adding user_id column to account_trades table...")
            accounts_cursor.execute("""
                ALTER TABLE account_trades ADD COLUMN user_id INTEGER
            """)
            
            # Update trades with user_id from their account
            accounts_cursor.execute("""
                UPDATE account_trades 
                SET user_id = (
                    SELECT user_id FROM accounts WHERE accounts.id = account_trades.account_id
                )
            """)
        
        # Step 6: Add user_id to account_performance table
        accounts_cursor.execute("PRAGMA table_info(account_performance)")
        perf_columns = [col[1] for col in accounts_cursor.fetchall()]
        
        if 'user_id' not in perf_columns:
            print("📝 Adding user_id column to account_performance table...")
            accounts_cursor.execute("""
                ALTER TABLE account_performance ADD COLUMN user_id INTEGER
            """)
            
            # Update performance with user_id from their account
            accounts_cursor.execute("""
                UPDATE account_performance 
                SET user_id = (
                    SELECT user_id FROM accounts WHERE accounts.account_id = account_performance.account_id
                )
            """)
        
        # Step 7: Create indexes for performance
        print("📝 Creating indexes...")
        try:
            accounts_cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id)
            """)
            accounts_cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_account_trades_user_id ON account_trades(user_id)
            """)
            accounts_cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_account_performance_user_id ON account_performance(user_id)
            """)
        except Exception as e:
            print(f"⚠️ Index creation warning: {e}")
        
        # Commit changes
        accounts_conn.commit()
        
        print("✅ Migration completed successfully!")
        print(f"   - All existing accounts assigned to admin user (ID: {admin_id})")
        print(f"   - user_id column added to all tables")
        print(f"   - Indexes created for performance")
        print("\n⚠️ IMPORTANT: Change admin password after first login!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        accounts_conn.rollback()
        raise
    finally:
        accounts_conn.close()
        users_conn.close()


if __name__ == "__main__":
    migrate_accounts_for_multi_user()
