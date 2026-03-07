"""
Learning Store - PostgreSQL-backed storage for auto-learning strategies.

Uses the existing db_adapter.py connection pool (DATABASE_URL on Railway).
Falls back to local JSON files if DATABASE_URL is not set (local dev).
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Check if PostgreSQL is available via db_adapter
try:
    from db_adapter import get_db_connection, USE_POSTGRES, convert_placeholders
    HAS_DB_ADAPTER = True
except ImportError:
    HAS_DB_ADAPTER = False
    USE_POSTGRES = False

# Fallback paths for local dev
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
STRATEGIES_FILE = LOG_DIR / "tested_strategies.json"
CURRENT_STRATEGY_FILE = LOG_DIR / "current_strategy.json"


def ensure_learning_tables():
    """Create learning tables in PostgreSQL (or skip for local dev fallback)."""
    if not USE_POSTGRES or not HAS_DB_ADAPTER:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        print("📁 Learning Store: using local JSON files (no DATABASE_URL)")
        return

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Main strategies table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_strategies (
                    id SERIAL PRIMARY KEY,
                    params JSONB NOT NULL,
                    metrics JSONB NOT NULL,
                    score REAL NOT NULL,
                    applied BOOLEAN DEFAULT FALSE,
                    applied_at TIMESTAMP,
                    data_source TEXT DEFAULT 'historical_binance',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Current (best applied) strategy
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_current_strategy (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    strategy JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for fast score lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_learning_strategies_score
                ON learning_strategies (score DESC)
            """)

            # Index for time-based queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_learning_strategies_created
                ON learning_strategies (created_at)
            """)

        print("✅ Learning Store: PostgreSQL tables ready")
    except Exception as e:
        print(f"⚠️ Learning Store table creation error: {e}")


# ─── Write Operations ───


def save_strategy(strategy: Dict):
    """Save a tested strategy."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        _pg_save_strategy(strategy)
    else:
        _json_save_strategy(strategy)


def set_current_strategy(strategy: Dict):
    """Set the currently applied strategy."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        _pg_set_current(strategy)
    else:
        _json_set_current(strategy)


# ─── Read Operations ───


def get_all_strategies(limit: int = 200) -> List[Dict]:
    """Get top strategies sorted by score descending."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        return _pg_get_strategies(limit)
    else:
        return _json_get_strategies(limit)


def get_current_strategy() -> Optional[Dict]:
    """Get the currently applied strategy."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        return _pg_get_current()
    else:
        return _json_get_current()


def get_learning_stats() -> Dict:
    """Get aggregated learning statistics."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        return _pg_get_stats()
    else:
        return _json_get_stats()


def get_evolution(days: int = 7) -> List[Dict]:
    """Get daily best score evolution."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        return _pg_get_evolution(days)
    else:
        return _json_get_evolution(days)


# ═══════════════════════════════════════════
# PostgreSQL implementations
# ═══════════════════════════════════════════


def _pg_save_strategy(strategy: Dict):
    """Save strategy to PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO learning_strategies (params, metrics, score, applied, data_source)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                json.dumps(strategy.get("params", {})),
                json.dumps(strategy.get("metrics", {})),
                strategy.get("score", 0),
                strategy.get("applied", False),
                strategy.get("data_source", "historical_binance")
            ))

            # Keep only top 500 strategies (prune old low-scorers)
            cursor.execute("""
                DELETE FROM learning_strategies
                WHERE id NOT IN (
                    SELECT id FROM learning_strategies
                    ORDER BY score DESC
                    LIMIT 500
                )
            """)
    except Exception as e:
        print(f"❌ PG save strategy error: {e}")


def _pg_set_current(strategy: Dict):
    """Set current strategy in PostgreSQL using upsert."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO learning_current_strategy (id, strategy, updated_at)
                VALUES (1, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE
                SET strategy = EXCLUDED.strategy,
                    updated_at = CURRENT_TIMESTAMP
            """, (json.dumps(strategy),))
    except Exception as e:
        print(f"❌ PG set current strategy error: {e}")


def _pg_get_strategies(limit: int) -> List[Dict]:
    """Get top strategies from PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT params, metrics, score, applied, data_source, created_at
                FROM learning_strategies
                ORDER BY score DESC
                LIMIT %s
            """, (limit,))

            rows = cursor.fetchall()
            strategies = []
            for row in rows:
                params_data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                metrics_data = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                strategies.append({
                    "params": params_data,
                    "metrics": metrics_data,
                    "score": row[2],
                    "applied": row[3],
                    "data_source": row[4],
                    "timestamp": row[5].isoformat() if row[5] else datetime.now().isoformat()
                })
            return strategies
    except Exception as e:
        print(f"❌ PG get strategies error: {e}")
        return []


