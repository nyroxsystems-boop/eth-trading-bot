"""
Brain Store — PostgreSQL persistence for the Trading Brain.

Stores brain memory, strategies, patterns, and ML models in Postgres
so they survive Railway deploys. Falls back to JSON files locally.

Uses the existing db_adapter.py connection pool.
"""
import os
import json
import logging
import pickle
import base64
from datetime import datetime, timezone
from typing import Optional, Dict

logger = logging.getLogger("ethbot.brain_store")

# Check if Postgres is available
try:
    from db_adapter import get_db_connection, USE_POSTGRES
    HAS_DB = True
except ImportError:
    HAS_DB = False
    USE_POSTGRES = False


def ensure_brain_tables():
    """Create brain tables in PostgreSQL."""
    if not USE_POSTGRES or not HAS_DB:
        return

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS brain_state (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

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

        logger.info("✅ Brain/Swarm Postgres tables ready")
    except Exception as e:
        logger.warning(f"Brain table creation error: {e}")


# ═══════════════════════════════════════════════════════════════════
# BRAIN MEMORY PERSISTENCE
# ═══════════════════════════════════════════════════════════════════

def save_brain_memory(memory: dict):
    """Save brain memory to Postgres."""
    if not USE_POSTGRES or not HAS_DB:
        return False

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO brain_state (key, value, updated_at)
                VALUES ('memory', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """, (json.dumps(memory, ensure_ascii=False),))
        return True
    except Exception as e:
        logger.warning(f"Brain memory save failed: {e}")
        return False


def load_brain_memory() -> Optional[dict]:
    """Load brain memory from Postgres."""
    if not USE_POSTGRES or not HAS_DB:
        return None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM brain_state WHERE key = 'memory'")
            row = cursor.fetchone()
            if row:
                data = row[0]
                return data if isinstance(data, dict) else json.loads(data)
    except Exception as e:
        logger.warning(f"Brain memory load failed: {e}")
    return None


def save_brain_strategies(strategies: dict):
    """Save strategy performance data to Postgres."""
    if not USE_POSTGRES or not HAS_DB:
        return False

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO brain_state (key, value, updated_at)
                VALUES ('strategies', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """, (json.dumps(strategies, ensure_ascii=False),))
        return True
    except Exception as e:
        logger.warning(f"Brain strategies save failed: {e}")
        return False


def load_brain_strategies() -> Optional[dict]:
    """Load strategy data from Postgres."""
    if not USE_POSTGRES or not HAS_DB:
        return None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM brain_state WHERE key = 'strategies'")
            row = cursor.fetchone()
            if row:
                data = row[0]
                return data if isinstance(data, dict) else json.loads(data)
    except Exception as e:
        logger.warning(f"Brain strategies load failed: {e}")
    return None


def save_brain_patterns(patterns: dict):
    """Save discovered patterns to Postgres."""
    if not USE_POSTGRES or not HAS_DB:
        return False

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO brain_state (key, value, updated_at)
                VALUES ('patterns', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """, (json.dumps(patterns, ensure_ascii=False),))
        return True
    except Exception as e:
        logger.warning(f"Brain patterns save failed: {e}")
        return False


def load_brain_patterns() -> Optional[dict]:
    """Load discovered patterns from Postgres."""
    if not USE_POSTGRES or not HAS_DB:
        return None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM brain_state WHERE key = 'patterns'")
            row = cursor.fetchone()
            if row:
                data = row[0]
                return data if isinstance(data, dict) else json.loads(data)
    except Exception as e:
        logger.warning(f"Brain patterns load failed: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════
# ML MODEL PERSISTENCE
# ═══════════════════════════════════════════════════════════════════

def save_ml_model(model, feature_cols: list, accuracy: float, train_count: int):
    """Save trained ML model to Postgres as base64-encoded pickle."""
    if not USE_POSTGRES or not HAS_DB:
        return False

    try:
        model_bytes = pickle.dumps(model)
        model_b64 = base64.b64encode(model_bytes).decode('ascii')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO brain_ml_model (id, model_blob, feature_cols, accuracy, train_count, updated_at)
                VALUES (1, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE
                SET model_blob = EXCLUDED.model_blob,
                    feature_cols = EXCLUDED.feature_cols,
                    accuracy = EXCLUDED.accuracy,
                    train_count = EXCLUDED.train_count,
                    updated_at = CURRENT_TIMESTAMP
            """, (model_b64, json.dumps(feature_cols), accuracy, train_count))
        logger.info(f"🧠 ML model saved to Postgres ({len(model_b64)} bytes)")
        return True
    except Exception as e:
        logger.warning(f"ML model save failed: {e}")
        return False


def load_ml_model():
    """Load ML model from Postgres. Returns (model, feature_cols, accuracy) or (None, None, None)."""
    if not USE_POSTGRES or not HAS_DB:
        return None, None, None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT model_blob, feature_cols, accuracy FROM brain_ml_model WHERE id = 1")
            row = cursor.fetchone()
            if row and row[0]:
                model_bytes = base64.b64decode(row[0])
                model = pickle.loads(model_bytes)
                feature_cols = row[1] if isinstance(row[1], list) else json.loads(row[1]) if row[1] else []
                accuracy = row[2] or 0.0
                logger.info(f"🧠 ML model loaded from Postgres (accuracy: {accuracy:.1%})")
                return model, feature_cols, accuracy
    except Exception as e:
        logger.warning(f"ML model load failed: {e}")
    return None, None, None


# ═══════════════════════════════════════════════════════════════════
# SWARM AGENT PERSISTENCE
# ═══════════════════════════════════════════════════════════════════

def save_swarm_agent(agent_name: str, weight: float, total_votes: int,
                     correct_votes: int, accuracy: float, recent_results: list):
    """Save a single swarm agent's state to Postgres."""
    if not USE_POSTGRES or not HAS_DB:
        return False

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO swarm_agents (agent_name, weight, total_votes, correct_votes, accuracy, recent_results, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (agent_name) DO UPDATE
                SET weight = EXCLUDED.weight,
                    total_votes = EXCLUDED.total_votes,
                    correct_votes = EXCLUDED.correct_votes,
                    accuracy = EXCLUDED.accuracy,
                    recent_results = EXCLUDED.recent_results,
                    updated_at = CURRENT_TIMESTAMP
            """, (agent_name, weight, total_votes, correct_votes, accuracy,
                  json.dumps(recent_results[-50:])))
        return True
    except Exception as e:
        logger.debug(f"Swarm agent save failed: {e}")
        return False


def save_all_swarm_agents(agents: list):
    """Batch save all swarm agents."""
    if not USE_POSTGRES or not HAS_DB:
        return False

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for agent in agents:
                cursor.execute("""
                    INSERT INTO swarm_agents (agent_name, weight, total_votes, correct_votes, accuracy, recent_results, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (agent_name) DO UPDATE
                    SET weight = EXCLUDED.weight,
                        total_votes = EXCLUDED.total_votes,
                        correct_votes = EXCLUDED.correct_votes,
                        accuracy = EXCLUDED.accuracy,
                        recent_results = EXCLUDED.recent_results,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    agent.name, agent.weight, agent.total_votes,
                    agent.correct_votes, agent.accuracy,
                    json.dumps(agent._recent_results[-50:])
                ))
        return True
    except Exception as e:
        logger.warning(f"Swarm batch save failed: {e}")
        return False


def load_swarm_agents() -> Dict[str, dict]:
    """Load all swarm agent states from Postgres. Returns {name: {weight, total_votes, ...}}."""
    if not USE_POSTGRES or not HAS_DB:
        return {}

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT agent_name, weight, total_votes, correct_votes, accuracy, recent_results FROM swarm_agents")
            rows = cursor.fetchall()
            agents = {}
            for row in rows:
                results = row[5]
                if isinstance(results, str):
                    results = json.loads(results)
                agents[row[0]] = {
                    "weight": row[1],
                    "total_votes": row[2],
                    "correct_votes": row[3],
                    "accuracy": row[4],
                    "recent_results": results or [],
                }
            if agents:
                logger.info(f"🐝 Swarm: loaded {len(agents)} agent states from Postgres")
            return agents
    except Exception as e:
        logger.warning(f"Swarm agent load failed: {e}")
    return {}


# Initialize tables on import
if USE_POSTGRES and HAS_DB:
    ensure_brain_tables()
