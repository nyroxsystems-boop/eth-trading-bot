"""
Enhanced DQN Trading Agent V2
Professional-grade Deep Q-Network with:
- Dueling DQN Architecture (separates value and advantage)
- Multi-Head Attention for pattern recognition
- LSTM for temporal dynamics
- Noisy Networks for exploration
- Prioritized Experience Replay
- Advanced State Engineering (50+ features)
- Sophisticated Reward Shaping
"""

import os
import sys
import math
import random
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import deque, namedtuple
from datetime import datetime

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.optim as optim
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    print("⚠️ PyTorch not installed")

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Experience tuple
Experience = namedtuple('Experience', ['state', 'action', 'reward', 'next_state', 'done', 'priority'])


class NoisyLinear(nn.Module):
    """Noisy Linear Layer for exploration (instead of epsilon-greedy)"""
    
    def __init__(self, in_features: int, out_features: int, sigma_init: float = 0.5):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.sigma_init = sigma_init
        
        # Learnable parameters
        self.weight_mu = nn.Parameter(torch.empty(out_features, in_features))
        self.weight_sigma = nn.Parameter(torch.empty(out_features, in_features))
        self.bias_mu = nn.Parameter(torch.empty(out_features))
        self.bias_sigma = nn.Parameter(torch.empty(out_features))
        
        # Factorized noise
        self.register_buffer('weight_epsilon', torch.empty(out_features, in_features))
        self.register_buffer('bias_epsilon', torch.empty(out_features))
        
        self._reset_parameters()
        self._reset_noise()
    
    def _reset_parameters(self):
        mu_range = 1 / math.sqrt(self.in_features)
        self.weight_mu.data.uniform_(-mu_range, mu_range)
        self.weight_sigma.data.fill_(self.sigma_init / math.sqrt(self.in_features))
        self.bias_mu.data.uniform_(-mu_range, mu_range)
        self.bias_sigma.data.fill_(self.sigma_init / math.sqrt(self.out_features))
    
    def _reset_noise(self):
        epsilon_in = self._scale_noise(self.in_features)
        epsilon_out = self._scale_noise(self.out_features)
        self.weight_epsilon.copy_(epsilon_out.outer(epsilon_in))
        self.bias_epsilon.copy_(epsilon_out)
    
    def _scale_noise(self, size: int) -> torch.Tensor:
        x = torch.randn(size)
        return x.sign() * x.abs().sqrt()
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.training:
            weight = self.weight_mu + self.weight_sigma * self.weight_epsilon
            bias = self.bias_mu + self.bias_sigma * self.bias_epsilon
        else:
            weight = self.weight_mu
            bias = self.bias_mu
        return F.linear(x, weight, bias)


class MultiHeadAttention(nn.Module):
    """Multi-Head Self-Attention for pattern recognition"""
    
    def __init__(self, embed_dim: int, num_heads: int = 4):
        super().__init__()
        self.attention = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
        self.norm = nn.LayerNorm(embed_dim)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch, seq_len, embed_dim)
        attn_out, _ = self.attention(x, x, x)
        return self.norm(x + attn_out)


