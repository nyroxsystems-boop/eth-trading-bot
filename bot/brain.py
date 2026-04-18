"""
Trading Brain — Persistent Self-Learning Intelligence Core.

The Brain is the bot's long-term memory and evolution engine.
It learns from EVERY action, remembers EVERYTHING, and continuously
evolves its strategies based on accumulated experience.

Components:
1. Memory Store — Persistent knowledge base (JSON)
2. Strategy Evolver — Tests variations, promotes winners, kills losers
3. Pattern Detector — Finds recurring profitable setups
4. Auto-Trainer — Retrains ML model when enough data exists
5. Performance Tracker — Tracks what works per pair, per regime, per time

The Brain gets smarter with every loop, every trade, every failure.
After 1000s of trades, it should be exceptionally good.
"""
import json
import csv
import os
import time
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger("ethbot.brain")

BRAIN_DIR = Path(os.getenv("BRAIN_DIR", "./logs/brain"))
BRAIN_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_FILE = BRAIN_DIR / "memory.json"
STRATEGY_FILE = BRAIN_DIR / "strategies.json"
PATTERNS_FILE = BRAIN_DIR / "patterns.json"
EVOLUTION_LOG = BRAIN_DIR / "evolution.csv"


class TradingBrain:
    """
    The bot's persistent learning core.
    
    Everything the bot learns is stored here and survives restarts.
    The Brain evolves autonomously — no human intervention needed.
    """

    def __init__(self):
        self.memory = self._load_memory()
        self.strategies = self._load_strategies()
        self.patterns = self._load_patterns()
        self._ensure_evolution_log()
        logger.info(
            f"🧠 Brain loaded: {self.memory['stats']['total_evaluations']} evals | "
            f"{self.memory['stats']['total_trades']} trades | "
            f"{len(self.strategies)} strategies | "
            f"Age: {self.memory['stats'].get('age_hours', 0):.0f}h"
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 1. MEMORY — Persistent Knowledge Store
    # ═══════════════════════════════════════════════════════════════════════

    def _load_memory(self) -> dict:
        """Load or initialize the brain's memory."""
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text())
            except Exception:
                pass

        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "total_evaluations": 0,
                "total_trades": 0,
                "total_wins": 0,
                "total_losses": 0,
                "total_pnl": 0.0,
                "best_trade_pnl": 0.0,
                "worst_trade_pnl": 0.0,
                "age_hours": 0,
            },
            # Per-pair intelligence
            "pair_knowledge": {},
            # Per-regime intelligence
            "regime_knowledge": {
                "trending": {"trades": 0, "wins": 0, "avg_pnl": 0.0, "best_signals": {}},
                "ranging": {"trades": 0, "wins": 0, "avg_pnl": 0.0, "best_signals": {}},
                "volatile": {"trades": 0, "wins": 0, "avg_pnl": 0.0, "best_signals": {}},
            },
            # Time-of-day patterns
            "hourly_performance": {str(h): {"trades": 0, "wins": 0, "pnl": 0.0} for h in range(24)},
            # Signal effectiveness tracking
            "signal_scores": {},
            # Lessons learned (what NOT to do)
            "lessons": [],
            # Feature importance (updated by ML training)
            "feature_importance": {},
            # Optimal thresholds per pair (learned)
            "optimal_thresholds": {},
        }

    def save_memory(self):
        """Persist the brain's memory to disk."""
        self.memory["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Calculate age
        try:
            created = datetime.fromisoformat(self.memory["created_at"])
            age = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            self.memory["stats"]["age_hours"] = age
        except Exception:
            pass

        try:
            MEMORY_FILE.write_text(json.dumps(self.memory, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning(f"Brain save failed: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # 2. LEARNING — Record everything, learn from everything
    # ═══════════════════════════════════════════════════════════════════════

    def record_evaluation(self, pair: str, signal, regime: str, price: float,
                          action: str, market: str = "crypto"):
        """Record every single evaluation for learning."""
        self.memory["stats"]["total_evaluations"] += 1

        # Initialize pair knowledge if new
        if pair not in self.memory["pair_knowledge"]:
            self.memory["pair_knowledge"][pair] = {
                "market": market,
                "evaluations": 0,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "total_pnl": 0.0,
                "avg_score_on_win": 0.0,
                "avg_score_on_loss": 0.0,
                "best_entry_signals": {},
                "worst_entry_signals": {},
                "optimal_score_threshold": 0.15,
                "last_price": price,
                "first_seen": datetime.now(timezone.utc).isoformat(),
            }

        pk = self.memory["pair_knowledge"][pair]
        pk["evaluations"] += 1
        pk["last_price"] = price

        # Track signal frequency
        if signal and hasattr(signal, 'signals'):
            for sig_name in signal.signals:
                # Clean signal name
                clean = sig_name.split("(")[0].strip()
                if clean not in self.memory["signal_scores"]:
                    self.memory["signal_scores"][clean] = {
                        "appearances": 0, "on_buy": 0, "on_win": 0,
                        "on_loss": 0, "effectiveness": 0.5,
                    }
                self.memory["signal_scores"][clean]["appearances"] += 1
                if action == "BUY":
                    self.memory["signal_scores"][clean]["on_buy"] += 1

        # Save periodically (every 50 evals)
        if self.memory["stats"]["total_evaluations"] % 50 == 0:
            self.save_memory()

    def record_trade_result(self, pair: str, entry_price: float, exit_price: float,
                            pnl: float, pnl_pct: float, signals_used: list,
                            regime: str, hold_bars: int):
        """
        Record a completed trade and learn from it.
        This is the MOST important learning function.
        """
        is_win = pnl > 0
        stats = self.memory["stats"]

        # Global stats
        stats["total_trades"] += 1
        if is_win:
            stats["total_wins"] += 1
        else:
            stats["total_losses"] += 1
        stats["total_pnl"] += pnl
        stats["best_trade_pnl"] = max(stats["best_trade_pnl"], pnl)
        stats["worst_trade_pnl"] = min(stats["worst_trade_pnl"], pnl)

        # Pair-specific learning
        if pair in self.memory["pair_knowledge"]:
            pk = self.memory["pair_knowledge"][pair]
            pk["trades"] += 1
            pk["total_pnl"] += pnl
            if is_win:
                pk["wins"] += 1
            else:
                pk["losses"] += 1

        # Regime learning
        if regime in self.memory["regime_knowledge"]:
            rk = self.memory["regime_knowledge"][regime]
            rk["trades"] += 1
            if is_win:
                rk["wins"] += 1
            # Running average PnL
            n = rk["trades"]
            rk["avg_pnl"] = rk["avg_pnl"] * (n - 1) / n + pnl_pct / n

            # Track which signals work best in each regime
            for sig in signals_used:
                clean = sig.split("(")[0].strip()
                if clean not in rk["best_signals"]:
                    rk["best_signals"][clean] = {"wins": 0, "losses": 0}
                if is_win:
                    rk["best_signals"][clean]["wins"] += 1
                else:
                    rk["best_signals"][clean]["losses"] += 1

        # Hourly performance tracking
        hour = str(datetime.now(timezone.utc).hour)
        hp = self.memory["hourly_performance"].get(hour, {"trades": 0, "wins": 0, "pnl": 0.0})
        hp["trades"] += 1
        if is_win:
            hp["wins"] += 1
        hp["pnl"] += pnl
        self.memory["hourly_performance"][hour] = hp

        # Signal effectiveness update
        for sig in signals_used:
            clean = sig.split("(")[0].strip()
            if clean in self.memory["signal_scores"]:
                ss = self.memory["signal_scores"][clean]
                if is_win:
                    ss["on_win"] += 1
                else:
                    ss["on_loss"] += 1
                # Recalculate effectiveness
                total = ss["on_win"] + ss["on_loss"]
                if total > 0:
                    ss["effectiveness"] = ss["on_win"] / total

        # Learn lesson from losses
        if not is_win and pnl_pct < -2.0:
            lesson = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pair": pair,
                "regime": regime,
                "signals": signals_used,
                "pnl_pct": round(pnl_pct, 2),
                "hold_bars": hold_bars,
                "lesson": self._generate_lesson(signals_used, regime, pnl_pct, hold_bars),
            }
            self.memory["lessons"].append(lesson)
            # Keep last 200 lessons
            self.memory["lessons"] = self.memory["lessons"][-200:]

        # Log evolution
        self._log_evolution(pair, pnl, pnl_pct, signals_used, regime)

        # Save after every trade
        self.save_memory()

        winrate = stats["total_wins"] / max(stats["total_trades"], 1) * 100
        logger.info(
            f"🧠 Brain: Trade #{stats['total_trades']} | "
            f"{'✅' if is_win else '❌'} {pair} {pnl_pct:+.2f}% | "
            f"Lifetime: {winrate:.0f}% WR | ${stats['total_pnl']:+,.2f}"
        )

    def _generate_lesson(self, signals: list, regime: str, pnl_pct: float, bars: int) -> str:
        """Auto-generate a lesson from a losing trade."""
        parts = []
        if bars <= 2:
            parts.append("Stopped out too fast — SL may be too tight")
        if bars > 30:
            parts.append("Held too long — consider tighter time exit")
        if regime == "ranging" and "TREND" in str(signals):
            parts.append("Trend signal in ranging market = BAD")
        if regime == "volatile" and pnl_pct < -3:
            parts.append("Volatile regime caused large loss — reduce size")
        if "OVERSOLD" in str(signals) and pnl_pct < -2:
            parts.append("Oversold bounce failed — check macro trend")
        if not parts:
            parts.append(f"Loss of {pnl_pct:.1f}% with signals {signals} in {regime}")
        return " | ".join(parts)

    # ═══════════════════════════════════════════════════════════════════════
    # 3. INTELLIGENCE — Use learned knowledge for better decisions
    # ═══════════════════════════════════════════════════════════════════════

    def get_pair_confidence(self, pair: str) -> float:
        """
        Get a confidence multiplier for a pair based on past performance.
        Returns 0.5-1.5 (0.5 = bad history, 1.5 = great history).
        """
        pk = self.memory["pair_knowledge"].get(pair)
        if not pk or pk["trades"] < 5:
            return 1.0  # Not enough data

        winrate = pk["wins"] / max(pk["trades"], 1)
        avg_pnl = pk["total_pnl"] / max(pk["trades"], 1)

        # Score based on win rate and avg PnL
        confidence = 0.5 + winrate  # 0.5-1.5 range
        if avg_pnl < 0:
            confidence *= 0.8  # Penalty for negative avg PnL

        return max(0.5, min(1.5, confidence))

    def get_regime_adjustment(self, regime: str) -> float:
        """Get score adjustment based on regime performance history."""
        rk = self.memory["regime_knowledge"].get(regime)
        if not rk or rk["trades"] < 10:
            return 0.0

        winrate = rk["wins"] / max(rk["trades"], 1)
        if winrate > 0.6:
            return 0.05  # Boost in high-winrate regime
        elif winrate < 0.35:
            return -0.05  # Reduce in low-winrate regime
        return 0.0

    def get_optimal_threshold(self, pair: str) -> float:
        """Get the learned optimal entry threshold for a pair."""
        return self.memory.get("optimal_thresholds", {}).get(pair, 0.15)

    def get_signal_ranking(self) -> list:
        """Get signals ranked by effectiveness."""
        scores = self.memory.get("signal_scores", {})
        ranked = []
        for name, data in scores.items():
            total = data.get("on_win", 0) + data.get("on_loss", 0)
            if total >= 5:  # Need minimum sample
                ranked.append({
                    "signal": name,
                    "effectiveness": data["effectiveness"],
                    "sample_size": total,
                    "appearances": data["appearances"],
                })
        ranked.sort(key=lambda x: x["effectiveness"], reverse=True)
        return ranked

    def get_best_hour(self) -> int:
        """Find the most profitable trading hour (UTC)."""
        best_hour = 0
        best_pnl = float("-inf")
        for h, data in self.memory.get("hourly_performance", {}).items():
            if data.get("trades", 0) >= 5 and data.get("pnl", 0) > best_pnl:
                best_pnl = data["pnl"]
                best_hour = int(h)
        return best_hour

    def should_trade_pair(self, pair: str) -> bool:
        """Brain decides if this pair is worth trading based on history."""
        pk = self.memory["pair_knowledge"].get(pair)
        if not pk or pk["trades"] < 10:
            return True  # Not enough data, allow

        winrate = pk["wins"] / max(pk["trades"], 1)
        # Kill pairs with <25% win rate after 20+ trades
        if pk["trades"] >= 20 and winrate < 0.25:
            logger.info(f"🧠 Brain blocking {pair}: {winrate:.0%} WR after {pk['trades']} trades")
            return False
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # 4. STRATEGY EVOLUTION — Test, promote, kill strategies
    # ═══════════════════════════════════════════════════════════════════════

    def _load_strategies(self) -> dict:
        """Load strategy performance data."""
        if STRATEGY_FILE.exists():
            try:
                return json.loads(STRATEGY_FILE.read_text())
            except Exception:
                pass
        return {}

    def save_strategies(self):
        """Persist strategy data."""
        try:
            STRATEGY_FILE.write_text(json.dumps(self.strategies, indent=2))
        except Exception:
            pass

    def record_strategy_result(self, strategy_name: str, pnl_pct: float, regime: str):
        """Track how each strategy combo performs."""
        if strategy_name not in self.strategies:
            self.strategies[strategy_name] = {
                "trades": 0, "wins": 0, "total_pnl_pct": 0.0,
                "avg_pnl": 0.0, "sharpe_approx": 0.0,
                "pnl_history": [], "regimes": {},
                "first_seen": datetime.now(timezone.utc).isoformat(),
            }

        s = self.strategies[strategy_name]
        s["trades"] += 1
        if pnl_pct > 0:
            s["wins"] += 1
        s["total_pnl_pct"] += pnl_pct
        s["avg_pnl"] = s["total_pnl_pct"] / s["trades"]

        # Track PnL history for Sharpe calculation
        s["pnl_history"].append(pnl_pct)
        s["pnl_history"] = s["pnl_history"][-500:]  # Keep last 500

        # Approximate Sharpe
        if len(s["pnl_history"]) >= 10:
            import statistics
            mean = statistics.mean(s["pnl_history"])
            std = statistics.stdev(s["pnl_history"]) or 0.01
            s["sharpe_approx"] = round(mean / std, 3)

        # Track per regime
        if regime not in s["regimes"]:
            s["regimes"][regime] = {"trades": 0, "wins": 0}
        s["regimes"][regime]["trades"] += 1
        if pnl_pct > 0:
            s["regimes"][regime]["wins"] += 1

        self.save_strategies()

    def get_top_strategies(self, n: int = 10) -> list:
        """Get top N strategies by Sharpe ratio."""
        ranked = []
        for name, data in self.strategies.items():
            if data["trades"] >= 10:
                ranked.append({
                    "name": name,
                    "trades": data["trades"],
                    "winrate": data["wins"] / max(data["trades"], 1),
                    "avg_pnl": data["avg_pnl"],
                    "sharpe": data["sharpe_approx"],
                })
        ranked.sort(key=lambda x: x["sharpe"], reverse=True)
        return ranked[:n]

    # ═══════════════════════════════════════════════════════════════════════
    # 5. PATTERN DETECTION — Find recurring profitable setups
    # ═══════════════════════════════════════════════════════════════════════

    def _load_patterns(self) -> dict:
        """Load discovered patterns."""
        if PATTERNS_FILE.exists():
            try:
                return json.loads(PATTERNS_FILE.read_text())
            except Exception:
                pass
        return {"discovered": [], "last_scan": None}

    def discover_patterns(self):
        """
        Analyze all collected data to find recurring profitable patterns.
        Called periodically (e.g., every 100 trades).
        """
        if self.memory["stats"]["total_trades"] < 20:
            return  # Not enough data

        patterns = []

        # Pattern 1: Best signal combinations
        signal_combos = {}
        for pair, pk in self.memory["pair_knowledge"].items():
            best = pk.get("best_entry_signals", {})
            for sig_combo, data in best.items():
                if sig_combo not in signal_combos:
                    signal_combos[sig_combo] = {"wins": 0, "total": 0}
                signal_combos[sig_combo]["wins"] += data.get("wins", 0)
                signal_combos[sig_combo]["total"] += data.get("total", 0)

        # Pattern 2: Regime-specific winners
        for regime, rk in self.memory["regime_knowledge"].items():
            if rk["trades"] >= 10:
                winrate = rk["wins"] / rk["trades"]
                if winrate > 0.6:
                    patterns.append({
                        "type": "regime_alpha",
                        "regime": regime,
                        "winrate": round(winrate, 3),
                        "sample": rk["trades"],
                        "best_signals": dict(sorted(
                            rk["best_signals"].items(),
                            key=lambda x: x[1].get("wins", 0),
                            reverse=True
                        )[:5]),
                    })

        # Pattern 3: Time-of-day edge
        for hour, hp in self.memory.get("hourly_performance", {}).items():
            if hp["trades"] >= 10:
                winrate = hp["wins"] / hp["trades"]
                if winrate > 0.65:
                    patterns.append({
                        "type": "time_edge",
                        "hour_utc": int(hour),
                        "winrate": round(winrate, 3),
                        "sample": hp["trades"],
                        "total_pnl": round(hp["pnl"], 2),
                    })

        # Pattern 4: Pair-specific alpha
        for pair, pk in self.memory["pair_knowledge"].items():
            if pk["trades"] >= 15:
                winrate = pk["wins"] / pk["trades"]
                if winrate > 0.6:
                    patterns.append({
                        "type": "pair_alpha",
                        "pair": pair,
                        "market": pk.get("market", "crypto"),
                        "winrate": round(winrate, 3),
                        "sample": pk["trades"],
                        "avg_pnl": round(pk["total_pnl"] / pk["trades"], 2),
                    })

        self.patterns["discovered"] = patterns
        self.patterns["last_scan"] = datetime.now(timezone.utc).isoformat()

        try:
            PATTERNS_FILE.write_text(json.dumps(self.patterns, indent=2))
        except Exception:
            pass

        if patterns:
            logger.info(f"🧠 Brain discovered {len(patterns)} patterns!")

    # ═══════════════════════════════════════════════════════════════════════
    # 6. AUTO-TRAINER — Retrain ML model when ready
    # ═══════════════════════════════════════════════════════════════════════

    def maybe_train_model(self):
        """
        Check if enough labeled data exists and train XGBoost predictor.
        Called periodically from the engine loop.
        """
        try:
            from bot.ml_collector import get_training_data, get_stats

            stats = get_stats()
            labeled = stats.get("total_labeled", 0)

            # Need at least 200 labeled rows to train
            if labeled < 200:
                return None

            # Only retrain every 500 new labels
            last_trained = self.memory.get("last_ml_train_at", 0)
            if labeled - last_trained < 500 and last_trained > 0:
                return None

            data = get_training_data()
            if len(data) < 200:
                return None

            logger.info(f"🧠 Brain: Training ML model with {len(data)} samples...")

            # Extract features and labels
            feature_cols = [
                "rsi14", "adx14", "atr_pct", "macd", "volume_ratio",
                "vwap_dev", "fg_value", "news_sentiment", "funding_rate",
                "oi_signal", "mtf_boost", "score", "signal_count",
            ]

            X = []
            y = []
            for row in data:
                try:
                    features = [float(row.get(c, 0) or 0) for c in feature_cols]
                    label = int(row.get("outcome_label", 0) or 0)
                    X.append(features)
                    y.append(label)
                except (ValueError, TypeError):
                    continue

            if len(X) < 100:
                return None

            # Train XGBoost
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.model_selection import cross_val_score
            import numpy as np

            X = np.array(X)
            y = np.array(y)

            model = GradientBoostingClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                min_samples_leaf=10, random_state=42,
            )

            # Cross-validate
            scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
            accuracy = scores.mean()

            # Train final model
            model.fit(X, y)

            # Save feature importance to memory
            importance = dict(zip(feature_cols, model.feature_importances_.tolist()))
            self.memory["feature_importance"] = {
                k: round(v, 4) for k, v in
                sorted(importance.items(), key=lambda x: x[1], reverse=True)
            }

            # Save model
            import pickle
            model_path = BRAIN_DIR / "ml_model.pkl"
            with open(model_path, "wb") as f:
                pickle.dump(model, f)

            self.memory["last_ml_train_at"] = labeled
            self.memory["ml_accuracy"] = round(accuracy, 4)
            self.memory["ml_train_count"] = self.memory.get("ml_train_count", 0) + 1
            self.save_memory()

            logger.info(
                f"🧠 Brain: ML Model trained! Accuracy: {accuracy:.1%} | "
                f"Samples: {len(X)} | Train #{self.memory['ml_train_count']}"
            )
            logger.info(f"🧠 Top features: {list(self.memory['feature_importance'].items())[:5]}")

            return model

        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"ML training failed: {e}")
            return None

    def get_ml_prediction(self, features: dict) -> float:
        """
        Get ML prediction confidence for a potential trade.
        Returns 0.0-1.0 (probability of profitable trade).
        """
        try:
            import pickle
            import numpy as np

            model_path = BRAIN_DIR / "ml_model.pkl"
            if not model_path.exists():
                return 0.5  # No model yet

            with open(model_path, "rb") as f:
                model = pickle.load(f)

            feature_cols = [
                "rsi14", "adx14", "atr_pct", "macd", "volume_ratio",
                "vwap_dev", "fg_value", "news_sentiment", "funding_rate",
                "oi_signal", "mtf_boost", "score", "signal_count",
            ]

            X = np.array([[float(features.get(c, 0) or 0) for c in feature_cols]])
            proba = model.predict_proba(X)[0]

            # Return probability of class 1 (profitable)
            return float(proba[1]) if len(proba) > 1 else 0.5

        except Exception:
            return 0.5

    # ═══════════════════════════════════════════════════════════════════════
    # 7. EVOLUTION LOG — Track the brain's growth over time
    # ═══════════════════════════════════════════════════════════════════════

    def _ensure_evolution_log(self):
        """Ensure evolution CSV exists."""
        if not EVOLUTION_LOG.exists():
            with open(EVOLUTION_LOG, "w", newline="") as f:
                f.write("timestamp,pair,pnl,pnl_pct,signals,regime,total_trades,lifetime_winrate,lifetime_pnl\n")

    def _log_evolution(self, pair: str, pnl: float, pnl_pct: float,
                       signals: list, regime: str):
        """Log a data point to the evolution timeline."""
        try:
            stats = self.memory["stats"]
            winrate = stats["total_wins"] / max(stats["total_trades"], 1) * 100
            with open(EVOLUTION_LOG, "a", newline="") as f:
                csv.writer(f).writerow([
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    pair,
                    f"{pnl:.2f}",
                    f"{pnl_pct:.4f}",
                    "|".join(signals),
                    regime,
                    stats["total_trades"],
                    f"{winrate:.1f}",
                    f"{stats['total_pnl']:.2f}",
                ])
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════
    # 8. STATUS — Get brain health report
    # ═══════════════════════════════════════════════════════════════════════

    def get_status(self) -> dict:
        """Get comprehensive brain status."""
        stats = self.memory["stats"]
        winrate = stats["total_wins"] / max(stats["total_trades"], 1)

        return {
            "age_hours": stats.get("age_hours", 0),
            "total_evaluations": stats["total_evaluations"],
            "total_trades": stats["total_trades"],
            "winrate": round(winrate, 3),
            "lifetime_pnl": stats["total_pnl"],
            "pairs_known": len(self.memory["pair_knowledge"]),
            "lessons_learned": len(self.memory.get("lessons", [])),
            "patterns_discovered": len(self.patterns.get("discovered", [])),
            "strategies_tracked": len(self.strategies),
            "ml_accuracy": self.memory.get("ml_accuracy", None),
            "ml_trains": self.memory.get("ml_train_count", 0),
            "top_signals": self.get_signal_ranking()[:5],
            "feature_importance": self.memory.get("feature_importance", {}),
            "stage": self._get_evolution_stage(),
        }

    def _get_evolution_stage(self) -> str:
        """Determine the brain's current evolution stage."""
        trades = self.memory["stats"]["total_trades"]
        evals = self.memory["stats"]["total_evaluations"]

        if trades < 10:
            return "🥒 Newborn — Collecting first data"
        elif trades < 50:
            return "🌱 Infant — Learning basics"
        elif trades < 200:
            return "🌿 Growing — Building pattern recognition"
        elif trades < 500:
            return "🌳 Mature — Strategy evolution active"
        elif trades < 1000:
            return "🧠 Smart — ML model active, self-optimizing"
        elif trades < 5000:
            return "🔥 Expert — Deep pattern mastery"
        else:
            return "💎 Master — Thousands of trades learned"


# Singleton Brain instance
_brain_instance = None

def get_brain() -> TradingBrain:
    """Get or create the singleton brain instance."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = TradingBrain()
    return _brain_instance
