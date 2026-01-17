"""
ML Trading Engine - DQN Integration
Connects deep reinforcement learning agent to live trading decisions
"""
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.logger import get_logger

logger = get_logger(__name__)


class MLTradingEngine:
    """
    Integrates DQN agent with live trading decisions.
    Provides ML-enhanced signals for entry/exit decisions.
    """
    
    def __init__(self, use_dqn: bool = True, confidence_threshold: float = 0.6):
        """
        Initialize ML Trading Engine
        
        Args:
            use_dqn: Whether to use DQN for trading decisions
            confidence_threshold: Minimum confidence to act on DQN signal
        """
        self.use_dqn = use_dqn
        self.confidence_threshold = confidence_threshold
        self.dqn_agent = None
        self.is_loaded = False
        self.last_signal = None
        self.signal_history = []
        
        # Try to load DQN agent
        if use_dqn:
            self._load_dqn_agent()
    
    def _load_dqn_agent(self) -> bool:
        """Load trained DQN agent from disk"""
        try:
            from rl_trading_agent import DQNAgent, TradingEnvironment
            
            env = TradingEnvironment(window_size=20)
            self.dqn_agent = DQNAgent(state_size=env.state_size)
            
            if self.dqn_agent.is_trained:
                self.is_loaded = True
                logger.info(f"✅ DQN Agent loaded (epsilon={self.dqn_agent.epsilon:.4f})")
                return True
            else:
                logger.warning("DQN Agent not trained yet")
                return False
                
        except Exception as e:
            logger.error(f"Failed to load DQN Agent: {e}")
            self.is_loaded = False
            return False
    
    def prepare_state(self, df, window_size: int = 20) -> Optional[np.ndarray]:
        """
        Prepare state vector from market data DataFrame
        
        Args:
            df: DataFrame with OHLCV and indicators
            window_size: Number of candles for price window
            
        Returns:
            State vector for DQN agent or None on error
        """
        try:
            if len(df) < window_size:
                return None
            
            # Get recent prices
            prices = df['close'].values[-window_size:]
            
            # Normalize to returns
            returns = np.diff(prices) / prices[:-1]
            returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)
            
            # Technical features
            sma_5 = np.mean(prices[-5:])
            sma_20 = np.mean(prices)
            current_price = prices[-1]
            volatility = np.std(returns) if len(returns) > 0 else 0.0
            trend = (prices[-1] - prices[0]) / prices[0] if prices[0] != 0 else 0.0
            
            # Position info (assume no position for signal generation)
            has_position = 0.0
            unrealized_pnl = 0.0
            balance_ratio = 0.0
            position_value = 0.0
            
            # Combine features
            state = np.concatenate([
                returns,  # window_size - 1 features
                [sma_5 / current_price - 1],
                [sma_20 / current_price - 1],
                [volatility],
                [trend],
                [has_position],
                [unrealized_pnl],
                [balance_ratio],
                [position_value]
            ])
            
            return state.astype(np.float32)
            
        except Exception as e:
            logger.error(f"Failed to prepare state: {e}")
            return None
    
    def get_dqn_signal(self, df) -> Dict[str, Any]:
        """
        Get trading signal from DQN agent
        
        Args:
            df: DataFrame with market data
            
        Returns:
            Dict with signal, confidence, probabilities
        """
        if not self.use_dqn or not self.is_loaded:
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "source": "default",
                "reason": "DQN not available"
            }
        
        state = self.prepare_state(df)
        
        if state is None:
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "source": "default",
                "reason": "Failed to prepare state"
            }
        
        try:
            decision = self.dqn_agent.get_trading_decision(state)
            
            signal = {
                "signal": decision["action"],
                "confidence": decision["confidence"],
                "q_values": decision["q_values"],
                "probabilities": decision["probabilities"],
                "source": "dqn",
                "epsilon": self.dqn_agent.epsilon,
                "timestamp": datetime.now().isoformat()
            }
            
            self.last_signal = signal
            self.signal_history.append(signal)
            
            # Keep only last 100 signals
            if len(self.signal_history) > 100:
                self.signal_history = self.signal_history[-100:]
            
            return signal
            
        except Exception as e:
            logger.error(f"DQN prediction failed: {e}")
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "source": "error",
                "reason": str(e)
            }
    
    def should_override_signal(self, 
                              traditional_signal: str, 
                              dqn_signal: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if DQN signal should override traditional signal
        
        Args:
            traditional_signal: Signal from traditional strategy ("BUY", "SELL", "HOLD")
            dqn_signal: Signal dict from DQN agent
            
        Returns:
            Tuple of (should_override, reason)
        """
        if not self.use_dqn or not self.is_loaded:
            return False, "DQN not active"
        
        dqn_action = dqn_signal.get("signal", "HOLD")
        dqn_confidence = dqn_signal.get("confidence", 0.0)
        epsilon = dqn_signal.get("epsilon", 1.0)
        
        # Don't override if DQN still exploring (epsilon > 0.3)
        if epsilon > 0.3:
            return False, f"DQN still training (ε={epsilon:.3f})"
        
        # Check confidence threshold
        if dqn_confidence < self.confidence_threshold:
            return False, f"Low confidence ({dqn_confidence:.1%} < {self.confidence_threshold:.1%})"
        
        # If signals agree, no override needed
        if traditional_signal == dqn_action:
            return False, "Signals agree"
        
        # Override if DQN has high confidence and disagrees
        if dqn_confidence >= 0.7:
            logger.info(f"🤖 DQN Override: {traditional_signal} → {dqn_action} ({dqn_confidence:.1%})")
            return True, f"DQN high confidence ({dqn_confidence:.1%})"
        
        return False, "No strong disagreement"
    
    def get_combined_signal(self, df, traditional_signal: str) -> Dict[str, Any]:
        """
        Get final signal combining traditional strategy and DQN
        
        Args:
            df: Market data DataFrame
            traditional_signal: Signal from traditional strategy
            
        Returns:
            Combined signal with reasoning
        """
        dqn_signal = self.get_dqn_signal(df)
        
        should_override, reason = self.should_override_signal(traditional_signal, dqn_signal)
        
        if should_override:
            return {
                "signal": dqn_signal["signal"],
                "confidence": dqn_signal["confidence"],
                "source": "dqn_override",
                "traditional_signal": traditional_signal,
                "dqn_signal": dqn_signal["signal"],
                "reason": reason
            }
        else:
            return {
                "signal": traditional_signal,
                "confidence": dqn_signal.get("confidence", 0.5),
                "source": "traditional",
                "traditional_signal": traditional_signal,
                "dqn_signal": dqn_signal.get("signal", "N/A"),
                "reason": reason
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current engine status"""
        return {
            "use_dqn": self.use_dqn,
            "is_loaded": self.is_loaded,
            "confidence_threshold": self.confidence_threshold,
            "epsilon": self.dqn_agent.epsilon if self.dqn_agent else None,
            "signal_count": len(self.signal_history),
            "last_signal": self.last_signal
        }


# Quick test
if __name__ == "__main__":
    engine = MLTradingEngine(use_dqn=True)
    print(f"Status: {engine.get_status()}")
    
    # Test with dummy data
    import pandas as pd
    dummy_df = pd.DataFrame({
        'close': np.random.uniform(3000, 3500, 100),
        'high': np.random.uniform(3050, 3550, 100),
        'low': np.random.uniform(2950, 3450, 100),
    })
    
    signal = engine.get_dqn_signal(dummy_df)
    print(f"DQN Signal: {signal}")
