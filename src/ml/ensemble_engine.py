"""
Enhanced ML Engine with Ensemble Models
Combines SGD, Random Forest, and XGBoost for better predictions
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional
from sklearn.linear_model import SGDClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EnsembleMLEngine:
    """Ensemble ML engine combining multiple models"""
    
    def __init__(self):
        self.config = get_config()
        self.ml_warm = False
        self.ml_classes = np.array([0, 1])
        self.ml_conf_boost = 0.0
        
        # Scaler for features
        self.scaler = StandardScaler(with_mean=True)
        
        # Model 1: SGD (fast online learning)
        self.sgd = SGDClassifier(
            loss=self.config.ml.loss,
            alpha=self.config.ml.alpha,
            max_iter=self.config.ml.max_iter,
            tol=self.config.ml.tol
        )
        
        # Model 2: Random Forest (non-linear, robust)
        self.rf = RandomForestClassifier(
            n_estimators=50,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1
        )
        
        # Model 3: XGBoost (high accuracy)
        try:
            from xgboost import XGBClassifier
            self.xgb = XGBClassifier(
                n_estimators=50,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                n_jobs=-1,
                verbosity=0
            )
            self.has_xgb = True
        except ImportError:
            logger.warning("XGBoost not available, using SGD + RF only")
            self.xgb = None
            self.has_xgb = False
        
        # Model weights (SGD, RF, XGB)
        if self.has_xgb:
            self.weights = np.array([0.3, 0.4, 0.3])
        else:
            self.weights = np.array([0.5, 0.5, 0.0])
        
        # Training counters
        self.samples_seen = 0
        self.retrain_interval = 1000
    
    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add engineered features to improve predictions
        
        Args:
            df: DataFrame with basic indicators
            
        Returns:
            DataFrame with additional features
        """
        df_eng = df.copy()
        
        # Momentum features
        df_eng['rsi_change'] = df_eng['rsi14'].diff(5)
        df_eng['macd_momentum'] = df_eng['macd'] - df_eng['macd_sig']
        
        # Volume features (if available)
        if 'volume' in df_eng.columns:
            df_eng['volume_ratio'] = df_eng['volume'] / df_eng['volume'].rolling(20).mean()
        else:
            df_eng['volume_ratio'] = 1.0
        
        # Volatility features
        df_eng['atr_pct'] = df_eng['atr'] / df_eng['close']
        df_eng['bb_width'] = (df_eng['bb_hi'] - df_eng['bb_lo']) / df_eng['close']
        
        # Trend features
        df_eng['ema_slope'] = df_eng['ema20'].diff(10) / df_eng['ema20'].shift(10)
        df_eng['trend_strength'] = (df_eng['ema20'] - df_eng['ema50']) / df_eng['close']
        
        # Price momentum
        df_eng['price_momentum'] = df_eng['close'].pct_change(10)
        
        # RSI extremes
        df_eng['rsi_extreme'] = ((df_eng['rsi14'] < 30) | (df_eng['rsi14'] > 70)).astype(int)
        
        return df_eng
    
    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare features and labels for ML training
        
        Args:
            df: DataFrame with technical indicators
            
        Returns:
            Tuple of (X features, y labels)
        """
        # Add engineered features
        df_eng = self._engineer_features(df)
        
        # Feature columns (basic + engineered)
        feature_cols = [
            # Basic indicators
            'ret1', 'ema20', 'ema50', 'macd', 'macd_sig',
            'rsi14', 'atr', 'bb_hi', 'bb_lo',
            # Engineered features
            'rsi_change', 'macd_momentum', 'volume_ratio',
            'atr_pct', 'bb_width', 'ema_slope', 'trend_strength',
            'price_momentum', 'rsi_extreme'
        ]
        
        X = df_eng[feature_cols].values
        
        # Create labels: 1 if future return > threshold, 0 otherwise
        future_return = df_eng['close'].pct_change().shift(-1)
        threshold = (df_eng['atr'] / df_eng['close']) * 0.2
        y = (future_return > threshold).astype(int).values
        
        # Remove last row (no future data)
        X = X[:-1]
        y = y[:-1]
        
        # Remove NaN rows
        mask = ~(np.isnan(X).any(axis=1) | np.isnan(y))
        X = X[mask]
        y = y[mask]
        
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
            
            # Scale features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train SGD
            self.sgd.fit(X_scaled, y)
            
            # Train Random Forest
            self.rf.fit(X_scaled, y)
            
            # Train XGBoost if available
            if self.has_xgb:
                self.xgb.fit(X_scaled, y)
            
            self.ml_warm = True
            self.samples_seen = X.shape[0]
            
            # Calculate confidence boost from recent accuracy
            recent_y = y[-500:] if len(y) >= 500 else y
            self.ml_conf_boost = float(np.mean(recent_y))
            
            logger.info(
                f"Ensemble trained on {X.shape[0]} samples | "
                f"Features: {X.shape[1]} | "
                f"Confidence: {self.ml_conf_boost:.3f}"
            )
            
        except Exception as e:
            logger.error(f"Ensemble training failed: {e}")
    
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
            X_scaled = self.scaler.transform(X_recent)
            
            # SGD: Online learning (partial_fit)
            self.sgd.partial_fit(X_scaled, y_recent)
            
            self.samples_seen += update_size
            
            # Retrain RF and XGB periodically
            if self.samples_seen >= self.retrain_interval:
                logger.info(f"Retraining RF/XGB after {self.samples_seen} samples")
                
                # Use more data for retraining
                retrain_size = min(2000, X.shape[0])
                X_retrain = X[-retrain_size:]
                y_retrain = y[-retrain_size:]
                X_retrain_scaled = self.scaler.transform(X_retrain)
                
                self.rf.fit(X_retrain_scaled, y_retrain)
                
                if self.has_xgb:
                    self.xgb.fit(X_retrain_scaled, y_retrain)
                
                self.samples_seen = 0
            
            # Update confidence boost
            recent_y = y[-500:] if len(y) >= 500 else y
            self.ml_conf_boost = float(np.mean(recent_y))
            
        except Exception as e:
            logger.warning(f"Ensemble online update failed: {e}")
    
    def predict(self, row: pd.Series) -> float:
        """
        Predict probability using ensemble
        
        Args:
            row: Series with technical indicators
            
        Returns:
            Ensemble probability (0.0 to 1.0)
        """
        if not self.ml_warm:
            return 0.5  # Neutral prediction
        
        try:
            # Engineer features for single row
            df_single = pd.DataFrame([row])
            df_eng = self._engineer_features(df_single)
            
            # Extract features
            feature_cols = [
                'ret1', 'ema20', 'ema50', 'macd', 'macd_sig',
                'rsi14', 'atr', 'bb_hi', 'bb_lo',
                'rsi_change', 'macd_momentum', 'volume_ratio',
                'atr_pct', 'bb_width', 'ema_slope', 'trend_strength',
                'price_momentum', 'rsi_extreme'
            ]
            
            features = df_eng[feature_cols].values
            
            # Scale features
            features_scaled = self.scaler.transform(features)
            
            # Get predictions from each model
            pred_sgd = self.sgd.predict_proba(features_scaled)[0, 1]
            pred_rf = self.rf.predict_proba(features_scaled)[0, 1]
            
            if self.has_xgb:
                pred_xgb = self.xgb.predict_proba(features_scaled)[0, 1]
            else:
                pred_xgb = 0.5
            
            # Weighted ensemble
            ensemble_pred = (
                self.weights[0] * pred_sgd +
                self.weights[1] * pred_rf +
                self.weights[2] * pred_xgb
            )
            
            return float(ensemble_pred)
            
        except Exception as e:
            logger.warning(f"Ensemble prediction failed: {e}")
            return 0.5
    
    def get_confidence_boost(self) -> float:
        """Get current confidence boost value"""
        return self.ml_conf_boost
    
    def is_warm(self) -> bool:
        """Check if models are trained and ready"""
        return self.ml_warm
    
    def get_model_info(self) -> dict:
        """Get information about ensemble models"""
        return {
            'warm': self.ml_warm,
            'samples_seen': self.samples_seen,
            'has_xgb': self.has_xgb,
            'weights': self.weights.tolist(),
            'confidence_boost': self.ml_conf_boost
        }
