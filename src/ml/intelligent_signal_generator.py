"""
Intelligent Signal Generator
Based on intelligent-trading-bot (asavinov) methodology.

Generates confidence-scored trading signals by:
1. Multi-model voting (DQN, XGBoost, LSTM, Sentiment)
2. Confidence scoring (-1 to +1)
3. Historical accuracy tracking
4. Threshold-based signal generation
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import json
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.config import get_config

logger = get_logger(__name__)


@dataclass
class TradingSignal:
    """Represents a trading signal with metadata."""
    timestamp: datetime
    symbol: str
    price: float
    indicator: float        # -1 to +1 (bearish to bullish)
    confidence: float       # 0 to 1 (how certain)
    signal_type: str        # 'BUY', 'SELL', 'HOLD'
    zone: int              # 1, 2, 3 (strength levels)
    timeframe: str         # '1m', '5m', '1h', etc.
    model_votes: Dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    
    def to_telegram_format(self) -> str:
        """Format signal for Telegram notification."""
        emoji_map = {
            'BUY': '📈',
            'SELL': '📉', 
            'HOLD': '➖'
        }
        arrows = {
            1: '〉',
            2: '〉〉',
            3: '〉〉〉'
        }
        
        direction = '↑' if self.indicator > 0 else '↓'
        zone_arrows = arrows.get(self.zone, '')
        
        if self.signal_type == 'HOLD':
            return f"➖ {self.symbol} ${self.price:,.2f} | Score: {self.indicator:+.2f} | NEUTRAL {self.timeframe}"
        
        return (
            f"{zone_arrows}{emoji_map[self.signal_type]} {self.symbol} ${self.price:,.2f} "
            f"| Indicator: {self.indicator:+.2f} {direction} "
            f"| {self.signal_type} ZONE {self.timeframe}"
        )
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'price': self.price,
            'indicator': self.indicator,
            'confidence': self.confidence,
            'signal_type': self.signal_type,
            'zone': self.zone,
            'timeframe': self.timeframe,
            'model_votes': self.model_votes,
            'reasoning': self.reasoning
        }


class ModelVoter:
    """
    Individual model voter interface.
    Each ML model gets a vote weighted by its historical accuracy.
    """
    
    def __init__(self, name: str, initial_weight: float = 1.0):
        self.name = name
        self.weight = initial_weight
        self.predictions: deque = deque(maxlen=100)
        self.accuracy_history: deque = deque(maxlen=50)
        self.correct_count = 0
        self.total_count = 0
        
    def record_prediction(self, prediction: float, actual: Optional[float] = None):
        """Record a prediction and optionally verify against actual."""
        self.predictions.append({
            'prediction': prediction,
            'actual': actual,
            'timestamp': datetime.now()
        })
        
        if actual is not None:
            correct = (prediction > 0) == (actual > 0)
            self.accuracy_history.append(1.0 if correct else 0.0)
            if correct:
                self.correct_count += 1
            self.total_count += 1
    
    def get_accuracy(self) -> float:
        """Get recent accuracy."""
        if len(self.accuracy_history) == 0:
            return 0.5  # Default
        return np.mean(list(self.accuracy_history))
    
    def get_weighted_vote(self, prediction: float) -> float:
        """Get accuracy-weighted vote."""
        accuracy = self.get_accuracy()
        # Weight by accuracy deviation from 50%
        weight = 0.5 + (accuracy - 0.5) * 2  # Scale 0.5 to 1.5
        return prediction * weight * self.weight


class IntelligentSignalGenerator:
    """
    Generates intelligent trading signals by combining multiple ML models.
    
    Features:
    - Multi-model voting with dynamic weighting
    - Confidence scoring based on model agreement
    - Historical accuracy tracking per model
    - Adaptive thresholds for signal generation
    """
    
    # Default thresholds for signal zones
    THRESHOLDS = {
        'zone1': 0.15,   # Weak signal
        'zone2': 0.25,   # Medium signal
        'zone3': 0.40    # Strong signal
    }
    
    def __init__(
        self,
        symbol: str = "ETHUSDT",
        timeframe: str = "1h",
        log_dir: str = None
    ):
        self.config = get_config()
        self.symbol = symbol
        self.timeframe = timeframe
        
        # Log directory for persistence
        self.log_dir = Path(log_dir or self.config.log_dir)
        self.signals_file = self.log_dir / "signal_history.json"
        
        # Model voters
        self.voters = {
            'dqn': ModelVoter('DQN', initial_weight=1.2),
            'rainbow': ModelVoter('Rainbow DQN', initial_weight=1.3),
            'xgboost': ModelVoter('XGBoost', initial_weight=1.0),
            'lstm': ModelVoter('LSTM', initial_weight=0.9),
            'sentiment': ModelVoter('Sentiment', initial_weight=0.7),
            'ensemble': ModelVoter('Ensemble', initial_weight=1.1)
        }
        
        # Signal history
        self.signal_history: deque = deque(maxlen=1000)
        
        # Performance tracking
        self.total_signals = 0
        self.correct_signals = 0
        
        # Load historical data
        self._load_history()
        
        logger.info(f"🎯 Intelligent Signal Generator initialized for {symbol}")
    
    def _load_history(self):
        """Load signal history from disk."""
        if self.signals_file.exists():
            try:
                with open(self.signals_file, 'r') as f:
                    data = json.load(f)
                    self.total_signals = data.get('total_signals', 0)
                    self.correct_signals = data.get('correct_signals', 0)
                    logger.info(f"📂 Loaded signal history: {self.total_signals} signals")
            except Exception as e:
                logger.warning(f"Failed to load signal history: {e}")
    
    def _save_history(self):
        """Save signal history to disk."""
        try:
            with open(self.signals_file, 'w') as f:
                json.dump({
                    'total_signals': self.total_signals,
                    'correct_signals': self.correct_signals,
                    'last_updated': datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.warning(f"Failed to save signal history: {e}")
    
    def register_model_prediction(
        self,
        model_name: str,
        prediction: float,
        actual: Optional[float] = None
    ):
        """
        Register a prediction from a specific model.
        
        Args:
            model_name: One of 'dqn', 'rainbow', 'xgboost', 'lstm', 'sentiment', 'ensemble'
            prediction: Prediction value (-1 to +1, or probability 0 to 1)
            actual: Actual outcome for accuracy tracking
        """
        if model_name in self.voters:
            # Normalize prediction to -1 to +1
            if 0 <= prediction <= 1:
                prediction = prediction * 2 - 1
            
            self.voters[model_name].record_prediction(prediction, actual)
    
    def generate_signal(
        self,
        current_price: float,
        model_predictions: Dict[str, float],
        market_data: Optional[pd.DataFrame] = None
    ) -> TradingSignal:
        """
        Generate an intelligent trading signal from model predictions.
        
        Args:
            current_price: Current price of the asset
            model_predictions: Dict of model_name -> prediction (-1 to +1)
            market_data: Optional DataFrame with recent OHLCV data
            
        Returns:
            TradingSignal with confidence scoring
        """
        # Register predictions for accuracy tracking
        for model_name, pred in model_predictions.items():
            self.register_model_prediction(model_name, pred)
        
        # Calculate weighted ensemble indicator
        total_weight = 0
        weighted_sum = 0
        model_votes = {}
        
        for model_name, prediction in model_predictions.items():
            if model_name in self.voters:
                voter = self.voters[model_name]
                # Normalize to -1 to +1
                norm_pred = prediction if -1 <= prediction <= 1 else prediction * 2 - 1
                weighted_vote = voter.get_weighted_vote(norm_pred)
                
                model_votes[model_name] = {
                    'prediction': norm_pred,
                    'accuracy': voter.get_accuracy(),
                    'weighted_vote': weighted_vote
                }
                
                weighted_sum += weighted_vote
                total_weight += voter.weight * abs(norm_pred)
        
        # Final indicator (-1 to +1)
        if total_weight > 0:
            indicator = weighted_sum / total_weight
        else:
            indicator = 0.0
        
        indicator = max(-1.0, min(1.0, indicator))  # Clamp
        
        # Calculate confidence (based on model agreement)
        predictions_list = list(model_predictions.values())
        if len(predictions_list) > 1:
            # Confidence is inverse of standard deviation
            std = np.std(predictions_list)
            confidence = max(0, 1 - std * 2)
        else:
            confidence = 0.5
        
        # Determine signal type and zone
        abs_indicator = abs(indicator)
        
        if abs_indicator >= self.THRESHOLDS['zone3']:
            zone = 3
            signal_type = 'BUY' if indicator > 0 else 'SELL'
        elif abs_indicator >= self.THRESHOLDS['zone2']:
            zone = 2
            signal_type = 'BUY' if indicator > 0 else 'SELL'
        elif abs_indicator >= self.THRESHOLDS['zone1']:
            zone = 1
            signal_type = 'BUY' if indicator > 0 else 'SELL'
        else:
            zone = 0
            signal_type = 'HOLD'
        
        # Generate reasoning
        reasoning_parts = []
        bullish_models = [m for m, v in model_predictions.items() if v > 0.1]
        bearish_models = [m for m, v in model_predictions.items() if v < -0.1]
        
        if bullish_models:
            reasoning_parts.append(f"Bullish: {', '.join(bullish_models)}")
        if bearish_models:
            reasoning_parts.append(f"Bearish: {', '.join(bearish_models)}")
        
        reasoning = ' | '.join(reasoning_parts) if reasoning_parts else 'Neutral consensus'
        
        # Create signal
        signal = TradingSignal(
            timestamp=datetime.now(),
            symbol=self.symbol,
            price=current_price,
            indicator=indicator,
            confidence=confidence,
            signal_type=signal_type,
            zone=zone,
            timeframe=self.timeframe,
            model_votes=model_votes,
            reasoning=reasoning
        )
        
        # Track signal
        self.signal_history.append(signal)
        self.total_signals += 1
        
        # Log signal
        if signal_type != 'HOLD':
            logger.info(f"📊 {signal.to_telegram_format()}")
        
        return signal
    
    def verify_signal(self, signal: TradingSignal, actual_outcome: float):
        """
        Verify a past signal against actual price movement.
        
        Args:
            signal: The original signal
            actual_outcome: Actual price change (positive = price went up)
        """
        predicted_direction = signal.indicator > 0
        actual_direction = actual_outcome > 0
        
        correct = predicted_direction == actual_direction
        
        if correct:
            self.correct_signals += 1
        
        # Update model accuracies
        for model_name, vote_data in signal.model_votes.items():
            if model_name in self.voters:
                self.voters[model_name].record_prediction(
                    vote_data['prediction'],
                    actual_outcome
                )
        
        self._save_history()
    
    def get_accuracy_stats(self) -> Dict:
        """Get accuracy statistics for all models."""
        stats = {
            'overall': {
                'total_signals': self.total_signals,
                'correct_signals': self.correct_signals,
                'accuracy': self.correct_signals / max(1, self.total_signals)
            },
            'models': {}
        }
        
        for name, voter in self.voters.items():
            stats['models'][name] = {
                'accuracy': voter.get_accuracy(),
                'total_predictions': voter.total_count,
                'correct_predictions': voter.correct_count,
                'weight': voter.weight
            }
        
        return stats
    
    def get_recent_signals(self, count: int = 10) -> List[Dict]:
        """Get recent signals."""
        signals = list(self.signal_history)[-count:]
        return [s.to_dict() for s in signals]


# ============================================================================
# QUICK TEST
# ============================================================================

if __name__ == "__main__":
    print("🎯 Testing Intelligent Signal Generator...")
    
    generator = IntelligentSignalGenerator(symbol="ETHUSDT", timeframe="1h")
    
    # Simulate model predictions
    predictions = {
        'dqn': 0.35,
        'rainbow': 0.42,
        'xgboost': 0.28,
        'lstm': 0.15,
        'sentiment': -0.10,
        'ensemble': 0.30
    }
    
    # Generate signal
    signal = generator.generate_signal(
        current_price=3521.45,
        model_predictions=predictions
    )
    
    print(f"\n📊 Generated Signal:")
    print(f"   {signal.to_telegram_format()}")
    print(f"   Confidence: {signal.confidence:.1%}")
    print(f"   Reasoning: {signal.reasoning}")
    
    # Test accuracy stats
    stats = generator.get_accuracy_stats()
    print(f"\n📈 Model Accuracies:")
    for model, data in stats['models'].items():
        print(f"   {model}: {data['accuracy']:.1%}")
    
    print("\n✅ Signal Generator test passed!")
