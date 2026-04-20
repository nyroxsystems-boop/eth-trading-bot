#!/usr/bin/env python3
"""
Integration Tests for Ethbot Trading Platform.

Tests the FULL pipeline across multiple modules working together:
1. Strategy Pipeline: save → retrieve → auto-apply decision
2. KV Store: set → get (cross-process communication)
3. Auth Pipeline: register → login → JWT verify → logout
4. Emergency Stop: set via KV → check in bot logic

These tests use the local SQLite/JSON fallback (no PostgreSQL needed).
"""

import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Force SQLite mode for tests (no DATABASE_URL)
if 'DATABASE_URL' in os.environ:
    del os.environ['DATABASE_URL']


# =================== FIXTURES ===================

@pytest.fixture(autouse=True)
def clean_test_env(tmp_path):
    """Set up isolated test environment with temp directories."""
    test_log_dir = str(tmp_path / "logs")
    os.makedirs(test_log_dir, exist_ok=True)
    os.environ['LOG_DIR'] = test_log_dir
    yield test_log_dir
    # Cleanup happens automatically (tmp_path is cleaned by pytest)


@pytest.fixture
def user_mgr(clean_test_env):
    """Fresh UserManager with a clean SQLite database."""
    # Force reimport to pick up LOG_DIR
    import importlib
    import db_adapter
    importlib.reload(db_adapter)
    
    from user_manager import UserManager
    mgr = UserManager()
    return mgr


# =================== STRATEGY PIPELINE ===================

class TestStrategyPipeline:
    """Test: Backtester saves strategy → learning_store stores it → auto_apply evaluates it"""
    
    def test_save_and_retrieve_strategy(self, clean_test_env):
        """Strategy saved with save_strategy() must be retrievable with get_all_strategies()"""
        import importlib
        import learning_store
        importlib.reload(learning_store)
        
        strategy = {
            "params": {"tp_min": 0.015, "stop_floor": 0.012, "rsi_oversold": 35},
            "metrics": {"win_rate": 67.5, "roi": 8.3, "max_drawdown": 4.2, "sharpe_ratio": 1.8},
            "score": 1250.5
        }
        
        learning_store.save_strategy(strategy)
        
        # Retrieve
        strategies = learning_store.get_all_strategies(limit=10)
        assert len(strategies) >= 1, "Should have at least 1 strategy"
        
        best = strategies[0]
        assert best["score"] == 1250.5
        assert best["metrics"]["win_rate"] == 67.5
    
    def test_best_strategy_wins(self, clean_test_env):
        """When multiple strategies stored, best score should come first"""
        import importlib
        import learning_store
        importlib.reload(learning_store)
        
        strategies = [
            {"params": {"tp_min": 0.01}, "metrics": {"win_rate": 55}, "score": 200},
            {"params": {"tp_min": 0.02}, "metrics": {"win_rate": 70}, "score": 1500},
            {"params": {"tp_min": 0.03}, "metrics": {"win_rate": 60}, "score": 800},
        ]
        
        for s in strategies:
            learning_store.save_strategy(s)
        
        top = learning_store.get_all_strategies(limit=3)
        assert top[0]["score"] >= top[-1]["score"], "Strategies should be sorted by score DESC"
    
    def test_save_strategy_then_auto_apply_evaluates(self, clean_test_env):
        """Full pipeline: save strategy → auto_apply.should_apply_strategy() works"""
        import importlib
        import learning_store
        importlib.reload(learning_store)
        
        from auto_apply import AutoApply
        
        # Save a strategy
        learning_store.save_strategy({
            "params": {"tp_min": 0.02},
            "metrics": {"win_rate": 68, "roi": 10, "max_drawdown": 5, "sharpe_ratio": 2.0},
            "score": 1200
        })
        
        # AutoApply evaluates it
        applier = AutoApply.__new__(AutoApply)
        applier.min_score_improvement = 1.005
        applier.min_win_rate = 55.0
        applier.max_drawdown = 15.0
        applier.min_roi = 1.0
        
        new_strategy = {
            "win_rate": 68, "roi": 10, "max_drawdown": 5, "score": 1200
        }
        
        # No current strategy → should accept
        result = applier.should_apply_strategy(new_strategy, None)
        assert result is True, "Should accept first good strategy"


# =================== KV STORE (cross-process) ===================

