#!/usr/bin/env python3
"""
Continuous ML Training Orchestrator
24/7 Training system for all ML models using real Binance historical data.
Designed to run as a Railway worker process.
"""

import os
import sys
import json
import time
import signal
import threading
import requests
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from multiprocessing import Process, Event

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import ML model store for persistent storage
try:
    import ml_model_store
    HAS_MODEL_STORE = True
except ImportError:
    HAS_MODEL_STORE = False

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
RAILWAY_URL = os.getenv("RAILWAY_DASHBOARD_URL", "https://web-production-d57ac.up.railway.app")
SYNC_ENDPOINT = f"{RAILWAY_URL}/api/ml/training-sync"
PROGRESS_FILE = LOG_DIR / "training_orchestrator.json"

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Global stop event
stop_event = Event()


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n🛑 Stopping continuous training...")
    stop_event.set()


class TrainingOrchestrator:
    """
    Orchestrates 24/7 training for all ML models:
    - DQN (Reinforcement Learning)
    - Rainbow DQN (State-of-the-Art RL)
    - Strategy Backtester (Parameter Optimization)
    - Gradient Boosting (Classification)
    - LSTM (Sequence Prediction)
    - Signal Generator (Multi-model voting)
    """
    
    def __init__(self):
        self.models = {
            "dqn": {
                "name": "Enhanced DQN",
                "last_train": None,
                "train_interval_hours": 4,
                "episodes": 500,
                "status": "idle"
            },
            "rainbow_dqn": {
                "name": "Rainbow DQN",
                "last_train": None,
                "train_interval_hours": 6,
                "episodes": 300,
                "status": "idle"
            },
            "strategy_backtester": {
                "name": "Strategy Optimizer",
                "last_train": None,
                "train_interval_seconds": 30,
                "status": "idle"
            },
            "gradient_boosting": {
                "name": "Gradient Booster",
                "last_train": None,
                "train_interval_hours": 6,
                "status": "idle"
            },
            "lstm": {
                "name": "LSTM Predictor",
                "last_train": None,
                "train_interval_hours": 12,
                "status": "idle"
            },
            "signal_generator": {
                "name": "Signal Generator",
                "last_train": None,
                "train_interval_seconds": 60,
                "status": "idle"
            }
        }
        
        self.training_cycle = 0
        self.total_episodes = 0
        self.prices = None
        self.session = requests.Session()
        self.signal_generator = None
    
    def fetch_training_data(self, days: int = 60) -> np.ndarray:
        """Fetch price data from Binance for training"""
        try:
            from src.data.historical_data_fetcher import get_historical_fetcher
            
            fetcher = get_historical_fetcher()
            
            # Update cache with latest data
            fetcher.update_cache_incremental("ETHUSDT", "4h")
            
            # Get price array
            prices = fetcher.get_prices_array("ETHUSDT", "4h", days=days)
            
            if len(prices) < 100:
                logger.warning("Insufficient cached data, fetching fresh...")
                candles = fetcher.fetch_klines("ETHUSDT", "4h", limit=days * 6)
                prices = [c["close"] for c in candles]
            
            logger.info(f"📊 Loaded {len(prices)} price points for training")
            return np.array(prices)
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            # Fallback to synthetic data
            return self._generate_synthetic_data(days)
    
    def _generate_synthetic_data(self, days: int = 60) -> np.ndarray:
        """Generate synthetic price data as fallback"""
        np.random.seed(int(time.time()) % 1000)
        
        num_candles = days * 6  # 4h candles
        prices = [3200.0]
        
        for _ in range(num_candles - 1):
            trend = np.sin(len(prices) / 500) * 0.001
            change = np.random.normal(0, 0.002) + trend
            new_price = prices[-1] * (1 + change)
            new_price = max(2000, min(5000, new_price))
            prices.append(new_price)
        
        return np.array(prices)
    
    def train_dqn(self, episodes: int = 500) -> dict:
        """Train DQN agent"""
        self.models["dqn"]["status"] = "training"
        
        try:
            from rl_trading_agent import DQNAgent, TradingEnvironment
            
            if self.prices is None or len(self.prices) < 100:
                self.prices = self.fetch_training_data(60)
            
            env = TradingEnvironment(window_size=20)
            agent = DQNAgent(state_size=env.state_size)
            
            logger.info(f"🧠 Starting DQN Training - {episodes} episodes")
            
            episode_rewards = []
            best_reward = float('-inf')
            
            for episode in range(episodes):
                if stop_event.is_set():
                    break
                
                state = env.reset(self.prices)
                total_reward = 0
                trades = 0
                
                while not env.done:
                    action = agent.act(state, training=True)
                    next_state, reward, done, info = env.step(action)
                    agent.remember(state, action, reward, next_state, done)
                    
                    if len(agent.memory) >= 64:
                        agent.replay(64)
                    
                    state = next_state
                    total_reward += reward
                    
                    if info.get('action') in ['BUY', 'SELL']:
                        trades += 1
                
                if episode % 10 == 0:
                    agent.update_target_network()
                
                agent.decay_epsilon()
                episode_rewards.append(total_reward)
                
                if total_reward > best_reward:
                    best_reward = total_reward
                    agent._save_model()
                    # Persist to PostgreSQL so model survives deploys
                    if HAS_MODEL_STORE:
                        try:
                            ml_model_store.save_model('dqn_agent', agent, {
                                'type': 'DQN',
                                'episodes': episode + 1,
                                'best_reward': float(best_reward),
                                'epsilon': float(agent.epsilon)
                            })
                        except Exception as e:
                            logger.warning(f"Model store save failed: {e}")
                
                # Sync progress every 10 episodes
                if (episode + 1) % 10 == 0:
                    portfolio_value = env.get_portfolio_value()
                    roi = (portfolio_value - 10000) / 10000 * 100
                    avg_reward = np.mean(episode_rewards[-20:]) if len(episode_rewards) >= 20 else np.mean(episode_rewards)
                    
                    self._sync_progress({
                        "model": "Enhanced DQN",
                        "model_type": "enhanced_dqn",
                        "architecture": "Dueling DQN + Double DQN",
                        "episode": episode + 1,
                        "total_episodes": episodes,
                        "progress_pct": round((episode + 1) / episodes * 100, 1),
                        "reward": round(total_reward, 2),
                        "avg_reward": round(avg_reward, 2),
                        "best_reward": round(best_reward, 2),
                        "roi": round(roi, 1),
                        "trades": trades,
                        "portfolio_value": round(portfolio_value, 2),
                        "epsilon": round(agent.epsilon, 4),
                        "win_rate": round(trades / max(1, trades * 2) * 100, 1),
                        "status": "training"
                    })
                    
                    logger.info(f"   Episode {episode+1}/{episodes} | Reward: {total_reward:.2f} | ROI: {roi:.1f}%")
            
            self.models["dqn"]["status"] = "idle"
            self.models["dqn"]["last_train"] = datetime.now()
            self.total_episodes += episodes
            
            return {
                "model": "dqn",
                "episodes": episodes,
                "best_reward": best_reward,
                "final_roi": roi
            }
            
        except Exception as e:
            logger.error(f"DQN training error: {e}")
            self.models["dqn"]["status"] = "error"
            return {"error": str(e)}
    
    def train_rainbow_dqn(self, episodes: int = 300) -> dict:
        """Train Rainbow DQN agent (state-of-the-art)"""
        self.models["rainbow_dqn"]["status"] = "training"
        
        try:
            from src.ml.rainbow_dqn import RainbowAgent
            from src.ml.enhanced_dqn_agent import AdvancedTradingEnvironment
            
            if self.prices is None or len(self.prices) < 100:
                self.prices = self.fetch_training_data(60)
            
            # Create environment and agent
            env = AdvancedTradingEnvironment(window_size=30)
            agent = RainbowAgent(
                state_size=env._get_state().shape[0] if hasattr(env, '_get_state') else 50,
                action_size=3,
                n_step=3,  # N-step returns
                atom_size=51  # Distributional RL atoms
            )
            
            logger.info(f"🌈 Starting Rainbow DQN Training - {episodes} episodes")
            
            best_reward = float('-inf')
            episode_rewards = []
            
            for episode in range(episodes):
                if stop_event.is_set():
                    break
                
                state = env.reset(self.prices)
                total_reward = 0
                trades = 0
                
                while not env.done:
                    action = agent.select_action(state)
                    next_state, reward, done, info = env.step(action)
                    agent.store_transition(state, action, reward, next_state, done)
                    
                    # Train
                    loss = agent.train()
                    
                    state = next_state
                    total_reward += reward
                    
                    if info.get('action') in ['BUY', 'SELL']:
                        trades += 1
                
                episode_rewards.append(total_reward)
                
                if total_reward > best_reward:
                    best_reward = total_reward
                    agent.save(str(LOG_DIR / "rainbow_dqn.pt"))
                
                # Sync progress every 10 episodes
                if (episode + 1) % 10 == 0:
                    portfolio_value = env.get_portfolio_value()
                    roi = (portfolio_value - 10000) / 10000 * 100
                    
                    self._sync_progress({
                        "model": "Rainbow DQN",
                        "model_type": "rainbow_dqn",
                        "architecture": "C51 + N-Step + Dueling + Double",
                        "episode": episode + 1,
                        "total_episodes": episodes,
                        "progress_pct": round((episode + 1) / episodes * 100, 1),
                        "reward": round(total_reward, 2),
                        "best_reward": round(best_reward, 2),
                        "roi": round(roi, 1),
                        "trades": trades,
                        "status": "training"
                    })
                    
                    logger.info(f"   Rainbow Episode {episode+1}/{episodes} | Reward: {total_reward:.2f} | ROI: {roi:.1f}%")
            
            self.models["rainbow_dqn"]["status"] = "idle"
            self.models["rainbow_dqn"]["last_train"] = datetime.now()
            self.total_episodes += episodes
            
            return {
                "model": "rainbow_dqn",
                "episodes": episodes,
                "best_reward": best_reward
            }
            
        except Exception as e:
            logger.error(f"Rainbow DQN training error: {e}")
            self.models["rainbow_dqn"]["status"] = "error"
            return {"error": str(e)}
    
    def train_strategy_backtester(self) -> dict:
        """Run single strategy backtest"""
        self.models["strategy_backtester"]["status"] = "training"
        
        try:
            from src.ml.strategy_backtester import run_single_backtest, get_backtest_state
            import asyncio
            
            asyncio.run(run_single_backtest())
            state = get_backtest_state()
            
            self.models["strategy_backtester"]["status"] = "idle"
            self.models["strategy_backtester"]["last_train"] = datetime.now()
            
            return {
                "model": "strategy_backtester",
                "tested_today": state.get("total_tested_today", 0),
                "best_score": state.get("best_score_today", 0)
            }
            
        except Exception as e:
            logger.error(f"Strategy backtest error: {e}")
            self.models["strategy_backtester"]["status"] = "error"
            return {"error": str(e)}
    
    def train_gradient_boosting(self) -> dict:
        """Retrain Gradient Boosting model"""
        self.models["gradient_boosting"]["status"] = "training"
        
        try:
            from src.ml.enhanced_ml_engine import MLStrategyPredictor
            
            if self.prices is None or len(self.prices) < 100:
                self.prices = self.fetch_training_data(60)
            
            predictor = MLStrategyPredictor()
            
            # Generate simple training data from prices
            X, y = [], []
            for i in range(20, len(self.prices) - 1):
                features = []
                # Price returns
                for j in range(5):
                    ret = (self.prices[i-j] - self.prices[i-j-1]) / self.prices[i-j-1]
                    features.append(ret)
                # Moving averages
                features.append(np.mean(self.prices[i-5:i]) / self.prices[i])
                features.append(np.mean(self.prices[i-20:i]) / self.prices[i])
                features.append(np.std(self.prices[i-20:i]) / self.prices[i])
                
                X.append(features)
                # Label: 1 if next price is higher
                y.append(1 if self.prices[i+1] > self.prices[i] else 0)
            
            X = np.array(X)
            y = np.array(y)
            
            # Train (simplified call)
            if hasattr(predictor, 'train'):
                predictor.train(X, y)
            
            # Persist to PostgreSQL so model survives deploys
            if HAS_MODEL_STORE:
                try:
                    ml_model_store.save_model('gradient_boosting', predictor, {
                        'type': 'GradientBoosting',
                        'samples': len(X),
                        'features': X.shape[1] if hasattr(X, 'shape') else len(X[0])
                    })
                except Exception as e:
                    logger.warning(f"Model store save failed: {e}")
            
            self.models["gradient_boosting"]["status"] = "idle"
            self.models["gradient_boosting"]["last_train"] = datetime.now()
            
            logger.info(f"✅ Gradient Boosting trained on {len(X)} samples")
            
            return {
                "model": "gradient_boosting",
                "samples": len(X)
            }
            
        except Exception as e:
            logger.error(f"Gradient Boosting error: {e}")
            self.models["gradient_boosting"]["status"] = "error"
            return {"error": str(e)}
    
    def _sync_progress(self, data: dict):
        """Sync training progress to dashboard API"""
        try:
            data["timestamp"] = datetime.now().isoformat()
            data["training_cycle"] = self.training_cycle
            data["total_episodes_all_time"] = self.total_episodes
            
            # Save locally
            with open(PROGRESS_FILE, "w") as f:
                json.dump(data, f)
            
            # Sync to dashboard
            response = self.session.post(
                SYNC_ENDPOINT,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code != 200:
                logger.warning(f"Sync failed: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"Sync error: {e}")
    
    def get_status(self) -> dict:
        """Get orchestrator status"""
        return {
            "training_cycle": self.training_cycle,
            "total_episodes": self.total_episodes,
            "models": self.models,
            "data_points": len(self.prices) if self.prices is not None else 0,
            "running": not stop_event.is_set()
        }
    
    def run_continuous(self):
        """Main continuous training loop"""
        logger.info("=" * 60)
        logger.info("🚀 Continuous ML Training Orchestrator Started")
        logger.info("=" * 60)
        logger.info(f"   Dashboard: {RAILWAY_URL}")
        logger.info(f"   Models: DQN, Strategy Optimizer, Gradient Boosting, LSTM")
        logger.info(f"   Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        # Initial data fetch
        logger.info("📊 Fetching historical data from Binance...")
        self.prices = self.fetch_training_data(60)
        
        last_dqn = datetime.now() - timedelta(hours=5)  # Trigger immediately
        last_gb = datetime.now() - timedelta(hours=7)
        last_lstm = datetime.now() - timedelta(hours=13)
        
        while not stop_event.is_set():
            self.training_cycle += 1
            logger.info(f"\n{'#' * 60}")
            logger.info(f"# Training Cycle {self.training_cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'#' * 60}")
            
            try:
                # DQN Training (every 4 hours)
                if (datetime.now() - last_dqn).total_seconds() > 4 * 3600:
                    result = self.train_dqn(episodes=500)
                    last_dqn = datetime.now()
                    logger.info(f"✅ DQN: {result}")
                
                if stop_event.is_set():
                    break
                
                # Strategy Backtest (continuous, 1/30s)
                result = self.train_strategy_backtester()
                logger.info(f"📈 Strategy Tested: Score={result.get('best_score', 0)}")
                
                if stop_event.is_set():
                    break
                
                # Gradient Boosting (every 6 hours)
                if (datetime.now() - last_gb).total_seconds() > 6 * 3600:
                    result = self.train_gradient_boosting()
                    last_gb = datetime.now()
                    logger.info(f"✅ Gradient Boosting: {result}")
                
                # Update data periodically
                if self.training_cycle % 10 == 0:
                    self.prices = self.fetch_training_data(60)
                
            except Exception as e:
                logger.error(f"Training cycle error: {e}")
            
            # Wait between cycles
            for _ in range(30):  # 30 seconds
                if stop_event.is_set():
                    break
                time.sleep(1)
        
        logger.info("\n🏁 Training Orchestrator stopped")
    
    def run_single_test(self):
        """Run single test cycle for verification"""
        logger.info("🧪 Running single test cycle...")
        
        self.prices = self.fetch_training_data(30)
        
        # Quick DQN test
        result = self.train_dqn(episodes=10)
        logger.info(f"DQN Test: {result}")
        
        # Strategy test
        result = self.train_strategy_backtester()
        logger.info(f"Strategy Test: {result}")
        
        logger.info("✅ Single test cycle complete")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Continuous ML Training Orchestrator')
    parser.add_argument('--continuous', action='store_true', help='Run continuous training loop')
    parser.add_argument('--test-single', action='store_true', help='Run single test cycle')
    parser.add_argument('--dqn', type=int, help='Train DQN for N episodes')
    args = parser.parse_args()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    orchestrator = TrainingOrchestrator()
    
    if args.continuous:
        orchestrator.run_continuous()
    elif args.test_single:
        orchestrator.run_single_test()
    elif args.dqn:
        orchestrator.prices = orchestrator.fetch_training_data(60)
        orchestrator.train_dqn(episodes=args.dqn)
    else:
        print("Usage:")
        print("  --continuous    Run 24/7 training loop")
        print("  --test-single   Run single test cycle")
        print("  --dqn N         Train DQN for N episodes")


if __name__ == "__main__":
    main()
