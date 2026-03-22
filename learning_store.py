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
        
        # One-time migration: re-score existing strategies with updated formula
        _rescore_migration_v2()
    except Exception as e:
        print(f"⚠️ Learning Store table creation error: {e}")


def _rescore_migration_v2():
    """One-time migration: re-score all existing strategies with the v5 formula.
    
    v5: Win Rate DOMINANT with RELIABILITY FILTERS.
    WR >= 99.5% = score 0, WR >= 90% with < 30 trades = score 0,
    WR >= 80% with < 10 trades = score 0, WR < 55% = score 0.
    Reliability gate raised to 10 trades, trade bonus requires 20 trades.
    Without this, old strategies with inflated scores block new ones forever.
    """
    if not USE_POSTGRES or not HAS_DB_ADAPTER:
        return
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if already migrated (v5 key — forces re-score from v4)
            cursor.execute("SELECT value FROM kv_store WHERE key = 'scoring_v5_migrated'")
            row = cursor.fetchone()
            if row:
                return  # Already done
            
            # Fetch all strategies
            cursor.execute("SELECT id, metrics, score FROM learning_strategies")
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("""
                    INSERT INTO kv_store (key, value) VALUES ('scoring_v4_migrated', 'true')
                    ON CONFLICT (key) DO UPDATE SET value = 'true'
                """)
                return
            
            updated = 0
            for row_id, metrics_raw, old_score in rows:
                metrics = metrics_raw if isinstance(metrics_raw, dict) else json.loads(metrics_raw)
                
                # v5 scoring formula (must match continuous_backtester.calculate_score)
                win_rate = metrics.get('win_rate', 0)
                total_trades = metrics.get('total_trades', 0)
                
                # FAKE GATES: reject unrealistically perfect strategies
                if win_rate >= 99.5:
                    new_score = 0.0
                elif win_rate >= 90.0 and total_trades < 30:
                    new_score = 0.0
                elif win_rate >= 80.0 and total_trades < 10:
                    new_score = 0.0
                # KILL GATE: WR < 55% = instant death
                elif win_rate < 55.0:
                    new_score = 0.0
                else:
                    new_score = 0.0
                    new_score += win_rate * 10.0
                    # Tier bonuses
                    if win_rate > 58: new_score += 100.0
                    if win_rate > 62: new_score += 250.0
                    if win_rate > 66: new_score += 500.0
                    if win_rate > 70: new_score += 800.0
                    # ROI tiebreaker
                    new_score += metrics.get('roi', 0) * 3.0
                    # Sharpe capped
                    new_score += min(metrics.get('sharpe_ratio', 0), 3.0) * 2.0
                    # Drawdown penalty
                    new_score -= metrics.get('max_drawdown', 0) * 2.0
                    # Trade count bonus (need ≥20 for full credit)
                    new_score += min(total_trades / 20, 1.0) * 50
                    # Reliability gate: <10 trades = divide by 10
                    if total_trades < 10:
                        new_score *= 0.1
                
                if abs(new_score - old_score) > 0.1:
                    cursor.execute(
                        "UPDATE learning_strategies SET score = %s WHERE id = %s",
                        (round(new_score, 2), row_id)
                    )
                    updated += 1
            
            # Mark migration as done
            cursor.execute("""
                INSERT INTO kv_store (key, value) VALUES ('scoring_v5_migrated', 'true')
                ON CONFLICT (key) DO UPDATE SET value = 'true'
            """)
            
            if updated:
                print(f"🔄 SCORING v5 MIGRATION: re-scored {updated}/{len(rows)} strategies (with fake gates)")
            else:
                print("✅ Scoring v5: all strategies already have correct scores")
    except Exception as e:
        print(f"⚠️ Scoring v4 migration error: {e}")
    
    # === v5 MIGRATION: Purge fake 100% WR strategies ===
    # The old backtester deleted all strategies with WR < 50%, so only "100% WR"
    # strategies survived. Their stored metrics are fake — tiny TP targets that
    # always hit, with losses hidden. These block new honest strategies.
    # Fix: set score=0 for any strategy with exactly 100% WR.
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT value FROM kv_store WHERE key = 'scoring_v5_purge_fake_wr'")
            row = cursor.fetchone()
            if row:
                pass  # v5 already done, fall through to v6
            else:
                # Use proper JSONB extraction instead of fragile string matching
                cursor.execute("""
                    UPDATE learning_strategies 
                    SET score = 0
                    WHERE CAST(metrics->>'win_rate' AS FLOAT) >= 99.9
                      AND score > 0
                """)
                purged = cursor.rowcount
                
                # Also purge strategies with WR > 95% and fewer than 20 trades
                cursor.execute("""
                    UPDATE learning_strategies 
                    SET score = 0
                    WHERE CAST(metrics->>'win_rate' AS FLOAT) > 95.0
                      AND CAST(metrics->>'total_trades' AS INTEGER) < 20
                      AND score > 0
                """)
                purged2 = cursor.rowcount
                
                cursor.execute("""
                    INSERT INTO kv_store (key, value) VALUES ('scoring_v5_purge_fake_wr', 'true')
                    ON CONFLICT (key) DO UPDATE SET value = 'true'
                """)
                
                if purged + purged2 > 0:
                    print(f"🧹 PURGE v5: Zeroed {purged} fake-100%-WR + {purged2} suspicious >95%-WR strategies")
                else:
                    print("✅ Purge v5: no fake strategies found")
    except Exception as e:
        print(f"⚠️ Purge v5 error: {e}")
    
    # === v6 MIGRATION: Aggressive purge of ALL unrealistic strategies ===
    # v5 was insufficient — string matching missed many 100% WR entries.
    # v6 uses robust JSONB queries and also catches:
    # - ANY 100% WR strategy (no legitimate strategy is perfect)
    # - WR >= 90% with < 30 trades (statistically meaningless)
    # - WR >= 80% with < 10 trades (too few samples)
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT value FROM kv_store WHERE key = 'scoring_v6_aggressive_purge'")
            row = cursor.fetchone()
            if row:
                return  # Already done
            
            # 1. Kill ALL 100% WR strategies — no real strategy is perfect
            cursor.execute("""
                UPDATE learning_strategies 
                SET score = 0
                WHERE CAST(metrics->>'win_rate' AS FLOAT) >= 99.5
                  AND score > 0
            """)
            purged_perfect = cursor.rowcount
            
            # 2. Kill WR >= 90% with fewer than 30 trades (statistically meaningless)
            cursor.execute("""
                UPDATE learning_strategies 
                SET score = 0
                WHERE CAST(metrics->>'win_rate' AS FLOAT) >= 90.0
                  AND CAST(metrics->>'total_trades' AS INTEGER) < 30
                  AND score > 0
            """)
            purged_suspicious = cursor.rowcount
            
            # 3. Kill WR >= 80% with fewer than 10 trades (way too few samples)
            cursor.execute("""
                UPDATE learning_strategies 
                SET score = 0
                WHERE CAST(metrics->>'win_rate' AS FLOAT) >= 80.0
                  AND CAST(metrics->>'total_trades' AS INTEGER) < 10
                  AND score > 0
            """)
            purged_tiny = cursor.rowcount
            
            cursor.execute("""
                INSERT INTO kv_store (key, value) VALUES ('scoring_v6_aggressive_purge', 'true')
                ON CONFLICT (key) DO UPDATE SET value = 'true'
            """)
            
            total_purged = purged_perfect + purged_suspicious + purged_tiny
            if total_purged > 0:
                print(f"🧹 PURGE v6: Zeroed {purged_perfect} perfect-WR + {purged_suspicious} suspicious-WR + {purged_tiny} tiny-sample strategies")
            else:
                print("✅ Purge v6: no unrealistic strategies found")
    except Exception as e:
        print(f"⚠️ Purge v6 error: {e}")


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


