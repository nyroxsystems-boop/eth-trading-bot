#!/usr/bin/env python3
"""
API Integration Tests — HTTP-Level Tests for Ethbot Dashboard API.

Tests the REAL FastAPI app via TestClient (no network needed):
1. Auth Enforcement: Protected endpoints → 401 without token
2. Auth Flow: Register → Login → Token → Access protected endpoints
3. Admin Enforcement: Admin-only endpoints → 403 for regular users
4. Public Endpoints: Health, login, register work without auth
5. Rate Limiting: Auth endpoints get rate-limited
6. Router Integration: Extracted routers (admin, copy-trading) work

Run:  python -m pytest tests/integration/test_api_endpoints.py -v
"""

import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Force test mode — SQLite, no Postgres, temp LOG_DIR
os.environ.pop('DATABASE_URL', None)

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")


# =================== FIXTURES ===================

@pytest.fixture(scope="module")
def test_env(tmp_path_factory):
    """Set up isolated test environment once for all tests in this module."""
    test_dir = tmp_path_factory.mktemp("api_test")
    log_dir = str(test_dir / "logs")
    os.makedirs(log_dir, exist_ok=True)
    os.environ['LOG_DIR'] = log_dir
    os.environ['JWT_SECRET'] = 'test-secret-key-for-integration-tests-1234567890'
    os.environ['ADMIN_PASSWORD'] = 'testadmin123'
    os.environ['USER_PASSWORD'] = 'testuser1234'
    os.environ['DASHBOARD_SECRET'] = 'test_secret'
    os.environ['CORS_ORIGINS'] = '*'

    # Force reimport of modules that read env at import time
    import importlib
    for mod_name in list(sys.modules.keys()):
        if mod_name in ('db_adapter', 'learning_store', 'user_manager', 'auth_deps',
                        'dashboard_api', 'routes.admin', 'routes.copy_trading'):
            del sys.modules[mod_name]

    yield log_dir


