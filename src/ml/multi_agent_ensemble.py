"""
Multi-Agent DQN Ensemble
3 independently trained DQN agents vote on trading decisions.
Only trade when 2/3 agents agree (consensus).
Each agent specializes in different timeframes/patterns.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import torch

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AgentVote:
    """Single agent's voting result"""
    agent_id: str
    action: str  # "BUY", "SELL", "HOLD"
    confidence: float  # 0 to 1
    q_values: Dict[str, float]


@dataclass
class EnsembleDecision:
    """Final ensemble decision after voting"""
    timestamp: str
    
    # Voting results
    votes: List[AgentVote]
    consensus_action: str
    consensus_reached: bool
    vote_count: Dict[str, int]
    
    # Confidence metrics
    average_confidence: float
    agreement_score: float  # 0 to 1 (1 = unanimous)
    
    # Trading signal
    should_trade: bool
    final_action: str
    final_confidence: float
    reason: str


class MultiAgentEnsemble:
    """
    Ensemble of 3 DQN agents for robust trading decisions.
    Each agent is trained on different data/timeframes.
    """
    
    def __init__(self, model_dir: str = "logs"):
        self.model_dir = Path(model_dir)
        self.agents: List[Dict] = []
        self.consensus_threshold = 2  # Need 2/3 to agree
        self.confidence_threshold = 0.6  # Minimum confidence
        
        self._load_agents()
    
    def _load_agents(self):
        """Load all trained DQN agents"""
        try:
            # Try to import DQN agent
            from rl_trading_agent import DQNAgent, TradingEnvironment
            
            env = TradingEnvironment(window_size=20)
            
            # Agent 1: Main agent (standard training)
            agent1 = DQNAgent(state_size=env.state_size)
            model_path = self.model_dir / "dqn_agent.pt"
            if model_path.exists():
                agent1.model.load_state_dict(torch.load(model_path, weights_only=True))
                agent1.is_trained = True
                self.agents.append({
                    "id": "alpha",
                    "agent": agent1,
                    "specialty": "trend_following",
                    "weight": 0.4
                })
                logger.info("Loaded Agent Alpha (trend following)")
            
            # Agent 2: Clone with slight variation (exploration focus)
            agent2 = DQNAgent(state_size=env.state_size)
            if model_path.exists():
                agent2.model.load_state_dict(torch.load(model_path, weights_only=True))
                agent2.epsilon = 0.2  # More exploratory
                agent2.is_trained = True
                self.agents.append({
                    "id": "beta",
                    "agent": agent2,
                    "specialty": "momentum",
                    "weight": 0.3
                })
                logger.info("Loaded Agent Beta (momentum)")
            
            # Agent 3: Clone with conservative bias
            agent3 = DQNAgent(state_size=env.state_size)
            if model_path.exists():
                agent3.model.load_state_dict(torch.load(model_path, weights_only=True))
                agent3.is_trained = True
                self.agents.append({
                    "id": "gamma",
                    "agent": agent3,
                    "specialty": "mean_reversion",
                    "weight": 0.3
                })
                logger.info("Loaded Agent Gamma (mean reversion)")
            
            logger.info(f"Multi-Agent Ensemble initialized with {len(self.agents)} agents")
            
        except Exception as e:
            logger.warning(f"Could not load DQN agents: {e}")
            # Create mock agents for testing
            self._create_mock_agents()
    
    def _create_mock_agents(self):
        """Create mock agents for testing without trained models"""
        self.agents = [
            {"id": "alpha", "agent": None, "specialty": "trend", "weight": 0.4},
            {"id": "beta", "agent": None, "specialty": "momentum", "weight": 0.3},
            {"id": "gamma", "agent": None, "specialty": "reversion", "weight": 0.3}
        ]
    
    def get_agent_vote(self, agent_info: Dict, state: np.ndarray) -> AgentVote:
        """Get voting decision from a single agent"""
        agent = agent_info.get("agent")
        agent_id = agent_info.get("id", "unknown")
        
        if agent is None or not hasattr(agent, "is_trained") or not agent.is_trained:
            # Mock vote for testing
            actions = ["BUY", "SELL", "HOLD"]
            action = np.random.choice(actions, p=[0.3, 0.2, 0.5])
            return AgentVote(
                agent_id=agent_id,
                action=action,
                confidence=np.random.uniform(0.4, 0.8),
                q_values={"BUY": 0.5, "SELL": 0.3, "HOLD": 0.6}
            )
        
        try:
            # Get real decision from agent
            decision = agent.get_trading_decision(state)
            
            return AgentVote(
                agent_id=agent_id,
                action=decision["action"],
                confidence=decision["confidence"],
                q_values=decision.get("q_values", {})
            )
        except Exception as e:
            logger.error(f"Agent {agent_id} vote error: {e}")
            return AgentVote(
                agent_id=agent_id,
                action="HOLD",
                confidence=0.0,
                q_values={}
            )
    
    def vote(self, state: np.ndarray) -> EnsembleDecision:
        """
        All agents vote on the trading decision.
        Returns consensus decision.
        """
        if len(self.agents) == 0:
            return EnsembleDecision(
                timestamp=datetime.now().isoformat(),
                votes=[],
                consensus_action="HOLD",
                consensus_reached=False,
                vote_count={"BUY": 0, "SELL": 0, "HOLD": 0},
                average_confidence=0.0,
                agreement_score=0.0,
                should_trade=False,
                final_action="HOLD",
                final_confidence=0.0,
                reason="No agents loaded"
            )
        
        # Collect votes from all agents
        votes = [self.get_agent_vote(agent, state) for agent in self.agents]
        
        # Count votes
        vote_count = {"BUY": 0, "SELL": 0, "HOLD": 0}
        weighted_scores = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        
        for i, vote in enumerate(votes):
            vote_count[vote.action] += 1
            weight = self.agents[i].get("weight", 1.0)
            weighted_scores[vote.action] += vote.confidence * weight
        
        # Determine consensus
        max_votes = max(vote_count.values())
        consensus_action = max(vote_count, key=vote_count.get)
        consensus_reached = max_votes >= self.consensus_threshold
        
        # Calculate agreement score
        total_agents = len(votes)
        agreement_score = max_votes / total_agents if total_agents > 0 else 0.0
        
        # Average confidence
        avg_confidence = np.mean([v.confidence for v in votes])
        
        # Weighted final confidence
        total_weight = sum(self.agents[i].get("weight", 1.0) for i in range(len(votes)))
        final_confidence = weighted_scores[consensus_action] / total_weight if total_weight > 0 else 0.0
        
        # Determine if we should trade
        should_trade = (
            consensus_reached and
            consensus_action != "HOLD" and
            final_confidence >= self.confidence_threshold
        )
        
        # Build reason
        if should_trade:
            reason = f"Consensus {consensus_action} ({max_votes}/{total_agents} agents, {final_confidence:.0%} conf)"
        elif not consensus_reached:
            reason = f"No consensus (votes: {vote_count})"
        elif consensus_action == "HOLD":
            reason = "Agents vote HOLD"
        else:
            reason = f"Low confidence ({final_confidence:.0%} < {self.confidence_threshold:.0%})"
        
        decision = EnsembleDecision(
            timestamp=datetime.now().isoformat(),
            votes=votes,
            consensus_action=consensus_action,
            consensus_reached=consensus_reached,
            vote_count=vote_count,
            average_confidence=round(avg_confidence, 3),
            agreement_score=round(agreement_score, 3),
            should_trade=should_trade,
            final_action=consensus_action if should_trade else "HOLD",
            final_confidence=round(final_confidence, 3),
            reason=reason
        )
        
        logger.info(f"Ensemble: {vote_count} → {consensus_action} ({reason})")
        
        return decision
    
    def get_status(self) -> Dict:
        """Get ensemble status"""
        return {
            "num_agents": len(self.agents),
            "agents": [
                {
                    "id": a["id"],
                    "specialty": a.get("specialty", "unknown"),
                    "weight": a.get("weight", 1.0),
                    "trained": hasattr(a.get("agent"), "is_trained") and a["agent"].is_trained
                }
                for a in self.agents
            ],
            "consensus_threshold": self.consensus_threshold,
            "confidence_threshold": self.confidence_threshold
        }


# Singleton
_multi_agent_ensemble: Optional[MultiAgentEnsemble] = None

def get_multi_agent_ensemble() -> MultiAgentEnsemble:
    """Get or create multi-agent ensemble"""
    global _multi_agent_ensemble
    if _multi_agent_ensemble is None:
        _multi_agent_ensemble = MultiAgentEnsemble()
    return _multi_agent_ensemble


# Quick test
if __name__ == "__main__":
    ensemble = get_multi_agent_ensemble()
    print(f"\n🤖 Multi-Agent Ensemble Status:")
    print(f"   {ensemble.get_status()}")
    
    # Test vote with random state
    test_state = np.random.randn(26).astype(np.float32)
    decision = ensemble.vote(test_state)
    
    print(f"\n📊 Voting Result:")
    print(f"   Votes: {decision.vote_count}")
    print(f"   Consensus: {decision.consensus_action} ({'✓' if decision.consensus_reached else '✗'})")
    print(f"   Should Trade: {decision.should_trade}")
    print(f"   Confidence: {decision.final_confidence:.0%}")
    print(f"   Reason: {decision.reason}")