def get_top_n_strategies(n: int = 3) -> List[Dict]:
    """Get top N strategies for ensemble use (sorted by score DESC)."""
    strategies = get_all_strategies(limit=n)
    return strategies[:n]


# ═══════════════════════════════════════════
# PostgreSQL implementations
# ═══════════════════════════════════════════


def _pg_save_strategy(strategy: Dict):
    """Save strategy to PostgreSQL with deduplication.
    
    Counter logic: total_tested increments AFTER successful insert,
    so deduped/skipped strategies don't inflate the count.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            score = strategy.get("score", 0)
            metrics = strategy.get("metrics", {})
            
            # DEDUP: Skip if a strategy with very similar score AND same win_rate already exists
            cursor.execute("""
                SELECT COUNT(*) FROM learning_strategies
                WHERE ABS(score - %s) < 1.0
                AND ABS(CAST(metrics->>'win_rate' AS FLOAT) - %s) < 0.1
            """, (
                score,
                float(metrics.get("win_rate", -1))
            ))
            if cursor.fetchone()[0] > 0:
                return  # Skip duplicate — do NOT increment counters
            
            # Apply reliability filter before saving: reject fake-looking strategies
            win_rate = float(metrics.get("win_rate", 0))
            total_trades = int(metrics.get("total_trades", 0))
            if win_rate >= 99.5:  # No real strategy is 100% WR
                score = 0
            elif win_rate >= 90.0 and total_trades < 30:
                score = 0  # Statistically meaningless
            elif win_rate >= 80.0 and total_trades < 10:
                score = 0  # Way too few samples
            
            cursor.execute("""
                INSERT INTO learning_strategies (params, metrics, score, applied, data_source)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                json.dumps(strategy.get("params", {})),
                json.dumps(metrics),
                score,
                strategy.get("applied", False),
                strategy.get("data_source", "historical_binance")
            ))

            # Increment counters AFTER successful insert (not before dedup)
            cursor.execute("""
                INSERT INTO kv_store (key, value) VALUES ('total_strategies_tested', '1')
                ON CONFLICT (key) DO UPDATE SET value = (COALESCE(kv_store.value::int, 0) + 1)::text
            """)
            today_key = f"strategies_tested_{datetime.now().strftime('%Y-%m-%d')}"
            cursor.execute("""
                INSERT INTO kv_store (key, value) VALUES (%s, '1')
                ON CONFLICT (key) DO UPDATE SET value = (COALESCE(kv_store.value::int, 0) + 1)::text
            """, (today_key,))
            hour_key = f"strategies_tested_{datetime.now().strftime('%Y-%m-%d_%H')}"
            cursor.execute("""
                INSERT INTO kv_store (key, value) VALUES (%s, '1')
                ON CONFLICT (key) DO UPDATE SET value = (COALESCE(kv_store.value::int, 0) + 1)::text
            """, (hour_key,))

            # Keep only top 1000 strategies (prune old low-scorers)
            cursor.execute("""
                DELETE FROM learning_strategies
                WHERE id NOT IN (
                    SELECT id FROM learning_strategies
                    ORDER BY score DESC
                    LIMIT 1000
                )
            """)
    except Exception as e:
        print(f"❌ PG save strategy error: {e}")


