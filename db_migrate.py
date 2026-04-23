"""
DB Migration — Run on every startup to ensure correct schema.

1. Creates all v3 Bot tables if missing
2. Drops legacy SaaS tables that are no longer needed
3. Migrates CSV trades to Postgres if they exist
"""
import os
import logging

logger = logging.getLogger("ethbot.db_migrate")

# Legacy tables from old SaaS platform (safe to drop)
LEGACY_TABLES = [
    "accounts",
    "account_trades",
    "account_performance",
    "users",
    "user_settings",
    "user_api_keys",
    "user_trading_pairs",
    "sessions",
    "password_reset_tokens",
    "kv_store",
    "paper_trades",
    "trade_journal",
]

# Tables that are currently unused but not harmful — keep for now
KEEP_TABLES = [
    "edge_predictions",    # edge_validator.py (could be useful later)
    "market_data_1m",      # data_collector.py (historical data)
]


def run_migration():
    """Run database migration on startup."""
    try:
        from db_adapter import USE_POSTGRES, get_db_connection
        if not USE_POSTGRES:
            logger.info("📁 Using SQLite — no migration needed")
            return False
    except ImportError:
        logger.info("📁 No db_adapter — no migration needed")
        return False

    logger.info("🔧 Running database migration...")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # ── Step 1: Create v3 Bot tables ──
            logger.info("📦 Creating v3 bot tables...")

            # trades — core trade log
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp 
                ON trades(timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_pair 
                ON trades(pair)
            """)

            # brain_state — brain memory persistence
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS brain_state (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # brain_ml_model — ML model storage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS brain_ml_model (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    model_blob TEXT NOT NULL,
                    feature_cols JSONB,
                    accuracy REAL,
                    train_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # swarm_agents — swarm weight persistence
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS swarm_agents (
                    agent_name TEXT PRIMARY KEY,
                    weight REAL DEFAULT 1.0,
                    total_votes INTEGER DEFAULT 0,
                    correct_votes INTEGER DEFAULT 0,
                    accuracy REAL DEFAULT 0.5,
                    recent_results JSONB DEFAULT '[]',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            logger.info("✅ v3 bot tables ready (trades, brain_state, brain_ml_model, swarm_agents)")

            # ── Step 2: Drop legacy SaaS tables ──
            dropped = []
            for table in LEGACY_TABLES:
                try:
                    # Check if table exists first
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        )
                    """, (table,))
                    exists = cursor.fetchone()[0]
                    if exists:
                        cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                        dropped.append(table)
                except Exception as e:
                    logger.debug(f"Drop {table}: {e}")

            if dropped:
                logger.info(f"🗑️ Dropped {len(dropped)} legacy tables: {', '.join(dropped)}")
            else:
                logger.info("✅ No legacy tables to drop")

            # ── Step 3: Migrate CSV trades to Postgres ──
            _migrate_csv_trades(cursor)

        logger.info("✅ Database migration complete")
        return True

    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}")
        return False


def _migrate_csv_trades(cursor):
    """Import trades from CSV into Postgres if the table is empty."""
    import csv
    from pathlib import Path

    csv_path = Path("logs/trades.csv")
    if not csv_path.exists():
        return

    # Check if trades table already has data
    cursor.execute("SELECT COUNT(*) FROM trades")
    count = cursor.fetchone()[0]
    if count > 0:
        logger.info(f"✅ Postgres trades table has {count} rows — skip CSV migration")
        return

    # Import from CSV
    migrated = 0
    try:
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    cursor.execute(
                        """INSERT INTO trades (timestamp, action, pair, qty, price, pnl) 
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (
                            row.get("timestamp", ""),
                            row.get("action", ""),
                            row.get("pair", "ETHUSDT"),
                            float(row.get("qty", 0)),
                            float(row.get("price", 0)),
                            float(row.get("pnl", 0)),
                        )
                    )
                    migrated += 1
                except Exception:
                    pass
        logger.info(f"📥 Migrated {migrated} trades from CSV to Postgres")
    except Exception as e:
        logger.warning(f"CSV migration error: {e}")
