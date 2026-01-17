"""
Auto-Retrain System
Automatically triggers model retraining when performance drops
"""
import os
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
import json

from src.utils.logger import get_logger
from src.ml.ml_performance_tracker import get_performance_tracker

logger = get_logger(__name__)


class AutoRetrainer:
    """
    Monitors ML model performance and triggers retraining when needed.
    Supports scheduled periodic retraining and threshold-based triggers.
    """
    
    def __init__(
        self,
        accuracy_threshold: float = 0.5,
        min_samples: int = 50,
        check_interval_minutes: int = 60,
        cooldown_hours: int = 6
    ):
        """
        Args:
            accuracy_threshold: Trigger retrain if accuracy drops below this
            min_samples: Minimum predictions before checking threshold
            check_interval_minutes: How often to check performance
            cooldown_hours: Minimum hours between retrains
        """
        self.accuracy_threshold = accuracy_threshold
        self.min_samples = min_samples
        self.check_interval = check_interval_minutes * 60
        self.cooldown = timedelta(hours=cooldown_hours)
        
        self.last_retrain: Dict[str, datetime] = {
            "dqn": datetime.min,
            "gradient_boosting": datetime.min,
            "lstm": datetime.min
        }
        
        self.active_training: Dict[str, subprocess.Popen] = {}
        self.monitor_thread = None
        self.stop_event = threading.Event()
        
        # Storage for retrain history
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        self.history_path = log_dir / "retrain_history.json"
        self.history = self._load_history()
    
    def _load_history(self) -> list:
        """Load retrain history from disk"""
        try:
            if self.history_path.exists():
                with open(self.history_path) as f:
                    return json.load(f)
        except:
            pass
        return []
    
    def _save_history(self):
        """Persist retrain history"""
        try:
            with open(self.history_path, "w") as f:
                json.dump(self.history[-100:], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save retrain history: {e}")
    
    def check_retrain_needed(self, model: str) -> tuple[bool, str]:
        """
        Check if model needs retraining
        
        Args:
            model: Model name (dqn, gradient_boosting, lstm)
            
        Returns:
            Tuple of (needs_retrain, reason)
        """
        tracker = get_performance_tracker()
        
        # Check cooldown
        if datetime.now() - self.last_retrain.get(model, datetime.min) < self.cooldown:
            return False, "In cooldown period"
        
        # Check if already training
        if model in self.active_training:
            proc = self.active_training[model]
            if proc.poll() is None:  # Still running
                return False, "Training already in progress"
            else:
                del self.active_training[model]
        
        # Check performance
        if tracker.needs_retrain(model, self.accuracy_threshold, self.min_samples):
            accuracy = tracker.calculate_accuracy(model, 100)
            return True, f"Accuracy {accuracy:.1%} below threshold {self.accuracy_threshold:.1%}"
        
        return False, "Performance acceptable"
    
    def trigger_retrain(self, model: str, episodes: int = 100) -> Dict[str, Any]:
        """
        Start background retraining for a model
        
        Args:
            model: Model name
            episodes: Training episodes (for DQN)
            
        Returns:
            Training status dict
        """
        logger.info(f"🔄 Triggering retrain for {model}")
        
        project_root = Path(__file__).parent.parent.parent
        
        if model == "dqn":
            cmd = [
                "python", str(project_root / "rl_trading_agent.py"),
                "--train", "--episodes", str(episodes)
            ]
        elif model == "gradient_boosting":
            cmd = [
                "python", str(project_root / "ml_strategy_predictor.py"),
                "--train"
            ]
        elif model == "lstm":
            cmd = [
                "python", str(project_root / "neural_strategy_predictor.py"),
                "--train"
            ]
        else:
            return {"status": "error", "message": f"Unknown model: {model}"}
        
        try:
            log_dir = Path(os.getenv("LOG_DIR", "./logs"))
            log_file = log_dir / f"{model}_retrain.log"
            
            with open(log_file, "w") as f:
                proc = subprocess.Popen(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=str(project_root)
                )
            
            self.active_training[model] = proc
            self.last_retrain[model] = datetime.now()
            
            # Record history
            self.history.append({
                "model": model,
                "timestamp": datetime.now().isoformat(),
                "reason": "auto_threshold",
                "pid": proc.pid
            })
            self._save_history()
            
            return {
                "status": "started",
                "model": model,
                "pid": proc.pid,
                "log_file": str(log_file)
            }
            
        except Exception as e:
            logger.error(f"Failed to start retrain: {e}")
            return {"status": "error", "message": str(e)}
    
    def check_all_models(self) -> Dict[str, Any]:
        """Check all models and trigger retrains as needed"""
        results = {}
        
        for model in ["dqn", "gradient_boosting", "lstm"]:
            needs_retrain, reason = self.check_retrain_needed(model)
            
            if needs_retrain:
                result = self.trigger_retrain(model)
                results[model] = {"triggered": True, "reason": reason, **result}
            else:
                results[model] = {"triggered": False, "reason": reason}
        
        return results
    
    def start_monitor(self, callback: Optional[Callable] = None):
        """
        Start background monitoring thread
        
        Args:
            callback: Optional function to call on retrain trigger
        """
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.warning("Monitor already running")
            return
        
        self.stop_event.clear()
        
        def monitor_loop():
            logger.info(f"🔍 Auto-retrain monitor started (check every {self.check_interval//60} min)")
            
            while not self.stop_event.is_set():
                try:
                    results = self.check_all_models()
                    
                    triggered = [m for m, r in results.items() if r.get("triggered")]
                    if triggered:
                        logger.info(f"Auto-retrain triggered for: {', '.join(triggered)}")
                        if callback:
                            callback(results)
                    
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                
                self.stop_event.wait(self.check_interval)
            
            logger.info("Auto-retrain monitor stopped")
        
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitor(self):
        """Stop background monitoring"""
        self.stop_event.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
    
    def schedule_periodic_retrain(self, model: str, interval_hours: int = 24):
        """
        Schedule periodic retraining for a model
        
        Args:
            model: Model name
            interval_hours: Hours between retrains
        """
        def scheduled_retrain():
            while not self.stop_event.is_set():
                self.stop_event.wait(interval_hours * 3600)
                if not self.stop_event.is_set():
                    logger.info(f"⏰ Scheduled retrain for {model}")
                    self.trigger_retrain(model)
        
        thread = threading.Thread(target=scheduled_retrain, daemon=True, name=f"retrain_{model}")
        thread.start()
        logger.info(f"Scheduled {model} retrain every {interval_hours} hours")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current retrainer status"""
        active = {}
        for model, proc in self.active_training.items():
            if proc.poll() is None:
                active[model] = {"pid": proc.pid, "status": "running"}
            else:
                active[model] = {"pid": proc.pid, "status": "completed", "exit_code": proc.returncode}
        
        return {
            "accuracy_threshold": self.accuracy_threshold,
            "min_samples": self.min_samples,
            "check_interval_minutes": self.check_interval // 60,
            "cooldown_hours": self.cooldown.total_seconds() / 3600,
            "last_retrain": {k: v.isoformat() if v != datetime.min else None 
                           for k, v in self.last_retrain.items()},
            "active_training": active,
            "monitor_running": self.monitor_thread.is_alive() if self.monitor_thread else False,
            "history_count": len(self.history)
        }


# Singleton
_retrainer = None

def get_auto_retrainer() -> AutoRetrainer:
    """Get global auto-retrainer instance"""
    global _retrainer
    if _retrainer is None:
        _retrainer = AutoRetrainer()
    return _retrainer


if __name__ == "__main__":
    retrainer = AutoRetrainer()
    print(f"Status: {retrainer.get_status()}")
    
    # Check models
    results = retrainer.check_all_models()
    print(f"Check results: {results}")