class DuelingDQN(nn.Module):
    """
    Dueling DQN with Attention and LSTM
    State-of-the-art architecture for trading
    """
    
    def __init__(
        self,
        state_size: int,
        action_size: int = 3,
        hidden_size: int = 256,
        lstm_hidden: int = 128,
        num_heads: int = 4,
        use_noisy: bool = True
    ):
        super().__init__()
        self.state_size = state_size
        self.action_size = action_size
        self.hidden_size = hidden_size
        
        # Initial feature extraction
        self.feature_layer = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.GELU(),
            nn.Dropout(0.1)
        )
        
        # Self-attention for pattern recognition
        self.attention = MultiHeadAttention(hidden_size, num_heads)
        
        # LSTM for temporal dynamics
        self.lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=lstm_hidden,
            num_layers=2,
            batch_first=True,
            dropout=0.1,
            bidirectional=True
        )
        
        lstm_out_size = lstm_hidden * 2  # Bidirectional
        
        # Dueling architecture branches
        LinearClass = NoisyLinear if use_noisy else nn.Linear
        
        # Value stream (how good is this state?)
        self.value_stream = nn.Sequential(
            LinearClass(lstm_out_size, 128),
            nn.GELU(),
            LinearClass(128, 1)
        )
        
        # Advantage stream (how good is each action relative to others?)
        self.advantage_stream = nn.Sequential(
            LinearClass(lstm_out_size, 128),
            nn.GELU(),
            LinearClass(128, action_size)
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.size(0)
        
        # Feature extraction
        features = self.feature_layer(x)
        
        # Reshape for attention (add sequence dimension)
        features = features.unsqueeze(1)  # (batch, 1, hidden)
        
        # Self-attention
        attended = self.attention(features)
        
        # LSTM processing
        lstm_out, _ = self.lstm(attended)
        lstm_out = lstm_out[:, -1, :]  # Take last output
        
        # Dueling: Q = V + (A - mean(A))
        value = self.value_stream(lstm_out)
        advantage = self.advantage_stream(lstm_out)
        
        # Combine using dueling formula
        q_values = value + (advantage - advantage.mean(dim=1, keepdim=True))
        
        return q_values
    
    def reset_noise(self):
        """Reset noise for noisy layers"""
        for module in self.modules():
            if isinstance(module, NoisyLinear):
                module._reset_noise()


class PrioritizedReplayBuffer:
    """
    Prioritized Experience Replay
    Samples experiences based on TD-error priority
    """
    
    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,  # Prioritization strength
        beta: float = 0.4,   # Importance sampling
        beta_increment: float = 0.001
    ):
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.buffer = []
        self.priorities = deque(maxlen=capacity)
        self.position = 0
    
    def push(self, state, action, reward, next_state, done, priority=None):
        max_priority = max(self.priorities) if self.priorities else 1.0
        
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        
        self.buffer[self.position] = Experience(state, action, reward, next_state, done, priority or max_priority)
        self.priorities.append(priority or max_priority)
        self.position = (self.position + 1) % self.capacity
    
    def sample(self, batch_size: int) -> Tuple:
        if len(self.buffer) == 0:
            return None
        
        # Calculate sampling probabilities
        priorities = np.array(list(self.priorities)[:len(self.buffer)]) ** self.alpha
        probs = priorities / priorities.sum()
        
        # Sample indices
        indices = np.random.choice(len(self.buffer), batch_size, p=probs)
        
        # Calculate importance sampling weights
        self.beta = min(1.0, self.beta + self.beta_increment)
        weights = (len(self.buffer) * probs[indices]) ** (-self.beta)
        weights = weights / weights.max()
        
        # Get experiences
        batch = [self.buffer[idx] for idx in indices]
        
        states = np.array([e.state for e in batch])
        actions = np.array([e.action for e in batch])
        rewards = np.array([e.reward for e in batch])
        next_states = np.array([e.next_state for e in batch])
        dones = np.array([e.done for e in batch])
        
        return states, actions, rewards, next_states, dones, indices, weights
    
    def update_priorities(self, indices: np.ndarray, priorities: np.ndarray):
        for idx, priority in zip(indices, priorities):
            if idx < len(self.priorities):
                self.priorities[idx] = priority + 1e-6
    
    def __len__(self):
        return len(self.buffer)


