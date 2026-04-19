"""
Experience Memory — Semantic Trade Memory with Similarity Search.

This is the bot's "déjà vu" system. It stores every market situation
as a numerical fingerprint and can find similar past situations
when making new decisions.

Think of it like: "I've seen this exact market pattern before —
last time I bought here it worked out 70% of the time."

Uses lightweight in-process vector search (no external DB needed).
Upgradable to ChromaDB for production scale.

Components:
1. Experience Store — Stores market snapshots as vectors
2. Similarity Search — Finds closest historical matches
3. Outcome Tracking — Links experiences to trade results
4. Wisdom Extraction — "What worked in situations like THIS?"
"""
import json
import math
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger("ethbot.experience")

EXP_DIR = Path(os.getenv("BRAIN_DIR", "./logs/brain")) / "experiences"
EXP_DIR.mkdir(parents=True, exist_ok=True)

EXPERIENCE_FILE = EXP_DIR / "experience_store.json"
MAX_EXPERIENCES = 50000  # Keep last 50k experiences


class MarketSnapshot:
    """A fingerprint of a market moment."""

    def __init__(self, pair: str, features: dict, timestamp: str = None):
        self.pair = pair
        self.features = features
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.vector = self._to_vector(features)

    def _to_vector(self, features: dict) -> list:
        """Convert features dict to a normalized numerical vector."""
        # Standard feature order — NO circular features (score removed)
        # NO fake features (news_sentiment, oi_signal removed)
        keys = [
            "rsi14", "adx14", "atr_pct", "macd_norm", "volume_ratio",
            "bb_position", "vwap_dev", "trend_strength",
            "fg_value", "funding_rate", "mtf_boost",
        ]
        raw = []
        for k in keys:
            val = float(features.get(k, 0) or 0)
            raw.append(val)

        # Normalize to [0, 1] range
        return self._normalize(raw)

    @staticmethod
    def _normalize(vector: list) -> list:
        """Min-max normalize a vector."""
        # Known ranges for each feature
        ranges = [
            (0, 100),     # rsi14
            (0, 100),     # adx14
            (0, 10),      # atr_pct
            (-1, 1),      # macd_norm
            (0, 5),       # volume_ratio
            (0, 1),       # bb_position
            (-5, 5),      # vwap_dev
            (-1, 1),      # trend_strength
            (0, 100),     # fg_value
            (-0.1, 0.1),  # funding_rate
            (-0.3, 0.3),  # mtf_boost
        ]
        result = []
        for i, val in enumerate(vector):
            if i < len(ranges):
                lo, hi = ranges[i]
                norm = (val - lo) / max(hi - lo, 0.001)
                result.append(max(0, min(1, norm)))
            else:
                result.append(val)
        return result

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "features": self.features,
            "vector": self.vector,
            "timestamp": self.timestamp,
        }


class Experience:
    """A complete experience: situation + action + outcome."""

    def __init__(self, snapshot: MarketSnapshot, action: str,
                 signals: list = None, regime: str = "unknown"):
        self.snapshot = snapshot
        self.action = action  # "BUY", "SKIP", "SELL"
        self.signals = signals or []
        self.regime = regime
        self.outcome = None  # Filled later: {"pnl_pct": ..., "win": bool}
        self.id = f"{snapshot.pair}_{snapshot.timestamp}"

    def set_outcome(self, pnl_pct: float):
        self.outcome = {
            "pnl_pct": round(pnl_pct, 4),
            "win": pnl_pct > 0,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "snapshot": self.snapshot.to_dict(),
            "action": self.action,
            "signals": self.signals,
            "regime": self.regime,
            "outcome": self.outcome,
        }


def cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a)) or 1e-10
    mag_b = math.sqrt(sum(x * x for x in b)) or 1e-10
    return dot / (mag_a * mag_b)


