"""
Trade Persistence Layer — Stores trades in PostgreSQL for deploy survival.

On Railway, the CSV file is ephemeral (lost on every deploy).
This module writes trades to Postgres AND CSV (dual-write),
and reads from Postgres first, falling back to CSV.
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger("ethbot.trade_store")

# Check if PostgreSQL is available
USE_POSTGRES = False
try:
    from db_adapter import USE_POSTGRES as _UP, get_db_connection, execute_query
    USE_POSTGRES = _UP
except ImportError:
    pass


def init_trades_table():
    """Create trades table if it doesn't exist."""
    if not USE_POSTGRES:
        return
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    action VARCHAR(20) NOT NULL,
                    pair VARCHAR(30) DEFAULT 'ETHUSDT',
                    qty REAL NOT NULL,
                    price REAL NOT NULL,
                    pnl REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create index for fast lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp 
                ON trades(timestamp DESC)
            """)
        logger.info("✅ Trades table initialized in PostgreSQL")
    except Exception as e:
        logger.warning(f"Failed to init trades table: {e}")


def save_trade(timestamp: str, action: str, pair: str, qty: float, price: float, pnl: float = 0.0):
    """Save a trade to PostgreSQL (and CSV as backup)."""
    if not USE_POSTGRES:
        return  # CSV-only mode (local dev)
    
    try:
        execute_query(
            """INSERT INTO trades (timestamp, action, pair, qty, price, pnl) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (timestamp, action, pair, qty, price, pnl)
        )
    except Exception as e:
        logger.warning(f"Failed to save trade to Postgres: {e}")


def get_trades(limit: int = 50) -> List[Dict]:
    """Read trades from PostgreSQL, fallback to CSV."""
    if not USE_POSTGRES:
        return []  # Let the CSV reader handle it
    
    try:
        rows = execute_query(
            """SELECT timestamp, action, pair, qty, price, pnl 
               FROM trades ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
            fetch='all'
        )
        if rows:
            return [
                {
                    "timestamp": str(r[0]),
                    "action": r[1],
                    "pair": r[2] or "ETHUSDT",
                    "qty": float(r[3]),
                    "price": float(r[4]),
                    "pnl": float(r[5]),
                }
                for r in rows
            ]
    except Exception as e:
        logger.warning(f"Failed to read trades from Postgres: {e}")
    
    return []  # Empty = let CSV fallback handle it


def get_all_trades() -> List[Dict]:
    """Read ALL trades from PostgreSQL (for stats calculation)."""
    if not USE_POSTGRES:
        return []
    
    try:
        rows = execute_query(
            """SELECT timestamp, action, pair, qty, price, pnl 
               FROM trades ORDER BY timestamp ASC""",
            fetch='all'
        )
        if rows:
            return [
                {
                    "timestamp": str(r[0]),
                    "action": r[1],
                    "pair": r[2] or "ETHUSDT",
                    "qty": float(r[3]),
                    "price": float(r[4]),
                    "pnl": float(r[5]),
                }
                for r in rows
            ]
    except Exception as e:
        logger.warning(f"Failed to read all trades from Postgres: {e}")
    
    return []


def get_trade_count() -> int:
    """Get total trade count from Postgres."""
    if not USE_POSTGRES:
        return 0
    
    try:
        result = execute_query(
            "SELECT COUNT(*) FROM trades",
            fetch='one'
        )
        return result[0] if result else 0
    except Exception:
        return 0


def migrate_csv_to_postgres():
    """One-time migration: import existing CSV trades into Postgres."""
    if not USE_POSTGRES:
        return
    
    import csv
    from pathlib import Path
    
    trades_csv = Path(os.getenv("LOG_DIR", "logs")) / "trades.csv"
    if not trades_csv.exists():
        return
    
    existing = get_trade_count()
    if existing > 0:
        logger.info(f"Postgres already has {existing} trades, skipping CSV migration")
        return
    
    try:
        with open(trades_csv) as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                save_trade(
                    timestamp=row.get("timestamp", ""),
                    action=row.get("action", ""),
                    pair=row.get("pair", "ETHUSDT"),
                    qty=float(row.get("qty", 0)),
                    price=float(row.get("price", 0)),
                    pnl=float(row.get("pnl", 0)),
                )
                count += 1
        logger.info(f"✅ Migrated {count} trades from CSV to PostgreSQL")
    except Exception as e:
        logger.warning(f"CSV migration failed: {e}")


# Auto-init on import
if USE_POSTGRES:
    init_trades_table()
