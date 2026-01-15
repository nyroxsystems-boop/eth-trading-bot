"""
Account Manager for Multi-Account Trading System
Handles CRUD operations for Binance API accounts
"""

import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from cryptography.fernet import Fernet
import base64
import hashlib

# Database path
LOG_DIR = Path(os.getenv("LOG_DIR", "/root/ethbot/logs"))
ACCOUNTS_DB = LOG_DIR / "accounts.db"

# Encryption key (derived from environment or generated)
def get_encryption_key():
    """Get or generate encryption key for API secrets"""
    key_file = LOG_DIR / ".encryption_key"
    if key_file.exists():
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        # Generate new key
        key = Fernet.generate_key()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(key_file, 'wb') as f:
            f.write(key)
        return key

ENCRYPTION_KEY = get_encryption_key()
cipher = Fernet(ENCRYPTION_KEY)


def init_database():
    """Initialize accounts database with schema"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(ACCOUNTS_DB)
    cursor = conn.cursor()
    
    # Accounts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            api_key TEXT NOT NULL,
            api_secret TEXT NOT NULL,
            capital REAL DEFAULT 10000,
            dry_run BOOLEAN DEFAULT 1,
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP
        )
    """)
    
    # Account trades table
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
    
    conn.commit()
    conn.close()
    print(f"✅ Accounts database initialized at {ACCOUNTS_DB}")


def encrypt_secret(secret: str) -> str:
    """Encrypt API secret"""
    return cipher.encrypt(secret.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    """Decrypt API secret"""
    return cipher.decrypt(encrypted.encode()).decode()


class AccountManager:
    """Manages trading accounts"""
    
    def __init__(self):
        init_database()
    
    def create_account(self, name: str, api_key: str, api_secret: str, 
                      capital: float = 10000, dry_run: bool = True) -> int:
        """Create a new trading account"""
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        try:
            # Encrypt the API secret
            encrypted_secret = encrypt_secret(api_secret)
            
            cursor.execute("""
                INSERT INTO accounts (name, api_key, api_secret, capital, dry_run, active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (name, api_key, encrypted_secret, capital, dry_run))
            
            account_id = cursor.lastrowid
            
            # Initialize performance record
            cursor.execute("""
                INSERT INTO account_performance (account_id)
                VALUES (?)
            """, (account_id,))
            
            conn.commit()
            print(f"✅ Created account '{name}' (ID: {account_id})")
            return account_id
            
        except sqlite3.IntegrityError:
            print(f"❌ Account '{name}' already exists")
            return -1
        finally:
            conn.close()
    
    def get_account(self, account_id: int) -> Optional[Dict]:
        """Get account by ID"""
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, name, api_key, api_secret, capital, dry_run, active, 
                   created_at, last_active
            FROM accounts
            WHERE id = ?
        """, (account_id,))
        
        row = cursor.fetchone()
        conn.close()
        
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
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, name, api_key, api_secret, capital, dry_run, active, 
                   created_at, last_active
            FROM accounts
            WHERE name = ?
        """, (name,))
        
        row = cursor.fetchone()
        conn.close()
        
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
    
    def list_accounts(self, active_only: bool = False) -> List[Dict]:
        """List all accounts"""
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
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
        conn.close()
        
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
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        # Build update query dynamically
        allowed_fields = ["name", "api_key", "api_secret", "capital", "dry_run", "active"]
        updates = []
        values = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                if field == "api_secret":
                    value = encrypt_secret(value)
                updates.append(f"{field} = ?")
                values.append(value)
        
        if not updates:
            conn.close()
            return False
        
        values.append(account_id)
        query = f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?"
        
        cursor.execute(query, values)
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        
        if success:
            print(f"✅ Updated account ID {account_id}")
        return success
    
    def delete_account(self, account_id: int) -> bool:
        """Delete account and all associated data"""
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        
        if success:
            print(f"✅ Deleted account ID {account_id}")
        return success
    
    def toggle_account(self, account_id: int) -> bool:
        """Toggle account active status"""
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE accounts 
            SET active = NOT active 
            WHERE id = ?
        """, (account_id,))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        
        if success:
            print(f"✅ Toggled account ID {account_id}")
        return success
    
    def update_last_active(self, account_id: int):
        """Update last active timestamp"""
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE accounts 
            SET last_active = ? 
            WHERE id = ?
        """, (datetime.now().isoformat(), account_id))
        
        conn.commit()
        conn.close()
    
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
        # Check if default account already exists
        existing = self.get_account_by_name("Default Account")
        if existing:
            print("✅ Default account already exists")
            return existing["id"]
        
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
