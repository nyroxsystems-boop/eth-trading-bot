#!/usr/bin/env python3
"""
Enhanced DQN Training Runner
Trains the enhanced DQN agent and logs progress in real-time.
"""

import os
import sys
import json
import time
import numpy as np
from pathlib import Path
from datetime import datetime

# Add project root
sys.path.insert(0, str(Path(__file__).parent))

from src.ml.enhanced_dqn_agent import EnhancedDQNAgent, AdvancedTradingEnvironment
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Configuration
EPISODES = int(os.getenv("DQN_EPISODES", "500"))
LOG_FILE = Path("logs/enhanced_dqn_training.json")
PROGRESS_FILE = Path("logs/dqn_training_live.json")


def generate_training_data(days: int = 90) -> np.ndarray:
    """Generate realistic ETH price data for training"""
    np.random.seed(int(time.time()) % 1000)
    
    hours = days * 24
    
    # Base price with multiple trends
    trend = np.cumsum(np.random.randn(hours) * 0.3)
    
    # Add cycles (weekly, daily)
    weekly_cycle = 50 * np.sin(np.arange(hours) * 2 * np.pi / (24 * 7))
    daily_cycle = 20 * np.sin(np.arange(hours) * 2 * np.pi / 24)
    
    # Volatility clusters
    volatility = 1 + 0.5 * np.abs(np.sin(np.arange(hours) * 2 * np.pi / (24 * 14)))
    noise = np.random.randn(hours) * 15 * volatility
    
    # Flash crashes (rare)
    crash_points = np.random.choice(hours, size=int(hours * 0.005), replace=False)
    crashes = np.zeros(hours)
    crashes[crash_points] = np.random.uniform(-100, -50, len(crash_points))
    
    # Combine
    prices = 2500 + trend + weekly_cycle + daily_cycle + noise + crashes
    prices = np.maximum(prices, 1500)  # Floor
    
    return prices.astype(np.float32)


def train_enhanced_dqn():
    """Main training loop with live logging"""
    logger.info(f"🧠 Starting Enhanced DQN Training: {EPISODES} episodes")
    
    # Initialize
    env = AdvancedTradingEnvironment(window_size=30, initial_balance=100000)
    agent = EnhancedDQNAgent(state_size=env.state_size)
    
    logger.info(f"   State size: {env.state_size}")
    logger.info(f"   Model params: {sum(p.numel() for p in agent.policy_net.parameters()):,}")
    
    # Generate training data
    prices = generate_training_data(days=180)
    logger.info(f"   Training data: {len(prices)} price points")
    
    best_reward = float('-inf')
    best_roi = 0
    rewards_history = []
    training_log = []
    
    start_time = datetime.now()
    
    for episode in range(1, EPISODES + 1):
        # Use different starting points for variety
        start_idx = np.random.randint(0, len(prices) - 1000)
        episode_prices = prices[start_idx:start_idx + 1000]
        
        state = env.reset(episode_prices)
        total_reward = 0
        episode_trades = 0
        
        while not env.done:
            action = agent.act(state, training=True)
            next_state, reward, done, info = env.step(action)
            
            agent.remember(state, action, reward, next_state, done)
            loss = agent.replay()
            
            state = next_state
            total_reward += reward
            
            if info.get('action') in ['BUY', 'SELL']:
                episode_trades += 1
        
        rewards_history.append(total_reward)
        
        # Calculate metrics
        portfolio = env.get_portfolio_value()
        roi = (portfolio / env.initial_balance - 1) * 100
        win_rate = env.wins / max(env.trades, 1) * 100
        
        # Track best
        if total_reward > best_reward:
            best_reward = total_reward
            best_roi = roi
            agent._save_model()
        
        # Progress logging
        progress = {
            "timestamp": datetime.now().isoformat(),
            "episode": episode,
            "total_episodes": EPISODES,
            "progress_pct": round(episode / EPISODES * 100, 1),
            "reward": round(total_reward, 2),
            "avg_reward_10": round(np.mean(rewards_history[-10:]), 2),
            "best_reward": round(best_reward, 2),
            "roi": round(roi, 2),
            "best_roi": round(best_roi, 2),
            "portfolio_value": round(portfolio, 2),
            "trades": env.trades,
            "wins": env.wins,
            "losses": env.losses,
            "win_rate": round(win_rate, 1),
            "training_steps": agent.training_steps,
            "memory_size": len(agent.memory),
            "elapsed_seconds": (datetime.now() - start_time).seconds
        }
        
        # Write live progress
        PROGRESS_FILE.parent.mkdir(exist_ok=True)
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f)
        
        # Log to training history
        training_log.append(progress)
        
        # Console output
        if episode % 5 == 0 or episode == 1:
            elapsed = (datetime.now() - start_time).seconds
            eta_seconds = elapsed / episode * (EPISODES - episode) if episode > 0 else 0
            eta_minutes = eta_seconds / 60
            
            logger.info(
                f"Ep {episode:3d}/{EPISODES} | "
                f"Reward: {total_reward:7.1f} | "
                f"ROI: {roi:+6.1f}% | "
                f"WinRate: {win_rate:4.0f}% | "
                f"Trades: {env.trades:3d} | "
                f"Best: {best_reward:.1f} | "
                f"ETA: {eta_minutes:.0f}min"
            )
        
        # Save full log periodically
        if episode % 50 == 0:
            with open(LOG_FILE, 'w') as f:
                json.dump(training_log, f, indent=2)
    
    # Final save
    agent._save_model()
    with open(LOG_FILE, 'w') as f:
        json.dump(training_log, f, indent=2)
    
    # Final stats
    total_time = (datetime.now() - start_time).seconds / 60
    logger.info(f"\n✅ Training Complete!")
    logger.info(f"   Total time: {total_time:.1f} minutes")
    logger.info(f"   Best Reward: {best_reward:.1f}")
    logger.info(f"   Best ROI: {best_roi:.1f}%")
    logger.info(f"   Training Steps: {agent.training_steps:,}")
    
    return {
        "episodes": EPISODES,
        "best_reward": best_reward,
        "best_roi": best_roi,
        "avg_reward": np.mean(rewards_history),
        "training_steps": agent.training_steps,
        "total_time_minutes": total_time
    }


if __name__ == "__main__":
    train_enhanced_dqn()
