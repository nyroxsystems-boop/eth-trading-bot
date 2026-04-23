"""
Swarm Intelligence Trading Engine — The Non Plus Ultra.

Instead of a single scoring algorithm, we deploy a SWARM of independent
trading agents. Each agent is a specialist with its own analysis method.
Together they vote on every trade decision through weighted consensus.

Architecture:
- Each Agent analyzes independently (RSI, MACD, Volume, Brain, Memory, etc.)
- Each Agent casts a VOTE: BUY, SKIP, or NEUTRAL with confidence 0-100%
- The Swarm aggregates all votes using weighted consensus
- Agent weights are SELF-LEARNING: agents with better track records get more influence
- Minimum consensus threshold must be met before any trade

Think of it like a hedge fund with 13 portfolio managers who all vote.
The ones with the best track record have the loudest voice.

This is how Renaissance Technologies and Citadel actually work.
"""
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("ethbot.swarm")


class Vote(Enum):
    """An agent's vote on a trade."""
    BUY = "BUY"
    SKIP = "SKIP"
    NEUTRAL = "NEUTRAL"


@dataclass
class AgentVote:
    """A single agent's vote with reasoning."""
    agent_name: str
    vote: Vote
    confidence: float  # 0.0 - 1.0
    reason: str = ""


@dataclass
class SwarmDecision:
    """The collective decision of the swarm."""
    final_vote: Vote
    consensus_pct: float  # % of agents voting BUY
    weighted_score: float  # Confidence-weighted consensus score
    total_agents: int
    buy_votes: int
    skip_votes: int
    neutral_votes: int
    votes: list  # All individual AgentVote objects
    approved: bool = False
    reasoning: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# AGENT BASE CLASS
# ═══════════════════════════════════════════════════════════════════════════

class SwarmAgent:
    """
    Base class for all swarm agents.
    
    Each agent is an independent specialist that analyzes the market
    from its own perspective and casts a vote.
    """

    def __init__(self, name: str, weight: float = 1.0):
        self.name = name
        self.weight = weight  # Voting power (self-learning)
        self.total_votes = 0
        self.correct_votes = 0
        self.accuracy = 0.5
        # Rolling window for weight updates (prevents survivorship bias)
        self._recent_results: list[bool] = []
        self._rolling_window = 50  # Only last 50 trades count

    def analyze(self, data: dict) -> AgentVote:
        """Override this: analyze market data and return a vote."""
        raise NotImplementedError

    def update_accuracy(self, was_correct: bool, agent_voted_buy: bool = True):
        """
        Update this agent's track record after a trade closes.

        CRITICAL FIX: Only count trades where this specific agent voted BUY.
        Previously all agents shared the same outcome regardless of their vote.
        Now: individual attribution — agent only gets credit/blame for trades
        where it personally voted BUY.
        """
        # Only attribute results to agents that voted for the trade
        if not agent_voted_buy:
            return

        self.total_votes += 1
        if was_correct:
            self.correct_votes += 1

        # Rolling window accuracy (prevents stale weights from old regimes)
        self._recent_results.append(was_correct)
        self._recent_results = self._recent_results[-self._rolling_window:]

        if self.total_votes > 0:
            self.accuracy = self.correct_votes / self.total_votes

        # Weight update: require minimum sample size for statistical significance
        # Don't adjust weights until we have ≥30 individual votes
        if len(self._recent_results) >= 30:
            rolling_accuracy = sum(self._recent_results) / len(self._recent_results)
            # Weight range: 0.3 (bad) to 2.0 (excellent)
            self.weight = max(0.3, min(2.0, 0.5 + rolling_accuracy * 1.5))
        elif self.total_votes >= 10:
            # Early stage: conservative weight adjustment
            self.weight = max(0.5, min(1.5, 0.5 + self.accuracy * 1.0))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weight": round(self.weight, 3),
            "total_votes": self.total_votes,
            "correct_votes": self.correct_votes,
            "accuracy": round(self.accuracy, 3),
        }


# ═══════════════════════════════════════════════════════════════════════════
# SPECIALIST AGENTS
# ═══════════════════════════════════════════════════════════════════════════

