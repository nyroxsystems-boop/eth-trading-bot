"""
Database Adapter for SQLite and PostgreSQL
Provides unified interface for database operations
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional, Any, Tuple
from contextlib import contextmanager

# Check if PostgreSQL is available
try:
    import psycopg2
    import psycopg2.pool
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None and POSTGRES_AVAILABLE

# PostgreSQL connection pool
_pg_pool = None


def init_postgres_pool():
    """Initialize PostgreSQL connection pool"""
    global _pg_pool
    if USE_POSTGRES and _pg_pool is None:
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            dsn=DATABASE_URL
        )
        print("✅ PostgreSQL connection pool initialized")


def get_connection():
    """Get database connection (PostgreSQL or SQLite)"""
    if USE_POSTGRES:
        if _pg_pool is None:
            init_postgres_pool()
        return _pg_pool.getconn()
    else:
        # Fallback to SQLite for local development
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        db_path = log_dir / "ethbot.db"
        return sqlite3.connect(str(db_path))


def release_connection(conn):
    """Release database connection back to pool"""
    if USE_POSTGRES:
        if _pg_pool:
            _pg_pool.putconn(conn)
    else:
        conn.close()


@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_connection(conn)


def execute_query(query: str, params: Optional[Tuple] = None, fetch: str = None) -> Any:
    """
    Execute a database query
    
    Args:
        query: SQL query string
        params: Query parameters
        fetch: 'one', 'all', or None
    
    Returns:
        Query results or None
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Convert SQLite placeholders (?) to PostgreSQL ($1, $2, etc.)
        if USE_POSTGRES and params:
            query = convert_placeholders(query)
        
        cursor.execute(query, params or ())
        
        if fetch == 'one':
            return cursor.fetchone()
        elif fetch == 'all':
            return cursor.fetchall()
        elif fetch == 'lastrowid':
            if USE_POSTGRES:
                return cursor.fetchone()[0] if cursor.rowcount > 0 else None
            else:
                return cursor.lastrowid
        else:
            return cursor.rowcount


def convert_placeholders(query: str) -> str:
    """Convert SQLite ? placeholders to PostgreSQL %s."""
    if not USE_POSTGRES:
        return query
    
    # psycopg2 uses %s (not $1, $2 like asyncpg)
    # Simple replacement: ? → %s (outside of strings)
    parts = []
    in_string = False
    escape_next = False
    
    for char in query:
        if escape_next:
            parts.append(char)
            escape_next = False
            continue
            
        if char == '\\':
            escape_next = True
            parts.append(char)
            continue
            
        if char == "'":
            in_string = not in_string
            parts.append(char)
            continue
            
        if char == '?' and not in_string:
            parts.append('%s')
        else:
            parts.append(char)
    
    return ''.join(parts)


def convert_schema_to_postgres(schema: str) -> str:
    """Convert SQLite schema to PostgreSQL schema"""
    if not USE_POSTGRES:
        return schema
    
    # Replace AUTOINCREMENT with SERIAL
    schema = schema.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
    schema = schema.replace('AUTOINCREMENT', '')
    
    # Replace BOOLEAN with BOOLEAN (already compatible)
    # Replace TEXT with TEXT (already compatible)
    # Replace REAL with REAL (already compatible)
    
    # Replace TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    schema = schema.replace('TIMESTAMP DEFAULT CURRENT_TIMESTAMP', 
                          'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    
    return schema


def create_table(table_name: str, schema: str):
    """Create a table with the given schema"""
    schema = convert_schema_to_postgres(schema)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(schema)
        print(f"✅ Table '{table_name}' created")


def table_exists(table_name: str) -> bool:
    """Check if a table exists"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                )
            """, (table_name,))
        else:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, (table_name,))
        
        result = cursor.fetchone()
        return bool(result[0]) if result else False


# Initialize on import
if USE_POSTGRES:
    print("🐘 Using PostgreSQL database")
    init_postgres_pool()
else:
    print("📁 Using SQLite database (local development)")
