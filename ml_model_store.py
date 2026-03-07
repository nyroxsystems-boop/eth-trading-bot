"""
ML Model Store - PostgreSQL-backed storage for trained ML models.

Stores serialized model weights (pickle/torch) in PostgreSQL BYTEA columns
so they survive Railway container deploys. Falls back to local filesystem.
"""

import os
import json
import pickle
import io
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Check if PostgreSQL is available
try:
    from db_adapter import get_db_connection, USE_POSTGRES
    HAS_DB_ADAPTER = True
except ImportError:
    HAS_DB_ADAPTER = False
    USE_POSTGRES = False

# Local fallback directory
MODEL_DIR = Path(os.getenv("LOG_DIR", "./logs")) / "ml_models"


def ensure_model_tables():
    """Create ml_models table in PostgreSQL."""
    if not USE_POSTGRES or not HAS_DB_ADAPTER:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        print("📁 ML Model Store: using local filesystem (no DATABASE_URL)")
        return

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ml_models (
                    model_name TEXT PRIMARY KEY,
                    model_data BYTEA NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    version INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        print("✅ ML Model Store: PostgreSQL table ready")
    except Exception as e:
        print(f"⚠️ ML Model Store table creation error: {e}")


def save_model(model_name: str, model_obj: Any, metadata: Optional[Dict] = None):
    """
    Save a trained model to persistent storage.
    
    Args:
        model_name: Unique identifier (e.g., 'dqn_agent', 'gradient_booster', 'ensemble')
        model_obj: The model object (must be pickle-serializable)
        metadata: Optional dict with accuracy, samples, hyperparams, etc.
    """
    if metadata is None:
        metadata = {}
    
    metadata['saved_at'] = datetime.now().isoformat()
    
    # Serialize model to bytes
    buffer = io.BytesIO()
    pickle.dump(model_obj, buffer)
    model_bytes = buffer.getvalue()
    
    metadata['size_bytes'] = len(model_bytes)
    
    if USE_POSTGRES and HAS_DB_ADAPTER:
        _pg_save_model(model_name, model_bytes, metadata)
    else:
        _local_save_model(model_name, model_bytes, metadata)
    
    size_kb = len(model_bytes) / 1024
    print(f"💾 Saved model '{model_name}' ({size_kb:.1f} KB)")


def load_model(model_name: str) -> Optional[Any]:
    """
    Load a trained model from persistent storage.
    
    Args:
        model_name: Model identifier
        
    Returns:
        Deserialized model object, or None if not found
    """
    if USE_POSTGRES and HAS_DB_ADAPTER:
        model_bytes = _pg_load_model(model_name)
    else:
        model_bytes = _local_load_model(model_name)
    
    if model_bytes is None:
        return None
    
    try:
        buffer = io.BytesIO(model_bytes)
        model_obj = pickle.load(buffer)
        print(f"📦 Loaded model '{model_name}' ({len(model_bytes)/1024:.1f} KB)")
        return model_obj
    except Exception as e:
        print(f"❌ Failed to deserialize model '{model_name}': {e}")
        return None


def get_model_info(model_name: str) -> Optional[Dict]:
    """Get metadata for a stored model without loading the full weights."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        return _pg_get_model_info(model_name)
    else:
        return _local_get_model_info(model_name)


def list_models() -> List[Dict]:
    """List all stored models with their metadata."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        return _pg_list_models()
    else:
        return _local_list_models()


def delete_model(model_name: str) -> bool:
    """Delete a stored model."""
    if USE_POSTGRES and HAS_DB_ADAPTER:
        return _pg_delete_model(model_name)
    else:
        return _local_delete_model(model_name)


# ═══════════════════════════════════════════
# PostgreSQL implementations
# ═══════════════════════════════════════════


def _pg_save_model(model_name: str, model_bytes: bytes, metadata: Dict):
    """Save model to PostgreSQL using upsert."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ml_models (model_name, model_data, metadata, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (model_name) DO UPDATE
                SET model_data = EXCLUDED.model_data,
                    metadata = EXCLUDED.metadata,
                    version = ml_models.version + 1,
                    updated_at = CURRENT_TIMESTAMP
            """, (model_name, model_bytes, json.dumps(metadata)))
    except Exception as e:
        print(f"❌ PG save model error: {e}")
        # Fallback to local
        _local_save_model(model_name, model_bytes, metadata)


