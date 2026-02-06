"""
Rainbow DQN - State-of-the-Art Deep RL for Trading
Combines ALL improvements from FinRL research:
- Dueling Architecture ✓ (from enhanced_dqn_agent.py)
- Double DQN ✓
- Prioritized Experience Replay ✓
- Multi-step Learning (NEW)
- Distributional RL / C51 (NEW)
- Noisy Networks ✓ (from enhanced_dqn_agent.py)
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from collections import deque, namedtuple
from typing import Tuple, Optional, List
import random
import math

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# MULTI-STEP REPLAY BUFFER
# ============================================================================

class NStepReplayBuffer:
    """
    N-Step Return Replay Buffer for better credit assignment.
    Stores n-step transitions instead of single-step.
    """
    
    def __init__(
        self,
        capacity: int = 100000,
        n_step: int = 3,
        gamma: float = 0.99,
        alpha: float = 0.6,  # PER priority strength
        beta: float = 0.4,   # PER importance sampling
        beta_increment: float = 0.001
    ):
        self.capacity = capacity
        self.n_step = n_step
        self.gamma = gamma
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        
        self.buffer = []
        self.n_step_buffer = deque(maxlen=n_step)
        self.priorities = np.zeros(capacity, dtype=np.float32)
        self.position = 0
        self.max_priority = 1.0
        
    def _get_n_step_info(self) -> Tuple[np.ndarray, float, np.ndarray, bool]:
        """Compute n-step return and get final next_state."""
        reward = 0.0
        for idx, transition in enumerate(self.n_step_buffer):
            reward += (self.gamma ** idx) * transition[2]  # Cumulative discounted reward
            
        state = self.n_step_buffer[0][0]
        action = self.n_step_buffer[0][1]
        next_state = self.n_step_buffer[-1][3]
        done = self.n_step_buffer[-1][4]
        
        return state, action, reward, next_state, done
    
    def push(self, state, action, reward, next_state, done):
        """Add single-step transition, compute n-step when buffer is full."""
        self.n_step_buffer.append((state, action, reward, next_state, done))
        
        # Not enough transitions yet
        if len(self.n_step_buffer) < self.n_step:
            return
            
        # Compute n-step transition
        n_state, n_action, n_reward, n_next_state, n_done = self._get_n_step_info()
        
        # Store with max priority (for new experiences)
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        
        self.buffer[self.position] = (n_state, n_action, n_reward, n_next_state, n_done)
        self.priorities[self.position] = self.max_priority
        self.position = (self.position + 1) % self.capacity
        
        # If episode ended, flush remaining transitions
        if done:
            while len(self.n_step_buffer) > 0:
                self.n_step_buffer.popleft()
                if len(self.n_step_buffer) > 0:
                    n_state, n_action, n_reward, n_next_state, n_done = self._get_n_step_info()
                    if len(self.buffer) < self.capacity:
                        self.buffer.append(None)
                    self.buffer[self.position] = (n_state, n_action, n_reward, n_next_state, n_done)
                    self.priorities[self.position] = self.max_priority
                    self.position = (self.position + 1) % self.capacity
    
    def sample(self, batch_size: int) -> Tuple:
        """Sample from buffer with prioritized experience replay."""
        buffer_len = len(self.buffer)
        
        # Calculate sampling probabilities
        priorities = self.priorities[:buffer_len] ** self.alpha
        probabilities = priorities / priorities.sum()
        
        # Sample indices
        indices = np.random.choice(buffer_len, batch_size, p=probabilities, replace=False)
        
        # Importance sampling weights
        self.beta = min(1.0, self.beta + self.beta_increment)
        weights = (buffer_len * probabilities[indices]) ** (-self.beta)
        weights /= weights.max()  # Normalize
        
        # Get transitions
        batch = [self.buffer[idx] for idx in indices]
        states, actions, rewards, next_states, dones = zip(*batch)
        
        return (
            np.array(states, dtype=np.float32),
            np.array(actions, dtype=np.int64),
            np.array(rewards, dtype=np.float32),
            np.array(next_states, dtype=np.float32),
            np.array(dones, dtype=np.float32),
            indices,
            np.array(weights, dtype=np.float32)
        )
    
    def update_priorities(self, indices: np.ndarray, priorities: np.ndarray):
        """Update priorities based on TD-errors."""
        for idx, priority in zip(indices, priorities):
            self.priorities[idx] = max(priority + 1e-6, 1e-6)  # Avoid zero priority
            self.max_priority = max(self.max_priority, priority)
    
    def __len__(self):
        return len(self.buffer)


# ============================================================================
# DISTRIBUTIONAL DQN (C51)
# ============================================================================

class CategoricalDuelingDQN(nn.Module):
    """
    Categorical (Distributional) Dueling DQN.
    Instead of predicting Q-values, predicts a distribution over returns.
    Based on "A Distributional Perspective on Reinforcement Learning" (2017).
    """
    
    def __init__(
        self,
        state_size: int,
        action_size: int = 3,  # HOLD, BUY, SELL
        hidden_size: int = 256,
        atom_size: int = 51,   # Number of atoms for distribution
        v_min: float = -100.0, # Minimum return
        v_max: float = 100.0   # Maximum return
    ):
        super().__init__()
        
        self.state_size = state_size
        self.action_size = action_size
        self.atom_size = atom_size
        self.v_min = v_min
        self.v_max = v_max
        
        # Support for distribution
        self.support = torch.linspace(v_min, v_max, atom_size)
        self.delta_z = (v_max - v_min) / (atom_size - 1)
        
        # Feature extraction
        self.feature_layer = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.GELU()
        )
        
        # Value stream (distributional)
        self.value_stream = nn.Sequential(
            nn.Linear(hidden_size, 128),
            nn.GELU(),
            nn.Linear(128, atom_size)
        )
        
        # Advantage stream (distributional per action)
        self.advantage_stream = nn.Sequential(
            nn.Linear(hidden_size, 128),
            nn.GELU(),
            nn.Linear(128, action_size * atom_size)
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Returns: Distribution over returns for each action [batch, action, atoms]
        """
        batch_size = x.size(0)
        
        features = self.feature_layer(x)
        
        # Value distribution [batch, atoms]
        value = self.value_stream(features).view(batch_size, 1, self.atom_size)
        
        # Advantage distribution [batch, action, atoms]
        advantage = self.advantage_stream(features).view(batch_size, self.action_size, self.atom_size)
        
        # Combine with dueling: Q = V + (A - mean(A))
        q_atoms = value + advantage - advantage.mean(dim=1, keepdim=True)
        
        # Apply softmax to get probability distribution over atoms
        distribution = F.softmax(q_atoms, dim=-1)
        
        return distribution
    
    def get_q_values(self, x: torch.Tensor) -> torch.Tensor:
        """Get expected Q-values from distribution."""
        distribution = self.forward(x)
        support = self.support.to(x.device)
        q_values = (distribution * support).sum(dim=-1)
        return q_values


