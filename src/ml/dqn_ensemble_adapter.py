"""
DQN Ensemble Adapter
Adapts the DQN agent for use in ensemble predictions with sklearn-style interface
"""
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import sys

# Add parent dir
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class DQNEnsembleAdapter:
    """
    Wraps DQN agent with sklearn-compatible predict_proba interface
    for use in ensemble models
    """
    
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.agent = None
        self.is_loaded = False
        self.window_size = 20
        
        self._load_agent()
    
    def _load_agent(self) -> bool:
        """Load DQN agent from disk"""
        try:
            from rl_trading_agent import DQNAgent, TradingEnvironment
            
            env = TradingEnvironment(window_size=self.window_size)
            self.agent = DQNAgent(state_size=env.state_size)
            
            if self.agent.is_trained:
                self.is_loaded = True
                return True
            return False
        except Exception as e:
            print(f"DQN load error: {e}")
            return False
    
    def prepare_state(self, prices: np.ndarray) -> Optional[np.ndarray]:
        """Convert price array to DQN state vector"""
        if len(prices) < self.window_size:
            return None
        
        prices = prices[-self.window_size:]
        
        # Returns
        returns = np.diff(prices) / prices[:-1]
        returns = np.nan_to_num(returns)
        
        # Features
        sma_5 = np.mean(prices[-5:])
        sma_20 = np.mean(prices)
        current = prices[-1]
        volatility = np.std(returns)
        trend = (prices[-1] - prices[0]) / prices[0] if prices[0] != 0 else 0
        
        state = np.concatenate([
            returns,
            [sma_5 / current - 1],
            [sma_20 / current - 1],
            [volatility],
            [trend],
            [0.0],  # has_position
            [0.0],  # unrealized_pnl
            [0.0],  # balance_ratio
            [0.0]   # position_value
        ])
        
        return state.astype(np.float32)
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Sklearn-compatible predict_proba
        
        Args:
            X: Array of shape (n_samples, n_features) - expects price windows
            
        Returns:
            Array of shape (n_samples, 2) with [P(down), P(up)]
        """
        if not self.is_loaded:
            # Return neutral prediction
            return np.full((len(X), 2), 0.5)
        
        results = []
        for row in X:
            # Interpret first 20 values as prices
            prices = row[:self.window_size] if len(row) >= self.window_size else row
            state = self.prepare_state(prices)
            
            if state is None:
                results.append([0.5, 0.5])
                continue
            
            try:
                decision = self.agent.get_trading_decision(state)
                # Convert BUY/SELL/HOLD to probability
                # P(up) = P(BUY), P(down) = P(SELL)
                probs = decision['probabilities']
                p_up = probs.get('BUY', 0.33)
                p_down = probs.get('SELL', 0.33)
                
                # Normalize
                total = p_up + p_down
                if total > 0:
                    p_up /= total
                    p_down /= total
                else:
                    p_up = p_down = 0.5
                
                results.append([p_down, p_up])
            except:
                results.append([0.5, 0.5])
        
        return np.array(results)
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return class predictions (0=down, 1=up)"""
        proba = self.predict_proba(X)
        return (proba[:, 1] > 0.5).astype(int)
    
    def get_signal(self, prices: np.ndarray) -> Dict[str, Any]:
        """Get trading signal for single price sequence"""
        if not self.is_loaded:
            return {"signal": "HOLD", "confidence": 0.0, "source": "default"}
        
        state = self.prepare_state(prices)
        if state is None:
            return {"signal": "HOLD", "confidence": 0.0, "source": "error"}
        
        decision = self.agent.get_trading_decision(state)
        return {
            "signal": decision["action"],
            "confidence": decision["confidence"],
            "q_values": decision["q_values"],
            "probabilities": decision["probabilities"],
            "source": "dqn"
        }