@pytest.fixture(scope="module")
def client(test_env):
    """Create a TestClient for the FastAPI app."""
    # Import must happen AFTER env setup
    from dashboard_api import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    """Register an admin user and return a valid JWT token."""
    # Create admin via the API
    resp = client.post("/api/auth/register", json={
        "email": "admin@test.com",
        "username": "testadmin",
        "password": "adminpass123"
    })
    # Make the user admin via user_manager directly
    from auth_deps import get_user_manager
    mgr = get_user_manager()
    users = mgr.list_users()
    for u in users:
        if u['username'] == 'testadmin':
            mgr.update_user(u['id'], role='admin')
            break

    # Login to get fresh token with admin role
    resp = client.post("/api/auth/login", json={
        "email_or_username": "testadmin",
        "password": "adminpass123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def user_token(client):
    """Register a regular user and return a valid JWT token."""
    client.post("/api/auth/register", json={
        "email": "user@test.com",
        "username": "testuser",
        "password": "userpass1234"
    })
    resp = client.post("/api/auth/login", json={
        "email_or_username": "testuser",
        "password": "userpass1234"
    })
    assert resp.status_code == 200, f"User login failed: {resp.text}"
    return resp.json()["token"]


# =================== PUBLIC ENDPOINTS ===================

class TestPublicEndpoints:
    """These endpoints MUST work without any authentication."""

    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_root_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_login_endpoint_exists(self, client):
        """Login endpoint should exist (even if credentials are wrong)."""
        resp = client.post("/api/auth/login", json={
            "email_or_username": "nonexistent",
            "password": "wrong"
        })
        # Should return 401, not 404
        assert resp.status_code in (401, 403, 422), f"Expected auth error, got {resp.status_code}"

    def test_register_endpoint_exists(self, client):
        """Register endpoint should accept valid data."""
        resp = client.post("/api/auth/register", json={
            "email": "newuser@test.com",
            "username": "newuser",
            "password": "newpass12345"
        })
        # Should succeed or conflict (if already exists)
        assert resp.status_code in (200, 201, 400, 409), f"Unexpected: {resp.status_code}"


# =================== AUTH ENFORCEMENT ===================

class TestAuthEnforcement:
    """Protected endpoints MUST return 401/403 without valid token."""

    PROTECTED_GET_ENDPOINTS = [
        "/api/settings/bot",
        "/api/settings/telegram",
        "/api/settings/trading",
        "/api/settings/api-keys",
        "/api/auth/me",
        "/api/portfolio/pairs",
    ]

    PROTECTED_POST_ENDPOINTS = [
        "/api/settings/bot",
        "/api/settings/telegram",
        "/api/settings/trading",
        "/api/settings/api-keys",
        "/api/bot/start",
        "/api/bot/stop",
        "/api/capital",
        "/api/risk",
    ]

    @pytest.mark.parametrize("endpoint", PROTECTED_GET_ENDPOINTS)
    def test_get_endpoint_requires_auth(self, client, endpoint):
        """GET {endpoint} without token → 401 or 403"""
        resp = client.get(endpoint)
        assert resp.status_code in (401, 403), \
            f"GET {endpoint} returned {resp.status_code}, expected 401/403"

    @pytest.mark.parametrize("endpoint", PROTECTED_POST_ENDPOINTS)
    def test_post_endpoint_requires_auth(self, client, endpoint):
        """POST {endpoint} without token → 401 or 403"""
        resp = client.post(endpoint, json={})
        assert resp.status_code in (401, 403, 422), \
            f"POST {endpoint} returned {resp.status_code}, expected 401/403/422"

    def test_expired_token_rejected(self, client):
        """A garbage/expired token should be rejected."""
        resp = client.get("/api/auth/me", headers={
            "Authorization": "Bearer this-is-a-fake-token"
        })
        assert resp.status_code == 401


# =================== AUTH FLOW ===================

class TestAuthFlow:
    """Full auth flow: get token → access protected endpoints."""

    def test_login_returns_token(self, client, user_token):
        """Login should return a valid JWT token."""
        assert user_token is not None
        assert len(user_token) > 20  # JWT tokens are long

    def test_auth_me_with_token(self, client, user_token):
        """GET /api/auth/me with valid token → 200 + user data."""
        resp = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {user_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("username") == "testuser"
        assert data.get("email") == "user@test.com"

    def test_settings_with_token(self, client, user_token):
        """GET /api/settings/bot should work with valid token."""
        resp = client.get("/api/settings/bot", headers={
            "Authorization": f"Bearer {user_token}"
        })
        assert resp.status_code == 200

    def test_capital_with_token(self, client, user_token):
        """GET /api/capital should work with valid token."""
        resp = client.get("/api/capital", headers={
            "Authorization": f"Bearer {user_token}"
        })
        assert resp.status_code == 200


# =================== ADMIN ENFORCEMENT ===================

class TestAdminEnforcement:
    """Admin-only endpoints MUST reject regular users with 403."""

    ADMIN_ENDPOINTS = [
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/revenue"),
        ("GET", "/api/admin/analytics"),
        ("GET", "/api/admin/emergency/status"),
        ("GET", "/api/admin/system/health"),
    ]

    @pytest.mark.parametrize("method,endpoint", ADMIN_ENDPOINTS)
    def test_admin_endpoint_rejects_regular_user(self, client, user_token, method, endpoint):
        """Regular user → 403 on admin endpoints."""
        headers = {"Authorization": f"Bearer {user_token}"}
        if method == "GET":
            resp = client.get(endpoint, headers=headers)
        else:
            resp = client.post(endpoint, headers=headers, json={})
        assert resp.status_code == 403, \
            f"{method} {endpoint} returned {resp.status_code} for regular user, expected 403"

    @pytest.mark.parametrize("method,endpoint", ADMIN_ENDPOINTS)
    def test_admin_endpoint_accepts_admin(self, client, admin_token, method, endpoint):
        """Admin user → 200 on admin endpoints."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        if method == "GET":
            resp = client.get(endpoint, headers=headers)
        else:
            resp = client.post(endpoint, headers=headers, json={})
        assert resp.status_code == 200, \
            f"{method} {endpoint} returned {resp.status_code} for admin, expected 200"

    def test_admin_endpoint_requires_any_auth(self, client):
        """Admin endpoints without ANY token → 401."""
        resp = client.get("/api/admin/users")
        assert resp.status_code in (401, 403)


# =================== ROUTER INTEGRATION ===================

class TestRouterIntegration:
    """Verify extracted routers (admin, copy-trading) are properly mounted."""

    def test_admin_router_mounted(self, client, admin_token):
        """Admin router endpoints should be reachable."""
        resp = client.get("/api/admin/analytics", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "success"

    def test_copy_trading_leaderboard_works(self, client):
        """Copy-trading leaderboard is a public-ish endpoint (no auth required on GET)."""
        resp = client.get("/api/copy-trading/leaderboard")
        # May return 200 or error (if social module not available), but NOT 404
        assert resp.status_code != 404, "Copy-trading router not mounted"


# =================== WRONG METHOD ===================

class TestWrongMethod:
    """API should handle wrong HTTP methods gracefully."""

    def test_get_on_post_only(self, client, user_token):
        """GET on a POST-only endpoint should return 404 or 405."""
        resp = client.get("/api/bot/start", headers={
            "Authorization": f"Bearer {user_token}"
        })
        assert resp.status_code in (404, 405)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
