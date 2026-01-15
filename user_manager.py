"""
User Manager for SaaS Trading Platform
Handles user registration, authentication, and management
Uses PostgreSQL in production, SQLite for local development
"""

import os
import secrets
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta
import jwt
import bcrypt

# Import database adapter
from db_adapter import get_db_connection, USE_POSTGRES

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


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
                    email_verified BOOLEAN DEFAULT false
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
                    email_verified BOOLEAN DEFAULT 0
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
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
        
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
            
            # Store session
            if USE_POSTGRES:
                cursor.execute("""
                    INSERT INTO sessions (user_id, token, expires_at)
                    VALUES (%s, %s, %s)
                """, (user_id, token, 
                      (datetime.now() + timedelta(hours=JWT_EXPIRATION_HOURS)).isoformat()))
            else:
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


# Initialize on import
if __name__ == "__main__":
    # Test the user manager
    manager = UserManager()
    
    # Create admin user if not exists
    try:
        admin_id = manager.create_admin(
            email="admin@ethbot.com",
            username="admin",
            password="admin123456"  # Change this!
        )
        print(f"✅ Admin user created (ID: {admin_id})")
    except ValueError as e:
        print(f"ℹ️ Admin user already exists or: {e}")
    
    # List all users
    users = manager.list_users()
    print(f"\n📊 Total users: {len(users)}")
    for user in users:
        print(f"  - {user['username']} ({user['email']}) - {user['role']}")
