"""
Ethbot v2: Edge Validator

The most critical module. Logs predictions WITHOUT trading and evaluates 
them against actual market outcomes to determine if an edge exists.

Rules:
1. Minimum 200 predictions before an edge is considered "validated"
2. Edge must have positive expectancy over the full sample
3. No live trading until validation passes

Usage:
    from edge_validator import validator
    
    # Log a prediction
    validator.log_prediction("funding_reversal", "SHORT", confidence=0.72, price=3200.0)
    
    # After time passes, evaluate
    report = validator.evaluate()
    print(report["status"])  # "VALIDATED" or "COLLECTING" or "NO_EDGE"
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger("ethbot.edge")

# Validation thresholds
MIN_PREDICTIONS = 200
MIN_WIN_RATE = 55.0         # %
MIN_PROFIT_FACTOR = 1.3
MAX_CONSECUTIVE_LOSSES = 6
EVALUATION_WINDOW_MINUTES = 60  # Check outcome after 1 hour


@dataclass
class Prediction:
    """A single prediction made by a signal."""
    id: int
    signal_name: str          # e.g. "funding_reversal"
    direction: str            # "LONG" or "SHORT"
    confidence: float         # 0.0 - 1.0
    price_at_prediction: float
    timestamp: float          # Unix timestamp
    
    # Filled in later when outcome is known
    price_at_evaluation: Optional[float] = None
    outcome: Optional[str] = None      # "WIN" or "LOSS"
    pnl_pct: Optional[float] = None    # % move in predicted direction
    evaluated_at: Optional[float] = None


class EdgeValidator:
    """Tracks predictions and evaluates edge statistical significance."""

    def __init__(self):
        self._predictions: List[Prediction] = []
        self._next_id = 1
        self._db_initialized = False

    # ─── Prediction Logging ───

    def log_prediction(
        self, 
        signal_name: str, 
        direction: str, 
        confidence: float, 
        price: float
    ) -> int:
        """Log a new prediction. Returns prediction ID."""
        pred = Prediction(
            id=self._next_id,
            signal_name=signal_name,
            direction=direction.upper(),
            confidence=confidence,
            price_at_prediction=price,
            timestamp=time.time()
        )
        self._predictions.append(pred)
        self._next_id += 1

        logger.info(
            f"📝 Prediction #{pred.id}: {signal_name} → {direction} "
            f"@ ${price:,.2f} (conf={confidence:.2f})"
        )

        # Persist to DB
        self._save_prediction(pred)
        return pred.id

    # ─── Outcome Evaluation ───

    def evaluate_outcomes(self, current_price: float):
        """Evaluate all pending predictions against current price.
        Called periodically (e.g. every minute) with the current price."""
        now = time.time()
        
        for pred in self._predictions:
            if pred.outcome is not None:
                continue  # Already evaluated
            
            # Check if enough time has passed
            elapsed_minutes = (now - pred.timestamp) / 60
            if elapsed_minutes < EVALUATION_WINDOW_MINUTES:
                continue

            # Calculate outcome
            if pred.direction == "LONG":
                pnl_pct = (current_price - pred.price_at_prediction) / pred.price_at_prediction * 100
            else:  # SHORT
                pnl_pct = (pred.price_at_prediction - current_price) / pred.price_at_prediction * 100

            pred.price_at_evaluation = current_price
            pred.pnl_pct = round(pnl_pct, 4)
            pred.outcome = "WIN" if pnl_pct > 0 else "LOSS"
            pred.evaluated_at = now

            logger.info(
                f"✅ Prediction #{pred.id} ({pred.signal_name}): "
                f"{pred.outcome} {pnl_pct:+.3f}% "
                f"(${pred.price_at_prediction:.2f} → ${current_price:.2f})"
            )

            # Update in DB
            self._update_prediction(pred)

    # ─── Edge Report ───

    def get_report(self, signal_name: str = None) -> Dict:
        """Generate comprehensive edge validation report.
        
        Args:
            signal_name: Filter by specific signal, or None for all.
        """
        evaluated = [
            p for p in self._predictions 
            if p.outcome is not None 
            and (signal_name is None or p.signal_name == signal_name)
        ]
        pending = [
            p for p in self._predictions 
            if p.outcome is None
            and (signal_name is None or p.signal_name == signal_name)
        ]

        total = len(evaluated)
        if total == 0:
            return {
                "status": "COLLECTING",
                "total_predictions": len(self._predictions),
                "evaluated": 0,
                "pending": len(pending),
                "target": MIN_PREDICTIONS,
                "progress_pct": 0,
                "message": "Collecting predictions. No outcomes yet."
            }

        wins = [p for p in evaluated if p.outcome == "WIN"]
        losses = [p for p in evaluated if p.outcome == "LOSS"]
        win_rate = len(wins) / total * 100

        # Expectancy
        avg_win = sum(p.pnl_pct for p in wins) / max(len(wins), 1)
        avg_loss = abs(sum(p.pnl_pct for p in losses) / max(len(losses), 1))
        expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

        # Profit factor
        gross_win = sum(p.pnl_pct for p in wins) if wins else 0
        gross_loss = abs(sum(p.pnl_pct for p in losses)) if losses else 0.0001
        profit_factor = gross_win / max(gross_loss, 0.0001)

        # Max consecutive losses
        max_consec_losses = 0
        current_streak = 0
        for p in evaluated:
            if p.outcome == "LOSS":
                current_streak += 1
                max_consec_losses = max(max_consec_losses, current_streak)
            else:
                current_streak = 0

        # Determine status
        if total < MIN_PREDICTIONS:
            status = "COLLECTING"
            message = f"Need {MIN_PREDICTIONS - total} more predictions for validation"
        elif win_rate >= MIN_WIN_RATE and profit_factor >= MIN_PROFIT_FACTOR and max_consec_losses <= MAX_CONSECUTIVE_LOSSES:
            status = "VALIDATED"
            message = f"Edge CONFIRMED! WR={win_rate:.1f}% PF={profit_factor:.2f} — READY FOR LIVE"
        elif expectancy <= 0:
            status = "NO_EDGE"
            message = f"No edge found. Expectancy={expectancy:.4f}% — DO NOT TRADE"
        else:
            status = "WEAK"
            reasons = []
            if win_rate < MIN_WIN_RATE:
                reasons.append(f"WR {win_rate:.1f}% < {MIN_WIN_RATE}%")
            if profit_factor < MIN_PROFIT_FACTOR:
                reasons.append(f"PF {profit_factor:.2f} < {MIN_PROFIT_FACTOR}")
            if max_consec_losses > MAX_CONSECUTIVE_LOSSES:
                reasons.append(f"Max streak {max_consec_losses} > {MAX_CONSECUTIVE_LOSSES}")
            message = f"Edge weak: {', '.join(reasons)}"

        # Per-signal breakdown
        signal_breakdown = {}
        signal_names = set(p.signal_name for p in evaluated)
        for sn in signal_names:
            s_preds = [p for p in evaluated if p.signal_name == sn]
            s_wins = [p for p in s_preds if p.outcome == "WIN"]
            s_wr = len(s_wins) / max(len(s_preds), 1) * 100
            s_avg_pnl = sum(p.pnl_pct for p in s_preds) / max(len(s_preds), 1)
            signal_breakdown[sn] = {
                "predictions": len(s_preds),
                "win_rate": round(s_wr, 1),
                "avg_pnl_pct": round(s_avg_pnl, 4),
                "total_pnl_pct": round(sum(p.pnl_pct for p in s_preds), 4)
            }

        return {
            "status": status,
            "message": message,
            "total_predictions": len(self._predictions),
            "evaluated": total,
            "pending": len(pending),
            "target": MIN_PREDICTIONS,
            "progress_pct": round(min(total / MIN_PREDICTIONS * 100, 100), 1),
            "win_rate": round(win_rate, 1),
            "expectancy_pct": round(expectancy, 4),
            "profit_factor": round(profit_factor, 2),
            "avg_win_pct": round(avg_win, 4),
            "avg_loss_pct": round(avg_loss, 4),
            "max_consecutive_losses": max_consec_losses,
            "total_pnl_pct": round(sum(p.pnl_pct for p in evaluated), 4),
            "signal_breakdown": signal_breakdown,
            "validation_criteria": {
                "min_predictions": MIN_PREDICTIONS,
                "min_win_rate": MIN_WIN_RATE,
                "min_profit_factor": MIN_PROFIT_FACTOR,
                "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
            }
        }

    # ─── Persistence ───

    def _save_prediction(self, pred: Prediction):
        """Save prediction to PostgreSQL."""
        try:
            from db_adapter import get_db_connection, USE_POSTGRES
            if not USE_POSTGRES:
                return
            
            if not self._db_initialized:
                self._ensure_table()

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO edge_predictions (
                        signal_name, direction, confidence, 
                        price_at_prediction, predicted_at
                    ) VALUES (%s, %s, %s, %s, NOW())
                """, (pred.signal_name, pred.direction, pred.confidence, 
                      pred.price_at_prediction))
        except Exception as e:
            logger.debug(f"Prediction save error: {e}")

    def _update_prediction(self, pred: Prediction):
        """Update prediction with outcome."""
        try:
            from db_adapter import get_db_connection, USE_POSTGRES
            if not USE_POSTGRES:
                return

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE edge_predictions SET 
                        price_at_evaluation = %s,
                        outcome = %s,
                        pnl_pct = %s,
                        evaluated_at = NOW()
                    WHERE id = %s
                """, (pred.price_at_evaluation, pred.outcome, pred.pnl_pct, pred.id))
        except Exception as e:
            logger.debug(f"Prediction update error: {e}")

    def _ensure_table(self):
        """Create predictions table."""
        try:
            from db_adapter import get_db_connection, USE_POSTGRES
            if not USE_POSTGRES:
                return

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS edge_predictions (
                        id SERIAL PRIMARY KEY,
                        signal_name VARCHAR(50) NOT NULL,
                        direction VARCHAR(5) NOT NULL,
                        confidence FLOAT,
                        price_at_prediction FLOAT NOT NULL,
                        predicted_at TIMESTAMPTZ DEFAULT NOW(),
                        price_at_evaluation FLOAT,
                        outcome VARCHAR(4),
                        pnl_pct FLOAT,
                        evaluated_at TIMESTAMPTZ
                    );
                    CREATE INDEX IF NOT EXISTS idx_edge_pred_signal 
                    ON edge_predictions (signal_name, predicted_at DESC);
                """)
            self._db_initialized = True
            logger.info("✅ edge_predictions table ready")
        except Exception as e:
            logger.error(f"Table creation error: {e}")


# Singleton
validator = EdgeValidator()
