"""
Shared authentication dependencies for FastAPI routers.
Extracted from dashboard_api.py to enable router splitting.

Usage in any router:
    from auth_deps import get_current_user, get_current_admin, verify_internal_api_key
"""

import os
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from user_manager import UserManager

# Singleton user manager
_user_mgr: Optional[UserManager] = None

def get_user_manager() -> UserManager:
    """Get or create the singleton UserManager instance."""
    global _user_mgr
    if _user_mgr is None:
        _user_mgr = UserManager()
    return _user_mgr


# Security scheme
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return current user."""
    user_mgr = get_user_manager()
    token = credentials.credentials
    payload = user_mgr.verify_jwt(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = user_mgr.get_user(payload['user_id'])
    if not user or not user['active']:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


async def get_current_user_optional(authorization: Optional[str] = Header(None)):
    """Get current user if token provided, otherwise None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None

    user_mgr = get_user_manager()
    token = authorization.replace("Bearer ", "")
    payload = user_mgr.verify_jwt(token)

    if not payload:
        return None

    return user_mgr.get_user(payload['user_id'])


async def get_current_admin(current_user: dict = Depends(get_current_user)):
    """Verify user is admin."""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# Internal API key for bot-to-API sync (Worker container → Web container)
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

async def verify_internal_api_key(request: Request):
    """Verify internal API key for bot-to-API sync endpoints.
    These endpoints are called by the Worker container, not by users.
    If INTERNAL_API_KEY is not set, allow all requests (backward compat)."""
    if not INTERNAL_API_KEY:
        return  # No key configured = allow (dev/legacy mode)
    key = request.headers.get("X-Internal-Key", "")
    if key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
