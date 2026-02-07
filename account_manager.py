"""
Account Manager for Multi-Account Trading System
Handles CRUD operations for Binance API accounts
Uses PostgreSQL in production, SQLite for local development
"""

import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from cryptography.fernet import Fernet

# Import database adapter
from db_adapter import get_db_connection, USE_POSTGRES

# Database path for encryption key
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))

# Encryption key (from env var first, then file, then generate)
def get_encryption_key():
    """Get or generate encryption key for API secrets"""
    # Priority 1: Environment variable (for Railway/production)
    env_key = os.getenv("ENCRYPTION_KEY")
    if env_key:
        # Make sure it's valid Fernet key
        try:
            key = env_key.encode() if isinstance(env_key, str) else env_key
            Fernet(key)  # Validate
            return key
        except Exception:
            print("⚠️ ENCRYPTION_KEY env var is invalid, falling back to file")
    
    # Priority 2: Key file
    key_file = LOG_DIR / ".encryption_key"
    if key_file.exists():
        with open(key_file, 'rb') as f:
            return f.read()
    
    # Priority 3: Generate new key and save
    key = Fernet.generate_key()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(key_file, 'wb') as f:
        f.write(key)
    # Also print it so it can be set as env var
    print(f"🔑 Generated new encryption key. Set as env var: ENCRYPTION_KEY={key.decode()}")
    return key

ENCRYPTION_KEY = get_encryption_key()
cipher = Fernet(ENCRYPTION_KEY)