def _pg_get_current() -> Optional[Dict]:
    """Get current strategy from PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT strategy FROM learning_current_strategy WHERE id = 1")
            row = cursor.fetchone()
            if row:
                return row[0] if isinstance(row[0], dict) else json.loads(row[0])
            return None
    except Exception as e:
        print(f"❌ PG get current strategy error: {e}")
        return None


def _pg_get_stats() -> Dict:
    """Get aggregated stats from PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Total & best
            cursor.execute("SELECT COUNT(*), COALESCE(MAX(score), 0) FROM learning_strategies")
            total_row = cursor.fetchone()
            total_tested = total_row[0] or 0
            best_score = min(total_row[1] or 0, 500)  # Cap insane scores

            # Applied count
            cursor.execute("SELECT COUNT(*) FROM learning_strategies WHERE applied = TRUE")
            applied_row = cursor.fetchone()
            total_applied = applied_row[0] or 0

            # Today's count
            cursor.execute("""
                SELECT COUNT(*) FROM learning_strategies
                WHERE created_at >= CURRENT_DATE
            """)
            today_row = cursor.fetchone()
            today_tested = today_row[0] or 0

            # This hour's count
            cursor.execute("""
                SELECT COUNT(*) FROM learning_strategies
                WHERE created_at >= NOW() - INTERVAL '1 hour'
            """)
            hour_row = cursor.fetchone()
            this_hour_tested = hour_row[0] or 0

            # Top 10 strategies for display
            cursor.execute("""
                SELECT params, metrics, score, applied, data_source, created_at
                FROM learning_strategies
                ORDER BY score DESC
                LIMIT 10
            """)
            top_strategies = []
            for row in cursor.fetchall():
                params_data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                metrics_data = row[1] if isinstance(row[1], dict) else json.loads(row[1])
                top_strategies.append({
                    "params": params_data,
                    "metrics": metrics_data,
                    "score": row[2],
                    "applied": row[3],
                    "data_source": row[4],
                    "timestamp": row[5].isoformat() if row[5] else ""
                })

            current = _pg_get_current()

            return {
                "stats": {
                    "total_tested": total_tested,
                    "best_score": round(best_score, 2),
                    "total_applied": total_applied,
                    "today_tested": today_tested,
                    "this_hour_tested": this_hour_tested
                },
                "strategies": top_strategies,
                "current_strategy": current
            }
    except Exception as e:
        print(f"❌ PG get stats error: {e}")
        return {
            "stats": {"total_tested": 0, "best_score": 0, "total_applied": 0,
                       "today_tested": 0, "this_hour_tested": 0},
            "strategies": [],
            "current_strategy": None
        }


def _pg_get_evolution(days: int) -> List[Dict]:
    """Get daily best score evolution from PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DATE(created_at) AS day, MAX(score) AS best_score
                FROM learning_strategies
                WHERE created_at >= NOW() - INTERVAL '%s days'
                GROUP BY DATE(created_at)
                ORDER BY day
            """ % int(days))  # Safe: days is always an int

            return [
                {"date": row[0].isoformat(), "best_score": round(row[1], 2)}
                for row in cursor.fetchall()
            ]
    except Exception as e:
        print(f"❌ PG get evolution error: {e}")
        return []


# ═══════════════════════════════════════════
# JSON fallback implementations (local dev)
# ═══════════════════════════════════════════


def _json_save_strategy(strategy: Dict):
    """Save strategy to JSON file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    all_strategies = _json_load_all()
    all_strategies.append(strategy)
    all_strategies.sort(key=lambda x: x.get("score", 0), reverse=True)
    all_strategies = all_strategies[:200]

    with open(STRATEGIES_FILE, "w") as f:
        json.dump(all_strategies, f, indent=2)


def _json_set_current(strategy: Dict):
    """Set current strategy in JSON file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CURRENT_STRATEGY_FILE, "w") as f:
        json.dump(strategy, f, indent=2)


def _json_load_all() -> List[Dict]:
    """Load all strategies from JSON."""
    if STRATEGIES_FILE.exists():
        try:
            with open(STRATEGIES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _json_get_strategies(limit: int) -> List[Dict]:
    """Get top strategies from JSON."""
    strategies = _json_load_all()
    strategies.sort(key=lambda x: x.get("score", 0), reverse=True)
    return strategies[:limit]


def _json_get_current() -> Optional[Dict]:
    """Get current strategy from JSON."""
    if CURRENT_STRATEGY_FILE.exists():
        try:
            with open(CURRENT_STRATEGY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _json_get_stats() -> Dict:
    """Get stats from JSON files."""
    strategies = _json_load_all()
    total = len(strategies)
    best = max([s.get("score", 0) for s in strategies]) if strategies else 0
    applied = len([s for s in strategies if s.get("applied", False)])

    today = datetime.now().date().isoformat()
    today_tested = len([s for s in strategies if s.get("timestamp", "").startswith(today)])

    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    this_hour = len([s for s in strategies if s.get("timestamp", "") >= one_hour_ago])

    current = _json_get_current()

    sorted_strats = sorted(strategies, key=lambda x: x.get("score", 0), reverse=True)

    return {
        "stats": {
            "total_tested": total,
            "best_score": round(best, 2),
            "total_applied": applied,
            "today_tested": today_tested,
            "this_hour_tested": this_hour
        },
        "strategies": sorted_strats[:10],
        "current_strategy": current
    }


def _json_get_evolution(days: int) -> List[Dict]:
    """Get evolution from JSON files."""
    strategies = _json_load_all()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    daily_best = {}

    for s in strategies:
        ts = s.get("timestamp", "")
        if ts >= cutoff:
            date = ts[:10]
            score = s.get("score", 0)
            if date not in daily_best or score > daily_best[date]:
                daily_best[date] = score

    return [{"date": d, "best_score": round(s, 2)} for d, s in sorted(daily_best.items())]