class ExperienceMemory:
    """
    The bot's semantic memory system.
    
    Stores market experiences as vectors and finds similar past
    situations using cosine similarity search.
    """

    def __init__(self):
        self.experiences: list = []
        self._load()
        logger.info(f"💾 Experience Memory: {len(self.experiences)} experiences loaded")

    def _load(self):
        """Load experiences from disk."""
        if EXPERIENCE_FILE.exists():
            try:
                data = json.loads(EXPERIENCE_FILE.read_text())
                self.experiences = data.get("experiences", [])
            except Exception:
                self.experiences = []

    def save(self):
        """Persist experiences to disk."""
        # Keep only latest MAX_EXPERIENCES
        self.experiences = self.experiences[-MAX_EXPERIENCES:]
        try:
            EXPERIENCE_FILE.write_text(json.dumps({
                "experiences": self.experiences,
                "count": len(self.experiences),
                "last_saved": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Experience save failed: {e}")

    def record(self, pair: str, features: dict, action: str,
               signals: list = None, regime: str = "unknown"):
        """Record a new experience."""
        snapshot = MarketSnapshot(pair, features)
        exp = Experience(snapshot, action, signals, regime)
        self.experiences.append(exp.to_dict())

        # Auto-save every 100 experiences
        if len(self.experiences) % 100 == 0:
            self.save()

    def record_outcome(self, pair: str, pnl_pct: float):
        """
        Retroactively add outcome to the most recent BUY experience for this pair.
        """
        for exp in reversed(self.experiences):
            if (exp.get("snapshot", {}).get("pair") == pair and
                exp.get("action") == "BUY" and
                exp.get("outcome") is None):
                exp["outcome"] = {
                    "pnl_pct": round(pnl_pct, 4),
                    "win": pnl_pct > 0,
                }
                break

    def find_similar(self, features: dict, pair: str = None,
                     top_k: int = 10, min_similarity: float = 0.65) -> list:
        """
        Find the most similar past experiences to the current situation.
        
        This is the "déjà vu" function — "Have I seen this before?"
        
        Returns list of (experience, similarity_score) sorted by similarity.
        """
        query_snapshot = MarketSnapshot(pair or "QUERY", features)
        query_vec = query_snapshot.vector

        scored = []
        for exp in self.experiences:
            # Only consider experiences with outcomes (we can learn from them)
            if exp.get("outcome") is None:
                continue

            exp_vec = exp.get("snapshot", {}).get("vector", [])
            if not exp_vec or len(exp_vec) != len(query_vec):
                continue

            sim = cosine_similarity(query_vec, exp_vec)
            if sim >= min_similarity:
                scored.append((exp, sim))

        # Sort by similarity (highest first)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get_wisdom(self, features: dict, pair: str = None) -> dict:
        """
        Extract wisdom from similar past experiences.
        
        Returns:
        - historical_winrate: What % of similar situations led to wins
        - avg_pnl: Average PnL of similar past trades
        - confidence: How confident are we (based on sample size)
        - recommendation: "BUY", "SKIP", or "NEUTRAL"
        - similar_count: How many similar experiences found
        """
        similar = self.find_similar(features, pair, top_k=20, min_similarity=0.60)

        if not similar:
            return {
                "historical_winrate": 0.5,
                "avg_pnl": 0.0,
                "confidence": 0.0,
                "recommendation": "NEUTRAL",
                "similar_count": 0,
            }

        wins = 0
        total_pnl = 0.0
        buy_outcomes = []
        total = 0

        for exp, sim in similar:
            outcome = exp.get("outcome", {})
            if outcome:
                total += 1
                pnl = outcome.get("pnl_pct", 0)
                total_pnl += pnl
                if outcome.get("win", False):
                    wins += 1
                if exp.get("action") == "BUY":
                    buy_outcomes.append(pnl)

        if total == 0:
            return {
                "historical_winrate": 0.5,
                "avg_pnl": 0.0,
                "confidence": 0.0,
                "recommendation": "NEUTRAL",
                "similar_count": 0,
            }

        winrate = wins / total
        avg_pnl = total_pnl / total

        # Confidence based on sample size and similarity
        avg_sim = sum(s for _, s in similar) / len(similar)
        confidence = min(1.0, (total / 20) * avg_sim)

        # Recommendation
        if winrate > 0.6 and avg_pnl > 0:
            recommendation = "BUY"
        elif winrate < 0.35 or avg_pnl < -1.0:
            recommendation = "SKIP"
        else:
            recommendation = "NEUTRAL"

        return {
            "historical_winrate": round(winrate, 3),
            "avg_pnl": round(avg_pnl, 3),
            "confidence": round(confidence, 3),
            "recommendation": recommendation,
            "similar_count": total,
            "best_match_similarity": round(similar[0][1], 3) if similar else 0,
        }

    def get_stats(self) -> dict:
        """Get memory statistics."""
        total = len(self.experiences)
        with_outcome = sum(1 for e in self.experiences if e.get("outcome"))
        buys = sum(1 for e in self.experiences if e.get("action") == "BUY")
        wins = sum(1 for e in self.experiences
                   if e.get("outcome", {}).get("win", False))

        pairs = set(e.get("snapshot", {}).get("pair", "")
                    for e in self.experiences)

        return {
            "total_experiences": total,
            "with_outcomes": with_outcome,
            "total_buys": buys,
            "total_wins": wins,
            "unique_pairs": len(pairs),
            "memory_mb": round(
                EXPERIENCE_FILE.stat().st_size / 1024 / 1024, 2
            ) if EXPERIENCE_FILE.exists() else 0,
        }


# ── Genetic Strategy Evolver ──────────────────────────────────────────────

class StrategyDNA:
    """A strategy encoded as a set of tunable parameters."""

    def __init__(self, params: dict = None):
        self.params = params or self._random_params()
        self.fitness = 0.0
        self.trades = 0
        self.wins = 0
        self.pnl_history = []
        self.generation = 0

    @staticmethod
    def _random_params() -> dict:
        """Generate random strategy parameters."""
        import random
        return {
            "rsi_min": random.randint(20, 40),
            "rsi_max": random.randint(65, 85),
            "adx_min": random.randint(15, 35),
            "entry_score_min": round(random.uniform(0.05, 0.30), 3),
            "tp_min": round(random.uniform(0.5, 3.0), 2),
            "tp_max": round(random.uniform(2.0, 8.0), 2),
            "sl_atr_mult": round(random.uniform(1.0, 3.0), 2),
            "volume_min_ratio": round(random.uniform(0.5, 2.0), 2),
            "bb_weight": round(random.uniform(0.0, 0.3), 3),
            "oversold_weight": round(random.uniform(0.0, 0.4), 3),
            "trend_weight": round(random.uniform(0.0, 0.3), 3),
            "max_hold_bars": random.randint(10, 60),
        }

    def mutate(self, rate: float = 0.2):
        """Randomly mutate some parameters."""
        import random
        for key, val in self.params.items():
            if random.random() < rate:
                if isinstance(val, int):
                    self.params[key] = max(1, val + random.randint(-5, 5))
                elif isinstance(val, float):
                    delta = val * random.uniform(-0.3, 0.3)
                    self.params[key] = round(max(0.01, val + delta), 4)

    @staticmethod
    def crossover(parent_a, parent_b):
        """Create child from two parents."""
        child_params = {}
        import random
        for key in parent_a.params:
            if random.random() < 0.5:
                child_params[key] = parent_a.params[key]
            else:
                child_params[key] = parent_b.params[key]
        child = StrategyDNA(child_params)
        child.generation = max(parent_a.generation, parent_b.generation) + 1
        return child

    def to_dict(self) -> dict:
        return {
            "params": self.params,
            "fitness": self.fitness,
            "trades": self.trades,
            "wins": self.wins,
            "generation": self.generation,
        }


class GeneticEvolver:
    """
    Evolves trading strategies through genetic algorithms.
    
    - Population of strategy variants
    - Fitness = Sharpe ratio from simulated results
    - Best strategies survive and breed
    - Mutations introduce new ideas
    - Over generations, optimal parameters emerge
    """

    EVOLVER_FILE = EXP_DIR / "genetic_pool.json"

    def __init__(self, population_size: int = 30):
        self.population_size = population_size
        self.population: list = []
        self.generation = 0
        self.best_ever = None
        self._load()

    def _load(self):
        """Load population from disk."""
        if self.EVOLVER_FILE.exists():
            try:
                data = json.loads(self.EVOLVER_FILE.read_text())
                self.generation = data.get("generation", 0)
                self.best_ever = data.get("best_ever")
                population_data = data.get("population", [])
                self.population = []
                for p in population_data:
                    dna = StrategyDNA(p.get("params"))
                    dna.fitness = p.get("fitness", 0)
                    dna.trades = p.get("trades", 0)
                    dna.wins = p.get("wins", 0)
                    dna.generation = p.get("generation", 0)
                    self.population.append(dna)
            except Exception:
                pass

        # Initialize if empty
        if not self.population:
            self.population = [StrategyDNA() for _ in range(self.population_size)]
            logger.info(f"🧬 Genetic Evolver: Created {self.population_size} random strategies")

    def save(self):
        """Persist population."""
        try:
            self.EVOLVER_FILE.write_text(json.dumps({
                "generation": self.generation,
                "best_ever": self.best_ever,
                "population": [dna.to_dict() for dna in self.population],
                "last_saved": datetime.now(timezone.utc).isoformat(),
            }, indent=2))
        except Exception:
            pass

    def record_trade(self, strategy_idx: int, pnl_pct: float):
        """Record a trade result for a specific strategy variant."""
        if 0 <= strategy_idx < len(self.population):
            dna = self.population[strategy_idx]
            dna.trades += 1
            if pnl_pct > 0:
                dna.wins += 1
            dna.pnl_history.append(pnl_pct)
            dna.pnl_history = dna.pnl_history[-200:]  # Keep last 200

            # Update fitness (Sharpe approximation)
            if len(dna.pnl_history) >= 5:
                import statistics
                mean = statistics.mean(dna.pnl_history)
                std = statistics.stdev(dna.pnl_history) or 0.01
                dna.fitness = mean / std

    def evolve(self):
        """Run one generation of evolution."""
        import random

        # Only evolve if we have enough data
        tested = [dna for dna in self.population if dna.trades >= 5]
        if len(tested) < 5:
            return  # Not enough data yet

        self.generation += 1

        # Sort by fitness
        self.population.sort(key=lambda x: x.fitness, reverse=True)

        # Track best ever
        best = self.population[0]
        if self.best_ever is None or best.fitness > self.best_ever.get("fitness", 0):
            self.best_ever = best.to_dict()

        # Top 30% survive (elitism)
        survivors = int(self.population_size * 0.3)
        elite = self.population[:survivors]

        # Generate children through crossover
        children = []
        while len(children) < self.population_size - survivors:
            p1, p2 = random.sample(elite, 2)
            child = StrategyDNA.crossover(p1, p2)
            child.mutate(rate=0.25)
            children.append(child)

        self.population = elite + children

        logger.info(
            f"🧬 Gen #{self.generation}: Best fitness={best.fitness:.3f} | "
            f"Params: RSI={best.params['rsi_min']}-{best.params['rsi_max']} | "
            f"Score≥{best.params['entry_score_min']} | "
            f"TP={best.params['tp_min']}-{best.params['tp_max']}%"
        )

        self.save()

    def get_best_params(self) -> dict:
        """Get the parameters of the best-performing strategy."""
        if not self.population:
            return {}
        best = max(self.population, key=lambda x: x.fitness)
        if best.fitness > 0 and best.trades >= 10:
            return best.params
        return {}

    def get_status(self) -> dict:
        """Get evolver status."""
        tested = sum(1 for d in self.population if d.trades > 0)
        return {
            "generation": self.generation,
            "population_size": len(self.population),
            "tested": tested,
            "best_fitness": max((d.fitness for d in self.population), default=0),
            "best_params": self.get_best_params(),
            "best_ever": self.best_ever,
        }


# ── Singleton instances ──────────────────────────────────────────────────

_memory_instance = None
_evolver_instance = None


def get_memory() -> ExperienceMemory:
    """Get or create the singleton experience memory."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ExperienceMemory()
    return _memory_instance


def get_evolver() -> GeneticEvolver:
    """Get or create the singleton genetic evolver."""
    global _evolver_instance
    if _evolver_instance is None:
        _evolver_instance = GeneticEvolver()
    return _evolver_instance