class UnifiedEnsemble:
    """
    Unified ensemble combining:
    - DQN (Reinforcement Learning)
    - Gradient Boosting
    - LSTM Neural Network
    """
    
    def __init__(self, weights: Dict[str, float] = None):
        """
        Args:
            weights: Model weights for voting (default: equal)
        """
        self.weights = weights or {
            "dqn": 0.4,
            "gradient_boosting": 0.35,
            "lstm": 0.25
        }
        
        self.dqn_adapter = None
        self.gb_model = None
        self.lstm_model = None
        self.models_loaded = {}
        
        self._load_models()
    
    def _load_models(self):
        """Load all available models"""
        # Load DQN
        try:
            self.dqn_adapter = DQNEnsembleAdapter()
            self.models_loaded["dqn"] = self.dqn_adapter.is_loaded
        except Exception as e:
            self.models_loaded["dqn"] = False
        
        # Load Gradient Boosting
        try:
            from ml_strategy_predictor import MLStrategyPredictor
            self.gb_model = MLStrategyPredictor()
            self.models_loaded["gradient_boosting"] = self.gb_model.is_trained
        except Exception as e:
            self.models_loaded["gradient_boosting"] = False
        
        # Load LSTM
        try:
            from neural_strategy_predictor import EnsemblePredictor
            self.lstm_model = EnsemblePredictor()
            self.models_loaded["lstm"] = True
        except Exception as e:
            self.models_loaded["lstm"] = False
    
    def predict(self, prices: np.ndarray, strategy_params: Dict = None) -> Dict[str, Any]:
        """
        Get ensemble prediction from all models
        
        Args:
            prices: Recent price array
            strategy_params: Optional strategy parameters for GB/LSTM
            
        Returns:
            Ensemble prediction with breakdown
        """
        predictions = {}
        confidences = {}
        
        # DQN prediction
        if self.models_loaded.get("dqn"):
            dqn_signal = self.dqn_adapter.get_signal(prices)
            predictions["dqn"] = dqn_signal["signal"]
            confidences["dqn"] = dqn_signal["confidence"]
        
        # Gradient Boosting prediction
        if self.models_loaded.get("gradient_boosting") and strategy_params:
            try:
                gb_score = self.gb_model.predict_score(strategy_params)
                predictions["gradient_boosting"] = "BUY" if gb_score > 0.55 else "SELL" if gb_score < 0.45 else "HOLD"
                confidences["gradient_boosting"] = abs(gb_score - 0.5) * 2
            except:
                pass
        
        # LSTM prediction
        if self.models_loaded.get("lstm") and strategy_params:
            try:
                lstm_preds = self.lstm_model.predict_score(strategy_params)
                lstm_score = lstm_preds.get("weighted", 0.5)
                predictions["lstm"] = "BUY" if lstm_score > 0.55 else "SELL" if lstm_score < 0.45 else "HOLD"
                confidences["lstm"] = abs(lstm_score - 0.5) * 2
            except:
                pass
        
        # Weighted voting
        votes = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        total_weight = 0.0
        
        for model, signal in predictions.items():
            weight = self.weights.get(model, 0.33)
            confidence = confidences.get(model, 0.5)
            weighted_vote = weight * confidence
            votes[signal] += weighted_vote
            total_weight += weighted_vote
        
        # Normalize
        if total_weight > 0:
            for k in votes:
                votes[k] /= total_weight
        
        # Final signal
        final_signal = max(votes, key=votes.get)
        final_confidence = votes[final_signal]
        
        return {
            "signal": final_signal,
            "confidence": final_confidence,
            "votes": votes,
            "predictions": predictions,
            "confidences": confidences,
            "models_active": sum(self.models_loaded.values())
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get ensemble status"""
        return {
            "models_loaded": self.models_loaded,
            "weights": self.weights,
            "active_models": sum(self.models_loaded.values())
        }


if __name__ == "__main__":
    ensemble = UnifiedEnsemble()
    print(f"Status: {ensemble.get_status()}")
    
    # Test
    prices = np.random.uniform(3000, 3500, 30)
    result = ensemble.predict(prices)
    print(f"Prediction: {result}")
