"""
ML Performance Tracker
Tracks prediction accuracy and performance metrics over time
"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import deque
import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PerformanceTracker:
    """
    Tracks ML model prediction accuracy and performance.
    Stores metrics in JSON for persistence.
    """
    
    def __init__(self, storage_path: Optional[str] = None, max_history: int = 1000):
        """
        Args:
            storage_path: Path to JSON storage file
            max_history: Maximum number of predictions to track
        """
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        self.storage_path = storage_path or (log_dir / "ml_performance.json")
        self.max_history = max_history
        
        # Prediction history
        self.predictions: List[Dict] = []
        self.outcomes: List[Dict] = []
        
        # Model-specific metrics
        self.model_metrics: Dict[str, Dict] = {
            "dqn": {"correct": 0, "total": 0, "accuracy": 0.0},
            "gradient_boosting": {"correct": 0, "total": 0, "accuracy": 0.0},
            "lstm": {"correct": 0, "total": 0, "accuracy": 0.0},
            "ensemble": {"correct": 0, "total": 0, "accuracy": 0.0}
        }
        
        # Load existing data
        self._load()
    
    def _load(self):
        """Load performance data from disk"""
        try:
            if Path(self.storage_path).exists():
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.predictions = data.get("predictions", [])[-self.max_history:]
                    self.outcomes = data.get("outcomes", [])[-self.max_history:]
                    self.model_metrics = data.get("model_metrics", self.model_metrics)
                    logger.info(f"Loaded {len(self.predictions)} prediction records")
        except Exception as e:
            logger.warning(f"Could not load performance data: {e}")
    
    def _save(self):
        """Persist performance data to disk"""
        try:
            data = {
                "predictions": self.predictions[-self.max_history:],
                "outcomes": self.outcomes[-self.max_history:],
                "model_metrics": self.model_metrics,
                "last_updated": datetime.now().isoformat()
            }
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save performance data: {e}")
    
    def log_prediction(self, model: str, signal: str, confidence: float, 
                       price: float, timestamp: Optional[str] = None) -> str:
        """
        Log a prediction from a model
        
        Args:
            model: Model name (dqn, gradient_boosting, lstm, ensemble)
            signal: Predicted signal (BUY, SELL, HOLD)
            confidence: Prediction confidence 0-1
            price: Current price at prediction time
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            Prediction ID for later matching
        """
        pred_id = f"{model}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        prediction = {
            "id": pred_id,
            "model": model,
            "signal": signal,
            "confidence": confidence,
            "price": price,
            "timestamp": timestamp or datetime.now().isoformat(),
            "matched": False
        }
        
        self.predictions.append(prediction)
        
        # Trim history
        if len(self.predictions) > self.max_history:
            self.predictions = self.predictions[-self.max_history:]
        
        return pred_id
    
    def log_outcome(self, price_before: float, price_after: float, 
                   actual_pnl: float, window_minutes: int = 30):
        """
        Log the actual outcome and match with predictions
        
        Args:
            price_before: Price at prediction time
            price_after: Price after outcome window
            actual_pnl: Actual PnL percentage
            window_minutes: Lookback window for matching predictions
        """
        now = datetime.now()
        cutoff = now - timedelta(minutes=window_minutes)
        
        # Determine actual direction
        if price_after > price_before * 1.001:
            actual_signal = "BUY"  # Price went up
        elif price_after < price_before * 0.999:
            actual_signal = "SELL"  # Price went down
        else:
            actual_signal = "HOLD"  # Sideways
        
        outcome = {
            "timestamp": now.isoformat(),
            "price_before": price_before,
            "price_after": price_after,
            "actual_signal": actual_signal,
            "actual_pnl": actual_pnl
        }
        
        self.outcomes.append(outcome)
        
        # Match with recent predictions
        matched_count = 0
        for pred in self.predictions:
            if pred["matched"]:
                continue
            
            pred_time = datetime.fromisoformat(pred["timestamp"])
            if pred_time < cutoff:
                continue
            
            # Check if price matches
            if abs(pred["price"] - price_before) / price_before < 0.001:
                pred["matched"] = True
                pred["actual_signal"] = actual_signal
                pred["actual_pnl"] = actual_pnl
                
                # Update metrics
                model = pred["model"]
                if model in self.model_metrics:
                    self.model_metrics[model]["total"] += 1
                    
                    # Correct if predicted direction matches actual
                    if pred["signal"] == actual_signal:
                        self.model_metrics[model]["correct"] += 1
                    elif pred["signal"] == "HOLD":
                        # Partial credit for HOLD
                        if abs(actual_pnl) < 0.5:
                            self.model_metrics[model]["correct"] += 0.5
                    
                    # Update accuracy
                    total = self.model_metrics[model]["total"]
                    correct = self.model_metrics[model]["correct"]
                    self.model_metrics[model]["accuracy"] = correct / total if total > 0 else 0.0
                
                matched_count += 1
        
        # Trim outcomes
        if len(self.outcomes) > self.max_history:
            self.outcomes = self.outcomes[-self.max_history:]
        
        # Save periodically
        if len(self.outcomes) % 10 == 0:
            self._save()
        
        return matched_count
    
    def calculate_accuracy(self, model: str, window: int = 100) -> float:
        """
        Calculate accuracy for a model over recent predictions
        
        Args:
            model: Model name
            window: Number of recent predictions to consider
            
        Returns:
            Accuracy (0.0 to 1.0)
        """
        recent = [p for p in self.predictions[-window:] 
                  if p["model"] == model and p.get("matched")]
        
        if not recent:
            return self.model_metrics.get(model, {}).get("accuracy", 0.0)
        
        correct = sum(1 for p in recent if p["signal"] == p.get("actual_signal"))
        return correct / len(recent)
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics
        
        Returns:
            Dict with accuracy, precision, recall, F1 by model
        """
        metrics = {}
        
        for model, data in self.model_metrics.items():
            matched_preds = [p for p in self.predictions if p["model"] == model and p.get("matched")]
            
            if not matched_preds:
                metrics[model] = {
                    "accuracy": data["accuracy"],
                    "total_predictions": data["total"],
                    "correct_predictions": data["correct"],
                    "precision": 0.0,
                    "recall": 0.0,
                    "f1_score": 0.0
                }
                continue
            
            # Calculate precision/recall for BUY signals
            true_positives = sum(1 for p in matched_preds 
                                if p["signal"] == "BUY" and p.get("actual_signal") == "BUY")
            false_positives = sum(1 for p in matched_preds 
                                 if p["signal"] == "BUY" and p.get("actual_signal") != "BUY")
            false_negatives = sum(1 for p in matched_preds 
                                 if p["signal"] != "BUY" and p.get("actual_signal") == "BUY")
            
            precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
            recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            
            metrics[model] = {
                "accuracy": data["accuracy"],
                "total_predictions": data["total"],
                "correct_predictions": data["correct"],
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4)
            }
        
        metrics["summary"] = {
            "total_predictions": sum(m.get("total_predictions", 0) for m in metrics.values() if isinstance(m, dict)),
            "avg_accuracy": np.mean([m.get("accuracy", 0) for m in metrics.values() if isinstance(m, dict) and m.get("total_predictions", 0) > 0]) if metrics else 0.0
        }
        
        return metrics
    
    def needs_retrain(self, model: str, threshold: float = 0.5, min_samples: int = 50) -> bool:
        """
        Check if model needs retraining due to poor accuracy
        
        Args:
            model: Model name
            threshold: Minimum acceptable accuracy
            min_samples: Minimum predictions before checking
            
        Returns:
            True if retraining recommended
        """
        data = self.model_metrics.get(model, {})
        total = data.get("total", 0)
        accuracy = data.get("accuracy", 1.0)
        
        if total < min_samples:
            return False
        
        return accuracy < threshold
    
    def get_accuracy_trend(self, model: str, windows: List[int] = [10, 50, 100]) -> Dict[str, float]:
        """Get accuracy trend across different windows"""
        trend = {}
        for w in windows:
            trend[f"last_{w}"] = self.calculate_accuracy(model, w)
        return trend


# Singleton instance
_tracker = None

def get_performance_tracker() -> PerformanceTracker:
    """Get global performance tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = PerformanceTracker()
    return _tracker


if __name__ == "__main__":
    tracker = PerformanceTracker()
    
    # Test logging
    pred_id = tracker.log_prediction("dqn", "BUY", 0.75, 3250.0)
    print(f"Logged prediction: {pred_id}")
    
    # Simulate outcome
    tracker.log_outcome(3250.0, 3280.0, 0.92)
    
    # Get metrics
    print(f"Metrics: {tracker.get_metrics()}")
