#!/usr/bin/env python3
"""
ML Strategy Predictor - Machine Learning based strategy optimization
Uses Random Forest to predict strategy performance before backtesting
"""

import os
import sqlite3
import numpy as np
import pickle
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Check for sklearn availability
try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ scikit-learn not installed. Run: pip install scikit-learn")


class MLStrategyPredictor:
    """
    Machine Learning based strategy score predictor.
    Learns from historical backtest results to predict which strategies
    are likely to perform well, enabling smart prioritization.
    """
    
    def __init__(self, db_path: str = None, model_path: str = None):
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        self.db_path = db_path or (log_dir / "learning.db")
        self.model_path = model_path or (log_dir / "ml_model.pkl")
        
        self.model = None
        self.scaler = None
        self.is_trained = False
        self.min_samples = 30  # Minimum samples needed for training
        
        self.feature_names = [
            'ml_threshold', 'risk_per_trade', 'tp_min', 'tp_max', 
            'stop_floor', 'max_trades_per_day'
        ]
        
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
        
        return np.array(features).reshape(1, -1)
    
    def _load_training_data(self) -> tuple:
        """Load historical strategies from PostgreSQL (preferred) or SQLite fallback."""
        
        # Try PostgreSQL first (has 9000+ strategies on Railway)
        try:
            import learning_store
            strategies = learning_store.get_all_strategies(limit=1000)
            if strategies and len(strategies) >= self.min_samples:
                X = []
                y = []
                for s in strategies:
                    params = s.get("params", {})
                    if not params:
                        continue
                    features = self._extract_features(params).flatten()
                    X.append(features)
                    y.append(s.get("score", 0))
                if len(X) >= self.min_samples:
                    print(f"📊 GB training data: {len(X)} strategies from PostgreSQL")
                    return np.array(X), np.array(y)
        except Exception as e:
            print(f"⚠️ PG load failed, falling back to SQLite: {e}")
        
        # Fallback: SQLite
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
                ORDER BY timestamp DESC
                LIMIT 1000
            """)
            rows = cursor.fetchall()
        except Exception as e:
            print(f"Error loading training data: {e}")
            conn.close()
            return None, None
        
        conn.close()
        
        if len(rows) < self.min_samples:
            print(f"Not enough data for training ({len(rows)}/{self.min_samples})")
            return None, None
        
        X = []
        y = []
        
        for row in rows:
            strategy = {
                'ml_threshold': row[0],
                'risk_per_trade': row[1],
                'tp_min': row[2],
                'tp_max': row[3],
                'stop_floor': row[4],
                'max_trades_per_day': row[5]
            }
            features = self._extract_features(strategy).flatten()
            X.append(features)
            y.append(row[6])  # score
        
        return np.array(X), np.array(y)
    
    def train(self, force: bool = False) -> bool:
        """Train the ML model on historical data"""
        if not SKLEARN_AVAILABLE:
            print("⚠️ Cannot train - scikit-learn not installed")
            return False
        
        X, y = self._load_training_data()
        
        if X is None or y is None:
            return False
        
        print(f"🧠 Training ML model on {len(X)} samples...")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train ensemble model
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        train_score = self.model.score(X_train_scaled, y_train)
        test_score = self.model.score(X_test_scaled, y_test)
        
        print(f"✅ Model trained! R² Train: {train_score:.3f}, Test: {test_score:.3f}")
        
        self.is_trained = True
        self._save_model()
        
        return True
    
    def predict_score(self, strategy: Dict[str, Any]) -> float:
        """Predict the score for a strategy"""
        if not self.is_trained or self.model is None:
            return 0.0
        
        try:
            features = self._extract_features(strategy)
            features_scaled = self.scaler.transform(features)
            predicted = self.model.predict(features_scaled)[0]
            return max(0, predicted)  # Scores can't be negative
        except Exception as e:
            print(f"Prediction error: {e}")
            return 0.0
    
    def should_test(self, strategy: Dict[str, Any], threshold_percentile: float = 50) -> bool:
        """
        Determine if a strategy is promising enough to test.
        Only tests strategies predicted to score above the threshold percentile.
        """
        if not self.is_trained:
            return True  # If not trained, test everything
        
        predicted_score = self.predict_score(strategy)
        
        # Get historical score distribution
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT score FROM strategies ORDER BY score")
        scores = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
        
        if not scores:
            return True
        
        threshold = np.percentile(scores, threshold_percentile)
        return predicted_score >= threshold
    
    def rank_strategies(self, strategies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank strategies by predicted score (best first)"""
        if not self.is_trained:
            return strategies
        
        scored = []
        for strategy in strategies:
            predicted = self.predict_score(strategy)
            scored.append({
                'strategy': strategy,
                'predicted_score': predicted
            })
        
        scored.sort(key=lambda x: x['predicted_score'], reverse=True)
        return [s['strategy'] for s in scored]
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from trained model"""
        if not self.is_trained or self.model is None:
            return {}
        
        extended_names = self.feature_names + ['tp_range', 'risk_ratio']
        importances = self.model.feature_importances_
        
        return dict(zip(extended_names, importances))
    
    def _save_model(self):
        """Save trained model to disk"""
        if self.model is None:
            return
        
        data = {
            'model': self.model,
            'scaler': self.scaler,
            'is_trained': self.is_trained,
            'timestamp': datetime.now().isoformat()
        }
        
        with open(self.model_path, 'wb') as f:
            pickle.dump(data, f)
        print(f"💾 Model saved to {self.model_path}")
    
    def _load_model(self):
        """Load model from disk if exists"""
        if not Path(self.model_path).exists():
            return
        
        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)
            
            self.model = data['model']
            self.scaler = data['scaler']
            self.is_trained = data['is_trained']
            print(f"📂 Loaded ML model from {data.get('timestamp', 'unknown')}")
        except Exception as e:
            print(f"Could not load model: {e}")


# CLI for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='ML Strategy Predictor')
    parser.add_argument('--train', action='store_true', help='Train the model')
    parser.add_argument('--predict', type=str, help='Predict score for strategy JSON')
    parser.add_argument('--importance', action='store_true', help='Show feature importance')
    args = parser.parse_args()
    
    predictor = MLStrategyPredictor()
    
    if args.train:
        predictor.train()
    
    if args.importance:
        importance = predictor.get_feature_importance()
        if importance:
            print("\n📊 Feature Importance:")
            for name, imp in sorted(importance.items(), key=lambda x: x[1], reverse=True):
                print(f"  {name}: {imp:.4f}")
    
    if args.predict:
        import json
        strategy = json.loads(args.predict)
        score = predictor.predict_score(strategy)
        print(f"Predicted score: {score:.2f}")