class AdvancedTradingEnvironment:
    """
    Enhanced Trading Environment with:
    - 50+ state features
    - Sophisticated reward shaping
    - Transaction costs
    - Slippage simulation
    """
    
    HOLD = 0
    BUY = 1
    SELL = 2
    
    def __init__(
        self,
        window_size: int = 30,
        initial_balance: float = 10000,
        transaction_cost: float = 0.001,  # 0.1% fee
        slippage: float = 0.0005  # 0.05% slippage
    ):
        self.window_size = window_size
        self.initial_balance = initial_balance
        self.transaction_cost = transaction_cost
        self.slippage = slippage
        
        # State size: returns(29) + technicals(15) + position(6) = 50
        self.state_size = (window_size - 1) + 15 + 6
        self.action_size = 3
        self.reset(np.array([100.0]))
    
    def reset(self, prices: np.ndarray, volumes: np.ndarray = None) -> np.ndarray:
        self.prices = prices
        self.volumes = volumes if volumes is not None else np.ones_like(prices)
        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.position = 0
        self.entry_price = 0
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0
        self.max_portfolio_value = self.initial_balance
        self.done = False
        
        return self._get_state()
    
    def _calculate_technicals(self, window: np.ndarray) -> np.ndarray:
        """Calculate technical indicators for state"""
        if len(window) < 2:
            return np.zeros(15)
        
        # Returns
        returns = np.diff(window) / window[:-1]
        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Moving averages
        sma_5 = np.mean(window[-5:]) if len(window) >= 5 else window[-1]
        sma_10 = np.mean(window[-10:]) if len(window) >= 10 else window[-1]
        sma_20 = np.mean(window[-20:]) if len(window) >= 20 else window[-1]
        ema_12 = self._ema(window, 12)
        ema_26 = self._ema(window, 26)
        
        current_price = window[-1]
        
        # Price relative to MAs
        sma_5_ratio = (current_price / sma_5 - 1) if sma_5 > 0 else 0
        sma_10_ratio = (current_price / sma_10 - 1) if sma_10 > 0 else 0
        sma_20_ratio = (current_price / sma_20 - 1) if sma_20 > 0 else 0
        
        # MACD
        macd = ema_12 - ema_26
        macd_signal = self._ema(np.array([macd]), 9) if macd != 0 else 0
        macd_normalized = macd / current_price if current_price > 0 else 0
        
        # RSI
        gains = np.maximum(returns, 0)
        losses = np.maximum(-returns, 0)
        avg_gain = np.mean(gains[-14:]) if len(gains) >= 14 else np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses[-14:]) if len(losses) >= 14 else np.mean(losses) if len(losses) > 0 else 0
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = (100 - 100 / (1 + rs)) / 100 - 0.5  # Normalize to [-0.5, 0.5]
        
        # Volatility
        volatility = np.std(returns) if len(returns) > 0 else 0
        volatility_ratio = volatility / np.mean(np.abs(returns) + 1e-10) if len(returns) > 0 else 0
        
        # Trend
        trend_5 = (window[-1] - window[-5]) / window[-5] if len(window) >= 5 and window[-5] > 0 else 0
        trend_10 = (window[-1] - window[-10]) / window[-10] if len(window) >= 10 and window[-10] > 0 else 0
        
        # Momentum
        momentum = returns[-1] if len(returns) > 0 else 0
        momentum_ma = np.mean(returns[-5:]) if len(returns) >= 5 else momentum
        
        # Volume features (normalized)
        volume_window = self.volumes[max(0, self.current_step - self.window_size):self.current_step]
        volume_ratio = volume_window[-1] / (np.mean(volume_window) + 1e-10) if len(volume_window) > 0 else 1.0
        
        return np.array([
            sma_5_ratio, sma_10_ratio, sma_20_ratio,
            macd_normalized,
            rsi,
            volatility, volatility_ratio,
            trend_5, trend_10,
            momentum, momentum_ma,
            volume_ratio,
            np.max(returns[-5:]) if len(returns) >= 5 else 0,  # Max recent return
            np.min(returns[-5:]) if len(returns) >= 5 else 0,  # Min recent return
            np.mean(returns) if len(returns) > 0 else 0  # Average return
        ])
    
    def _ema(self, data: np.ndarray, period: int) -> float:
        if len(data) == 0:
            return 0.0
        alpha = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema
    
    def _get_state(self) -> np.ndarray:
        """Get enhanced state representation"""
        start_idx = max(0, self.current_step - self.window_size)
        window = self.prices[start_idx:self.current_step]
        
        if len(window) < self.window_size:
            window = np.pad(window, (self.window_size - len(window), 0), mode='edge')
        
        # Returns sequence
        returns = np.diff(window) / window[:-1]
        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Technical features
        technicals = self._calculate_technicals(window)
        
        # Position features
        current_price = self.prices[self.current_step]
        has_position = 1.0 if self.position > 0 else 0.0
        unrealized_pnl = 0.0
        position_duration = 0.0
        
        if self.position > 0 and self.entry_price > 0:
            unrealized_pnl = (current_price - self.entry_price) / self.entry_price
        
        portfolio_value = self.balance + self.position * current_price
        drawdown = (self.max_portfolio_value - portfolio_value) / self.max_portfolio_value
        win_rate = self.wins / max(self.trades, 1)
        
        position_features = np.array([
            has_position,
            unrealized_pnl,
            (self.balance / self.initial_balance) - 1,
            (portfolio_value / self.initial_balance) - 1,
            drawdown,
            win_rate - 0.5  # Center around 0
        ])
        
        # Combine all features
        state = np.concatenate([returns, technicals, position_features])
        
        return state.astype(np.float32)
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """Execute action with realistic costs and reward shaping"""
        current_price = self.prices[self.current_step]
        reward = 0.0
        info = {'action': 'HOLD'}
        
        # Apply slippage to execution price
        if action == self.BUY:
            exec_price = current_price * (1 + self.slippage)
        elif action == self.SELL:
            exec_price = current_price * (1 - self.slippage)
        else:
            exec_price = current_price
        
        if action == self.BUY and self.position == 0:
            # Calculate amount after transaction cost
            available = self.balance * (1 - self.transaction_cost)
            amount = available / exec_price
            
            self.position = amount
            self.entry_price = exec_price
            self.balance = 0
            self.trades += 1
            
            info = {'action': 'BUY', 'price': exec_price, 'amount': amount}
            
            # Small penalty for action (encourage precision)
            reward = -0.1
            
        elif action == self.SELL and self.position > 0:
            # Sell with transaction cost
            gross_value = self.position * exec_price
            net_value = gross_value * (1 - self.transaction_cost)
            
            pnl = (exec_price - self.entry_price) / self.entry_price
            pnl_usd = net_value - (self.position * self.entry_price)
            
            self.balance = net_value
            self.total_pnl += pnl_usd
            
            # Track wins/losses
            if pnl > 0:
                self.wins += 1
            else:
                self.losses += 1
            
            # Reward shaping: asymmetric - bigger punishment for losses
            if pnl > 0:
                reward = pnl * 100 * (1 + pnl)  # Compound reward for bigger wins
            else:
                reward = pnl * 150  # Stronger penalty for losses (risk management)
            
            # Bonus for maintaining win rate
            win_rate = self.wins / max(self.trades, 1)
            if win_rate > 0.6:
                reward += 1.0
            
            info = {'action': 'SELL', 'price': exec_price, 'pnl': pnl, 'pnl_usd': pnl_usd}
            
            self.position = 0
            self.entry_price = 0
            
        else:
            # Hold
            if self.position > 0:
                # Small reward/penalty based on unrealized movement
                prev_price = self.prices[self.current_step - 1]
                price_change = (current_price - prev_price) / prev_price
                reward = price_change * 5
            else:
                # Tiny penalty for not being in market during uptrend
                if self.current_step > 1:
                    prev_price = self.prices[self.current_step - 1]
                    if current_price > prev_price:
                        reward = -0.01  # Missed opportunity
        
        # Update portfolio tracking
        portfolio_value = self.balance + self.position * current_price
        self.max_portfolio_value = max(self.max_portfolio_value, portfolio_value)
        
        # Move forward
        self.current_step += 1
        
        # Check if done
        if self.current_step >= len(self.prices) - 1:
            self.done = True
            
            # Final portfolio value
            final_value = self.balance + self.position * self.prices[self.current_step]
            total_return = (final_value - self.initial_balance) / self.initial_balance
            
            # Final reward based on overall performance
            reward += total_return * 100
            
            # Bonus for consistent performance
            sharpe_approx = total_return / (np.std(self.prices[-100:]) / np.mean(self.prices[-100:]) + 1e-10)
            reward += np.clip(sharpe_approx, -10, 10)
        
        new_state = self._get_state() if not self.done else np.zeros(self.state_size)
        
        return new_state, reward, self.done, info
    
    def get_portfolio_value(self) -> float:
        current_price = self.prices[min(self.current_step, len(self.prices) - 1)]
        return self.balance + self.position * current_price


