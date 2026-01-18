"""
User Manager for SaaS Trading Platform
Handles user registration, authentication, and management
Uses PostgreSQL in production, SQLite for local development
Supports multi-tenant API key storage with encryption
"""

import os
import secrets
import base64
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta
import jwt
import bcrypt

# Import database adapter
from db_adapter import get_db_connection, USE_POSTGRES

# Encryption for API keys
try:
    from cryptography.fernet import Fernet
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False
    print("⚠️ cryptography not installed - API keys will not be encrypted")

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Encryption key for API secrets (generate once and store in env)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
if not ENCRYPTION_KEY and ENCRYPTION_AVAILABLE:
    # Generate a new key if not set (should be set in production!)
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"⚠️ No ENCRYPTION_KEY set! Generated temporary key (set in production!)")

def get_fernet():
    """Get Fernet instance for encryption/decryption"""
    if not ENCRYPTION_AVAILABLE:
        return None
    try:
        return Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
    except Exception as e:
        print(f"⚠️ Fernet initialization failed: {e}")
        return None

def encrypt_value(value: str) -> str:
    """Encrypt a value using Fernet"""
    if not value:
        return ""
    fernet = get_fernet()
    if not fernet:
        return value  # Return plaintext if encryption not available
    return fernet.encrypt(value.encode()).decode()

def decrypt_value(encrypted: str) -> str:
    """Decrypt a value using Fernet"""
    if not encrypted:
        return ""
    fernet = get_fernet()
    if not fernet:
        return encrypted  # Return as-is if decryption not available
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except Exception as e:
        print(f"⚠️ Decryption failed: {e}")
        return ""


