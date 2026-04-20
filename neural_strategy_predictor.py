#!/usr/bin/env python3
"""
Neural Network Strategy Predictor - LSTM-based deep learning
Learns temporal patterns in strategy performance for smarter predictions
"""

import os
import sqlite3
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

# Check for PyTorch availability
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    print("⚠️ PyTorch not installed. Run: pip install torch")


class StrategyLSTM(nn.Module):
    """LSTM Neural Network for strategy score prediction"""
    
    def __init__(self, input_size: int = 8, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super(StrategyLSTM, self).__init__()
        
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0
        )
        
        # Fully connected layers
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )
    
    def forward(self, x):
        # LSTM forward
        lstm_out, _ = self.lstm(x)
        
        # Take only the last output
        last_output = lstm_out[:, -1, :]
        
        # Fully connected
        out = self.fc(last_output)
        return out


class NeuralStrategyPredictor:
    """
    LSTM-based Neural Network for strategy prediction.
    Learns from sequences of historical strategies to predict performance.
    """
    
    def __init__(self, db_path: str = None, model_path: str = None):
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        self.db_path = db_path or (log_dir / "learning.db")
        self.model_path = model_path or (log_dir / "neural_model.pt")
        
        self.model = None
        self.scaler_mean = None
        self.scaler_std = None
        self.is_trained = False
        self.min_samples = 50  # Need more data for neural networks
        self.sequence_length = 5  # Use last 5 strategies as context
        
        self.feature_names = [
            'ml_threshold', 'risk_per_trade', 'tp_min', 'tp_max', 
            'stop_floor', 'max_trades_per_day'
        ]
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Try to load existing model
        self._load_model()
    
    def _extract_features(self, strategy: Dict[str, Any]) -> np.ndarray:
        """Extract feature vector from strategy parameters"""
        features = []
        for name in self.feature_names:
            value = strategy.get(name, 0)
            features.append(float(value) if value is not None else 0.0)
        
        # Add derived features
        features.append(strategy.get('tp_max', 0) - strategy.get('tp_min', 0))  # TP range
        features.append(strategy.get('risk_per_trade', 0) / max(strategy.get('stop_floor', 0.001), 0.001))  # Risk ratio
        
        return np.array(features, dtype=np.float32)
    
    def _normalize(self, data: np.ndarray, fit: bool = False) -> np.ndarray:
        """Normalize data using z-score"""
        if fit:
            self.scaler_mean = np.mean(data, axis=0)
            self.scaler_std = np.std(data, axis=0) + 1e-8
        
        if self.scaler_mean is None:
            return data
        
        return (data - self.scaler_mean) / self.scaler_std
    
    def _load_training_data(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Load and prepare sequential training data"""
        if not Path(self.db_path).exists():
            return None, None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, 
                       max_trades_per_day, score
                FROM strategies
                WHERE score IS NOT NULL AND score > 0
                ORDER BY timestamp ASC
                LIMIT 1000
            """)
            rows = cursor.fetchall()
        except Exception as e:
            print(f"Error loading training data: {e}")
            conn.close()
            return None, None
        
        conn.close()
        
        if len(rows) < self.min_samples:
            print(f"Not enough data for neural training ({len(rows)}/{self.min_samples})")
            return None, None
        
        # Extract features and scores
        all_features = []
        all_scores = []
        
        for row in rows:
            strategy = {
                'ml_threshold': row[0],
                'risk_per_trade': row[1],
                'tp_min': row[2],
                'tp_max': row[3],
                'stop_floor': row[4],
                'max_trades_per_day': row[5]
            }
            features = self._extract_features(strategy)
            all_features.append(features)
            all_scores.append(row[6])
        
        all_features = np.array(all_features)
        all_scores = np.array(all_scores, dtype=np.float32)
        
        # Create sequences
        X_sequences = []
        y_targets = []
        
        for i in range(len(all_features) - self.sequence_length):
            seq = all_features[i:i + self.sequence_length]
            target = all_scores[i + self.sequence_length]
            X_sequences.append(seq)
            y_targets.append(target)
        
        return np.array(X_sequences), np.array(y_targets)
    
    def train(self, epochs: int = 100, learning_rate: float = 0.001) -> bool:
        """Train the LSTM model on historical data"""
        if not PYTORCH_AVAILABLE:
            print("⚠️ Cannot train - PyTorch not installed")
            return False
        
        X, y = self._load_training_data()
        
        if X is None or y is None:
            return False
        
        print(f"🧠 Training LSTM Neural Network on {len(X)} sequences...")
        
        # Normalize features
        X_flat = X.reshape(-1, X.shape[-1])
        X_normalized = self._normalize(X_flat, fit=True)
        X = X_normalized.reshape(X.shape)
        
        # Normalize targets
        y_mean = np.mean(y)
        y_std = np.std(y) + 1e-8
        y_normalized = (y - y_mean) / y_std
        
        # Store for denormalization
        self.y_mean = y_mean
        self.y_std = y_std
        
        # Split data
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y_normalized[:split_idx], y_normalized[split_idx:]
        
        # Convert to tensors
        X_train_t = torch.FloatTensor(X_train).to(self.device)
        y_train_t = torch.FloatTensor(y_train).unsqueeze(1).to(self.device)
        X_test_t = torch.FloatTensor(X_test).to(self.device)
        y_test_t = torch.FloatTensor(y_test).unsqueeze(1).to(self.device)
        
        # Create model
        input_size = X.shape[-1]
        self.model = StrategyLSTM(input_size=input_size).to(self.device)
        
        criterion = nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        
        # Training loop
        best_loss = float('inf')
        patience_counter = 0
        patience = 15
        
        for epoch in range(epochs):
            self.model.train()
            optimizer.zero_grad()
            
            outputs = self.model(X_train_t)
            loss = criterion(outputs, y_train_t)
            
            loss.backward()
            optimizer.step()
            
            # Validation
            self.model.eval()
            with torch.no_grad():
                val_outputs = self.model(X_test_t)
                val_loss = criterion(val_outputs, y_test_t)
            
            if val_loss < best_loss:
                best_loss = val_loss
                patience_counter = 0
            else:
                patience_counter += 1
            
            if patience_counter >= patience:
                print(f"   Early stopping at epoch {epoch}")
                break
            
            if (epoch + 1) % 20 == 0:
                print(f"   Epoch {epoch+1}/{epochs}, Train Loss: {loss.item():.4f}, Val Loss: {val_loss.item():.4f}")
        
        # Final evaluation
        self.model.eval()
        with torch.no_grad():
            train_pred = self.model(X_train_t).cpu().numpy().flatten()
            test_pred = self.model(X_test_t).cpu().numpy().flatten()
            
            # R² score (approximate)
            train_r2 = 1 - np.sum((y_train - train_pred)**2) / np.sum((y_train - np.mean(y_train))**2)
            test_r2 = 1 - np.sum((y_test - test_pred)**2) / np.sum((y_test - np.mean(y_test))**2)
        
        print(f"✅ LSTM trained! R² Train: {train_r2:.3f}, Test: {test_r2:.3f}")
        
        self.is_trained = True
        self._save_model()
        
        return True
    
    def predict_score(self, strategy: Dict[str, Any], context: List[Dict[str, Any]] = None) -> float:
        """
        Predict the score for a strategy.
        If context is provided, uses it for sequential prediction.
        """
        if not self.is_trained or self.model is None:
            return 0.0
        
        try:
            # Extract current strategy features
            current_features = self._extract_features(strategy)
            
            # Build sequence (use context or pad with current)
            if context and len(context) >= self.sequence_length - 1:
                sequence = []
                for ctx in context[-(self.sequence_length - 1):]:
                    sequence.append(self._extract_features(ctx))
                sequence.append(current_features)
            else:
                # Pad with current strategy if no context
                sequence = [current_features] * self.sequence_length
            
            sequence = np.array(sequence, dtype=np.float32)
            
            # Normalize
            if self.scaler_mean is not None:
                sequence = (sequence - self.scaler_mean) / self.scaler_std
            
            # Predict
            self.model.eval()
            with torch.no_grad():
                x = torch.FloatTensor(sequence).unsqueeze(0).to(self.device)
                pred = self.model(x).cpu().numpy()[0, 0]
            
            # Denormalize
            predicted_score = pred * self.y_std + self.y_mean
            
            return max(0, float(predicted_score))
            
        except Exception as e:
            print(f"Neural prediction error: {e}")
            return 0.0
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the trained model"""
        if not self.is_trained:
            return {"status": "not_trained"}
        
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        
        return {
            "status": "trained",
            "model_type": "LSTM",
            "total_parameters": total_params,
            "trainable_parameters": trainable_params,
            "sequence_length": self.sequence_length,
            "device": str(self.device)
        }
    
    def _save_model(self):
        """Save trained model to disk"""
        if self.model is None:
            return
        
        data = {
            'model_state': self.model.state_dict(),
            'scaler_mean': self.scaler_mean,
            'scaler_std': self.scaler_std,
            'y_mean': getattr(self, 'y_mean', 0),
            'y_std': getattr(self, 'y_std', 1),
            'is_trained': self.is_trained,
            'timestamp': datetime.now().isoformat()
        }
        
        torch.save(data, self.model_path)
        print(f"💾 Neural model saved to {self.model_path}")
    
    def _load_model(self):
        """Load model from disk if exists"""
        if not Path(self.model_path).exists():
            return
        
        if not PYTORCH_AVAILABLE:
            return
        
        try:
            data = torch.load(self.model_path, map_location=self.device, weights_only=False)
            
            self.scaler_mean = data['scaler_mean']
            self.scaler_std = data['scaler_std']
            self.y_mean = data.get('y_mean', 0)
            self.y_std = data.get('y_std', 1)
            self.is_trained = data['is_trained']
            
            # Recreate model architecture
            input_size = len(self.scaler_mean) if self.scaler_mean is not None else 8
            self.model = StrategyLSTM(input_size=input_size).to(self.device)
            self.model.load_state_dict(data['model_state'])
            self.model.eval()
            
            print(f"📂 Loaded Neural model from {data.get('timestamp', 'unknown')}")
        except Exception as e:
            print(f"Could not load neural model: {e}")


class EnsemblePredictor:
    """
    Ensemble of Gradient Boosting + LSTM for robust predictions.
    Uses both models and combines their predictions.
    """
    
    def __init__(self, db_path: str = None):
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        self.db_path = db_path or (log_dir / "learning.db")
        
        # Import gradient boosting predictor
        try:
            from ml_strategy_predictor import MLStrategyPredictor
            self.gb_predictor = MLStrategyPredictor(db_path=str(self.db_path))
        except:
            self.gb_predictor = None
        
        # Neural predictor
        self.neural_predictor = NeuralStrategyPredictor(db_path=str(self.db_path))
        
        # Ensemble weights (can be tuned)
        self.gb_weight = 0.4
        self.neural_weight = 0.6
    
    def train_all(self) -> Dict[str, bool]:
        """Train all models"""
        results = {}
        
        if self.gb_predictor:
            print("\n📊 Training Gradient Boosting...")
            results['gradient_boosting'] = self.gb_predictor.train()
        
        print("\n🧠 Training LSTM Neural Network...")
        results['lstm'] = self.neural_predictor.train()
        
        return results
    
    def predict_score(self, strategy: Dict[str, Any]) -> Dict[str, float]:
        """Get predictions from all models"""
        predictions = {}
        
        if self.gb_predictor and self.gb_predictor.is_trained:
            predictions['gradient_boosting'] = self.gb_predictor.predict_score(strategy)
        
        if self.neural_predictor.is_trained:
            predictions['lstm'] = self.neural_predictor.predict_score(strategy)
        
        # Ensemble prediction
        if predictions:
            weights = []
            scores = []
            
            if 'gradient_boosting' in predictions:
                scores.append(predictions['gradient_boosting'])
                weights.append(self.gb_weight)
            
            if 'lstm' in predictions:
                scores.append(predictions['lstm'])
                weights.append(self.neural_weight)
            
            # Weighted average
            total_weight = sum(weights)
            ensemble = sum(s * w for s, w in zip(scores, weights)) / total_weight
            predictions['ensemble'] = ensemble
        
        return predictions


# CLI for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Neural Strategy Predictor')
    parser.add_argument('--train', action='store_true', help='Train the LSTM model')
    parser.add_argument('--ensemble', action='store_true', help='Train ensemble (GB + LSTM)')
    parser.add_argument('--info', action='store_true', help='Show model info')
    args = parser.parse_args()
    
    if args.ensemble:
        ensemble = EnsemblePredictor()
        results = ensemble.train_all()
        print(f"\n📊 Training Results: {results}")
        
        # Test prediction
        test_strategy = {
            'ml_threshold': 0.55,
            'risk_per_trade': 0.008,
            'tp_min': 0.010,
            'tp_max': 0.020,
            'stop_floor': 0.008,
            'max_trades_per_day': 15
        }
        predictions = ensemble.predict_score(test_strategy)
        print("\n🎯 Test Predictions:")
        for model, score in predictions.items():
            print(f"   {model}: {score:.2f}")
    
    elif args.train:
        predictor = NeuralStrategyPredictor()
        predictor.train()
    
    elif args.info:
        predictor = NeuralStrategyPredictor()
        info = predictor.get_model_info()
        print("\n📊 Model Info:")
        for k, v in info.items():
            print(f"   {k}: {v}")