def _pg_load_model(model_name: str) -> Optional[bytes]:
    """Load model bytes from PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT model_data FROM ml_models WHERE model_name = %s",
                (model_name,)
            )
            row = cursor.fetchone()
            if row:
                data = row[0]
                # Handle memoryview from psycopg2
                if isinstance(data, memoryview):
                    return bytes(data)
                return data
            return None
    except Exception as e:
        print(f"❌ PG load model error: {e}")
        return _local_load_model(model_name)


def _pg_get_model_info(model_name: str) -> Optional[Dict]:
    """Get model metadata from PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT metadata, version, created_at, updated_at FROM ml_models WHERE model_name = %s",
                (model_name,)
            )
            row = cursor.fetchone()
            if row:
                meta = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                meta['version'] = row[1]
                meta['created_at'] = row[2].isoformat() if row[2] else None
                meta['updated_at'] = row[3].isoformat() if row[3] else None
                return meta
            return None
    except Exception as e:
        print(f"❌ PG get model info error: {e}")
        return None


def _pg_list_models() -> List[Dict]:
    """List all models from PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT model_name, metadata, version, updated_at FROM ml_models ORDER BY updated_at DESC"
            )
            return [
                {
                    "name": row[0],
                    "metadata": row[1] if isinstance(row[1], dict) else json.loads(row[1]),
                    "version": row[2],
                    "updated_at": row[3].isoformat() if row[3] else None
                }
                for row in cursor.fetchall()
            ]
    except Exception as e:
        print(f"❌ PG list models error: {e}")
        return []


def _pg_delete_model(model_name: str) -> bool:
    """Delete model from PostgreSQL."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ml_models WHERE model_name = %s", (model_name,))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ PG delete model error: {e}")
        return False


# ═══════════════════════════════════════════
# Local filesystem fallback
# ═══════════════════════════════════════════


def _local_save_model(model_name: str, model_bytes: bytes, metadata: Dict):
    """Save model to local filesystem."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"{model_name}.pkl"
    meta_path = MODEL_DIR / f"{model_name}.meta.json"
    
    with open(model_path, 'wb') as f:
        f.write(model_bytes)
    
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)


def _local_load_model(model_name: str) -> Optional[bytes]:
    """Load model from local filesystem."""
    model_path = MODEL_DIR / f"{model_name}.pkl"
    if model_path.exists():
        with open(model_path, 'rb') as f:
            return f.read()
    return None


def _local_get_model_info(model_name: str) -> Optional[Dict]:
    """Get model metadata from local filesystem."""
    meta_path = MODEL_DIR / f"{model_name}.meta.json"
    if meta_path.exists():
        with open(meta_path, 'r') as f:
            return json.load(f)
    return None


def _local_list_models() -> List[Dict]:
    """List all local models."""
    if not MODEL_DIR.exists():
        return []
    
    models = []
    for pkl_file in MODEL_DIR.glob("*.pkl"):
        name = pkl_file.stem
        meta = _local_get_model_info(name) or {}
        models.append({
            "name": name,
            "metadata": meta,
            "version": meta.get("version", 1),
            "updated_at": meta.get("saved_at")
        })
    return models


def _local_delete_model(model_name: str) -> bool:
    """Delete local model files."""
    deleted = False
    for ext in ['.pkl', '.meta.json']:
        path = MODEL_DIR / f"{model_name}{ext}"
        if path.exists():
            path.unlink()
            deleted = True
    return deleted
