"""
Reinforcement Learning Optimizer — Self-optimizing Swarm Weights.

Instead of static weights that update slowly via rolling accuracy,
this RL agent learns which Swarm agents perform best in which REGIME
and dynamically adjusts weights for maximum edge.

Algorithm: Contextual Multi-Armed Bandit (Thompson Sampling)
- Each agent is an "arm"  
- Context = market regime (trending/ranging/volatile)
- Reward = trade outcome (win/loss/partial)

Why Thompson Sampling > Q-Learning for trading:
- Handles non-stationary environments (markets change)
- Natural exploration/exploitation balance
- Works with small sample sizes
- No hyperparameter tuning needed

This is what Renaissance Technologies does at scale.
"""
import json
import logging
import math
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

logger = logging.getLogger("ethbot.rl")


@dataclass
class AgentArm:
    """Thompson Sampling arm for one Swarm agent."""
    name: str
    # Beta distribution parameters per regime
    alpha: dict = field(default_factory=lambda: defaultdict(lambda: 1.0))  # Successes + 1
    beta: dict = field(default_factory=lambda: defaultdict(lambda: 1.0))   # Failures + 1
    total_plays: int = 0

    def sample(self, regime: str) -> float:
        """Sample from Beta distribution for this regime."""
        a = self.alpha.get(regime, 1.0)
        b = self.beta.get(regime, 1.0)
        try:
            return random.betavariate(max(0.01, a), max(0.01, b))
        except ValueError:
            return 0.5

    def update(self, regime: str, was_correct: bool):
        """Update Beta distribution with outcome."""
        if regime not in self.alpha:
            self.alpha[regime] = 1.0
        if regime not in self.beta:
            self.beta[regime] = 1.0

        if was_correct:
            self.alpha[regime] += 1.0
        else:
            self.beta[regime] += 1.0

        self.total_plays += 1

        # Decay: prevent old data from dominating
        # Every 100 plays, decay by 5% toward prior
        if self.total_plays % 100 == 0:
            for r in list(self.alpha.keys()):
                self.alpha[r] = max(1.0, self.alpha[r] * 0.95)
                self.beta[r] = max(1.0, self.beta[r] * 0.95)

    def get_expected_value(self, regime: str) -> float:
        """Get expected win rate for this regime."""
        a = self.alpha.get(regime, 1.0)
        b = self.beta.get(regime, 1.0)
        return a / (a + b)


class RLOptimizer:
    """
    Reinforcement Learning optimizer for Swarm agent weights.
    
    Uses Thompson Sampling to learn which agents perform best
    in each market regime, then adjusts their voting power.
    """

    SAVE_PATH = Path("./logs/brain/rl_weights.json")
    # Weight range
    MIN_WEIGHT = 0.3
    MAX_WEIGHT = 2.5
    # Minimum samples before adjusting weights
    MIN_SAMPLES = 15

    def __init__(self, agent_names: list[str]):
        self.arms: dict[str, AgentArm] = {}
        for name in agent_names:
            self.arms[name] = AgentArm(name=name)
        self._load()
        logger.info(f"🤖 RL Optimizer: {len(self.arms)} agents | Thompson Sampling")

    def get_weights(self, regime: str) -> dict[str, float]:
        """
        Get optimized weights for each agent given the current regime.
        
        Returns:
            Dict of agent_name → weight (0.3 to 2.5)
        """
        weights = {}
        for name, arm in self.arms.items():
            if arm.total_plays < self.MIN_SAMPLES:
                # Not enough data — use default weight
                weights[name] = 1.0
                continue

            # Sample from posterior (exploration + exploitation)
            sampled_value = arm.sample(regime)

            # Convert to weight: 0.3 (bad) to 2.5 (excellent)
            weight = self.MIN_WEIGHT + sampled_value * (self.MAX_WEIGHT - self.MIN_WEIGHT)
            weights[name] = round(weight, 3)

        return weights

    def update(self, agent_name: str, regime: str, voted_buy: bool, was_profitable: bool):
        """
        Update agent's arm after trade outcome.
        
        Only agents that voted BUY get credit/blame.
        """
        if agent_name not in self.arms:
            self.arms[agent_name] = AgentArm(name=agent_name)

        if voted_buy:
            self.arms[agent_name].update(regime, was_profitable)

    def learn_from_trade(self, votes: list[dict], regime: str, was_profitable: bool):
        """
        Learn from a completed trade.
        
        Args:
            votes: List of agent votes from SwarmDecision
            regime: Market regime during trade
            was_profitable: Whether the trade was profitable
        """
        for v in votes:
            agent_name = v.get("agent", "")
            vote_value = v.get("vote", "NEUTRAL")

            if vote_value == "BUY":
                self.update(agent_name, regime, True, was_profitable)
            elif vote_value == "SKIP":
                # SKIP agents are "correct" if trade was NOT profitable
                self.update(agent_name, regime, False, not was_profitable)

        self._save()

    def get_stats(self) -> dict:
        """Get RL optimizer stats."""
        stats = {}
        for name, arm in self.arms.items():
            regime_stats = {}
            for regime in ["trending", "ranging", "volatile"]:
                ev = arm.get_expected_value(regime)
                regime_stats[regime] = round(ev, 3)
            stats[name] = {
                "total_plays": arm.total_plays,
                "expected_values": regime_stats,
            }
        return {
            "total_agents": len(self.arms),
            "total_updates": sum(a.total_plays for a in self.arms.values()),
            "agents": stats,
        }

    def _save(self):
        """Persist RL state."""
        self.SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {}
            for name, arm in self.arms.items():
                data[name] = {
                    "alpha": dict(arm.alpha),
                    "beta": dict(arm.beta),
                    "total_plays": arm.total_plays,
                }
            self.SAVE_PATH.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.debug(f"RL save: {e}")

    def _load(self):
        """Load RL state."""
        if not self.SAVE_PATH.exists():
            return
        try:
            data = json.loads(self.SAVE_PATH.read_text())
            for name, saved in data.items():
                if name in self.arms:
                    arm = self.arms[name]
                    arm.alpha = defaultdict(lambda: 1.0, saved.get("alpha", {}))
                    arm.beta = defaultdict(lambda: 1.0, saved.get("beta", {}))
                    arm.total_plays = saved.get("total_plays", 0)
            logger.info(f"🤖 RL state loaded: {sum(a.total_plays for a in self.arms.values())} total updates")
        except Exception as e:
            logger.debug(f"RL load: {e}")


# Singleton
_instance: Optional[RLOptimizer] = None

def get_rl_optimizer(agent_names: list[str] = None) -> RLOptimizer:
    global _instance
    if _instance is None:
        if agent_names is None:
            agent_names = [
                "RSI", "MACD", "Bollinger", "Volume", "VWAP",
                "ADX", "Regime", "MTF", "Intel", "Brain",
                "Memory", "ML", "OrderFlow",
            ]
        _instance = RLOptimizer(agent_names)
    return _instance