class RSIAgent(SwarmAgent):
    """Analyzes RSI for oversold bounces and trend confirmation."""

    def __init__(self):
        super().__init__("RSI", weight=1.0)

    def analyze(self, data: dict) -> AgentVote:
        rsi = data.get("rsi", 50)

        if rsi < 30:
            return AgentVote(self.name, Vote.BUY, 0.85, f"Oversold RSI={rsi:.0f}")
        elif rsi < 40:
            return AgentVote(self.name, Vote.BUY, 0.65, f"Low RSI={rsi:.0f}")
        elif rsi > 75:
            return AgentVote(self.name, Vote.SKIP, 0.80, f"Overbought RSI={rsi:.0f}")
        elif rsi > 60:
            return AgentVote(self.name, Vote.SKIP, 0.50, f"High RSI={rsi:.0f}")
        else:
            return AgentVote(self.name, Vote.NEUTRAL, 0.40, f"Neutral RSI={rsi:.0f}")


class MACDAgent(SwarmAgent):
    """Analyzes MACD crossover and histogram momentum."""

    def __init__(self):
        super().__init__("MACD", weight=1.0)

    def analyze(self, data: dict) -> AgentVote:
        macd = data.get("macd", 0)
        macd_signal = data.get("macd_signal", 0)
        macd_hist = data.get("macd_hist", 0)

        if macd > macd_signal and macd_hist > 0:
            conf = min(0.90, 0.5 + abs(macd_hist) * 10)
            return AgentVote(self.name, Vote.BUY, conf, "Bullish crossover")
        elif macd < macd_signal and macd_hist < 0:
            conf = min(0.85, 0.5 + abs(macd_hist) * 10)
            return AgentVote(self.name, Vote.SKIP, conf, "Bearish crossover")
        else:
            return AgentVote(self.name, Vote.NEUTRAL, 0.30, "MACD flat")


class BollingerAgent(SwarmAgent):
    """Analyzes Bollinger Band position for mean reversion."""

    def __init__(self):
        super().__init__("Bollinger", weight=1.0)

    def analyze(self, data: dict) -> AgentVote:
        bb_pct = data.get("bb_pct", 0.5)  # 0 = lower band, 1 = upper band

        if bb_pct < 0.1:
            return AgentVote(self.name, Vote.BUY, 0.85, f"Below lower BB ({bb_pct:.2f})")
        elif bb_pct < 0.25:
            return AgentVote(self.name, Vote.BUY, 0.60, f"Near lower BB ({bb_pct:.2f})")
        elif bb_pct > 0.95:
            return AgentVote(self.name, Vote.SKIP, 0.80, f"Above upper BB ({bb_pct:.2f})")
        elif bb_pct > 0.75:
            return AgentVote(self.name, Vote.SKIP, 0.50, f"Near upper BB ({bb_pct:.2f})")
        else:
            return AgentVote(self.name, Vote.NEUTRAL, 0.30, f"Mid BB ({bb_pct:.2f})")


class VolumeAgent(SwarmAgent):
    """Analyzes volume for confirmation of moves."""

    def __init__(self):
        super().__init__("Volume", weight=0.8)

    def analyze(self, data: dict) -> AgentVote:
        vol_ratio = data.get("volume_ratio", 1.0)

        if vol_ratio > 2.0:
            return AgentVote(self.name, Vote.BUY, 0.75, f"High volume ({vol_ratio:.1f}x)")
        elif vol_ratio > 1.3:
            return AgentVote(self.name, Vote.BUY, 0.55, f"Above avg volume ({vol_ratio:.1f}x)")
        elif vol_ratio < 0.5:
            return AgentVote(self.name, Vote.SKIP, 0.60, f"Low volume ({vol_ratio:.1f}x)")
        else:
            return AgentVote(self.name, Vote.NEUTRAL, 0.30, f"Normal volume ({vol_ratio:.1f}x)")


class VWAPAgent(SwarmAgent):
    """Analyzes VWAP deviation for institutional price levels."""

    def __init__(self):
        super().__init__("VWAP", weight=1.0)

    def analyze(self, data: dict) -> AgentVote:
        vwap_dev = data.get("vwap_dev", 0)  # % deviation from VWAP

        if vwap_dev < -2.0:
            return AgentVote(self.name, Vote.BUY, 0.80, f"Deep below VWAP ({vwap_dev:+.1f}%)")
        elif vwap_dev < -0.5:
            return AgentVote(self.name, Vote.BUY, 0.60, f"Below VWAP ({vwap_dev:+.1f}%)")
        elif vwap_dev > 2.0:
            return AgentVote(self.name, Vote.SKIP, 0.70, f"Far above VWAP ({vwap_dev:+.1f}%)")
        else:
            return AgentVote(self.name, Vote.NEUTRAL, 0.30, f"Near VWAP ({vwap_dev:+.1f}%)")