class EnhancedDQNAgent:
    """
    Professional-Grade DQN Agent
    Features: Dueling DQN, PER, Noisy Nets, Double DQN
    """
    
    def __init__(
        self,
        state_size: int = 50,
        action_size: int = 3,
        learning_rate: float = 0.0003,
        gamma: float = 0.99,
        tau: float = 0.005,  # Soft update rate
        buffer_size: int = 100000,
        batch_size: int = 128,
        model_path: str = None
    ):
        if not PYTORCH_AVAILABLE:
            raise ImportError("PyTorch required")
        
        self.state_size = state_size
        self.action_size = action_size
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        self.model_path = model_path or "logs/enhanced_dqn.pt"
        
        # Networks
        self.policy_net = DuelingDQN(state_size, action_size)
        self.target_net = DuelingDQN(state_size, action_size)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()
        
        # Optimizers
        self.optimizer = optim.AdamW(self.policy_net.parameters(), lr=learning_rate, weight_decay=0.01)
        self.scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(self.optimizer, T_0=100, T_mult=2)
        
        # Prioritized replay
        self.memory = PrioritizedReplayBuffer(capacity=buffer_size)
        
        # Training stats
        self.training_steps = 0
        self.is_trained = False
        
        self._load_model()
    
    def act(self, state: np.ndarray, training: bool = True) -> int:
        """Choose action using the policy network"""
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0)
            
            if training:
                self.policy_net.reset_noise()
            
            q_values = self.policy_net(state_t)
            return q_values.argmax().item()
    
    def remember(self, state, action, reward, next_state, done):
        """Store experience with priority"""
        self.memory.push(state, action, reward, next_state, done)
    
    def replay(self) -> float:
        """Train on batch with prioritized replay"""
        if len(self.memory) < self.batch_size:
            return 0.0
        
        result = self.memory.sample(self.batch_size)
        if result is None:
            return 0.0
        
        states, actions, rewards, next_states, dones, indices, weights = result
        
        # Convert to tensors
        states_t = torch.FloatTensor(states)
        actions_t = torch.LongTensor(actions)
        rewards_t = torch.FloatTensor(rewards)
        next_states_t = torch.FloatTensor(next_states)
        dones_t = torch.FloatTensor(dones)
        weights_t = torch.FloatTensor(weights)
        
        # Current Q values
        current_q = self.policy_net(states_t).gather(1, actions_t.unsqueeze(1))
        
        # Double DQN: use policy net to select action, target net to evaluate
        with torch.no_grad():
            next_actions = self.policy_net(next_states_t).argmax(1, keepdim=True)
            next_q = self.target_net(next_states_t).gather(1, next_actions)
            target_q = rewards_t.unsqueeze(1) + (1 - dones_t.unsqueeze(1)) * self.gamma * next_q
        
        # TD errors for priority update
        td_errors = torch.abs(current_q - target_q).detach().numpy().flatten()
        self.memory.update_priorities(indices, td_errors)
        
        # Weighted loss
        loss = (weights_t.unsqueeze(1) * F.smooth_l1_loss(current_q, target_q, reduction='none')).mean()
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()
        self.scheduler.step()
        
        # Soft update target network
        self._soft_update()
        
        self.training_steps += 1
        
        return loss.item()
    
    def _soft_update(self):
        """Soft update of target network"""
        for target_param, policy_param in zip(self.target_net.parameters(), self.policy_net.parameters()):
            target_param.data.copy_(self.tau * policy_param.data + (1 - self.tau) * target_param.data)
    
    def get_trading_decision(self, state: np.ndarray) -> Dict:
        """Get trading decision with confidence"""
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0)
            q_values = self.policy_net(state_t).squeeze().numpy()
            
            action_idx = np.argmax(q_values)
            actions = ["HOLD", "BUY", "SELL"]
            
            # Confidence via softmax
            probs = np.exp(q_values) / np.sum(np.exp(q_values))
            
            return {
                "action": actions[action_idx],
                "confidence": float(probs[action_idx]),
                "q_values": {actions[i]: float(q_values[i]) for i in range(3)},
                "probabilities": {actions[i]: float(probs[i]) for i in range(3)}
            }
    
    def train(self, price_data: np.ndarray, episodes: int = 100) -> Dict:
        """Train agent on historical data"""
        env = AdvancedTradingEnvironment(window_size=30, initial_balance=10000)
        
        best_reward = float('-inf')
        rewards_history = []
        
        logger.info(f"Starting Enhanced DQN Training: {episodes} episodes")
        
        for episode in range(episodes):
            state = env.reset(price_data)
            total_reward = 0
            
            while not env.done:
                action = self.act(state, training=True)
                next_state, reward, done, info = env.step(action)
                
                self.remember(state, action, reward, next_state, done)
                loss = self.replay()
                
                state = next_state
                total_reward += reward
            
            rewards_history.append(total_reward)
            
            if total_reward > best_reward:
                best_reward = total_reward
                self._save_model()
            
            if episode % 10 == 0:
                avg_reward = np.mean(rewards_history[-10:])
                portfolio = env.get_portfolio_value()
                roi = (portfolio / env.initial_balance - 1) * 100
                
                logger.info(
                    f"Episode {episode}/{episodes} | "
                    f"Reward: {total_reward:.1f} | "
                    f"Avg: {avg_reward:.1f} | "
                    f"ROI: {roi:.1f}% | "
                    f"Trades: {env.trades} | "
                    f"WinRate: {env.wins/max(env.trades,1)*100:.0f}%"
                )
        
        self.is_trained = True
        self._save_model()
        
        return {
            "episodes": episodes,
            "best_reward": best_reward,
            "avg_reward": np.mean(rewards_history),
            "final_portfolio": env.get_portfolio_value(),
            "total_trades": env.trades,
            "win_rate": env.wins / max(env.trades, 1)
        }
    
    def _save_model(self):
        """Save model to disk"""
        Path(self.model_path).parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            'policy_net': self.policy_net.state_dict(),
            'target_net': self.target_net.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'training_steps': self.training_steps,
            'is_trained': self.is_trained
        }, self.model_path)
        logger.info(f"Model saved to {self.model_path}")
    
    def _load_model(self):
        """Load model from disk"""
        if Path(self.model_path).exists():
            try:
                checkpoint = torch.load(self.model_path, weights_only=False)
                self.policy_net.load_state_dict(checkpoint['policy_net'])
                self.target_net.load_state_dict(checkpoint['target_net'])
                self.optimizer.load_state_dict(checkpoint['optimizer'])
                self.training_steps = checkpoint.get('training_steps', 0)
                self.is_trained = checkpoint.get('is_trained', False)
                logger.info(f"✅ Loaded Enhanced DQN from {self.model_path}")
            except Exception as e:
                logger.warning(f"Could not load model: {e}")


# Quick test
if __name__ == "__main__":
    # Generate test data
    np.random.seed(42)
    days = 30
    hours_per_day = 24
    prices = 2000 + np.cumsum(np.random.randn(days * hours_per_day) * 10)
    prices = np.maximum(prices, 1000)  # Ensure positive
    
    agent = EnhancedDQNAgent(state_size=50)
    
    print("🧠 Enhanced DQN Agent initialized")
    print(f"   State size: {agent.state_size}")
    print(f"   Policy net parameters: {sum(p.numel() for p in agent.policy_net.parameters()):,}")
    
    # Quick training test
    results = agent.train(prices, episodes=10)
    print(f"\n📊 Training Results:")
    print(f"   Best Reward: {results['best_reward']:.1f}")
    print(f"   Win Rate: {results['win_rate']*100:.0f}%")