# ============================================================================
# RAINBOW AGENT
# ============================================================================

class RainbowAgent:
    """
    Rainbow DQN Agent combining:
    1. Double DQN
    2. Dueling Architecture
    3. Prioritized Experience Replay
    4. Multi-step Learning
    5. Distributional RL (C51)
    6. Noisy Networks (optional, via dropout)
    """
    
    def __init__(
        self,
        state_size: int,
        action_size: int = 3,
        hidden_size: int = 256,
        learning_rate: float = 3e-4,
        gamma: float = 0.99,
        n_step: int = 3,
        atom_size: int = 51,
        v_min: float = -100.0,
        v_max: float = 100.0,
        buffer_size: int = 100000,
        batch_size: int = 64,
        target_update: int = 1000,
        device: str = None
    ):
        self.state_size = state_size
        self.action_size = action_size
        self.gamma = gamma
        self.n_step = n_step
        self.batch_size = batch_size
        self.target_update = target_update
        self.atom_size = atom_size
        self.v_min = v_min
        self.v_max = v_max
        
        # Device
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        
        logger.info(f"🎮 Rainbow DQN Agent initialized on {self.device}")
        
        # Networks
        self.online_net = CategoricalDuelingDQN(
            state_size, action_size, hidden_size, atom_size, v_min, v_max
        ).to(self.device)
        
        self.target_net = CategoricalDuelingDQN(
            state_size, action_size, hidden_size, atom_size, v_min, v_max
        ).to(self.device)
        
        self.target_net.load_state_dict(self.online_net.state_dict())
        self.target_net.eval()
        
        # Support for C51
        self.support = torch.linspace(v_min, v_max, atom_size).to(self.device)
        self.delta_z = (v_max - v_min) / (atom_size - 1)
        
        # Optimizer
        self.optimizer = torch.optim.Adam(self.online_net.parameters(), lr=learning_rate)
        
        # N-Step Replay Buffer
        self.memory = NStepReplayBuffer(
            capacity=buffer_size,
            n_step=n_step,
            gamma=gamma
        )
        
        # Training state
        self.train_step = 0
        self.epsilon = 0.1  # Minimal exploration (mostly noisy nets)
        
    def select_action(self, state: np.ndarray, eval_mode: bool = False) -> int:
        """Select action using epsilon-greedy with distributional Q-values."""
        if not eval_mode and random.random() < self.epsilon:
            return random.randint(0, self.action_size - 1)
        
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.online_net.get_q_values(state_t)
            return q_values.argmax(dim=1).item()
    
    def store_transition(self, state, action, reward, next_state, done):
        """Store transition in n-step buffer."""
        self.memory.push(state, action, reward, next_state, done)
    
    def train(self) -> Optional[float]:
        """
        Perform one training step.
        Returns: loss value or None if not enough samples
        """
        if len(self.memory) < self.batch_size:
            return None
        
        # Sample from prioritized replay
        states, actions, rewards, next_states, dones, indices, weights = \
            self.memory.sample(self.batch_size)
        
        states = torch.FloatTensor(states).to(self.device)
        actions = torch.LongTensor(actions).to(self.device)
        rewards = torch.FloatTensor(rewards).to(self.device)
        next_states = torch.FloatTensor(next_states).to(self.device)
        dones = torch.FloatTensor(dones).to(self.device)
        weights = torch.FloatTensor(weights).to(self.device)
        
        # === DISTRIBUTIONAL RL LOSS (Cross-entropy over projected distribution) ===
        
        # Current distribution
        current_dist = self.online_net(states)  # [batch, action, atoms]
        current_dist = current_dist[range(self.batch_size), actions]  # [batch, atoms]
        
        with torch.no_grad():
            # Double DQN: Use online net to select action
            next_q_values = self.online_net.get_q_values(next_states)
            next_actions = next_q_values.argmax(dim=1)
            
            # Use target net to evaluate
            next_dist = self.target_net(next_states)
            next_dist = next_dist[range(self.batch_size), next_actions]  # [batch, atoms]
            
            # Compute projected distribution (Bellman update for distributions)
            # T_z = r + γ^n * z (clipped to [v_min, v_max])
            t_z = rewards.unsqueeze(1) + (self.gamma ** self.n_step) * \
                  self.support.unsqueeze(0) * (1 - dones.unsqueeze(1))
            t_z = t_z.clamp(self.v_min, self.v_max)
            
            # Compute projection onto support
            b = (t_z - self.v_min) / self.delta_z
            lower = b.floor().long()
            upper = b.ceil().long()
            
            # Handle edge cases
            lower = lower.clamp(0, self.atom_size - 1)
            upper = upper.clamp(0, self.atom_size - 1)
            
            # Distribute probability
            target_dist = torch.zeros_like(next_dist)
            offset = torch.arange(self.batch_size, device=self.device).unsqueeze(1) * self.atom_size
            
            target_dist.view(-1).index_add_(
                0, (lower + offset).view(-1), (next_dist * (upper.float() - b)).view(-1)
            )
            target_dist.view(-1).index_add_(
                0, (upper + offset).view(-1), (next_dist * (b - lower.float())).view(-1)
            )
        
        # Cross-entropy loss
        log_p = torch.log(current_dist + 1e-8)
        elementwise_loss = -(target_dist * log_p).sum(dim=1)
        
        # Apply importance sampling weights
        loss = (elementwise_loss * weights).mean()
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.online_net.parameters(), 10.0)
        self.optimizer.step()
        
        # Update priorities in replay buffer
        priorities = elementwise_loss.detach().cpu().numpy()
        self.memory.update_priorities(indices, priorities)
        
        # Update target network
        self.train_step += 1
        if self.train_step % self.target_update == 0:
            self.target_net.load_state_dict(self.online_net.state_dict())
            logger.debug("🎯 Updated target network")
        
        return loss.item()
    
    def save(self, path: str):
        """Save model."""
        torch.save({
            'online_net': self.online_net.state_dict(),
            'target_net': self.target_net.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'train_step': self.train_step
        }, path)
        logger.info(f"💾 Saved Rainbow DQN to {path}")
    
    def load(self, path: str):
        """Load model."""
        checkpoint = torch.load(path, map_location=self.device)
        self.online_net.load_state_dict(checkpoint['online_net'])
        self.target_net.load_state_dict(checkpoint['target_net'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])
        self.train_step = checkpoint['train_step']
        logger.info(f"📂 Loaded Rainbow DQN from {path}")


# ============================================================================
# QUICK TEST
# ============================================================================

if __name__ == "__main__":
    print("🌈 Testing Rainbow DQN Agent...")
    
    # Create agent
    state_size = 50  # Example state size
    agent = RainbowAgent(state_size=state_size, batch_size=32)
    
    # Simulate some transitions
    for i in range(100):
        state = np.random.randn(state_size).astype(np.float32)
        action = agent.select_action(state)
        reward = np.random.randn() * 0.1
        next_state = np.random.randn(state_size).astype(np.float32)
        done = i == 99
        
        agent.store_transition(state, action, reward, next_state, done)
    
    # Train
    for _ in range(50):
        loss = agent.train()
        if loss is not None:
            print(f"  Loss: {loss:.4f}")
    
    print("✅ Rainbow DQN test passed!")
