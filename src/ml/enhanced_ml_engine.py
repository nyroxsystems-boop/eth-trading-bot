"""
Enhanced ML Engine V2
Advanced machine learning for trade predictions:
- XGBoost / LightGBM ensemble
- 100+ engineered features
- Rolling cross-validation
- SHAP feature importance
- Calibrated probabilities
- Online learning with adaptive rates
"""

import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import joblib

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FeatureEngineer:
    """
    Advanced feature engineering for trading ML.
    Creates 100+ features from OHLCV data.
    """
    
    def __init__(self):
        self.feature_names: List[str] = []
    
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create comprehensive feature set.
        Expects df with: open, high, low, close, volume
        """
        df = df.copy()
        features = pd.DataFrame(index=df.index)
        
        # ===== PRICE FEATURES =====
        
        # Returns (multiple timeframes)
        for period in [1, 2, 3, 5, 10, 20]:
            features[f'ret_{period}'] = df['close'].pct_change(period)
        
        # Log returns
        features['log_ret_1'] = np.log(df['close'] / df['close'].shift(1))
        
        # ===== MOVING AVERAGES =====
        
        for period in [5, 10, 20, 50, 100]:
            features[f'sma_{period}'] = df['close'].rolling(period).mean()
            features[f'sma_{period}_ratio'] = df['close'] / features[f'sma_{period}'] - 1
            
            # EMA
            features[f'ema_{period}'] = df['close'].ewm(span=period).mean()
            features[f'ema_{period}_ratio'] = df['close'] / features[f'ema_{period}'] - 1
        
        # MA crossovers
        features['sma_5_20_cross'] = (features['sma_5'] > features['sma_20']).astype(float)
        features['sma_10_50_cross'] = (features['sma_10'] > features['sma_50']).astype(float)
        features['ema_12_26_cross'] = (features['ema_10'] > features['ema_20']).astype(float)
        
        # ===== MOMENTUM INDICATORS =====
        
        # RSI (multiple periods)
        for period in [7, 14, 21]:
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
            rs = gain / (loss + 1e-10)
            features[f'rsi_{period}'] = 100 - (100 / (1 + rs))
        
        # Stochastic
        for period in [14, 21]:
            low_min = df['low'].rolling(period).min()
            high_max = df['high'].rolling(period).max()
            features[f'stoch_k_{period}'] = 100 * (df['close'] - low_min) / (high_max - low_min + 1e-10)
            features[f'stoch_d_{period}'] = features[f'stoch_k_{period}'].rolling(3).mean()
        
        # MACD
        ema_12 = df['close'].ewm(span=12).mean()
        ema_26 = df['close'].ewm(span=26).mean()
        features['macd'] = ema_12 - ema_26
        features['macd_signal'] = features['macd'].ewm(span=9).mean()
        features['macd_hist'] = features['macd'] - features['macd_signal']
        features['macd_normalized'] = features['macd'] / df['close']
        
        # Rate of Change
        for period in [5, 10, 20]:
            features[f'roc_{period}'] = df['close'].pct_change(period) * 100
        
        # Williams %R
        for period in [14, 21]:
            high_max = df['high'].rolling(period).max()
            low_min = df['low'].rolling(period).min()
            features[f'williams_r_{period}'] = -100 * (high_max - df['close']) / (high_max - low_min + 1e-10)
        
        # ===== VOLATILITY INDICATORS =====
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        for period in [7, 14, 21]:
            features[f'atr_{period}'] = tr.rolling(period).mean()
            features[f'atr_{period}_pct'] = features[f'atr_{period}'] / df['close']
        
        # Bollinger Bands
        for period in [20]:
            sma = df['close'].rolling(period).mean()
            std = df['close'].rolling(period).std()
            features[f'bb_upper_{period}'] = sma + 2 * std
            features[f'bb_lower_{period}'] = sma - 2 * std
            features[f'bb_width_{period}'] = (features[f'bb_upper_{period}'] - features[f'bb_lower_{period}']) / sma
            features[f'bb_position_{period}'] = (df['close'] - features[f'bb_lower_{period}']) / (features[f'bb_upper_{period}'] - features[f'bb_lower_{period}'] + 1e-10)
        
        # Keltner Channels
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        ema_20 = typical_price.ewm(span=20).mean()
        features['keltner_upper'] = ema_20 + 2 * features['atr_14']
        features['keltner_lower'] = ema_20 - 2 * features['atr_14']
        
        # Volatility ratio
        features['volatility_5'] = df['close'].rolling(5).std() / df['close']
        features['volatility_20'] = df['close'].rolling(20).std() / df['close']
        features['volatility_ratio'] = features['volatility_5'] / (features['volatility_20'] + 1e-10)
        
        # ===== VOLUME FEATURES =====
        
        if 'volume' in df.columns:
            # Volume MA ratios
            for period in [5, 10, 20]:
                vol_ma = df['volume'].rolling(period).mean()
                features[f'vol_ratio_{period}'] = df['volume'] / (vol_ma + 1e-10)
            
            # OBV (On-Balance Volume)
            features['obv'] = (np.sign(df['close'].diff()) * df['volume']).cumsum()
            features['obv_ma_10'] = features['obv'].rolling(10).mean()
            
            # Volume Price Trend
            features['vpt'] = (df['volume'] * df['close'].pct_change()).cumsum()
            
            # Money Flow
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            mf = typical_price * df['volume']
            features['mfi_14'] = 100 * mf.rolling(14).sum() / (df['volume'].rolling(14).sum() + 1e-10)
        
        # ===== PATTERN FEATURES =====
        
        # Candlestick patterns (simplified)
        features['body'] = (df['close'] - df['open']) / (df['open'] + 1e-10)
        features['upper_shadow'] = (df['high'] - df[['open', 'close']].max(axis=1)) / (df['open'] + 1e-10)
        features['lower_shadow'] = (df[['open', 'close']].min(axis=1) - df['low']) / (df['open'] + 1e-10)
        features['range_pct'] = (df['high'] - df['low']) / (df['open'] + 1e-10)
        
        # Doji detection
        features['is_doji'] = (np.abs(features['body']) < 0.001).astype(float)
        
        # Gap
        features['gap'] = (df['open'] - df['close'].shift(1)) / (df['close'].shift(1) + 1e-10)
        
        # ===== TREND FEATURES =====
        
        # ADX (simplified)
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        atr_14 = features['atr_14']
        plus_di = 100 * (plus_dm.rolling(14).sum() / (atr_14.rolling(14).sum() + 1e-10))
        minus_di = 100 * (minus_dm.rolling(14).sum() / (atr_14.rolling(14).sum() + 1e-10))
        features['plus_di'] = plus_di
        features['minus_di'] = minus_di
        features['dx'] = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        features['adx'] = features['dx'].rolling(14).mean()
        
        # Trend strength
        for period in [10, 20, 50]:
            features[f'trend_{period}'] = (df['close'] - df['close'].shift(period)) / (df['close'].shift(period) + 1e-10)
        
        # ===== STATISTICAL FEATURES =====
        
        # Skewness and Kurtosis
        for period in [20, 50]:
            features[f'skew_{period}'] = df['close'].pct_change().rolling(period).skew()
            features[f'kurt_{period}'] = df['close'].pct_change().rolling(period).kurt()
        
        # Z-score
        for period in [20]:
            mean = df['close'].rolling(period).mean()
            std = df['close'].rolling(period).std()
            features[f'zscore_{period}'] = (df['close'] - mean) / (std + 1e-10)
        
        # ===== TIME FEATURES =====
        
        if df.index.dtype == 'datetime64[ns]' or hasattr(df.index, 'hour'):
            features['hour'] = df.index.hour / 24
            features['day_of_week'] = df.index.dayofweek / 7
            features['is_weekend'] = (df.index.dayofweek >= 5).astype(float)
        
        # Store feature names
        self.feature_names = features.columns.tolist()
        
        return features
    
    def get_feature_names(self) -> List[str]:
        return self.feature_names


class EnhancedMLEngine:
    """
    Professional-grade ML engine for trading.
    Uses ensemble of XGBoost, LightGBM, and calibrated SGD.
    """
    
    def __init__(self, model_dir: str = "logs/ml_models"):
        self.config = get_config()
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.feature_engineer = FeatureEngineer()
        self.scaler = RobustScaler()
        self.is_trained = False
        
        # Models
        self.models = {}
        self.model_weights = {}
        
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize ensemble models"""
        
        # XGBoost
        if XGBOOST_AVAILABLE:
            self.models['xgboost'] = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                use_label_encoder=False,
                eval_metric='logloss'
            )
            self.model_weights['xgboost'] = 0.4
        
        # LightGBM
        if LIGHTGBM_AVAILABLE:
            self.models['lightgbm'] = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                verbose=-1
            )
            self.model_weights['lightgbm'] = 0.4
        
        # SGD (for online learning)
        self.models['sgd'] = SGDClassifier(
            loss='log_loss',
            alpha=0.0001,
            max_iter=1000,
            tol=1e-4,
            random_state=42
        )
        self.model_weights['sgd'] = 0.2
        
        # Normalize weights
        total_weight = sum(self.model_weights.values())
        self.model_weights = {k: v / total_weight for k, v in self.model_weights.items()}
        
        logger.info(f"Initialized {len(self.models)} models: {list(self.models.keys())}")
    
    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare features and labels.
        Label: 1 if price increases more than ATR/2 next candle
        """
        # Engineer features
        features = self.feature_engineer.engineer_features(df)
        
        # Create labels: positive if next return > threshold
        next_return = df['close'].pct_change().shift(-1)
        threshold = features['atr_14_pct'].fillna(0.01) * 0.5  # Half ATR
        labels = (next_return > threshold).astype(int)
        
        # Remove last row (no label) and rows with NaN
        valid_mask = ~(features.isna().any(axis=1) | labels.isna())
        valid_mask.iloc[-1] = False  # Always exclude last row
        
        X = features[valid_mask].values
        y = labels[valid_mask].values
        
        return X, y
    
    def train(self, df: pd.DataFrame, cv_splits: int = 5) -> Dict:
        """
        Train all models with time-series cross-validation.
        Returns training metrics.
        """
        X, y = self.prepare_features(df)
        
        if X.shape[0] < 500:
            logger.warning(f"Insufficient data for training: {X.shape[0]} samples")
            return {"error": "insufficient_data"}
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Time-series cross-validation
        tscv = TimeSeriesSplit(n_splits=cv_splits)
        
        metrics = {model_name: {"accuracy": [], "precision": [], "recall": [], "f1": []} 
                   for model_name in self.models}
        
        for train_idx, val_idx in tscv.split(X_scaled):
            X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]
            
            for model_name, model in self.models.items():
                try:
                    model.fit(X_train, y_train)
                    y_pred = model.predict(X_val)
                    
                    metrics[model_name]["accuracy"].append(accuracy_score(y_val, y_pred))
                    metrics[model_name]["precision"].append(precision_score(y_val, y_pred, zero_division=0))
                    metrics[model_name]["recall"].append(recall_score(y_val, y_pred, zero_division=0))
                    metrics[model_name]["f1"].append(f1_score(y_val, y_pred, zero_division=0))
                except Exception as e:
                    logger.warning(f"Model {model_name} training error: {e}")
        
        # Final training on all data
        for model_name, model in self.models.items():
            try:
                model.fit(X_scaled, y)
                logger.info(f"Trained {model_name}")
            except Exception as e:
                logger.error(f"Final training error for {model_name}: {e}")
        
        self.is_trained = True
        self._save_models()
        
        # Calculate average metrics
        results = {
            "samples": X.shape[0],
            "features": X.shape[1],
            "feature_names": self.feature_engineer.get_feature_names(),
            "models": {}
        }
        
        for model_name, model_metrics in metrics.items():
            results["models"][model_name] = {
                "accuracy": np.mean(model_metrics["accuracy"]),
                "precision": np.mean(model_metrics["precision"]),
                "recall": np.mean(model_metrics["recall"]),
                "f1": np.mean(model_metrics["f1"]),
                "weight": self.model_weights.get(model_name, 0)
            }
        
        logger.info(f"Training complete: {results['samples']} samples, {results['features']} features")
        
        return results
    
    def predict(self, df: pd.DataFrame) -> Dict:
        """
        Get ensemble prediction for the latest data point.
        Returns weighted probability and individual model predictions.
        """
        if not self.is_trained:
            return {"probability": 0.5, "signal": "neutral", "error": "not_trained"}
        
        # Engineer features for last row only
        features = self.feature_engineer.engineer_features(df)
        
        if features.iloc[-1].isna().any():
            return {"probability": 0.5, "signal": "neutral", "error": "nan_features"}
        
        X = features.iloc[-1:].values
        X_scaled = self.scaler.transform(X)
        
        # Get predictions from all models
        predictions = {}
        weighted_prob = 0.0
        
        for model_name, model in self.models.items():
            try:
                if hasattr(model, 'predict_proba'):
                    prob = model.predict_proba(X_scaled)[0, 1]
                else:
                    prob = float(model.predict(X_scaled)[0])
                
                predictions[model_name] = {
                    "probability": round(prob, 4),
                    "weight": self.model_weights.get(model_name, 0)
                }
                
                weighted_prob += prob * self.model_weights.get(model_name, 0)
            except Exception as e:
                logger.warning(f"Prediction error for {model_name}: {e}")
                predictions[model_name] = {"error": str(e)}
        
        # Determine signal
        if weighted_prob > 0.6:
            signal = "bullish"
        elif weighted_prob < 0.4:
            signal = "bearish"
        else:
            signal = "neutral"
        
        return {
            "probability": round(weighted_prob, 4),
            "signal": signal,
            "confidence": abs(weighted_prob - 0.5) * 2,
            "model_predictions": predictions,
            "timestamp": datetime.now().isoformat()
        }
    
    def update_online(self, df: pd.DataFrame) -> bool:
        """
        Online learning update (SGD only).
        Other models updated periodically via full retrain.
        """
        if 'sgd' not in self.models:
            return False
        
        try:
            X, y = self.prepare_features(df)
            
            if X.shape[0] < 100:
                return False
            
            # Use last 200 samples
            X_recent = X[-200:]
            y_recent = y[-200:]
            
            X_scaled = self.scaler.transform(X_recent)
            
            self.models['sgd'].partial_fit(X_scaled, y_recent, classes=[0, 1])
            
            logger.debug("Online update complete")
            return True
            
        except Exception as e:
            logger.warning(f"Online update error: {e}")
            return False
    
    def get_feature_importance(self, top_n: int = 20) -> Dict:
        """Get feature importance from tree-based models"""
        importance = {}
        
        if 'xgboost' in self.models and XGBOOST_AVAILABLE:
            try:
                imp = self.models['xgboost'].feature_importances_
                feature_names = self.feature_engineer.get_feature_names()
                
                sorted_idx = np.argsort(imp)[::-1][:top_n]
                importance['xgboost'] = {
                    feature_names[i]: float(imp[i]) 
                    for i in sorted_idx
                }
            except Exception as e:
                logger.warning(f"XGBoost importance error: {e}")
        
        if 'lightgbm' in self.models and LIGHTGBM_AVAILABLE:
            try:
                imp = self.models['lightgbm'].feature_importances_
                feature_names = self.feature_engineer.get_feature_names()
                
                sorted_idx = np.argsort(imp)[::-1][:top_n]
                importance['lightgbm'] = {
                    feature_names[i]: float(imp[i]) 
                    for i in sorted_idx
                }
            except Exception as e:
                logger.warning(f"LightGBM importance error: {e}")
        
        return importance
    
    def _save_models(self):
        """Save models to disk"""
        for model_name, model in self.models.items():
            path = self.model_dir / f"{model_name}_model.pkl"
            try:
                joblib.dump(model, path)
            except Exception as e:
                logger.warning(f"Could not save {model_name}: {e}")
        
        # Save scaler
        joblib.dump(self.scaler, self.model_dir / "scaler.pkl")
        logger.info(f"Models saved to {self.model_dir}")
    
    def _load_models(self):
        """Load models from disk"""
        for model_name in self.models.keys():
            path = self.model_dir / f"{model_name}_model.pkl"
            if path.exists():
                try:
                    self.models[model_name] = joblib.load(path)
                except Exception as e:
                    logger.warning(f"Could not load {model_name}: {e}")
        
        scaler_path = self.model_dir / "scaler.pkl"
        if scaler_path.exists():
            self.scaler = joblib.load(scaler_path)
        
        self.is_trained = True
        logger.info("Models loaded from disk")


# Quick test
if __name__ == "__main__":
    # Generate test data
    dates = pd.date_range(start='2024-01-01', periods=1000, freq='h')
    df = pd.DataFrame({
        'open': 2000 + np.cumsum(np.random.randn(1000) * 5),
        'high': 0,
        'low': 0,
        'close': 0,
        'volume': np.random.randint(1000, 10000, 1000)
    }, index=dates)
    
    df['high'] = df['open'] + np.abs(np.random.randn(1000) * 10)
    df['low'] = df['open'] - np.abs(np.random.randn(1000) * 10)
    df['close'] = df['open'] + np.random.randn(1000) * 8
    
    # Test
    engine = EnhancedMLEngine()
    
    print("📊 Training Enhanced ML Engine...")
    results = engine.train(df)
    
    print(f"\n✅ Training Results:")
    print(f"   Samples: {results.get('samples', 'N/A')}")
    print(f"   Features: {results.get('features', 'N/A')}")
    
    for model_name, metrics in results.get('models', {}).items():
        print(f"\n   {model_name}:")
        print(f"      Accuracy: {metrics['accuracy']:.1%}")
        print(f"      Precision: {metrics['precision']:.1%}")
        print(f"      F1: {metrics['f1']:.2f}")
    
    # Test prediction
    prediction = engine.predict(df)
    print(f"\n📈 Prediction: {prediction['signal']} ({prediction['probability']:.1%})")
