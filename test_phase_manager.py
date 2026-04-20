"""
Test Phase Manager for SaaS Platform
Tracks 30-day paper trading test phases per cryptocurrency
"""

import json
from typing import Dict, Optional
from datetime import datetime, timezone

from db_adapter import get_db_connection, USE_POSTGRES


class TestPhaseManager:
    """Manages 30-day test phases for cryptocurrencies"""
    
    def __init__(self):
        pass
    
    def get_test_phase(self, user_id: int, symbol: str) -> Optional[Dict]:
        """Get test phase status for a specific coin"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT test_phases FROM users WHERE id = %s
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT test_phases FROM users WHERE id = ?
                """, (user_id,))
            
            result = cursor.fetchone()
            
            if not result or not result[0]:
                return None
            
            try:
                test_phases = json.loads(result[0]) if isinstance(result[0], str) else result[0]
                return test_phases.get(symbol)
            except:
                return None
    
    def start_test_phase(self, user_id: int, symbol: str) -> Dict:
        """Start a new 30-day test phase for a cryptocurrency"""
        now = datetime.now(timezone.utc)
        
        test_phase = {
            "symbol": symbol,
            "start_date": now.isoformat(),
            "days_elapsed": 0,
            "days_remaining": 30,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "completed": False,
            "ready_for_live": False,
            "performance_score": 0.0
        }
        
        # Get existing test phases
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT test_phases FROM users WHERE id = %s
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT test_phases FROM users WHERE id = ?
                """, (user_id,))
            
            result = cursor.fetchone()
            
            try:
                test_phases = json.loads(result[0]) if result and result[0] else {}
            except:
                test_phases = {}
            
            # Add new test phase
            test_phases[symbol] = test_phase
            
            # Update database
            if USE_POSTGRES:
                cursor.execute("""
                    UPDATE users SET test_phases = %s WHERE id = %s
                """, (json.dumps(test_phases), user_id))
            else:
                cursor.execute("""
                    UPDATE users SET test_phases = ? WHERE id = ?
                """, (json.dumps(test_phases), user_id))
        
        return test_phase
    
    def update_test_phase(self, user_id: int, symbol: str, metrics: Dict) -> Dict:
        """Update test phase with new performance metrics"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT test_phases FROM users WHERE id = %s
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT test_phases FROM users WHERE id = ?
                """, (user_id,))
            
            result = cursor.fetchone()
            
            if not result or not result[0]:
                return self.start_test_phase(user_id, symbol)
            
            try:
                test_phases = json.loads(result[0]) if isinstance(result[0], str) else result[0]
            except:
                test_phases = {}
            
            if symbol not in test_phases:
                return self.start_test_phase(user_id, symbol)
            
            phase = test_phases[symbol]
            
            # Calculate days elapsed
            start_date = datetime.fromisoformat(phase["start_date"])
            now = datetime.now(timezone.utc)
            days_elapsed = (now - start_date).days
            days_remaining = max(0, 30 - days_elapsed)
            
            # Update metrics
            phase.update({
                "days_elapsed": days_elapsed,
                "days_remaining": days_remaining,
                "total_trades": metrics.get("total_trades", phase["total_trades"]),
                "winning_trades": metrics.get("winning_trades", phase["winning_trades"]),
                "losing_trades": metrics.get("losing_trades", phase["losing_trades"]),
                "win_rate": metrics.get("win_rate", phase["win_rate"]),
                "total_pnl": metrics.get("total_pnl", phase["total_pnl"]),
                "sharpe_ratio": metrics.get("sharpe_ratio", phase["sharpe_ratio"]),
                "max_drawdown": metrics.get("max_drawdown", phase["max_drawdown"])
            })
            
            # Check if completed
            phase["completed"] = days_elapsed >= 30
            
            # Calculate readiness for live trading
            phase["ready_for_live"] = self._calculate_readiness(phase)
            phase["performance_score"] = self._calculate_performance_score(phase)
            
            test_phases[symbol] = phase
            
            # Update database
            if USE_POSTGRES:
                cursor.execute("""
                    UPDATE users SET test_phases = %s WHERE id = %s
                """, (json.dumps(test_phases), user_id))
            else:
                cursor.execute("""
                    UPDATE users SET test_phases = ? WHERE id = ?
                """, (json.dumps(test_phases), user_id))
        
        return phase
    
    def get_all_test_phases(self, user_id: int) -> Dict:
        """Get all test phases for a user"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT test_phases FROM users WHERE id = %s
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT test_phases FROM users WHERE id = ?
                """, (user_id,))
            
            result = cursor.fetchone()
            
            if not result or not result[0]:
                return {}
            
            try:
                return json.loads(result[0]) if isinstance(result[0], str) else result[0]
            except:
                return {}
    
    def _calculate_readiness(self, phase: Dict) -> bool:
        """Calculate if coin is ready for live trading"""
        # Criteria:
        # 1. Test phase completed (30 days)
        # 2. Win rate >= 60%
        # 3. Total trades >= 20
        # 4. Positive total PnL
        # 5. Sharpe ratio >= 1.0 (if available)
        
        if not phase["completed"]:
            return False
        
        if phase["total_trades"] < 20:
            return False
        
        if phase["win_rate"] < 0.60:
            return False
        
        if phase["total_pnl"] <= 0:
            return False
        
        # Optional: Sharpe ratio check
        if phase.get("sharpe_ratio", 0) > 0 and phase["sharpe_ratio"] < 1.0:
            return False
        
        return True
    
    def _calculate_performance_score(self, phase: Dict) -> float:
        """Calculate overall performance score (0-100)"""
        score = 0.0
        
        # Win rate (40 points max)
        if phase["win_rate"] > 0:
            score += min(40, phase["win_rate"] * 100 * 0.4)
        
        # PnL (30 points max)
        if phase["total_pnl"] > 0:
            # Normalize PnL to 0-30 range (assuming 10% is excellent)
            pnl_pct = phase["total_pnl"] / 100000  # Assuming $100k starting capital
            score += min(30, pnl_pct * 100 * 3)
        
        # Trade count (15 points max)
        if phase["total_trades"] >= 20:
            score += 15
        elif phase["total_trades"] > 0:
            score += (phase["total_trades"] / 20) * 15
        
        # Sharpe ratio (15 points max)
        if phase.get("sharpe_ratio", 0) > 0:
            score += min(15, phase["sharpe_ratio"] * 7.5)
        
        return round(min(100, score), 2)


# Singleton instance
test_phase_manager = TestPhaseManager()


if __name__ == "__main__":
    # Test the manager
    manager = TestPhaseManager()
    
    # Example: Start test phase
    phase = manager.start_test_phase(1, "ETHUSDT")
    print(f"Started test phase: {json.dumps(phase, indent=2)}")
    
    # Example: Update with metrics
    metrics = {
        "total_trades": 25,
        "winning_trades": 16,
        "losing_trades": 9,
        "win_rate": 0.64,
        "total_pnl": 125.50,
        "sharpe_ratio": 1.2,
        "max_drawdown": 0.05
    }
    
    updated = manager.update_test_phase(1, "ETHUSDT", metrics)
    print(f"\nUpdated test phase: {json.dumps(updated, indent=2)}")
