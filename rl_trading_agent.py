#!/usr/bin/env python3
"""
Reinforcement Learning Trading Agent - Deep Q-Network (DQN)
Learns optimal trading decisions through experience and rewards
"""

import os
import random
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple
from collections import deque
from datetime import datetime
import json

# Check for PyTorch
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    import torch.nn.functional as F
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    nn = None  # type: ignore
    torch = None  # type: ignore
    optim = None  # type: ignore
    F = None  # type: ignore
    print("⚠️ PyTorch not installed. Run: pip install torch")

_BASE = nn.Module if PYTORCH_AVAILABLE else object


class TradingEnvironment:
    """
    Trading environment for RL agent.
    Simulates market conditions and provides rewards based on trading decisions.
    """
    
    # Actions
    HOLD = 0
    BUY = 1
    SELL = 2
    
    def __init__(self, window_size: int = 20, initial_balance: float = 10000):
        self.window_size = window_size
        self.initial_balance = initial_balance
        
        # State
        self.balance = initial_balance
        self.position = 0.0  # Amount of ETH held
        self.entry_price = 0.0
        self.current_step = 0
        self.prices = []
        self.done = False
        
        # State size: (window_size - 1) returns + 8 additional features
        self.state_size = (window_size - 1) + 8
    
    def reset(self, prices: np.ndarray) -> np.ndarray:
        """Reset environment with new price data"""
        self.prices = prices
        self.balance = self.initial_balance
        self.position = 0.0
        self.entry_price = 0.0
        self.current_step = self.window_size
        self.done = False
        
        return self._get_state()
    
    def _get_state(self) -> np.ndarray:
        """Get current state representation"""
        # Price window (normalized returns)
        start_idx = max(0, self.current_step - self.window_size)
        window = self.prices[start_idx:self.current_step]
        
        if len(window) < self.window_size:
            # Pad if needed
            window = np.pad(window, (self.window_size - len(window), 0), mode='edge')
        
        # Normalize prices to returns
        returns = np.diff(window) / window[:-1]
        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Technical features
        sma_5 = np.mean(window[-5:]) if len(window) >= 5 else window[-1]
        sma_20 = np.mean(window)
        volatility = np.std(returns) if len(returns) > 0 else 0.0
        trend = (window[-1] - window[0]) / window[0] if window[0] != 0 else 0.0
        
        # Position info
        has_position = 1.0 if self.position > 0 else 0.0
        unrealized_pnl = 0.0
        if self.position > 0:
            unrealized_pnl = (self.prices[self.current_step] - self.entry_price) / self.entry_price
        
        # Combine features
        features = np.concatenate([
            returns,  # window_size - 1 features
            [sma_5 / self.prices[self.current_step] - 1],  # 1 feature
            [sma_20 / self.prices[self.current_step] - 1],  # 1 feature
            [volatility],  # 1 feature
            [trend],  # 1 feature
            [has_position],  # 1 feature
            [unrealized_pnl],  # 1 feature
            [self.balance / self.initial_balance - 1],  # 1 feature
            [(self.position * self.prices[self.current_step]) / self.initial_balance]  # 1 feature
        ])
        
        return features.astype(np.float32)
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """Execute action and return new state, reward, done, info"""
        current_price = self.prices[self.current_step]
        reward = 0.0
        info = {}
        
        if action == self.BUY and self.position == 0:
            # Buy with 95% of balance (keep some for fees)
            amount_to_buy = (self.balance * 0.95) / current_price
            self.position = amount_to_buy
            self.entry_price = current_price
            self.balance -= amount_to_buy * current_price
            info['action'] = 'BUY'
            info['price'] = current_price
            info['amount'] = amount_to_buy
            
        elif action == self.SELL and self.position > 0:
            # Sell all position
            sell_value = self.position * current_price
            pnl = (current_price - self.entry_price) / self.entry_price
            reward = pnl * 100  # Reward proportional to PnL
            self.balance += sell_value
            info['action'] = 'SELL'
            info['price'] = current_price
            info['pnl'] = pnl
            self.position = 0
            self.entry_price = 0
            
        else:
            # Hold
            info['action'] = 'HOLD'
            # Small negative reward for holding to encourage action
            if self.position > 0:
                # Reward/penalize based on price movement
                prev_price = self.prices[self.current_step - 1]
                price_change = (current_price - prev_price) / prev_price
                reward = price_change * 10  # Small reward for price increase while holding
        
        # Move to next step
        self.current_step += 1
        
        # Check if done
        if self.current_step >= len(self.prices) - 1:
            self.done = True
            # Final reward: total portfolio value vs initial
            total_value = self.balance + self.position * self.prices[self.current_step]
            final_return = (total_value - self.initial_balance) / self.initial_balance
            reward += final_return * 50  # Bonus for good final performance
        
        new_state = self._get_state() if not self.done else np.zeros(self.state_size)
        
        return new_state, reward, self.done, info
    
    def get_portfolio_value(self) -> float:
        """Get current total portfolio value"""
        return self.balance + self.position * self.prices[min(self.current_step, len(self.prices) - 1)]


