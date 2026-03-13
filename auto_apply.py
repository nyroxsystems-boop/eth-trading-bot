#!/usr/bin/env python3
"""
Auto-Apply System - Auto-Learning
Automatically applies best strategies to live bot
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from contextlib import contextmanager
import requests

# Learning DB path
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LEARNING_DB = LOG_DIR / "learning.db"

@contextmanager
def get_learning_db():
    """Context manager for learning.db connection"""
    conn = sqlite3.connect(LEARNING_DB)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

class AutoApply:
    def __init__(
        self,
        db_path: str = "/root/ethbot/logs/learning.db",
        settings_file: str = "/root/ethbot/logs/bot_settings.json",
        api_url: str = "http://localhost:8000",
        telegram_bot_token: str = None,
        telegram_chat_id: str = None
    ):
        self.db_path = Path(db_path)
        self.settings_file = Path(settings_file)
        self.api_url = api_url
        self.telegram_bot_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        
        # Safety thresholds
        self.min_score_improvement = float(os.getenv("MIN_SCORE_IMPROVEMENT", "1.1"))  # 10% better
        self.min_win_rate = float(os.getenv("MIN_WIN_RATE", "55.0"))
        self.max_drawdown = float(os.getenv("MAX_DRAWDOWN_THRESHOLD", "15.0"))
        self.min_roi = float(os.getenv("MIN_ROI", "2.0"))
    
    def get_current_strategy(self) -> Optional[Dict[str, Any]]:
        """Get currently applied strategy from PostgreSQL via learning_store."""
        try:
            import learning_store
            current = learning_store.get_current_strategy()
            if current:
                params = current.get("params", {})
                metrics = current.get("metrics", {})
                return {
                    'params': params,
                    'score': current.get("score", 0),
                    'win_rate': metrics.get("win_rate", 0),
                    'roi': metrics.get("roi", 0),
                    'max_drawdown': metrics.get("max_drawdown", 0)
                }
        except Exception as e:
            print(f"⚠️ PG current strategy read failed: {e}")
        
        # Fallback to SQLite
        try:
            with get_learning_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                           score, win_rate, roi, max_drawdown
                    FROM strategies
                    WHERE applied = 1
                    ORDER BY applied_at DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
            if row:
                return {
                    'params': {
                        'ml_threshold': row[0], 'risk_per_trade': row[1],
                        'tp_min': row[2], 'tp_max': row[3],
                        'stop_floor': row[4], 'max_trades_per_day': row[5]
                    },
                    'score': row[6], 'win_rate': row[7], 'roi': row[8], 'max_drawdown': row[9]
                }
        except Exception:
            pass
        return None
    
    def get_best_strategy(self) -> Optional[Dict[str, Any]]:
        """Get best strategy from PostgreSQL via learning_store."""
        try:
            import learning_store
            strategies = learning_store.get_all_strategies(limit=1)
            if strategies:
                s = strategies[0]
                params = s.get("params", {})
                metrics = s.get("metrics", {})
                return {
                    'params': params,
                    'score': s.get("score", 0),
                    'win_rate': metrics.get("win_rate", 0),
                    'roi': metrics.get("roi", 0),
                    'max_drawdown': metrics.get("max_drawdown", 0),
                    'sharpe_ratio': metrics.get("sharpe_ratio", 0)
                }
        except Exception as e:
            print(f"⚠️ PG best strategy read failed: {e}")
        
        # Fallback to SQLite
        try:
            with get_learning_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                           score, win_rate, roi, max_drawdown, sharpe_ratio
                    FROM strategies
                    ORDER BY score DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
            if row:
                return {
                    'params': {
                        'ml_threshold': row[0], 'risk_per_trade': row[1],
                        'tp_min': row[2], 'tp_max': row[3],
                        'stop_floor': row[4], 'max_trades_per_day': row[5]
                    },
                    'score': row[6], 'win_rate': row[7], 'roi': row[8],
                    'max_drawdown': row[9], 'sharpe_ratio': row[10]
                }
        except Exception:
            pass
        return None
    
    def should_apply_strategy(self, new_strategy: Dict[str, Any], current_strategy: Optional[Dict[str, Any]]) -> bool:
        """Check if new strategy should be applied"""
        
        # Safety checks
        if new_strategy['win_rate'] < self.min_win_rate:
            print(f"❌ Win rate too low: {new_strategy['win_rate']:.1f}% < {self.min_win_rate}%")
            return False
        
        if new_strategy['max_drawdown'] > self.max_drawdown:
            print(f"❌ Drawdown too high: {new_strategy['max_drawdown']:.1f}% > {self.max_drawdown}%")
            return False
        
        if new_strategy['roi'] < self.min_roi:
            print(f"❌ ROI too low: {new_strategy['roi']:.2f}% < {self.min_roi}%")
            return False
        
        # If no current strategy, apply if passes safety checks
        if not current_strategy:
            print("✅ No current strategy, applying first good one")
            return True
        
        # Must be significantly better
        score_improvement = new_strategy['score'] / current_strategy['score']
        if score_improvement < self.min_score_improvement:
            print(f"❌ Not enough improvement: {score_improvement:.2f}x < {self.min_score_improvement}x")
            return False
        
        print(f"✅ New strategy is {score_improvement:.2f}x better!")
        return True
    
    def apply_strategy(self, strategy: Dict[str, Any]) -> bool:
        """Apply strategy to bot settings"""
        try:
            # Load current settings
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
            else:
                settings = {}
            
            # Update with new strategy parameters
            settings.update({
                'ml_threshold': strategy['params']['ml_threshold'],
                'risk_per_trade': strategy['params']['risk_per_trade'],
                'tp_min': strategy['params']['tp_min'],
                'tp_max': strategy['params']['tp_max'],
                'stop_floor': strategy['params']['stop_floor'],
                'max_trades_per_day': strategy['params']['max_trades_per_day']
            })
            
            # Save settings
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            
            # Mark as applied in database
            with get_learning_db() as conn:
                cursor = conn.cursor()
                
                if False:  # SQLite only
                    cursor.execute("""
                        UPDATE strategies
                        SET applied = true, applied_at = %s
                        WHERE ml_threshold = %s AND risk_per_trade = %s AND tp_min = %s
                    """, (
                        datetime.now().isoformat(),
                        strategy['params']['ml_threshold'],
                        strategy['params']['risk_per_trade'],
                        strategy['params']['tp_min']
                    ))
                else:
                    cursor.execute("""
                        UPDATE strategies
                        SET applied = 1, applied_at = ?
                        WHERE ml_threshold = ? AND risk_per_trade = ? AND tp_min = ?
                    """, (
                        datetime.now().isoformat(),
                        strategy['params']['ml_threshold'],
                        strategy['params']['risk_per_trade'],
                        strategy['params']['tp_min']
                    ))
            
            return True
            
        except Exception as e:
            print(f"Error applying strategy: {e}")
            return False
    
    def send_telegram_notification(self, message: str):
        """Send Telegram notification"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            requests.post(url, json={
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }, timeout=10)
        except Exception as e:
            print(f"Error sending Telegram notification: {e}")
    
    def check_and_apply(self) -> bool:
        """Check if should apply new strategy and do it"""
        current = self.get_current_strategy()
        best = self.get_best_strategy()
        
        if not best:
            print("No strategies in database yet")
            return False
        
        print(f"\n{'='*60}")
        print(f"AUTO-APPLY CHECK - {datetime.now()}")
        print(f"{'='*60}")
        
        if current:
            print(f"\nCurrent Strategy:")
            print(f"  Score: {current['score']:.2f}")
            print(f"  Win Rate: {current['win_rate']:.1f}%")
            print(f"  ROI: {current['roi']:.2f}%")
        else:
            print("\nNo current strategy applied")
        
        print(f"\nBest Strategy:")
        print(f"  Score: {best['score']:.2f}")
        print(f"  Win Rate: {best['win_rate']:.1f}%")
        print(f"  ROI: {best['roi']:.2f}%")
        print(f"  Sharpe: {best['sharpe_ratio']:.2f}")
        print(f"  Max DD: {best['max_drawdown']:.1f}%")
        
        if self.should_apply_strategy(best, current):
            print(f"\n🚀 APPLYING NEW STRATEGY!")
            
            if self.apply_strategy(best):
                # Send notification
                message = f"""
🤖 *Auto-Learning: New Strategy Applied*

📊 *Performance:*
• Win Rate: {best['win_rate']:.1f}%
• ROI: {best['roi']:.2f}%
• Sharpe: {best['sharpe_ratio']:.2f}
• Max DD: {best['max_drawdown']:.1f}%

⚙️ *Parameters:*
• ML Threshold: {best['params']['ml_threshold']:.3f}
• Risk: {best['params']['risk_per_trade']:.4f}
• TP: {best['params']['tp_min']:.3f} - {best['params']['tp_max']:.3f}
• SL: {best['params']['stop_floor']:.3f}
• Max Trades: {best['params']['max_trades_per_day']}

✅ Strategy automatically applied!
                """
                
                self.send_telegram_notification(message)
                print("✅ Strategy applied successfully!")
                return True
            else:
                print("❌ Failed to apply strategy")
                return False
        else:
            print("\n⏸️  Not applying - current strategy is good enough")
            return False

if __name__ == "__main__":
    auto_apply = AutoApply()
    auto_apply.check_and_apply()
