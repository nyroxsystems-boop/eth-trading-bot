#!/usr/bin/env python3
"""
Continuous Backtester - Auto-Learning System
Tests strategies 24/7 and saves results
"""

import asyncio
import aiohttp
import json
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from contextlib import contextmanager

from strategy_generator import StrategyGenerator

# Learning DB path
LEARNING_DB = Path(os.getenv("LOG_DIR", "./logs")) / "learning.db"

@contextmanager
def get_learning_db():
    """Context manager for learning.db connection"""
    conn = sqlite3.connect(LEARNING_DB)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


class ContinuousBacktester:
    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        db_path: str = "/root/ethbot/logs/learning.db",
        strategies_per_hour: int = 10
    ):
        self.api_url = api_url
        self.db_path = Path(db_path)
        self.strategies_per_hour = strategies_per_hour
        self.generator = StrategyGenerator()
        self.init_database()
    
    def init_database(self):
        """Initialize database for learning"""
        with get_learning_db() as conn:
            cursor = conn.cursor()
            
            if False:  # SQLite only
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS strategies (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ml_threshold REAL,
                        risk_per_trade REAL,
                        tp_min REAL,
                        tp_max REAL,
                        stop_floor REAL,
                        max_trades_per_day INTEGER,
                        
                        total_trades INTEGER,
                        winning_trades INTEGER,
                        losing_trades INTEGER,
                        win_rate REAL,
                        total_pnl REAL,
                        roi REAL,
                        sharpe_ratio REAL,
                        max_drawdown REAL,
                        
                        score REAL,
                        applied BOOLEAN DEFAULT false,
                        applied_at TIMESTAMP
                    )
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS strategies (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        ml_threshold REAL,
                        risk_per_trade REAL,
                        tp_min REAL,
                        tp_max REAL,
                        stop_floor REAL,
                        max_trades_per_day INTEGER,
                        
                        total_trades INTEGER,
                        winning_trades INTEGER,
                        losing_trades INTEGER,
                        win_rate REAL,
                        total_pnl REAL,
                        roi REAL,
                        sharpe_ratio REAL,
                        max_drawdown REAL,
                        
                        score REAL,
                        applied BOOLEAN DEFAULT 0,
                        applied_at DATETIME
                    )
                """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_score ON strategies(score DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON strategies(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_applied ON strategies(applied, score DESC)")
    
    async def backtest_strategy(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Run backtest for a single strategy"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/backtest",
                    json=strategy,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"Backtest failed: {response.status}")
                        return None
        except Exception as e:
            print(f"Error backtesting strategy: {e}")
            return None
    
    def calculate_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate strategy score — WIN RATE DOMINANT with RELIABILITY FILTERS (v5).
        
        Philosophy: Win Rate IS the score. ROI is a tiebreaker.
        A 65% WR + 2% ROI strategy MUST beat a 50% WR + 30% ROI strategy.
        
        Formula:
          FAKE GATE:   WR >= 99.5%                     → score = 0 (no real strategy is perfect)
          FAKE GATE:   WR >= 90% AND trades < 30       → score = 0 (statistically meaningless)
          FAKE GATE:   WR >= 80% AND trades < 10       → score = 0 (too few samples)
          KILL GATE:   WR < 55%                        → score = 0 (bad strategy)
          RELIABILITY: trades < 10                     → score ÷ 10
          Base:        WR × 10.0
          WR Tiers:    +100 if WR>58%, +250 if WR>62%, +500 if WR>66%, +800 if WR>70%
          ROI:         × 3.0  (tiebreaker only)
          Sharpe:      × 2.0  (capped at 3.0 raw)
          Drawdown:    × -2.0 (penalty)
          Trades:      min(trades/20, 1) × 50 (need ≥20 trades for full credit)
        """
        if not metrics:
            return 0.0
        
        win_rate = metrics.get('win_rate', 0)
        total_trades = metrics.get('total_trades', 0)
        
        # FAKE GATES: reject unrealistically perfect strategies
        if win_rate >= 99.5:
            return 0.0  # No real strategy has 100% WR
        if win_rate >= 90.0 and total_trades < 30:
            return 0.0  # Statistically meaningless with so few trades
        if win_rate >= 80.0 and total_trades < 10:
            return 0.0  # Way too few samples for such high WR
        
        # KILL GATE: below 55% WR = instant death
        if win_rate < 55.0:
            return 0.0
        
        score = 0.0
        
        # Win Rate — DOMINANT: this IS the score
        score += win_rate * 10.0
        
        # Win Rate TIER BONUSES — exponential reward for higher WR
        if win_rate > 58:
            score += 100.0   # Breaking 58% = solid
        if win_rate > 62:
            score += 250.0   # Breaking 62% = very good
        if win_rate > 66:
            score += 500.0   # Breaking 66% = excellent
        if win_rate > 70:
            score += 800.0   # Breaking 70% = exceptional
        
        # ROI — tiebreaker only (not dominant)
        roi = metrics.get('roi', 0)
        score += roi * 3.0
        
        # Sharpe Ratio — capped and minor
        sharpe = metrics.get('sharpe_ratio', 0)
        score += min(sharpe, 3.0) * 2.0
        
        # Max Drawdown — heavy penalty
        max_dd = metrics.get('max_drawdown', 0)
        score -= max_dd * 2.0
        
        # Trade count reliability bonus (need ≥20 trades for full credit)
        score += min(total_trades / 20, 1.0) * 50
        
        # RELIABILITY GATE: <10 trades = divide by 10
        if total_trades < 10:
            score *= 0.1
        
        return score
    
    def save_result(self, strategy: Dict[str, Any], metrics: Dict[str, Any], score: float):
        """Save backtest result to database"""
        with get_learning_db() as conn:
            cursor = conn.cursor()
            
            if False:  # SQLite only
                cursor.execute("""
                    INSERT INTO strategies (
                        ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                        total_trades, winning_trades, losing_trades, win_rate, total_pnl, roi,
                        sharpe_ratio, max_drawdown, score
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    strategy['ml_threshold'],
                    strategy['risk_per_trade'],
                    strategy['tp_min'],
                    strategy['tp_max'],
                    strategy['stop_floor'],
                    strategy['max_trades_per_day'],
                    metrics.get('total_trades', 0),
                    metrics.get('winning_trades', 0),
                    metrics.get('losing_trades', 0),
                    metrics.get('win_rate', 0),
                    metrics.get('total_pnl', 0),
                    metrics.get('roi', 0),
                    metrics.get('sharpe_ratio', 0),
                    metrics.get('max_drawdown', 0),
                    score
                ))
            else:
                cursor.execute("""
                    INSERT INTO strategies (
                        timestamp, ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                        total_trades, winning_trades, losing_trades, win_rate, total_pnl, roi,
                        sharpe_ratio, max_drawdown, score
                    ) VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    strategy['ml_threshold'],
                    strategy['risk_per_trade'],
                    strategy['tp_min'],
                    strategy['tp_max'],
                    strategy['stop_floor'],
                    strategy['max_trades_per_day'],
                    metrics.get('total_trades', 0),
                    metrics.get('winning_trades', 0),
                    metrics.get('losing_trades', 0),
                    metrics.get('win_rate', 0),
                    metrics.get('total_pnl', 0),
                    metrics.get('roi', 0),
                    metrics.get('sharpe_ratio', 0),
                    metrics.get('max_drawdown', 0),
                    score
                ))
    
    def get_top_strategies(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top performing strategies"""
        with get_learning_db() as conn:
            cursor = conn.cursor()
            
            if False:  # SQLite only
                cursor.execute("""
                    SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                           total_trades, win_rate, roi, sharpe_ratio, max_drawdown, score
                    FROM strategies
                    ORDER BY score DESC
                    LIMIT %s
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                           total_trades, win_rate, roi, sharpe_ratio, max_drawdown, score
                    FROM strategies
                    ORDER BY score DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
        
        strategies = []
        for row in rows:
            strategies.append({
                'params': {
                    'ml_threshold': row[0],
                    'risk_per_trade': row[1],
                    'tp_min': row[2],
                    'tp_max': row[3],
                    'stop_floor': row[4],
                    'max_trades_per_day': row[5]
                },
                'metrics': {
                    'total_trades': row[6],
                    'win_rate': row[7],
                    'roi': row[8],
                    'sharpe_ratio': row[9],
                    'max_drawdown': row[10]
                },
                'score': row[11]
            })
        
        return strategies
    
    async def run_cycle(self):
        """Run one backtest cycle"""
        print(f"\n[{datetime.now()}] Starting backtest cycle...")
        
        # Get top strategies for guided generation
        top_strategies = self.get_top_strategies(5)
        
        # Generate new strategies
        strategies = self.generator.generate_strategies(
            count=self.strategies_per_hour,
            best_strategies=top_strategies if top_strategies else None
        )
        
        print(f"Generated {len(strategies)} strategies to test")
        
        # Test each strategy
        results = []
        for i, strategy in enumerate(strategies, 1):
            print(f"  Testing strategy {i}/{len(strategies)}...", end=" ")
            
            metrics = await self.backtest_strategy(strategy)
            
            if metrics:
                score = self.calculate_score(metrics)
                self.save_result(strategy, metrics, score)
                
                # === SYNC TO POSTGRESQL via learning_store ===
                # Without this, apply_best_strategy() never sees new results!
                try:
                    import learning_store
                    learning_store.save_strategy({
                        "params": strategy,
                        "metrics": metrics,
                        "score": score,
                        "applied": False,
                        "data_source": "continuous_backtester"
                    })
                except Exception as e:
                    print(f" [PG sync: {e}]", end="")
                
                results.append({
                    'params': strategy,
                    'metrics': metrics,
                    'score': score
                })
                print(f"Score: {score:.2f}, Win Rate: {metrics['win_rate']:.1f}%, ROI: {metrics['roi']:.2f}%")
            else:
                print("FAILED")
        
        # Show best from this cycle
        if results:
            best = max(results, key=lambda x: x['score'])
            print(f"\nBest this cycle:")
            print(f"  Score: {best['score']:.2f}")
            print(f"  Win Rate: {best['metrics']['win_rate']:.1f}%")
            print(f"  ROI: {best['metrics']['roi']:.2f}%")
            print(f"  Sharpe: {best['metrics']['sharpe_ratio']:.2f}")
            
            # Mark best strategy as current in PostgreSQL
            try:
                import learning_store
                learning_store.set_current_strategy(best)
            except Exception as e:
                print(f"  ⚠️ Set current strategy error: {e}")
        
        print(f"Cycle complete. Tested {len(results)} strategies.")
        
        # === ML & AUTO-APPLY INTEGRATION ===
        await self._post_cycle_ml_and_apply()
    
    async def _post_cycle_ml_and_apply(self):
        """Run ML training and auto-apply after each cycle"""
        try:
            # 1. Train/update Ensemble (Gradient Boosting + LSTM)
            try:
                from neural_strategy_predictor import EnsemblePredictor
                print("\n🧠 Updating Ensemble Model (GB + LSTM)...")
                ensemble = EnsemblePredictor(db_path=str(self.db_path))
                results = ensemble.train_all()
                print(f"   Training results: GB={results.get('gradient_boosting', False)}, LSTM={results.get('lstm', False)}")
                
                # Show feature importance from GB
                if ensemble.gb_predictor and ensemble.gb_predictor.is_trained:
                    importance = ensemble.gb_predictor.get_feature_importance()
                    if importance:
                        top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:3]
                        print(f"   Top features: {', '.join(f'{k}={v:.3f}' for k, v in top_features)}")
            except Exception as e:
                print(f"   ⚠️ Ensemble not available, falling back to GB: {e}")
                from ml_strategy_predictor import MLStrategyPredictor
                predictor = MLStrategyPredictor(db_path=str(self.db_path))
                predictor.train()
            
            # 2. Check if should auto-apply new strategy
            from auto_apply import AutoApply
            print("\n🔄 Checking for auto-apply...")
            auto_apply = AutoApply(
                db_path=str(self.db_path),
                settings_file=str(LEARNING_DB.parent / "bot_settings.json")
            )
            auto_apply.check_and_apply()
            
        except Exception as e:
            print(f"⚠️ ML/Auto-apply error (non-critical): {e}")
    
    async def run_continuous(self):
        """Run continuous backtesting loop"""
        print("🚀 Starting continuous backtester...")
        print(f"   Testing {self.strategies_per_hour} strategies per hour")
        print(f"   ML-enhanced: Smart strategy prioritization")
        print(f"   Auto-apply: Best strategies applied automatically")
        
        # Try to use ML for smarter strategy selection
        try:
            from ml_strategy_predictor import MLStrategyPredictor
            self.ml_predictor = MLStrategyPredictor(db_path=str(self.db_path))
            if self.ml_predictor.is_trained:
                print(f"   ✅ ML Model loaded - will prioritize promising strategies")
            else:
                self.ml_predictor = None
                print(f"   ⏳ ML Model will train after {self.ml_predictor.min_samples if hasattr(self, 'ml_predictor') else 30} samples")
        except Exception as e:
            self.ml_predictor = None
            print(f"   ⚠️ ML not available: {e}")
        
        while True:
            try:
                await self.run_cycle()
                
                # Wait 1 hour (but check more frequently for first few cycles)
                total_strategies = self._count_strategies()
                if total_strategies < 100:
                    wait_time = 300  # 5 minutes for first 100 strategies
                    print(f"⏱️  Fast mode: Next cycle in 5 minutes ({total_strategies}/100 strategies)...")
                else:
                    wait_time = 3600  # 1 hour normally
                    print(f"⏱️  Waiting 1 hour until next cycle...")
                
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                print(f"❌ Error in backtest cycle: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    def _count_strategies(self) -> int:
        """Count total strategies in database"""
        try:
            with get_learning_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM strategies")
                return cursor.fetchone()[0] or 0
        except:
            return 0

if __name__ == "__main__":
    backtester = ContinuousBacktester()
    asyncio.run(backtester.run_continuous())