class DQN(_BASE):  # type: ignore[misc]
    """Deep Q-Network for trading decisions"""
    
    def __init__(self, state_size: int, action_size: int = 3, hidden_size: int = 128):
        super(DQN, self).__init__()
        
        self.network = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Linear(64, action_size)
        )
    
    def forward(self, x):
        return self.network(x)


class ReplayBuffer:
    """Experience replay buffer for DQN training"""
    
    def __init__(self, capacity: int = 10000):
        self.buffer = deque(maxlen=capacity)
    
    def push(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))
    
    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, min(batch_size, len(self.buffer)))
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.array(states),
            np.array(actions),
            np.array(rewards),
            np.array(next_states),
            np.array(dones)
        )
    
    def __len__(self):
        return len(self.buffer)


class DQNAgent:
    """
    Deep Q-Network RL Agent for autonomous trading.
    Learns optimal buy/sell/hold decisions through experience.
    """
    
    def __init__(
        self,
        state_size: int = 27,
        action_size: int = 3,
        learning_rate: float = 0.001,
        gamma: float = 0.99,
        epsilon: float = 1.0,
        epsilon_min: float = 0.01,
        epsilon_decay: float = 0.995,
        model_path: str = None
    ):
        self.state_size = state_size
        self.action_size = action_size
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        self.model_path = model_path or (log_dir / "dqn_agent.pt")
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Networks
        self.policy_net = DQN(state_size, action_size).to(self.device)
        self.target_net = DQN(state_size, action_size).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=learning_rate)
        self.memory = ReplayBuffer(capacity=50000)
        
        self.is_trained = False
        self.training_stats = {
            'episodes': 0,
            'total_rewards': [],
            'epsilon_history': []
        }
        
        # Try to load existing model
        self._load_model()
    
    def act(self, state: np.ndarray, training: bool = True) -> int:
        """Choose action using epsilon-greedy policy"""
        if training and random.random() < self.epsilon:
            return random.randrange(self.action_size)
        
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor)
            return q_values.argmax().item()
    
    def remember(self, state, action, reward, next_state, done):
        """Store experience in replay buffer"""
        self.memory.push(state, action, reward, next_state, done)
    
    def replay(self, batch_size: int = 64) -> float:
        """Train on batch of experiences"""
        if len(self.memory) < batch_size:
            return 0.0
        
        states, actions, rewards, next_states, dones = self.memory.sample(batch_size)
        
        states = torch.FloatTensor(states).to(self.device)
        actions = torch.LongTensor(actions).to(self.device)
        rewards = torch.FloatTensor(rewards).to(self.device)
        next_states = torch.FloatTensor(next_states).to(self.device)
        dones = torch.FloatTensor(dones).to(self.device)
        
        # Current Q values
        current_q = self.policy_net(states).gather(1, actions.unsqueeze(1))
        
        # Target Q values (Double DQN)
        with torch.no_grad():
            next_actions = self.policy_net(next_states).argmax(1)
            next_q = self.target_net(next_states).gather(1, next_actions.unsqueeze(1))
            target_q = rewards.unsqueeze(1) + (1 - dones.unsqueeze(1)) * self.gamma * next_q
        
        # Loss
        loss = F.smooth_l1_loss(current_q, target_q)
        
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()
        
        return loss.item()
    
    def update_target_network(self):
        """Copy weights from policy to target network"""
        self.target_net.load_state_dict(self.policy_net.state_dict())
    
    def decay_epsilon(self):
        """Decay exploration rate"""
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
    
    def train(self, price_data: np.ndarray, episodes: int = 100, batch_size: int = 64) -> Dict[str, Any]:
        """Train agent on historical price data"""
        if not PYTORCH_AVAILABLE:
            return {"error": "PyTorch not installed"}
        
        print(f"🎮 Training DQN Agent for {episodes} episodes...")
        
        # Log file for live monitoring
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        training_log = log_dir / "dqn_training_live.json"
        
        env = TradingEnvironment(window_size=20, initial_balance=10000)
        
        episode_rewards = []
        best_reward = float('-inf')
        
        for episode in range(episodes):
            state = env.reset(price_data)
            total_reward = 0
            trades = 0
            
            while not env.done:
                action = self.act(state, training=True)
                next_state, reward, done, info = env.step(action)
                
                self.remember(state, action, reward, next_state, done)
                
                # Train
                if len(self.memory) >= batch_size:
                    self.replay(batch_size)
                
                state = next_state
                total_reward += reward
                
                if info.get('action') in ['BUY', 'SELL']:
                    trades += 1
            
            # Update target network periodically
            if episode % 10 == 0:
                self.update_target_network()
            
            self.decay_epsilon()
            episode_rewards.append(total_reward)
            
            # Track best
            if total_reward > best_reward:
                best_reward = total_reward
                self._save_model()
            
            # Write live training log every 10 episodes
            if (episode + 1) % 10 == 0:
                avg_reward = np.mean(episode_rewards[-20:]) if len(episode_rewards) >= 20 else np.mean(episode_rewards)
                portfolio_value = env.get_portfolio_value()
                roi = (portfolio_value - 10000) / 10000 * 100
                
                live_data = {
                    "timestamp": datetime.now().isoformat(),
                    "episode": episode + 1,
                    "total_episodes": episodes,
                    "progress_pct": round((episode + 1) / episodes * 100, 1),
                    "avg_reward": round(avg_reward, 2),
                    "best_reward": round(best_reward, 2),
                    "last_reward": round(total_reward, 2),
                    "roi": round(roi, 1),
                    "epsilon": round(self.epsilon, 4),
                    "trades": trades,
                    "portfolio_value": round(portfolio_value, 2)
                }
                
                # Write to file (flush immediately)
                with open(training_log, "w") as f:
                    json.dump(live_data, f)
                
                print(f"   Episode {episode+1}/{episodes} | Avg Reward: {avg_reward:.2f} | ROI: {roi:.1f}% | ε: {self.epsilon:.3f} | Trades: {trades}")
        
        self.is_trained = True
        self.training_stats['episodes'] += episodes
        self.training_stats['total_rewards'].extend(episode_rewards)
        self.training_stats['epsilon_history'].append(self.epsilon)
        
        self._save_model()
        
        return {
            "episodes_trained": episodes,
            "best_reward": best_reward,
            "final_epsilon": self.epsilon,
            "avg_reward_last_20": np.mean(episode_rewards[-20:])
        }
    
    def get_trading_decision(self, state: np.ndarray) -> Dict[str, Any]:
        """Get trading decision with confidence scores"""
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor).cpu().numpy()[0]
        
        # Softmax for probabilities
        exp_q = np.exp(q_values - np.max(q_values))
        probabilities = exp_q / exp_q.sum()
        
        action = q_values.argmax()
        action_names = ['HOLD', 'BUY', 'SELL']
        
        return {
            'action': action_names[action],
            'action_id': int(action),
            'confidence': float(probabilities[action]),
            'q_values': {
                'HOLD': float(q_values[0]),
                'BUY': float(q_values[1]),
                'SELL': float(q_values[2])
            },
            'probabilities': {
                'HOLD': float(probabilities[0]),
                'BUY': float(probabilities[1]),
                'SELL': float(probabilities[2])
            }
        }
    
    def _save_model(self):
        """Save model to disk"""
        data = {
            'policy_state': self.policy_net.state_dict(),
            'target_state': self.target_net.state_dict(),
            'optimizer_state': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'is_trained': self.is_trained,
            'training_stats': self.training_stats,
            'timestamp': datetime.now().isoformat()
        }
        torch.save(data, self.model_path)
    
    def _load_model(self):
        """Load model from disk"""
        if not Path(self.model_path).exists():
            return
        
        try:
            data = torch.load(self.model_path, map_location=self.device, weights_only=False)
            self.policy_net.load_state_dict(data['policy_state'])
            self.target_net.load_state_dict(data['target_state'])
            self.optimizer.load_state_dict(data['optimizer_state'])
            self.epsilon = data['epsilon']
            self.is_trained = data['is_trained']
            self.training_stats = data.get('training_stats', {})
            print(f"📂 Loaded DQN Agent from {data.get('timestamp', 'unknown')}")
        except Exception as e:
            print(f"Could not load DQN model: {e}")