def _pg_set_current(strategy: Dict):
    """Set current strategy in PostgreSQL using upsert."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Clear old applied flags
            cursor.execute("UPDATE learning_strategies SET applied = FALSE WHERE applied = TRUE")
            # Mark the current strategy as applied (match by score)
            score = strategy.get("score", 0)
            cursor.execute("""
                UPDATE learning_strategies SET applied = TRUE
                WHERE id = (
                    SELECT id FROM learning_strategies
                    WHERE ABS(score - %s) < 0.5
                    ORDER BY score DESC LIMIT 1
                )
            """, (score,))
            # Upsert into current_strategy table
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

            # Total — use lifetime counter from kv_store if available
            total_tested = 0
            try:
                cursor.execute("SELECT value FROM kv_store WHERE key = 'total_strategies_tested'")
                kv_row = cursor.fetchone()
                if kv_row:
                    total_tested = int(kv_row[0])
            except Exception:
                pass
            if total_tested == 0:
                cursor.execute("SELECT COUNT(*) FROM learning_strategies")
                total_tested = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COALESCE(MAX(score), 0) FROM learning_strategies")
            best_score = cursor.fetchone()[0] or 0  # No cap — reliability multiplier handles inflated scores

            # Applied count
            cursor.execute("SELECT COUNT(*) FROM learning_strategies WHERE applied = TRUE")
            applied_row = cursor.fetchone()
            total_applied = applied_row[0] or 0

            # Today's count — use daily kv_store counter
            today_tested = 0
            try:
                today_key = f"strategies_tested_{datetime.now().strftime('%Y-%m-%d')}"
                cursor.execute("SELECT value FROM kv_store WHERE key = %s", (today_key,))
                today_kv = cursor.fetchone()
                if today_kv:
                    today_tested = int(today_kv[0])
            except Exception:
                pass
            if today_tested == 0:
                cursor.execute("""
                    SELECT COUNT(*) FROM learning_strategies
                    WHERE created_at >= CURRENT_DATE
                """)
                today_tested = cursor.fetchone()[0] or 0

            # This hour's count — use kv_store hourly counter (counts ALL tested, not just saved)
            this_hour_tested = 0
            try:
                hour_key = f"strategies_tested_{datetime.now().strftime('%Y-%m-%d_%H')}"
                cursor.execute("SELECT value FROM kv_store WHERE key = %s", (hour_key,))
                hour_kv = cursor.fetchone()
                if hour_kv:
                    this_hour_tested = int(hour_kv[0])
            except Exception:
                pass
            if this_hour_tested == 0:
                # Fallback: count DB rows created this hour
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