class ADXAgent(SwarmAgent):
    """Analyzes ADX for trend strength — only buys in strong trends."""

    def __init__(self):
        super().__init__("ADX", weight=1.0)

    def analyze(self, data: dict) -> AgentVote:
        adx = data.get("adx", 20)

        if adx > 30:
            return AgentVote(self.name, Vote.BUY, 0.70, f"Strong trend ADX={adx:.0f}")
        elif adx > 20:
            return AgentVote(self.name, Vote.NEUTRAL, 0.40, f"Moderate ADX={adx:.0f}")
        else:
            return AgentVote(self.name, Vote.SKIP, 0.55, f"Weak trend ADX={adx:.0f}")


class RegimeAgent(SwarmAgent):
    """Analyzes market regime and adapts strategy accordingly."""

    def __init__(self):
        super().__init__("Regime", weight=1.2)

    def analyze(self, data: dict) -> AgentVote:
        regime = data.get("regime", "unknown")
        adx = data.get("adx", 20)
        rsi = data.get("rsi", 50)

        if regime == "trending" and adx > 25:
            return AgentVote(self.name, Vote.BUY, 0.70, "Trending market, follow momentum")
        elif regime == "volatile":
            if rsi < 35:
                return AgentVote(self.name, Vote.BUY, 0.55, "Volatile oversold — risky bounce")
            return AgentVote(self.name, Vote.SKIP, 0.65, "Volatile — too risky")
        elif regime == "ranging":
            if rsi < 35:
                return AgentVote(self.name, Vote.BUY, 0.60, "Ranging oversold — mean reversion")
            return AgentVote(self.name, Vote.NEUTRAL, 0.35, "Ranging — wait for extremes")
        return AgentVote(self.name, Vote.NEUTRAL, 0.30, "Unknown regime")


class MTFAgent(SwarmAgent):
    """Multi-Timeframe Alignment Agent — checks if multiple timeframes agree."""

    def __init__(self):
        super().__init__("MTF", weight=1.3)

    def analyze(self, data: dict) -> AgentVote:
        mtf_boost = data.get("mtf_boost", 0)

        if mtf_boost > 0.1:
            return AgentVote(self.name, Vote.BUY, 0.85, f"All timeframes aligned ↑ ({mtf_boost:+.3f})")
        elif mtf_boost > 0:
            return AgentVote(self.name, Vote.BUY, 0.55, f"Partial alignment ↑ ({mtf_boost:+.3f})")
        elif mtf_boost < -0.25:
            return AgentVote(self.name, Vote.SKIP, 0.70, f"All timeframes against ↓ ({mtf_boost:+.3f})")
        elif mtf_boost < -0.10:
            return AgentVote(self.name, Vote.NEUTRAL, 0.40, f"Partial divergence ↓ ({mtf_boost:+.3f})")
        return AgentVote(self.name, Vote.NEUTRAL, 0.30, "MTF neutral")


class IntelAgent(SwarmAgent):
    """Market Intelligence Agent — Fear & Greed, News, Whale Activity."""

    def __init__(self):
        super().__init__("Intel", weight=1.1)

    def analyze(self, data: dict) -> AgentVote:
        fg = data.get("fg_value", 50)
        news = data.get("news_sentiment", 0)
        intel_composite = data.get("intel_composite", 0)

        if fg < 25 and intel_composite > 0:
            return AgentVote(self.name, Vote.BUY, 0.75, "Extreme Fear + positive intel → contrarian buy")
        elif fg < 35:
            return AgentVote(self.name, Vote.BUY, 0.55, f"Fear zone (FG={fg:.0f})")
        elif fg > 75:
            return AgentVote(self.name, Vote.SKIP, 0.65, f"Extreme Greed (FG={fg:.0f})")
        else:
            return AgentVote(self.name, Vote.NEUTRAL, 0.30, f"FG={fg:.0f}")