def init_database():
    """Initialize accounts database with schema"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Accounts table
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER DEFAULT 1,
                    name TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    api_secret TEXT NOT NULL,
                    capital REAL DEFAULT 10000,
                    dry_run BOOLEAN DEFAULT true,
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP,
                    UNIQUE(user_id, name)
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER DEFAULT 1,
                    name TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    api_secret TEXT NOT NULL,
                    capital REAL DEFAULT 10000,
                    dry_run BOOLEAN DEFAULT 1,
                    active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP,
                    UNIQUE(user_id, name)
                )
            """)
        
        # Account trades table
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_trades (
                    id SERIAL PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    qty REAL NOT NULL,
                    price REAL NOT NULL,
                    pnl REAL DEFAULT 0,
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    qty REAL NOT NULL,
                    price REAL NOT NULL,
                    pnl REAL DEFAULT 0,
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
            """)
        
        # Account performance table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_performance (
                account_id INTEGER PRIMARY KEY,
                total_pnl REAL DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0,
                sharpe_ratio REAL DEFAULT 0,
                max_drawdown REAL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_account_trades_account_id ON account_trades(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_account_trades_timestamp ON account_trades(timestamp)")
        
        print(f"✅ Accounts database initialized")


def encrypt_secret(secret: str) -> str:
    """Encrypt API secret"""
    return cipher.encrypt(secret.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    """Decrypt API secret, returns placeholder if key mismatch"""
    try:
        return cipher.decrypt(encrypted.encode()).decode()
    except Exception:
        # Key mismatch - return masked value instead of crashing
        print(f"⚠️ Could not decrypt secret (key mismatch). Returning placeholder.")
        return "ENCRYPTED_KEY_MISMATCH"


class AccountManager:
    """Manages trading accounts"""
    
    def __init__(self):
        init_database()
    
    def create_account(self, user_id: int, name: str, api_key: str, api_secret: str, 
                      capital: float = 10000, dry_run: bool = True) -> int:
        """Create a new trading account"""
        try:
            # Encrypt the API secret
            encrypted_secret = encrypt_secret(api_secret)
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                if USE_POSTGRES:
                    cursor.execute("""
                        INSERT INTO accounts (user_id, name, api_key, api_secret, capital, dry_run, active)
                        VALUES (%s, %s, %s, %s, %s, %s, true)
                        RETURNING id
                    """, (user_id, name, api_key, encrypted_secret, capital, dry_run))
                    account_id = cursor.fetchone()[0]
                    
                    cursor.execute("""
                        INSERT INTO account_performance (account_id)
                        VALUES (%s)
                    """, (account_id,))
                else:
                    cursor.execute("""
                        INSERT INTO accounts (user_id, name, api_key, api_secret, capital, dry_run, active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    """, (user_id, name, api_key, encrypted_secret, capital, dry_run))
                    account_id = cursor.lastrowid
                    
                    cursor.execute("""
                        INSERT INTO account_performance (account_id)
                        VALUES (?)
                    """, (account_id,))
                
                print(f"✅ Created account '{name}' (ID: {account_id})")
                return account_id
                
        except Exception as e:
            error_str = str(e).lower()
            if 'unique' in error_str or 'duplicate' in error_str:
                print(f"❌ Account '{name}' already exists")
                return -1
            raise
    
    def get_account(self, account_id: int) -> Optional[Dict]:
        """Get account by ID"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT id, name, api_key, api_secret, capital, dry_run, active, 
                           created_at, last_active
                    FROM accounts
                    WHERE id = %s
                """, (account_id,))
            else:
                cursor.execute("""
                    SELECT id, name, api_key, api_secret, capital, dry_run, active, 
                           created_at, last_active
                    FROM accounts
                    WHERE id = ?
                """, (account_id,))
            
            row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "name": row[1],
            "api_key": row[2],
            "api_secret": decrypt_secret(row[3]),
            "capital": row[4],
            "dry_run": bool(row[5]),
            "active": bool(row[6]),
            "created_at": row[7],
            "last_active": row[8]
        }
    
    def get_account_by_name(self, name: str) -> Optional[Dict]:
        """Get account by name"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT id, name, api_key, api_secret, capital, dry_run, active, 
                           created_at, last_active
                    FROM accounts
                    WHERE name = %s
                """, (name,))
            else:
                cursor.execute("""
                    SELECT id, name, api_key, api_secret, capital, dry_run, active, 
                           created_at, last_active
                    FROM accounts
                    WHERE name = ?
                """, (name,))
            
            row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "name": row[1],
            "api_key": row[2],
            "api_secret": decrypt_secret(row[3]),
            "capital": row[4],
            "dry_run": bool(row[5]),
            "active": bool(row[6]),
            "created_at": row[7],
            "last_active": row[8]
        }
    
    def list_accounts(self, user_id: int = None, active_only: bool = False) -> List[Dict]:
        """List accounts for a specific user"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if user_id:
                if USE_POSTGRES:
                    if active_only:
                        cursor.execute("""
                            SELECT id, name, api_key, capital, dry_run, active, 
                                   created_at, last_active
                            FROM accounts
                            WHERE user_id = %s AND active = true
                            ORDER BY created_at DESC
                        """, (user_id,))
                    else:
                        cursor.execute("""
                            SELECT id, name, api_key, capital, dry_run, active, 
                                   created_at, last_active
                            FROM accounts
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                        """, (user_id,))
                else:
                    if active_only:
                        cursor.execute("""
                            SELECT id, name, api_key, capital, dry_run, active, 
                                   created_at, last_active
                            FROM accounts
                            WHERE user_id = ? AND active = 1
                            ORDER BY created_at DESC
                        """, (user_id,))
                    else:
                        cursor.execute("""
                            SELECT id, name, api_key, capital, dry_run, active, 
                                   created_at, last_active
                            FROM accounts
                            WHERE user_id = ?
                            ORDER BY created_at DESC
                        """, (user_id,))
            else:
                # Admin: show all accounts
                if USE_POSTGRES:
                    if active_only:
                        cursor.execute("""
                            SELECT id, name, api_key, capital, dry_run, active, 
                                   created_at, last_active
                            FROM accounts
                            WHERE active = true
                            ORDER BY created_at DESC
                        """)
                    else:
                        cursor.execute("""
                            SELECT id, name, api_key, capital, dry_run, active, 
                                   created_at, last_active
                            FROM accounts
                            ORDER BY created_at DESC
                        """)
                else:
                    if active_only:
                        cursor.execute("""
                            SELECT id, name, api_key, capital, dry_run, active, 
                                   created_at, last_active
                            FROM accounts
                            WHERE active = 1
                            ORDER BY created_at DESC
                        """)
                    else:
                        cursor.execute("""
                            SELECT id, name, api_key, capital, dry_run, active, 
                                   created_at, last_active
                            FROM accounts
                            ORDER BY created_at DESC
                        """)
            
            rows = cursor.fetchall()
        
        accounts = []
        for row in rows:
            accounts.append({
                "id": row[0],
                "name": row[1],
                "api_key": row[2],
                "api_secret_masked": "•" * 16,  # Don't expose secrets in list
                "capital": row[3],
                "dry_run": bool(row[4]),
                "active": bool(row[5]),
                "created_at": row[6],
                "last_active": row[7]
            })
        
        return accounts
    
    def update_account(self, account_id: int, **kwargs) -> bool:
        """Update account fields"""
        # Build update query dynamically
        allowed_fields = ["name", "api_key", "api_secret", "capital", "dry_run", "active"]
        updates = []
        values = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                if field == "api_secret":
                    value = encrypt_secret(value)
                updates.append(f"{field} = {'%s' if USE_POSTGRES else '?'}")
                values.append(value)
        
        if not updates:
            return False
        
        values.append(account_id)
        query = f"UPDATE accounts SET {', '.join(updates)} WHERE id = {'%s' if USE_POSTGRES else '?'}"
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, values)
            success = cursor.rowcount > 0
        
        if success:
            print(f"✅ Updated account ID {account_id}")
        return success
    
    def delete_account(self, account_id: int) -> bool:
        """Delete account and all associated data"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("DELETE FROM accounts WHERE id = %s", (account_id,))
            else:
                cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            
            success = cursor.rowcount > 0
        
        if success:
            print(f"✅ Deleted account ID {account_id}")
        return success
    
    def toggle_account(self, account_id: int) -> bool:
        """Toggle account active status"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE accounts 
                SET active = NOT active 
                WHERE id = {}
            """.format('%s' if USE_POSTGRES else '?'), (account_id,))
            
            success = cursor.rowcount > 0
        
        if success:
            print(f"✅ Toggled account ID {account_id}")
        return success
    
    def update_last_active(self, account_id: int):
        """Update last active timestamp"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    UPDATE accounts 
                    SET last_active = %s 
                    WHERE id = %s
                """, (datetime.now().isoformat(), account_id))
            else:
                cursor.execute("""
                    UPDATE accounts 
                    SET last_active = ? 
                    WHERE id = ?
                """, (datetime.now().isoformat(), account_id))
    
    def validate_credentials(self, api_key: str, api_secret: str) -> bool:
        """Validate Binance API credentials"""
        try:
            from binance.client import Client
            client = Client(api_key, api_secret)
            # Test API call
            client.get_account()
            return True
        except Exception as e:
            print(f"❌ API validation failed: {e}")
            return False
    
    def migrate_legacy_account(self):
        """Migrate existing single-account setup to multi-account"""
        try:
            # Check if default account already exists
            existing = self.get_account_by_name("Default Account")
            if existing:
                # If the secret couldn't be decrypted, re-encrypt with current key
                if existing.get("api_secret") == "ENCRYPTED_KEY_MISMATCH":
                    print("🔄 Re-encrypting Default Account with current key...")
                    api_key = os.getenv("BINANCE_API_KEY", "")
                    api_secret = os.getenv("BINANCE_API_SECRET", "")
                    if api_key and api_secret:
                        self.update_account(existing["id"], api_key=api_key, api_secret=api_secret)
                        print("✅ Re-encrypted Default Account successfully")
                print("✅ Default account already exists")
                return existing["id"]
        except Exception as e:
            print(f"⚠️ Error checking existing account: {e}")
        
        # Get credentials from environment
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        capital = float(os.getenv("PAPER_BASE_USDT", "10000"))
        dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        
        if not api_key or not api_secret:
            print("⚠️ No legacy credentials found in environment")
            return None
        
        # Create default account
        account_id = self.create_account(
            user_id=1,
            name="Default Account",
            api_key=api_key,
            api_secret=api_secret,
            capital=capital,
            dry_run=dry_run
        )
        
        print(f"✅ Migrated legacy account to ID {account_id}")
        return account_id


# Initialize on import
if __name__ == "__main__":
    # Test the account manager
    manager = AccountManager()
    
    # Migrate legacy account if exists
    manager.migrate_legacy_account()
    
    # List all accounts
    accounts = manager.list_accounts()
    print(f"\n📊 Total accounts: {len(accounts)}")
    for acc in accounts:
        print(f"  - {acc['name']} (ID: {acc['id']}, Active: {acc['active']}, Mode: {'Paper' if acc['dry_run'] else 'Live'})")
