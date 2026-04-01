#!/usr/bin/env python3
"""
Continuous Backtester - Auto-Learning System
Tests strategies 24/7 and saves results
"""

import asyncio
import aiohttp
import json

import os
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

from strategy_generator import StrategyGenerator

import learning_store

LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))


class ContinuousBacktester:
    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        db_path: str = None,
        strategies_per_hour: int = 10
    ):
        self.api_url = api_url
        self.db_path = Path(db_path)
        self.strategies_per_hour = strategies_per_hour
        self.generator = StrategyGenerator()
        self.init_database()
    
    def init_database(self):
        """Initialize database for learning — delegates to learning_store (PostgreSQL)."""
        learning_store.ensure_learning_tables()
    
    async def backtest_strategy(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Run backtest for a single strategy — DIRECT import (no HTTP).
        
        v8: Uses strategy_backtester directly with walk-forward validation.
        The old HTTP approach fails on Railway when services run in different containers.
        """
        try:
            from src.ml.strategy_backtester import (
                fetch_historical_data, calculate_indicators, run_backtest
            )
            
            def _run_direct():
                # Fetch real Binance data
                candles = fetch_historical_data(days=7)
                if not candles or len(candles) < 120:
                    return None
                candles = calculate_indicators(candles)
                
                # Walk-Forward: 70% train / 30% test
                split_idx = int(len(candles) * 0.7)
                train_candles = candles[:split_idx]
                test_candles = candles[split_idx:]
                
                # Run on test set (out-of-sample)
                test_metrics = run_backtest(test_candles, strategy)
                if not test_metrics:
                    return None
                
                # Also run on train for blended score
                train_metrics = run_backtest(train_candles, strategy)
                if train_metrics and test_metrics.get("score", 0) > 0:
                    blended = test_metrics["score"] * 0.7 + train_metrics["score"] * 0.3
                    test_metrics["score"] = round(blended, 2)
                
                test_metrics["data_source"] = "direct_backtester"
                return test_metrics
            
            result = await asyncio.get_event_loop().run_in_executor(None, _run_direct)
            return result
            
        except ImportError:
            # Fallback: HTTP if direct import fails
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.api_url}/api/backtest",
                        json=strategy,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        return None
            except Exception as e:
                print(f"Error backtesting (HTTP fallback): {e}")
                return None
        except Exception as e:
            print(f"Error backtesting strategy: {e}")
            return None
    
    def calculate_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate strategy score — v8 synced with strategy_backtester.
        
        v8 changes: WR-BOOST + PROFITABILITY balanced.
        More granular WR tiers from 58%+, sweet spot bonus 60-75%,
        ROI×80, softer ROI floor to not kill high-WR low-ROI strategies.
        """
        if not metrics:
            return 0.0
        
        win_rate = metrics.get('win_rate', 0)
        total_trades = metrics.get('total_trades', 0)
        
        # FAKE GATES: reject unrealistically perfect strategies
        if win_rate >= 99.5:
            return 0.0
        if win_rate >= 90.0 and total_trades < 20:
            return 0.0
        if win_rate >= 80.0 and total_trades < 10:
            return 0.0
        
        # KILL GATE: below 55% WR = instant death
        if win_rate < 55.0:
            return 0.0
        
        score = 0.0
        
        # Win Rate — v8: boosted back to *7 to push WR higher
        score += win_rate * 7.0
        
        # Tier bonuses (v8: MORE TIERS from 58% for granular WR optimization)
        if win_rate > 58: score += 50.0
        if win_rate > 60: score += 100.0
        if win_rate > 63: score += 200.0
        if win_rate > 65: score += 300.0
        if win_rate > 68: score += 400.0
        if win_rate > 70: score += 500.0
        if win_rate > 75: score += 700.0
        if win_rate > 80: score += 1000.0
        if win_rate > 85: score += 1500.0
        
        # WR CONSISTENCY BONUS (v8 NEW): sweet spot 60-75%
        if 60 <= win_rate <= 75:
            score += 200.0
        
        # ROI — balanced with WR (v8: 80x, was 100x)
        roi = metrics.get('roi', 0)
        score += roi * 80.0
        
        # PROFIT FACTOR
        pf = metrics.get('profit_factor', 0)
        if pf >= 2.0:
            score += 300.0
        elif pf >= 1.5:
            score += 200.0
        elif pf >= 1.2:
            score += 100.0
        elif pf < 0.8:
            score *= 0.3
        
        # ROI FLOOR (v8: softer — don't kill high WR strategies)
        if roi < 5.0:
            score *= 0.6
        if roi < 0:
            score *= 0.25
        
        # Sharpe Ratio
        sharpe = metrics.get('sharpe_ratio', 0)
        score += min(sharpe, 3.0) * 5.0
        
        # Max Drawdown penalty
        max_dd = metrics.get('max_drawdown', 0)
        score -= max_dd * 5.0
        
        # Trade count reliability bonus
        score += min(total_trades / 20, 1.0) * 50
        
        # Reliability gate
        if total_trades < 10:
            score *= 0.1
        
        return score
    
    def save_result(self, strategy: Dict[str, Any], metrics: Dict[str, Any], score: float):
        """Save backtest result to PostgreSQL via learning_store (no more SQLite)."""
        learning_store.save_strategy({
            "params": strategy,
            "metrics": metrics,
            "score": score,
            "applied": False,
            "data_source": "continuous_backtester"
        })
    
    def get_top_strategies(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top performing strategies from PostgreSQL via learning_store."""
        return learning_store.get_top_n_strategies(limit)
    
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
                settings_file=str(LOG_DIR / "bot_settings.json")
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
            stats = learning_store.get_learning_stats()
            return stats.get("stats", {}).get("total_tested", 0)
        except:
            return 0

if __name__ == "__main__":
    backtester = ContinuousBacktester()
    asyncio.run(backtester.run_continuous())