class BrainAgent(SwarmAgent):
    """Brain Intelligence Agent — uses accumulated trading knowledge."""

    def __init__(self):
        super().__init__("Brain", weight=1.2)  # Moderate weight — earns more through experience

    def analyze(self, data: dict) -> AgentVote:
        try:
            from bot.brain import get_brain
            brain = get_brain()

            pair = data.get("pair", "")
            regime = data.get("regime", "unknown")

            # Check if brain recommends this pair
            if not brain.should_trade_pair(pair):
                return AgentVote(self.name, Vote.SKIP, 0.90,
                                 f"Brain blocks {pair} (poor history)")

            # Pair confidence
            conf = brain.get_pair_confidence(pair)
            if conf > 1.2:
                return AgentVote(self.name, Vote.BUY, 0.75,
                                 f"Brain loves {pair} (conf={conf:.2f})")
            elif conf < 0.7:
                return AgentVote(self.name, Vote.SKIP, 0.65,
                                 f"Brain distrusts {pair} (conf={conf:.2f})")

            # Regime knowledge
            regime_adj = brain.get_regime_adjustment(regime)
            if regime_adj > 0.03:
                return AgentVote(self.name, Vote.BUY, 0.60,
                                 f"Brain: {regime} is profitable regime")
            elif regime_adj < -0.03:
                return AgentVote(self.name, Vote.SKIP, 0.55,
                                 f"Brain: {regime} is losing regime")

            return AgentVote(self.name, Vote.NEUTRAL, 0.40, "Brain: insufficient data")

        except Exception:
            return AgentVote(self.name, Vote.NEUTRAL, 0.30, "Brain unavailable")


class MemoryAgent(SwarmAgent):
    """Experience Memory Agent — searches for similar past situations."""

    def __init__(self):
        super().__init__("Memory", weight=1.4)

    def analyze(self, data: dict) -> AgentVote:
        try:
            from bot.experience import get_memory
            memory = get_memory()

            features = {
                "rsi14": data.get("rsi", 50),
                "adx14": data.get("adx", 20),
                "atr_pct": data.get("atr_pct", 1),
                "macd_norm": data.get("macd", 0),
                "volume_ratio": data.get("volume_ratio", 1),
                "bb_position": data.get("bb_pct", 0.5),
                "vwap_dev": data.get("vwap_dev", 0),
                "trend_strength": data.get("score", 0),
                "fg_value": data.get("fg_value", 50),
                "news_sentiment": data.get("news_sentiment", 0),
                "funding_rate": data.get("funding_rate", 0),
                "oi_signal": data.get("oi_signal", 0),
                "mtf_boost": data.get("mtf_boost", 0),
                "score": data.get("score", 0),
            }

            wisdom = memory.get_wisdom(features, data.get("pair"))

            if wisdom["similar_count"] < 5:
                return AgentVote(self.name, Vote.NEUTRAL, 0.25,
                                 f"Not enough history ({wisdom['similar_count']} matches)")

            if wisdom["recommendation"] == "BUY":
                return AgentVote(self.name, Vote.BUY, wisdom["confidence"],
                                 f"Déjà vu: {wisdom['historical_winrate']:.0%} WR "
                                 f"({wisdom['similar_count']} matches)")
            elif wisdom["recommendation"] == "SKIP":
                return AgentVote(self.name, Vote.SKIP, wisdom["confidence"],
                                 f"Déjà vu: {wisdom['historical_winrate']:.0%} WR "
                                 f"({wisdom['similar_count']} matches, BAD)")

            return AgentVote(self.name, Vote.NEUTRAL, 0.35,
                             f"Memory unclear ({wisdom['similar_count']} matches)")

        except Exception:
            return AgentVote(self.name, Vote.NEUTRAL, 0.20, "Memory unavailable")


