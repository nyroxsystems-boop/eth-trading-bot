"""
Rate Limiting Middleware for FastAPI
Tier-based rate limiting with Redis backend
"""

import os
from typing import Optional, Callable
from functools import wraps
from datetime import datetime
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse


# Tier-based rate limits (requests per minute)
TIER_LIMITS = {
    "free": {
        "requests_per_minute": 30,
        "requests_per_hour": 500,
        "requests_per_day": 5000
    },
    "basic": {
        "requests_per_minute": 100,
        "requests_per_hour": 2000,
        "requests_per_day": 20000
    },
    "pro": {
        "requests_per_minute": 500,
        "requests_per_hour": 10000,
        "requests_per_day": 100000
    },
    "enterprise": {
        "requests_per_minute": 2000,
        "requests_per_hour": 50000,
        "requests_per_day": None  # Unlimited
    }
}

# Endpoint-specific limits (multiplier of base rate)
ENDPOINT_LIMITS = {
    "/api/ml/": 0.5,        # ML endpoints are expensive
    "/api/analytics/": 0.5,  # Analytics endpoints are expensive
    "/api/admin/": 1.0,      # Admin has standard rate
    "/api/auth/": 2.0,       # Auth endpoints need higher limit
}


class RateLimiter:
    """
    Rate limiter using sliding window algorithm.
    Uses Redis for distributed rate limiting.
    """
    
    def __init__(self):
        self._redis = None
        self._memory_store: dict = {}
        self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            from src.infra.redis_client import get_redis_client
            self._redis = get_redis_client()
        except ImportError:
            print("⚠️ Redis client not available - using memory rate limiting")
    
    def _get_user_tier(self, user_id: Optional[int]) -> str:
        """Get user's subscription tier"""
        if not user_id:
            return "free"
        
        try:
            from subscription_manager import SubscriptionManager
            sub_mgr = SubscriptionManager()
            return sub_mgr.get_user_tier(user_id)
        except:
            return "free"
    
    def _get_identifier(self, request: Request) -> str:
        """Get unique identifier for rate limiting"""
        # Try to get user ID from request state
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"
        
        # Fallback to IP
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        
        return f"ip:{client_ip}"
    
    def _get_endpoint_multiplier(self, path: str) -> float:
        """Get rate limit multiplier for endpoint"""
        for prefix, multiplier in ENDPOINT_LIMITS.items():
            if path.startswith(prefix):
                return multiplier
        return 1.0
    
    def check_rate_limit(
        self, 
        request: Request,
        user_id: Optional[int] = None
    ) -> tuple[bool, dict]:
        """
        Check if request is within rate limits.
        Returns (is_allowed, limit_info)
        """
        identifier = self._get_identifier(request)
        tier = self._get_user_tier(user_id)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
        
        # Get endpoint multiplier
        multiplier = self._get_endpoint_multiplier(request.url.path)
        
        # Calculate effective limit
        minute_limit = int(limits["requests_per_minute"] * multiplier)
        
        # Check rate limit
        if self._redis:
            key = f"ratelimit:{identifier}:minute"
            allowed, remaining = self._redis.check_rate_limit(
                identifier, minute_limit, 60
            )
        else:
            # Memory-based rate limiting
            allowed, remaining = self._memory_rate_check(
                identifier, minute_limit, 60
            )
        
        limit_info = {
            "tier": tier,
            "limit": minute_limit,
            "remaining": remaining,
            "reset": 60,  # seconds
            "identifier": identifier
        }
        
        return allowed, limit_info
    
    def _memory_rate_check(
        self, 
        identifier: str, 
        limit: int, 
        window: int
    ) -> tuple[bool, int]:
        """Memory-based rate limiting fallback"""
        now = datetime.now().timestamp()
        key = f"{identifier}:{int(now / window)}"
        
        current = self._memory_store.get(key, 0)
        self._memory_store[key] = current + 1
        
        # Clean old entries
        old_keys = [k for k in self._memory_store if k.split(":")[0] == identifier and k != key]
        for k in old_keys:
            del self._memory_store[k]
        
        remaining = max(0, limit - current - 1)
        return current < limit, remaining
    
    def get_headers(self, limit_info: dict) -> dict:
        """Get rate limit headers for response"""
        return {
            "X-RateLimit-Limit": str(limit_info["limit"]),
            "X-RateLimit-Remaining": str(limit_info["remaining"]),
            "X-RateLimit-Reset": str(limit_info["reset"]),
            "X-RateLimit-Tier": limit_info["tier"]
        }


# Singleton instance
_rate_limiter: Optional[RateLimiter] = None

def get_rate_limiter() -> RateLimiter:
    """Get or create rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def rate_limit_middleware(request: Request, call_next):
    """
    FastAPI middleware for rate limiting.
    Add to app with: app.middleware("http")(rate_limit_middleware)
    """
    # Skip rate limiting for certain paths
    skip_paths = ["/health", "/api/health", "/docs", "/openapi.json", "/"]
    if request.url.path in skip_paths:
        return await call_next(request)
    
    # Get user ID if available
    user_id = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            import jwt
            token = auth_header.replace("Bearer ", "")
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("user_id")
        except:
            pass
    
    # Check rate limit
    limiter = get_rate_limiter()
    allowed, limit_info = limiter.check_rate_limit(request, user_id)
    
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Limit: {limit_info['limit']}/min for {limit_info['tier']} tier.",
                "retry_after": limit_info["reset"]
            },
            headers=limiter.get_headers(limit_info)
        )
    
    # Process request
    response = await call_next(request)
    
    # Add rate limit headers to response
    for key, value in limiter.get_headers(limit_info).items():
        response.headers[key] = value
    
    return response


def rate_limit(
    requests_per_minute: Optional[int] = None,
    requests_per_hour: Optional[int] = None
):
    """
    Decorator for endpoint-specific rate limiting.
    
    Usage:
        @app.get("/api/expensive")
        @rate_limit(requests_per_minute=10)
        async def expensive_endpoint():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if request and requests_per_minute:
                limiter = get_rate_limiter()
                identifier = limiter._get_identifier(request)
                
                # Check custom limit
                if limiter._redis:
                    allowed, remaining = limiter._redis.check_rate_limit(
                        f"{identifier}:{func.__name__}",
                        requests_per_minute,
                        60
                    )
                else:
                    allowed, remaining = limiter._memory_rate_check(
                        f"{identifier}:{func.__name__}",
                        requests_per_minute,
                        60
                    )
                
                if not allowed:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded for this endpoint. Max: {requests_per_minute}/min"
                    )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


if __name__ == "__main__":
    print("\n📊 Rate Limiter Configuration:")
    print("\nTier Limits:")
    for tier, limits in TIER_LIMITS.items():
        print(f"   {tier.upper()}:")
        for key, value in limits.items():
            print(f"      {key}: {value or 'unlimited'}")
    
    print("\nEndpoint Multipliers:")
    for endpoint, mult in ENDPOINT_LIMITS.items():
        print(f"   {endpoint}: {mult}x")