class TestKVStore:
    """Test: set_kv → get_kv — the cross-process communication mechanism"""
    
    def test_set_and_get_kv(self, clean_test_env):
        """Basic set/get round-trip"""
        import importlib
        import learning_store
        importlib.reload(learning_store)
        
        learning_store.set_kv("test_key", "test_value_123")
        result = learning_store.get_kv("test_key")
        assert result == "test_value_123"
    
    def test_get_nonexistent_key_returns_none(self, clean_test_env):
        """Missing key should return None, not crash"""
        import importlib
        import learning_store
        importlib.reload(learning_store)
        
        result = learning_store.get_kv("key_that_does_not_exist")
        assert result is None
    
    def test_kv_overwrite(self, clean_test_env):
        """Overwriting a key should return the new value"""
        import importlib
        import learning_store
        importlib.reload(learning_store)
        
        learning_store.set_kv("overwrite_test", "value_1")
        learning_store.set_kv("overwrite_test", "value_2")
        assert learning_store.get_kv("overwrite_test") == "value_2"
    
    def test_emergency_stop_via_kv(self, clean_test_env):
        """Emergency stop signal via KV store — the real production flow"""
        import importlib
        import learning_store
        importlib.reload(learning_store)
        
        # Set emergency stop (this is what the dashboard does)
        learning_store.set_kv("emergency_trading_stopped", "true")
        
        # Bot checks it
        val = learning_store.get_kv("emergency_trading_stopped")
        assert val is not None
        assert val.lower() in ("true", "1", "yes"), "Emergency stop should be active"
        
        # Resume (dashboard clears it)
        learning_store.set_kv("emergency_trading_stopped", "false")
        val = learning_store.get_kv("emergency_trading_stopped")
        assert val.lower() not in ("true", "1", "yes"), "Emergency stop should be cleared"


# =================== AUTH PIPELINE ===================

class TestAuthPipeline:
    """Test: register → login → JWT verify → get_user → logout"""
    
    def test_register_and_login(self, user_mgr):
        """Full auth flow: register, login, verify token"""
        # Register
        user_id = user_mgr.register_user("test@example.com", "testuser", "password123")
        assert user_id is not None
        assert user_id > 0
        
        # Login
        result = user_mgr.login("testuser", "password123")
        assert result is not None
        assert result["username"] == "testuser"
        assert "token" in result
        
        # Verify JWT
        payload = user_mgr.verify_jwt(result["token"])
        assert payload is not None
        assert payload["user_id"] == user_id
        assert payload["email"] == "test@example.com"
    
    def test_login_with_email(self, user_mgr):
        """Login should work with email too"""
        user_mgr.register_user("emailtest@example.com", "emailuser", "password123")
        result = user_mgr.login("emailtest@example.com", "password123")
        assert result is not None
        assert result["username"] == "emailuser"
    
    def test_wrong_password_rejected(self, user_mgr):
        """Wrong password must return None"""
        user_mgr.register_user("wrong@example.com", "wrongpw", "correctpass1")
        result = user_mgr.login("wrongpw", "wrongpassword")
        assert result is None
    
    def test_duplicate_email_rejected(self, user_mgr):
        """Duplicate email registration must raise ValueError"""
        user_mgr.register_user("dupe@example.com", "first_user", "password123")
        with pytest.raises(ValueError, match="already"):
            user_mgr.register_user("dupe@example.com", "second_user", "password123")
    
    def test_short_password_rejected(self, user_mgr):
        """Passwords < 8 chars must be rejected"""
        with pytest.raises(ValueError, match="8 characters"):
            user_mgr.register_user("short@example.com", "shortpw", "1234567")
    
    def test_logout_revokes_token(self, user_mgr):
        """After logout, JWT should no longer verify"""
        user_mgr.register_user("logout@example.com", "logoutuser", "password123")
        result = user_mgr.login("logoutuser", "password123")
        token = result["token"]
        
        # Verify works before logout
        assert user_mgr.verify_jwt(token) is not None
        
        # Logout
        user_mgr.logout(token)
        
        # Verify should fail after logout
        assert user_mgr.verify_jwt(token) is None
    
    def test_admin_creation(self, user_mgr):
        """Admin user should have admin role"""
        user_id = user_mgr.create_admin("admin@example.com", "admin", "adminpass123")
        user = user_mgr.get_user(user_id)
        assert user["role"] == "admin"
    
    def test_get_user_returns_correct_data(self, user_mgr):
        """get_user should return all expected fields"""
        user_id = user_mgr.register_user("data@example.com", "datauser", "password123")
        user = user_mgr.get_user(user_id)
        
        assert user["id"] == user_id
        assert user["email"] == "data@example.com"
        assert user["username"] == "datauser"
        assert user["role"] == "user"
        assert user["active"] is True
        assert "subscription_tier" in user


# =================== LEARNING STATS ===================

class TestLearningStats:
    """Test: learning stats aggregation works end-to-end"""
    
    def test_stats_with_strategies(self, clean_test_env):
        """Stats should reflect saved strategies"""
        import importlib
        import learning_store
        importlib.reload(learning_store)
        
        # Save some strategies
        for i in range(5):
            learning_store.save_strategy({
                "params": {"tp_min": 0.01 + i * 0.005},
                "metrics": {"win_rate": 55 + i * 3, "roi": 2 + i},
                "score": 300 + i * 100
            })
        
        stats = learning_store.get_learning_stats()
        assert stats["stats"]["total_tested"] >= 5
        assert stats["stats"]["best_score"] >= 700  # 300 + 4*100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