class MLAgent(SwarmAgent):
    """Machine Learning Agent — uses trained XGBoost model."""

    def __init__(self):
        super().__init__("ML", weight=0.5)  # Low weight until trained (was 1.6)

    def analyze(self, data: dict) -> AgentVote:
        try:
            from bot.brain import get_brain
            brain = get_brain()

            features = {
                "rsi14": data.get("rsi", 50),
                "adx14": data.get("adx", 20),
                "atr_pct": data.get("atr_pct", 1),
                "macd": data.get("macd", 0),
                "volume_ratio": data.get("volume_ratio", 1),
                "vwap_dev": data.get("vwap_dev", 0),
                "fg_value": data.get("fg_value", 50),
                "news_sentiment": data.get("news_sentiment", 0),
                "funding_rate": data.get("funding_rate", 0),
                "oi_signal": data.get("oi_signal", 0),
                "mtf_boost": data.get("mtf_boost", 0),
                "score": data.get("score", 0),
                "signal_count": data.get("signal_count", 0),
            }

            prediction = brain.get_ml_prediction(features)

            if prediction > 0.7:
                return AgentVote(self.name, Vote.BUY, prediction,
                                 f"ML predicts WIN ({prediction:.0%})")
            elif prediction < 0.3:
                return AgentVote(self.name, Vote.SKIP, 1.0 - prediction,
                                 f"ML predicts LOSS ({prediction:.0%})")
            else:
                return AgentVote(self.name, Vote.NEUTRAL, 0.30,
                                 f"ML uncertain ({prediction:.0%})")

        except Exception:
            return AgentVote(self.name, Vote.NEUTRAL, 0.10, "ML model not trained yet")


class OrderFlowAgent(SwarmAgent):
    """Order Flow Agent — analyzes real-time buy/sell pressure (CVD)."""

    def __init__(self):
        super().__init__("OrderFlow", weight=1.2)

    def analyze(self, data: dict) -> AgentVote:
        try:
            from bot.shield import get_order_flow
            pair = data.get("pair", "")
            if not pair or not pair.endswith("USDT"):
                return AgentVote(self.name, Vote.NEUTRAL, 0.20, "Non-crypto pair")

            flow = get_order_flow().analyze(pair)
            signal = flow.get("signal", 0)
            buy_ratio = flow.get("buy_ratio", 0.5)

            if signal > 0.3 and buy_ratio > 0.6:
                return AgentVote(self.name, Vote.BUY, min(0.85, 0.5 + signal),
                                 f"Buyers dominate ({buy_ratio:.0%} buy, CVD +{flow['cvd']:.0f})")
            elif signal < -0.3 and buy_ratio < 0.4:
                return AgentVote(self.name, Vote.SKIP, min(0.80, 0.5 + abs(signal)),
                                 f"Sellers dominate ({buy_ratio:.0%} buy, CVD {flow['cvd']:.0f})")
            else:
                return AgentVote(self.name, Vote.NEUTRAL, 0.30,
                                 f"Order flow balanced ({buy_ratio:.0%} buy)")

        except Exception:
            return AgentVote(self.name, Vote.NEUTRAL, 0.20, "Order flow unavailable")