def init_users_database():
    """Initialize users database with schema"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Users table
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    subscription_tier TEXT DEFAULT 'free',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    active BOOLEAN DEFAULT true,
                    email_verified BOOLEAN DEFAULT false,
                    test_phases TEXT DEFAULT '{}'
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    subscription_tier TEXT DEFAULT 'free',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    active BOOLEAN DEFAULT 1,
                    email_verified BOOLEAN DEFAULT 0,
                    test_phases TEXT DEFAULT '{}'
                )
            """)
        
        # User settings table
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    telegram_bot_token TEXT,
                    telegram_chat_id TEXT,
                    default_trading_pair TEXT DEFAULT 'ETHUSDT',
                    risk_tolerance TEXT DEFAULT 'medium',
                    notifications_enabled BOOLEAN DEFAULT true,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    telegram_bot_token TEXT,
                    telegram_chat_id TEXT,
                    default_trading_pair TEXT DEFAULT 'ETHUSDT',
                    risk_tolerance TEXT DEFAULT 'medium',
                    notifications_enabled BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        
        # Password reset tokens table
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT false,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        
        # Sessions table (for token blacklisting)
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    revoked BOOLEAN DEFAULT false,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    revoked BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        
        # User API Keys table (encrypted storage for Binance/Telegram credentials)
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_api_keys (
                    user_id INTEGER PRIMARY KEY,
                    binance_api_key TEXT,
                    binance_api_secret TEXT,
                    telegram_bot_token TEXT,
                    telegram_chat_id TEXT,
                    trading_enabled BOOLEAN DEFAULT false,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_api_keys (
                    user_id INTEGER PRIMARY KEY,
                    binance_api_key TEXT,
                    binance_api_secret TEXT,
                    telegram_bot_token TEXT,
                    telegram_chat_id TEXT,
                    trading_enabled BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
        
        # Migration: Add test_phases column if not exists (for existing tables)
        try:
            if USE_POSTGRES:
                cursor.execute("""
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS test_phases TEXT DEFAULT '{}'
                """)
            else:
                # SQLite doesn't have ADD COLUMN IF NOT EXISTS - check first
                cursor.execute("PRAGMA table_info(users)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'test_phases' not in columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN test_phases TEXT DEFAULT '{}'")
        except Exception as e:
            print(f"Note: test_phases column migration: {e}")
        
        # Migration: Add trading_pair column to user_api_keys
        try:
            if USE_POSTGRES:
                cursor.execute("""
                    ALTER TABLE user_api_keys ADD COLUMN IF NOT EXISTS trading_pair TEXT DEFAULT 'ETHUSDT'
                """)
            else:
                cursor.execute("PRAGMA table_info(user_api_keys)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'trading_pair' not in columns:
                    cursor.execute("ALTER TABLE user_api_keys ADD COLUMN trading_pair TEXT DEFAULT 'ETHUSDT'")
        except Exception as e:
            print(f"Note: trading_pair column migration: {e}")
        
        # User Trading Pairs table (multi-pair portfolio with individual settings)
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_trading_pairs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    trading_pair TEXT NOT NULL,
                    pair_name TEXT,
                    pair_icon TEXT DEFAULT '💰',
                    allocated_capital DECIMAL(18,2) DEFAULT 100.00,
                    risk_per_trade DECIMAL(5,4) DEFAULT 0.01,
                    max_trades_per_day INTEGER DEFAULT 10,
                    take_profit_pct DECIMAL(5,4) DEFAULT 0.015,
                    stop_loss_pct DECIMAL(5,4) DEFAULT 0.01,
                    enabled BOOLEAN DEFAULT true,
                    total_pnl DECIMAL(18,2) DEFAULT 0.00,
                    total_trades INTEGER DEFAULT 0,
                    win_rate DECIMAL(5,2) DEFAULT 0.00,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, trading_pair)
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_trading_pairs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    trading_pair TEXT NOT NULL,
                    pair_name TEXT,
                    pair_icon TEXT DEFAULT '💰',
                    allocated_capital REAL DEFAULT 100.00,
                    risk_per_trade REAL DEFAULT 0.01,
                    max_trades_per_day INTEGER DEFAULT 10,
                    take_profit_pct REAL DEFAULT 0.015,
                    stop_loss_pct REAL DEFAULT 0.01,
                    enabled BOOLEAN DEFAULT 1,
                    total_pnl REAL DEFAULT 0.00,
                    total_trades INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0.00,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, trading_pair)
                )
            """)
        
        # Index for fast lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_trading_pairs_user ON user_trading_pairs(user_id)")
        
        print(f"✅ Users database initialized")


class UserManager:
    """Manages user accounts and authentication"""
    
    def __init__(self):
        init_users_database()
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    
    def generate_jwt(self, user_id: int, email: str, role: str) -> str:
        """Generate JWT token"""
        payload = {
            'user_id': user_id,
            'email': email,
            'role': role,
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    def verify_jwt(self, token: str) -> Optional[Dict]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            
            # Check if token is revoked
            with get_db_connection() as conn:
                cursor = conn.cursor()
                if USE_POSTGRES:
                    cursor.execute("SELECT revoked FROM sessions WHERE token = %s", (token,))
                else:
                    cursor.execute("SELECT revoked FROM sessions WHERE token = ?", (token,))
                result = cursor.fetchone()
            
            if result and result[0]:
                return None
            
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def register_user(self, email: str, username: str, password: str, 
                     role: str = 'user') -> Optional[int]:
        """Register a new user"""
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        
        if '@' not in email:
            raise ValueError("Invalid email address")
        
        try:
            password_hash = self.hash_password(password)
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                if USE_POSTGRES:
                    cursor.execute("""
                        INSERT INTO users (email, username, password_hash, role)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (email.lower(), username, password_hash, role))
                    user_id = cursor.fetchone()[0]
                    
                    cursor.execute("""
                        INSERT INTO user_settings (user_id)
                        VALUES (%s)
                    """, (user_id,))
                else:
                    cursor.execute("""
                        INSERT INTO users (email, username, password_hash, role)
                        VALUES (?, ?, ?, ?)
                    """, (email.lower(), username, password_hash, role))
                    user_id = cursor.lastrowid
                    
                    cursor.execute("""
                        INSERT INTO user_settings (user_id)
                        VALUES (?)
                    """, (user_id,))
                
                print(f"✅ User '{username}' registered (ID: {user_id})")
                return user_id
                
        except Exception as e:
            error_str = str(e).lower()
            if 'email' in error_str and ('unique' in error_str or 'duplicate' in error_str):
                raise ValueError("Email already registered")
            elif 'username' in error_str and ('unique' in error_str or 'duplicate' in error_str):
                raise ValueError("Username already taken")
            else:
                raise ValueError(f"Registration failed: {e}")
    
    def login(self, email_or_username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return token"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Try to find user by email or username
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT id, email, username, password_hash, role, active
                    FROM users
                    WHERE email = %s OR username = %s
                """, (email_or_username.lower(), email_or_username))
            else:
                cursor.execute("""
                    SELECT id, email, username, password_hash, role, active
                    FROM users
                    WHERE email = ? OR username = ?
                """, (email_or_username.lower(), email_or_username))
            
            user = cursor.fetchone()
            
            if not user:
                return None
            
            user_id, email, username, password_hash, role, active = user
            
            if not active:
                raise ValueError("Account is suspended")
            
            if not self.verify_password(password, password_hash):
                return None
            
            # Update last login
            if USE_POSTGRES:
                cursor.execute("""
                    UPDATE users SET last_login = %s WHERE id = %s
                """, (datetime.now().isoformat(), user_id))
            else:
                cursor.execute("""
                    UPDATE users SET last_login = ? WHERE id = ?
                """, (datetime.now().isoformat(), user_id))
            
            # Generate JWT
            token = self.generate_jwt(user_id, email, role)
            
            # Store session (delete old ones first to avoid unique constraint)
            if USE_POSTGRES:
                cursor.execute("""
                    DELETE FROM sessions WHERE user_id = %s
                """, (user_id,))
                cursor.execute("""
                    INSERT INTO sessions (user_id, token, expires_at)
                    VALUES (%s, %s, %s)
                """, (user_id, token, 
                      (datetime.now() + timedelta(hours=JWT_EXPIRATION_HOURS)).isoformat()))
            else:
                cursor.execute("""
                    DELETE FROM sessions WHERE user_id = ?
                """, (user_id,))
                cursor.execute("""
                    INSERT INTO sessions (user_id, token, expires_at)
                    VALUES (?, ?, ?)
                """, (user_id, token, 
                      (datetime.now() + timedelta(hours=JWT_EXPIRATION_HOURS)).isoformat()))
            
            print(f"✅ User '{username}' logged in")
            
            return {
                'user_id': user_id,
                'email': email,
                'username': username,
                'role': role,
                'token': token
            }
    
    def logout(self, token: str) -> bool:
        """Revoke a token (logout)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("UPDATE sessions SET revoked = true WHERE token = %s", (token,))
            else:
                cursor.execute("UPDATE sessions SET revoked = 1 WHERE token = ?", (token,))
            
            return cursor.rowcount > 0
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT id, email, username, role, subscription_tier, 
                           created_at, last_login, active
                    FROM users
                    WHERE id = %s
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT id, email, username, role, subscription_tier, 
                           created_at, last_login, active
                    FROM users
                    WHERE id = ?
                """, (user_id,))
            
            user = cursor.fetchone()
        
        if not user:
            return None
        
        return {
            'id': user[0],
            'email': user[1],
            'username': user[2],
            'role': user[3],
            'subscription_tier': user[4],
            'created_at': user[5],
            'last_login': user[6],
            'active': bool(user[7])
        }
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT id, email, username, role, subscription_tier, 
                           created_at, last_login, active
                    FROM users
                    WHERE email = %s
                """, (email.lower(),))
            else:
                cursor.execute("""
                    SELECT id, email, username, role, subscription_tier, 
                           created_at, last_login, active
                    FROM users
                    WHERE email = ?
                """, (email.lower(),))
            
            user = cursor.fetchone()
        
        if not user:
            return None
        
        return {
            'id': user[0],
            'email': user[1],
            'username': user[2],
            'role': user[3],
            'subscription_tier': user[4],
            'created_at': user[5],
            'last_login': user[6],
            'active': bool(user[7])
        }
    
    def list_users(self, active_only: bool = False) -> list:
        """List all users"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                if active_only:
                    cursor.execute("""
                        SELECT id, email, username, role, subscription_tier, 
                               created_at, last_login, active
                        FROM users
                        WHERE active = true
                        ORDER BY created_at DESC
                    """)
                else:
                    cursor.execute("""
                        SELECT id, email, username, role, subscription_tier, 
                               created_at, last_login, active
                        FROM users
                        ORDER BY created_at DESC
                    """)
            else:
                if active_only:
                    cursor.execute("""
                        SELECT id, email, username, role, subscription_tier, 
                               created_at, last_login, active
                        FROM users
                        WHERE active = 1
                        ORDER BY created_at DESC
                    """)
                else:
                    cursor.execute("""
                        SELECT id, email, username, role, subscription_tier, 
                               created_at, last_login, active
                        FROM users
                        ORDER BY created_at DESC
                    """)
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'id': row[0],
                    'email': row[1],
                    'username': row[2],
                    'role': row[3],
                    'subscription_tier': row[4],
                    'created_at': row[5],
                    'last_login': row[6],
                    'active': bool(row[7])
                })
        
        return users
    
    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user fields"""
        allowed_fields = ['email', 'username', 'role', 'subscription_tier', 'active']
        updates = []
        values = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f"{field} = {'%s' if USE_POSTGRES else '?'}")
                values.append(value)
        
        if not updates:
            return False
        
        values.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = {'%s' if USE_POSTGRES else '?'}"
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, values)
            return cursor.rowcount > 0
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            else:
                cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            
            return cursor.rowcount > 0
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """Change user password"""
        if len(new_password) < 8:
            raise ValueError("Password must be at least 8 characters")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
            else:
                cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return False
            
            if not self.verify_password(old_password, result[0]):
                raise ValueError("Incorrect current password")
            
            new_hash = self.hash_password(new_password)
            
            if USE_POSTGRES:
                cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", 
                              (new_hash, user_id))
            else:
                cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", 
                              (new_hash, user_id))
            
            return True
    
    def create_admin(self, email: str, username: str, password: str) -> int:
        """Create an admin user"""
        return self.register_user(email, username, password, role='admin')
    
    # ============ API Key Management ============
    
    def save_api_keys(self, user_id: int, binance_api_key: str = None, 
                     binance_api_secret: str = None, telegram_bot_token: str = None,
                     telegram_chat_id: str = None, trading_enabled: bool = False) -> bool:
        """Save or update user's API keys (encrypted)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Encrypt sensitive values
            encrypted_api_key = encrypt_value(binance_api_key) if binance_api_key else ""
            encrypted_api_secret = encrypt_value(binance_api_secret) if binance_api_secret else ""
            encrypted_telegram = encrypt_value(telegram_bot_token) if telegram_bot_token else ""
            
            if USE_POSTGRES:
                cursor.execute("""
                    INSERT INTO user_api_keys 
                    (user_id, binance_api_key, binance_api_secret, telegram_bot_token, 
                     telegram_chat_id, trading_enabled, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        binance_api_key = EXCLUDED.binance_api_key,
                        binance_api_secret = EXCLUDED.binance_api_secret,
                        telegram_bot_token = EXCLUDED.telegram_bot_token,
                        telegram_chat_id = EXCLUDED.telegram_chat_id,
                        trading_enabled = EXCLUDED.trading_enabled,
                        updated_at = EXCLUDED.updated_at
                """, (user_id, encrypted_api_key, encrypted_api_secret, 
                      encrypted_telegram, telegram_chat_id or "", trading_enabled,
                      datetime.now().isoformat()))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO user_api_keys 
                    (user_id, binance_api_key, binance_api_secret, telegram_bot_token, 
                     telegram_chat_id, trading_enabled, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, encrypted_api_key, encrypted_api_secret, 
                      encrypted_telegram, telegram_chat_id or "", trading_enabled,
                      datetime.now().isoformat()))
            
            print(f"✅ API keys saved for user {user_id}")
            return True
    
    def get_api_keys(self, user_id: int, decrypt: bool = True) -> Optional[Dict]:
        """Get user's API keys (optionally decrypted)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT binance_api_key, binance_api_secret, telegram_bot_token,
                           telegram_chat_id, trading_enabled, updated_at
                    FROM user_api_keys WHERE user_id = %s
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT binance_api_key, binance_api_secret, telegram_bot_token,
                           telegram_chat_id, trading_enabled, updated_at
                    FROM user_api_keys WHERE user_id = ?
                """, (user_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return None
            
            api_key, api_secret, telegram_token, telegram_chat, trading_enabled, updated_at = result
            
            if decrypt:
                return {
                    'binance_api_key': decrypt_value(api_key) if api_key else "",
                    'binance_api_secret': decrypt_value(api_secret) if api_secret else "",
                    'telegram_bot_token': decrypt_value(telegram_token) if telegram_token else "",
                    'telegram_chat_id': telegram_chat or "",
                    'trading_enabled': bool(trading_enabled),
                    'updated_at': updated_at
                }
            else:
                # Return masked values for display
                return {
                    'binance_api_key': api_key[:10] + "..." if api_key and len(api_key) > 10 else "",
                    'binance_api_secret': "••••••••" if api_secret else "",
                    'telegram_bot_token': "••••••••" if telegram_token else "",
                    'telegram_chat_id': telegram_chat or "",
                    'trading_enabled': bool(trading_enabled),
                    'has_binance_keys': bool(api_key and api_secret),
                    'has_telegram': bool(telegram_token and telegram_chat)
                }
    
    def has_api_keys(self, user_id: int) -> bool:
        """Check if user has configured API keys"""
        keys = self.get_api_keys(user_id, decrypt=False)
        return keys is not None and keys.get('has_binance_keys', False)
    
    # ============ Password Reset ============
    
    def generate_reset_token(self, email: str) -> Optional[str]:
        """Generate a password reset token for a user"""
        user = self.get_user_by_email(email)
        if not user:
            return None  # Don't reveal if email exists
        
        # Generate secure token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=1)  # 1 hour expiry
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Invalidate any existing tokens for this user
            if USE_POSTGRES:
                cursor.execute(
                    "UPDATE password_reset_tokens SET used = true WHERE user_id = %s",
                    (user['id'],)
                )
                cursor.execute("""
                    INSERT INTO password_reset_tokens (user_id, token, expires_at)
                    VALUES (%s, %s, %s)
                """, (user['id'], token, expires_at.isoformat()))
            else:
                cursor.execute(
                    "UPDATE password_reset_tokens SET used = 1 WHERE user_id = ?",
                    (user['id'],)
                )
                cursor.execute("""
                    INSERT INTO password_reset_tokens (user_id, token, expires_at)
                    VALUES (?, ?, ?)
                """, (user['id'], token, expires_at.isoformat()))
        
        print(f"✅ Reset token generated for {email}")
        return token
    
    def verify_reset_token(self, token: str) -> Optional[int]:
        """Verify a reset token and return user_id if valid"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT user_id, expires_at, used
                    FROM password_reset_tokens
                    WHERE token = %s
                """, (token,))
            else:
                cursor.execute("""
                    SELECT user_id, expires_at, used
                    FROM password_reset_tokens
                    WHERE token = ?
                """, (token,))
            
            result = cursor.fetchone()
            
            if not result:
                return None
            
            user_id, expires_at, used = result
            
            # Check if token is used
            if used:
                return None
            
            # Check if token is expired
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            
            if datetime.now() > expires_at:
                return None
            
            return user_id
    
    def reset_password_with_token(self, token: str, new_password: str) -> bool:
        """Reset password using a valid reset token"""
        if len(new_password) < 8:
            raise ValueError("Password must be at least 8 characters")
        
        user_id = self.verify_reset_token(token)
        if not user_id:
            raise ValueError("Invalid or expired reset token")
        
        new_hash = self.hash_password(new_password)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Update password
            if USE_POSTGRES:
                cursor.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (new_hash, user_id)
                )
                # Mark token as used
                cursor.execute(
                    "UPDATE password_reset_tokens SET used = true WHERE token = %s",
                    (token,)
                )
            else:
                cursor.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (new_hash, user_id)
                )
                cursor.execute(
                    "UPDATE password_reset_tokens SET used = 1 WHERE token = ?",
                    (token,)
                )
            
            # Revoke all sessions for this user (force re-login)
            if USE_POSTGRES:
                cursor.execute(
                    "UPDATE sessions SET revoked = true WHERE user_id = %s",
                    (user_id,)
                )
            else:
                cursor.execute(
                    "UPDATE sessions SET revoked = 1 WHERE user_id = ?",
                    (user_id,)
                )
        
        print(f"✅ Password reset for user {user_id}")
        return True
    
    def admin_reset_password(self, user_id: int, new_password: str) -> bool:
        """Admin function to reset a user's password directly"""
        if len(new_password) < 8:
            raise ValueError("Password must be at least 8 characters")
        
        new_hash = self.hash_password(new_password)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (new_hash, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (new_hash, user_id)
                )
            
            if cursor.rowcount == 0:
                return False
            
            # Revoke all sessions
            if USE_POSTGRES:
                cursor.execute(
                    "UPDATE sessions SET revoked = true WHERE user_id = %s",
                    (user_id,)
                )
            else:
                cursor.execute(
                    "UPDATE sessions SET revoked = 1 WHERE user_id = ?",
                    (user_id,)
                )
        
        print(f"✅ Admin password reset for user {user_id}")
        return True


def seed_initial_users():
    """Seed admin and initial user accounts"""
    manager = UserManager()
    
    # 1. Create Admin account
    try:
        admin_id = manager.create_admin(
            email="nyroxsystems@gmail.com",
            username="Nyrox",
            password="Test007!"
        )
        print(f"✅ Admin 'Nyrox' created (ID: {admin_id})")
    except ValueError as e:
        if "already" in str(e).lower():
            print(f"ℹ️ Admin 'Nyrox' already exists")
            # Get existing admin ID
            admin = manager.get_user_by_email("nyroxsystems@gmail.com")
            admin_id = admin['id'] if admin else None
        else:
            print(f"⚠️ Admin creation error: {e}")
            admin_id = None
    
    # 2. Create User account (Aaron) with Binance Keys from environment
    try:
        user_id = manager.register_user(
            email="vogtaaron0@gmail.com",
            username="Aaron",
            password="Masterlolli46_",
            role="user"
        )
        print(f"✅ User 'Aaron' created (ID: {user_id})")
        
        # Save the Binance/Telegram keys from environment
        binance_key = os.getenv("BINANCE_API_KEY", "")
        binance_secret = os.getenv("BINANCE_API_SECRET", "")
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        telegram_chat = os.getenv("TELEGRAM_CHAT_ID", "")
        
        if binance_key and binance_secret:
            manager.save_api_keys(
                user_id=user_id,
                binance_api_key=binance_key,
                binance_api_secret=binance_secret,
                telegram_bot_token=telegram_token,
                telegram_chat_id=telegram_chat,
                trading_enabled=True
            )
            print(f"✅ API keys saved for user 'Aaron'")
        else:
            print(f"⚠️ No Binance API keys in environment - skipping key setup")
            
    except ValueError as e:
        if "already" in str(e).lower():
            print(f"ℹ️ User 'Aaron' already exists")
        else:
            print(f"⚠️ User creation error: {e}")
    
    # List all users
    users = manager.list_users()
    print(f"\n📊 Total users: {len(users)}")
    for user in users:
        has_keys = manager.has_api_keys(user['id'])
        keys_status = "🔑" if has_keys else "❌"
        print(f"  - {user['username']} ({user['email']}) - {user['role']} {keys_status}")


# Initialize on import
if __name__ == "__main__":
    seed_initial_users()
