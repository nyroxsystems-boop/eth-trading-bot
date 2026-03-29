"""
Machine Learning Engine Module
Handles ML model training, prediction, and online learning
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MLEngine:
    """Machine learning engine for trade predictions"""
    
    def __init__(self):
        self.config = get_config()
        self.ml_warm = False
        self.ml_classes = np.array([0, 1])
        self.ml_conf_boost = 0.0
        
        # Create ML pipeline
        self.clf = Pipeline([
            ("scaler", StandardScaler(with_mean=True)),
            ("sgd", SGDClassifier(
                loss=self.config.ml.loss,
                alpha=self.config.ml.alpha,
                max_iter=self.config.ml.max_iter,
                tol=self.config.ml.tol
            ))
        ])
    
    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare features and labels for ML training
        
        Args:
            df: DataFrame with technical indicators
            
        Returns:
            Tuple of (X features, y labels)
        """
        # Feature columns
        feature_cols = [
            "ret1", "ema20", "ema50", "macd", "macd_sig",
            "rsi14", "atr", "bb_hi", "bb_lo"
        ]
        
        X = df[feature_cols].values
        
        # Create labels: 1 if future return > threshold, 0 otherwise
        future_return = df["close"].pct_change().shift(-1)
        threshold = (df["atr"] / df["close"]) * 0.2
        y = (future_return > threshold).astype(int).values
        
        # Remove last row (no future data)
        X = X[:-1]
        y = y[:-1]
        
        return X, y
    
    def train_initial(self, df: pd.DataFrame):
        """
        Perform initial model training
        
        Args:
            df: DataFrame with technical indicators
        """
        try:
            X, y = self.prepare_features(df)
            
            if X.shape[0] < self.config.ml.min_samples:
                logger.warning(
                    f"Insufficient data for training: {X.shape[0]} < {self.config.ml.min_samples}"
                )
                return
            
            # Initial fit on first portion
            initial_size = min(500, X.shape[0] // 2)
            self.clf.fit(X[:initial_size], y[:initial_size])
            
            # Partial fit on remaining data
            if X.shape[0] > initial_size:
                self.clf.named_steps["sgd"].partial_fit(
                    self.clf.named_steps["scaler"].transform(X[initial_size:]),
                    y[initial_size:],
                    classes=self.ml_classes
                )
            
            self.ml_warm = True
            
            # Calculate confidence boost from recent accuracy
            recent_y = y[-500:] if len(y) >= 500 else y
            self.ml_conf_boost = float(np.mean(recent_y))
            
            logger.info(
                f"ML model trained on {X.shape[0]} samples, "
                f"confidence boost: {self.ml_conf_boost:.3f}"
            )
            
        except Exception as e:
            logger.error(f"ML training failed: {e}")
    
    def update_online(self, df: pd.DataFrame):
        """
        Perform online learning update
        
        Args:
            df: DataFrame with technical indicators
        """
        try:
            X, y = self.prepare_features(df)
            
            if X.shape[0] < self.config.ml.min_samples:
                return
            
            if not self.ml_warm:
                # First time - do initial training
                self.train_initial(df)
                return
            
            # Online update with recent data
            update_size = min(200, X.shape[0])
            X_recent = X[-update_size:]
            y_recent = y[-update_size:]
            
            # Transform features using existing scaler
            X_scaled = self.clf.named_steps["scaler"].transform(X_recent)
            
            # Partial fit
            self.clf.named_steps["sgd"].partial_fit(X_scaled, y_recent)
            
            # Update confidence boost
            recent_y = y[-500:] if len(y) >= 500 else y
            self.ml_conf_boost = float(np.mean(recent_y))
            
        except Exception as e:
            logger.warning(f"ML online update failed: {e}")
    
    def predict(self, row: pd.Series) -> float:
        """
        Predict probability for a single data point.
        
        If config.ml.threshold > 0 (set via Strategy Lab's mlThreshold),
        predictions below the threshold are clamped to 0.5 (neutral).
        
        Args:
            row: Series with technical indicators
            
        Returns:
            Probability of positive class (0.0 to 1.0)
        """
        if not self.ml_warm:
            return 0.5  # Neutral prediction
        
        try:
            # Extract features
            features = np.array([[
                row["ret1"], row["ema20"], row["ema50"],
                row["macd"], row["macd_sig"], row["rsi14"],
                row["atr"], row["bb_hi"], row["bb_lo"]
            ]])
            
            # Predict probability
            proba = self.clf.predict_proba(features)[0, 1]
            
            # Apply mlThreshold gate if configured (> 0 means active)
            threshold = getattr(self.config.ml, 'threshold', 0.0)
            if threshold > 0 and proba < threshold:
                logger.debug(f"ML prediction {proba:.3f} below threshold {threshold:.3f} → neutral")
                return 0.5
            
            return float(proba)
            
        except Exception as e:
            logger.warning(f"ML prediction failed: {e}")
            return 0.5
    
    def get_confidence_boost(self) -> float:
        """Get current confidence boost value"""
        return self.ml_conf_boost
    
    def is_warm(self) -> bool:
        """Check if model is trained and ready"""
        return self.ml_warm