# ═══════════════════════════════════════════════════════════════════════════
# SWARM CONSENSUS ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class TradingSwarm:
    """
    The collective intelligence engine.
    
    Deploys all agents, collects votes, and produces a consensus decision.
    Agent weights are self-learning based on historical accuracy.
    """

    # Minimum weighted consensus to approve a trade (0-1)
    # Loosened for data collection phase — tighten after 500+ trades
    CONSENSUS_THRESHOLD = 0.40

    # Minimum number of BUY votes required
    MIN_BUY_VOTES = 3

    # Cold-start: relaxed thresholds while agents have <N votes
    COLD_START_THRESHOLD = 10
    COLD_START_CONSENSUS = 0.35
    COLD_START_MIN_BUY = 2

    def __init__(self):
        self.agents: list[SwarmAgent] = [
            RSIAgent(),
            MACDAgent(),
            BollingerAgent(),
            VolumeAgent(),
            VWAPAgent(),
            ADXAgent(),
            RegimeAgent(),
            MTFAgent(),
            IntelAgent(),
            BrainAgent(),
            MemoryAgent(),
            MLAgent(),
            OrderFlowAgent(),
        ]
        self._load_weights()
        logger.info(
            f"🐝 Swarm deployed: {len(self.agents)} agents | "
            f"Threshold: {self.CONSENSUS_THRESHOLD:.0%} | "
            f"Min BUY votes: {self.MIN_BUY_VOTES}"
        )

    def decide(self, market_data: dict) -> SwarmDecision:
        """
        Run all agents and produce a consensus decision.
        
        market_data should contain:
        - rsi, adx, macd, macd_signal, macd_hist
        - bb_pct, volume_ratio, vwap_dev, atr_pct
        - regime, mtf_boost, fg_value, news_sentiment
        - funding_rate, oi_signal, intel_composite
        - score, signal_count, pair
        """
        votes = []

        for agent in self.agents:
            try:
                vote = agent.analyze(market_data)
                votes.append(vote)
            except Exception as e:
                votes.append(AgentVote(agent.name, Vote.NEUTRAL, 0.0, f"Error: {e}"))

        # Count votes
        buy_votes = [v for v in votes if v.vote == Vote.BUY]
        skip_votes = [v for v in votes if v.vote == Vote.SKIP]
        neutral_votes = [v for v in votes if v.vote == Vote.NEUTRAL]

        # Calculate weighted consensus
        total_weight = sum(
            self._get_agent_weight(v.agent_name) for v in votes
            if v.vote != Vote.NEUTRAL
        )
        buy_weight = sum(
            self._get_agent_weight(v.agent_name) * v.confidence
            for v in buy_votes
        )
        skip_weight = sum(
            self._get_agent_weight(v.agent_name) * v.confidence
            for v in skip_votes
        )

        # Weighted score: -1.0 (all SKIP) to +1.0 (all BUY)
        if total_weight > 0:
            weighted_score = (buy_weight - skip_weight) / total_weight
        else:
            weighted_score = 0.0

        # Consensus percentage (of non-neutral votes)
        active_voters = len(buy_votes) + len(skip_votes)
        consensus_pct = len(buy_votes) / max(active_voters, 1)

        # Cold-start detection: are most agents still newborns?
        total_agent_votes = sum(a.total_votes for a in self.agents)
        avg_agent_votes = total_agent_votes / max(len(self.agents), 1)
        cold_start = avg_agent_votes < self.COLD_START_THRESHOLD

        # Use relaxed thresholds during cold-start (learning phase)
        if cold_start:
            req_consensus = self.COLD_START_CONSENSUS
            req_min_buy = self.COLD_START_MIN_BUY
            req_weight = 0.0  # Any positive weighted score
        else:
            req_consensus = self.CONSENSUS_THRESHOLD
            req_min_buy = self.MIN_BUY_VOTES
            req_weight = 0.1

        # Decision
        approved = (
            consensus_pct >= req_consensus and
            len(buy_votes) >= req_min_buy and
            weighted_score > req_weight
        )

        if approved:
            final_vote = Vote.BUY
        elif consensus_pct < 0.3 or weighted_score < -0.2:
            final_vote = Vote.SKIP
        else:
            final_vote = Vote.NEUTRAL

        # Build reasoning string
        top_buy = sorted(buy_votes, key=lambda v: v.confidence, reverse=True)[:3]
        top_skip = sorted(skip_votes, key=lambda v: v.confidence, reverse=True)[:2]
        reasoning_parts = []
        for v in top_buy:
            reasoning_parts.append(f"✅{v.agent_name}({v.confidence:.0%})")
        for v in top_skip:
            reasoning_parts.append(f"❌{v.agent_name}({v.confidence:.0%})")
        reasoning = " | ".join(reasoning_parts)

        decision = SwarmDecision(
            final_vote=final_vote,
            consensus_pct=round(consensus_pct, 3),
            weighted_score=round(weighted_score, 3),
            total_agents=len(self.agents),
            buy_votes=len(buy_votes),
            skip_votes=len(skip_votes),
            neutral_votes=len(neutral_votes),
            votes=[{
                "agent": v.agent_name,
                "vote": v.vote.value,
                "confidence": round(v.confidence, 2),
                "reason": v.reason,
            } for v in votes],
            approved=approved,
            reasoning=reasoning,
        )

        return decision

    def learn_from_outcome(self, market_data: dict, was_profitable: bool):
        """
        After a trade closes, update each agent's accuracy.
        
        SIMPLIFIED: Don't re-analyze (agents crash on missing keys).
        Instead, directly update every agent with the trade outcome.
        Each agent is judged on whether it WOULD HAVE voted correctly
        based on the simplified market data.
        """
        learn_count = 0
        for agent in self.agents:
            try:
                # Try to get the agent's vote, but if it fails,
                # still update with a default assumption
                try:
                    vote = agent.analyze(market_data)
                    vote_type = vote.vote
                except Exception:
                    # Agent can't analyze this data — treat as NEUTRAL
                    vote_type = Vote.NEUTRAL
                
                # Determine if this agent was "correct"
                if vote_type == Vote.BUY:
                    was_correct = was_profitable
                elif vote_type == Vote.SKIP:
                    was_correct = not was_profitable
                else:  # NEUTRAL
                    was_correct = not was_profitable  # Conservative = correct if loss
                
                # FORCE the update — bypass the agent_voted_buy filter
                agent.total_votes += 1
                if was_correct:
                    agent.correct_votes += 1
                
                # Rolling window
                agent._recent_results.append(was_correct)
                agent._recent_results = agent._recent_results[-agent._rolling_window:]
                
                if agent.total_votes > 0:
                    agent.accuracy = agent.correct_votes / agent.total_votes
                
                # Weight update
                if len(agent._recent_results) >= 30:
                    rolling_acc = sum(agent._recent_results) / len(agent._recent_results)
                    agent.weight = max(0.3, min(2.0, 0.5 + rolling_acc * 1.5))
                elif agent.total_votes >= 10:
                    agent.weight = max(0.5, min(1.5, 0.5 + agent.accuracy * 1.0))
                
                learn_count += 1
            except Exception as e:
                logger.debug(f"Swarm learn error for {agent.name}: {e}")
        
        logger.info(f"🐝 Swarm: {learn_count}/{len(self.agents)} agents learned (profitable={was_profitable})")
        self._save_weights()

    def _get_agent_weight(self, name: str) -> float:
        """Get an agent's current weight."""
        for agent in self.agents:
            if agent.name == name:
                return agent.weight
        return 1.0

    def _save_weights(self):
        """Persist agent weights to JSON + Postgres."""
        import json
        from pathlib import Path
        weights_path = Path("./logs/brain/swarm_weights.json")
        weights_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {a.name: a.to_dict() for a in self.agents}
            weights_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

        # Persist to Postgres (survives deploys)
        try:
            from bot.brain_store import save_all_swarm_agents
            save_all_swarm_agents(self.agents)
        except Exception:
            pass

    def _load_weights(self):
        """Load agent weights from Postgres first, then JSON fallback."""
        loaded = False

        # Try Postgres first (persistent across deploys)
        try:
            from bot.brain_store import load_swarm_agents
            pg_data = load_swarm_agents()
            if pg_data:
                for agent in self.agents:
                    if agent.name in pg_data:
                        saved = pg_data[agent.name]
                        agent.weight = saved.get("weight", agent.weight)
                        agent.total_votes = saved.get("total_votes", 0)
                        agent.correct_votes = saved.get("correct_votes", 0)
                        agent.accuracy = saved.get("accuracy", 0.5)
                        agent._recent_results = saved.get("recent_results", [])
                loaded = True
        except Exception:
            pass

        # Fallback to JSON
        if not loaded:
            import json
            from pathlib import Path
            weights_path = Path("./logs/brain/swarm_weights.json")
            if not weights_path.exists():
                return
            try:
                data = json.loads(weights_path.read_text())
                for agent in self.agents:
                    if agent.name in data:
                        saved = data[agent.name]
                        agent.weight = saved.get("weight", agent.weight)
                        agent.total_votes = saved.get("total_votes", 0)
                        agent.correct_votes = saved.get("correct_votes", 0)
                        agent.accuracy = saved.get("accuracy", 0.5)
            except Exception:
                pass

    def get_status(self) -> dict:
        """Get swarm status."""
        return {
            "total_agents": len(self.agents),
            "agents": [a.to_dict() for a in self.agents],
            "consensus_threshold": self.CONSENSUS_THRESHOLD,
            "min_buy_votes": self.MIN_BUY_VOTES,
        }


# ── Singleton ──────────────────────────────────────────────────────────────

_swarm_instance = None

def get_swarm() -> TradingSwarm:
    """Get or create the singleton swarm instance."""
    global _swarm_instance
    if _swarm_instance is None:
        _swarm_instance = TradingSwarm()
    return _swarm_instance