def generate_training_data(days: int = 30) -> np.ndarray:
    """Generate realistic price data for training"""
    np.random.seed(42)
    
    # 5-minute candles
    num_candles = days * 24 * 12
    
    prices = [3200.0]
    for _ in range(num_candles - 1):
        # Trend
        trend = np.sin(len(prices) / 500) * 0.001
        # Volatility
        change = np.random.normal(0, 0.002) + trend
        new_price = prices[-1] * (1 + change)
        
        # Support/Resistance
        if new_price < 2800:
            new_price = 2800 + abs(np.random.normal(0, 50))
        elif new_price > 3800:
            new_price = 3800 - abs(np.random.normal(0, 50))
        
        prices.append(new_price)
    
    return np.array(prices)


# CLI
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='DQN Trading Agent')
    parser.add_argument('--train', action='store_true', help='Train the agent')
    parser.add_argument('--episodes', type=int, default=100, help='Training episodes')
    parser.add_argument('--test', action='store_true', help='Test agent on new data')
    args = parser.parse_args()
    
    if args.train:
        print("🚀 Training DQN Trading Agent...")
        prices = generate_training_data(days=60)
        print(f"   Generated {len(prices)} price points for training")
        
        # Use state_size from environment
        env = TradingEnvironment(window_size=20)
        agent = DQNAgent(state_size=env.state_size)
        results = agent.train(prices, episodes=args.episodes)
        
        print("\n✅ Training Complete!")
        print(f"   Episodes: {results['episodes_trained']}")
        print(f"   Best Reward: {results['best_reward']:.2f}")
        print(f"   Final ε: {results['final_epsilon']:.3f}")
    
    elif args.test:
        print("🧪 Testing DQN Agent...")
        env = TradingEnvironment(window_size=20)
        agent = DQNAgent(state_size=env.state_size)
        
        if not agent.is_trained:
            print("⚠️ Agent not trained yet!")
        else:
            # Generate test state
            test_state = np.random.randn(24).astype(np.float32)
            decision = agent.get_trading_decision(test_state)
            
            print("\n📊 Trading Decision:")
            print(f"   Action: {decision['action']}")
            print(f"   Confidence: {decision['confidence']:.2%}")
            print("\n   Q-Values:")
            for action, value in decision['q_values'].items():
                print(f"      {action}: {value:.4f}")
