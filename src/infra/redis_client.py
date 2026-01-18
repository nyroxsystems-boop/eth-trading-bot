"""
Redis Client for Caching and Session Management
Provides centralized caching for the trading bot
"""

import os
import json
from typing import Optional, Any, Union
from datetime import timedelta
import hashlib

# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "")


class RedisClient:
    """
    Redis client wrapper with connection pooling and fallback.
    Falls back to in-memory cache if Redis is unavailable.
    """
    
    def __init__(self):
        self._redis = None
        self._memory_cache: dict = {}
        self._connected = False
        self._connect()
    
    def _connect(self):
        """Attempt to connect to Redis"""
        if not REDIS_URL:
            print("⚠️ REDIS_URL not set - using in-memory cache")
            return
        
        try:
            import redis
            self._redis = redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            # Test connection
            self._redis.ping()
            self._connected = True
            print("✅ Redis connected successfully")
        except ImportError:
            print("⚠️ redis package not installed - using in-memory cache")
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e} - using in-memory cache")
            self._redis = None
    
    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self._connected and self._redis is not None
    
    def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        try:
            if self.is_connected:
                return self._redis.get(key)
            return self._memory_cache.get(key)
        except Exception as e:
            print(f"⚠️ Redis GET error: {e}")
            return self._memory_cache.get(key)
    
    def set(
        self, 
        key: str, 
        value: Union[str, dict, list], 
        ttl: Optional[int] = 3600
    ) -> bool:
        """Set value in cache with optional TTL (seconds)"""
        try:
            # Serialize if not string
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            if self.is_connected:
                if ttl:
                    self._redis.setex(key, ttl, value)
                else:
                    self._redis.set(key, value)
                return True
            else:
                self._memory_cache[key] = value
                return True
        except Exception as e:
            print(f"⚠️ Redis SET error: {e}")
            self._memory_cache[key] = value
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            if self.is_connected:
                self._redis.delete(key)
            self._memory_cache.pop(key, None)
            return True
        except Exception as e:
            print(f"⚠️ Redis DELETE error: {e}")
            return False
    
    def get_json(self, key: str) -> Optional[Any]:
        """Get and parse JSON value"""
        value = self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    def set_json(self, key: str, value: Any, ttl: Optional[int] = 3600) -> bool:
        """Set JSON-serializable value"""
        return self.set(key, json.dumps(value), ttl)
    
    def incr(self, key: str) -> int:
        """Increment counter"""
        try:
            if self.is_connected:
                return self._redis.incr(key)
            else:
                val = int(self._memory_cache.get(key, 0)) + 1
                self._memory_cache[key] = str(val)
                return val
        except Exception as e:
            print(f"⚠️ Redis INCR error: {e}")
            return 0
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key"""
        try:
            if self.is_connected:
                self._redis.expire(key, ttl)
                return True
            return False
        except Exception as e:
            print(f"⚠️ Redis EXPIRE error: {e}")
            return False
    
    # === Session Management ===
    
    def store_session(self, user_id: int, session_id: str, ttl: int = 86400) -> bool:
        """Store user session"""
        key = f"session:{user_id}:{session_id}"
        return self.set(key, "active", ttl)
    
    def validate_session(self, user_id: int, session_id: str) -> bool:
        """Check if session is valid"""
        key = f"session:{user_id}:{session_id}"
        result = self.get(key)
        return result == "active"
    
    def revoke_session(self, user_id: int, session_id: str) -> bool:
        """Revoke specific session"""
        key = f"session:{user_id}:{session_id}"
        return self.delete(key)
    
    def revoke_all_sessions(self, user_id: int) -> int:
        """Revoke all sessions for user"""
        count = 0
        try:
            if self.is_connected:
                pattern = f"session:{user_id}:*"
                keys = self._redis.keys(pattern)
                if keys:
                    count = self._redis.delete(*keys)
            # Also clean memory cache
            to_delete = [k for k in self._memory_cache if k.startswith(f"session:{user_id}:")]
            for k in to_delete:
                del self._memory_cache[k]
                count += 1
            return count
        except Exception as e:
            print(f"⚠️ Redis REVOKE_ALL error: {e}")
            return count
    
    # === Token Blacklist ===
    
    def blacklist_token(self, token_hash: str, ttl: int = 86400) -> bool:
        """Add JWT token to blacklist"""
        key = f"blacklist:{token_hash}"
        return self.set(key, "revoked", ttl)
    
    def is_token_blacklisted(self, token_hash: str) -> bool:
        """Check if token is blacklisted"""
        key = f"blacklist:{token_hash}"
        return self.get(key) == "revoked"
    
    # === Rate Limiting ===
    
    def check_rate_limit(
        self, 
        identifier: str, 
        limit: int, 
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check and update rate limit.
        Returns (is_allowed, remaining_requests)
        """
        key = f"ratelimit:{identifier}"
        
        try:
            current = self.incr(key)
            
            # Set expiry on first request
            if current == 1:
                self.expire(key, window_seconds)
            
            remaining = max(0, limit - current)
            is_allowed = current <= limit
            
            return is_allowed, remaining
        except Exception as e:
            print(f"⚠️ Rate limit check error: {e}")
            return True, limit  # Fail open
    
    # === Caching Helpers ===
    
    def cache_key(self, *args) -> str:
        """Generate cache key from arguments"""
        key_str = ":".join(str(a) for a in args)
        return hashlib.md5(key_str.encode()).hexdigest()[:16]
    
    def get_or_set(
        self, 
        key: str, 
        generator_func, 
        ttl: int = 3600
    ) -> Any:
        """Get from cache or generate and cache"""
        cached = self.get_json(key)
        if cached is not None:
            return cached
        
        value = generator_func()
        self.set_json(key, value, ttl)
        return value
    
    def flush_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        count = 0
        try:
            if self.is_connected:
                keys = self._redis.keys(pattern)
                if keys:
                    count = self._redis.delete(*keys)
            return count
        except Exception as e:
            print(f"⚠️ Redis FLUSH_PATTERN error: {e}")
            return count
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        stats = {
            "connected": self.is_connected,
            "backend": "redis" if self.is_connected else "memory",
            "memory_cache_size": len(self._memory_cache)
        }
        
        if self.is_connected:
            try:
                info = self._redis.info("memory")
                stats["redis_memory"] = info.get("used_memory_human", "unknown")
                stats["redis_keys"] = self._redis.dbsize()
            except:
                pass
        
        return stats


# Singleton instance
_redis_client: Optional[RedisClient] = None

def get_redis_client() -> RedisClient:
    """Get or create Redis client instance"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


# Convenience functions
def cache_get(key: str) -> Optional[str]:
    return get_redis_client().get(key)

def cache_set(key: str, value: Any, ttl: int = 3600) -> bool:
    return get_redis_client().set(key, value, ttl)

def cache_delete(key: str) -> bool:
    return get_redis_client().delete(key)


if __name__ == "__main__":
    # Test Redis client
    client = get_redis_client()
    
    print(f"\n📊 Redis Client Status:")
    stats = client.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Test basic operations
    print("\n🧪 Testing basic operations...")
    client.set("test_key", "test_value", 60)
    value = client.get("test_key")
    print(f"   SET/GET: {'✅' if value == 'test_value' else '❌'}")
    
    # Test rate limiting
    print("\n🧪 Testing rate limiting...")
    for i in range(5):
        allowed, remaining = client.check_rate_limit("test_user", 3, 60)
        print(f"   Request {i+1}: {'✅' if allowed else '❌'} (remaining: {remaining})")
