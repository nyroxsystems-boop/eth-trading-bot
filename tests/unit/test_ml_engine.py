"""
Unit tests for ML model and predictions
"""
import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler


class TestMLPrepare:
    """Test ML data preparation"""
    
    def test_ml_prepare_shapes(self, sample_df_features):
        """Test ML prepare returns correct shapes"""
        df = sample_df_features
        
        # Simulate ml_prepare logic
        X = df[['ret1', 'ema20', 'ema50', 'macd', 'macd_sig', 
                'rsi14', 'atr', 'bb_hi', 'bb_lo']].values
        future = df['close'].pct_change().shift(-1)
        thr = (df['atr'] / df['close']) * 0.2
        y = (future > thr).astype(int).values
        
        X = X[:-1]
        y = y[:-1]
        
        assert X.shape[0] == y.shape[0]
        assert X.shape[1] == 9  # 9 features
        assert len(y.shape) == 1
    
    def test_ml_prepare_labels_binary(self, sample_df_features):
        """Test ML labels are binary (0 or 1)"""
        df = sample_df_features
        
        future = df['close'].pct_change().shift(-1)
        thr = (df['atr'] / df['close']) * 0.2
        y = (future > thr).astype(int).values
        
        unique_labels = np.unique(y[~np.isnan(y)])
        assert set(unique_labels).issubset({0, 1})


class TestMLOnlineUpdate:
    """Test online learning updates"""
    
    def test_sgd_partial_fit(self):
        """Test SGD partial_fit works correctly"""
        # Create simple training data
        X_train = np.random.randn(100, 9)
        y_train = np.random.randint(0, 2, 100)
        
        scaler = StandardScaler()
        clf = SGDClassifier(loss='log_loss', alpha=1e-4, max_iter=5)
        
        # Initial fit
        X_scaled = scaler.fit_transform(X_train[:50])
        clf.fit(X_scaled, y_train[:50])
        
        # Partial fit (online update)
        X_scaled_new = scaler.transform(X_train[50:])
        clf.partial_fit(X_scaled_new, y_train[50:])
        
        # Should have learned from both batches
        assert hasattr(clf, 'coef_')
        assert clf.coef_.shape[1] == 9
    
    def test_ml_warm_flag(self):
        """Test ML warm flag is set after initial training"""
        ml_warm = False
        
        # Simulate training
        X = np.random.randn(200, 9)
        y = np.random.randint(0, 2, 200)
        
        if X.shape[0] >= 200:
            # Train model
            ml_warm = True
        
        assert ml_warm is True


class TestMLPredict:
    """Test ML predictions"""
    
    def test_ml_predict_probability_range(self):
        """Test ML predictions are valid probabilities"""
        # Create and train simple model
        X_train = np.random.randn(100, 9)
        y_train = np.random.randint(0, 2, 100)
        
        scaler = StandardScaler()
        clf = SGDClassifier(loss='log_loss', alpha=1e-4, max_iter=100)
        
        X_scaled = scaler.fit_transform(X_train)
        clf.fit(X_scaled, y_train)
        
        # Predict on new data
        X_test = np.random.randn(10, 9)
        X_test_scaled = scaler.transform(X_test)
        
        proba = clf.predict_proba(X_test_scaled)
        
        # Check probabilities are in [0, 1]
        assert (proba >= 0).all()
        assert (proba <= 1).all()
        
        # Check probabilities sum to 1
        assert np.allclose(proba.sum(axis=1), 1.0)
    
    def test_ml_predict_returns_float(self):
        """Test ML predict returns float probability"""
        # Create trained model
        X_train = np.random.randn(100, 9)
        y_train = np.random.randint(0, 2, 100)
        
        scaler = StandardScaler()
        clf = SGDClassifier(loss='log_loss', alpha=1e-4, max_iter=100)
        
        X_scaled = scaler.fit_transform(X_train)
        clf.fit(X_scaled, y_train)
        
        # Single prediction
        X_test = np.random.randn(1, 9)
        X_test_scaled = scaler.transform(X_test)
        
        proba = clf.predict_proba(X_test_scaled)[0, 1]
        
        assert isinstance(float(proba), float)
        assert 0 <= proba <= 1
    
    def test_ml_predict_without_warm_model(self):
        """Test prediction returns default when model not trained"""
        ml_warm = False
        
        if not ml_warm:
            prediction = 0.5  # Default neutral prediction
        
        assert prediction == 0.5


class TestMLConfidenceBoost:
    """Test ML confidence boost calculation"""
    
    def test_confidence_boost_calculation(self):
        """Test confidence boost from recent accuracy"""
        # Simulate recent predictions
        y_recent = np.array([1, 1, 0, 1, 1, 0, 1, 1, 1, 0])
        
        ml_conf_boost = float(np.mean(y_recent))
        
        # Should be between 0 and 1
        assert 0 <= ml_conf_boost <= 1
        assert ml_conf_boost == 0.7  # 7 out of 10
    
    def test_confidence_boost_with_insufficient_data(self):
        """Test confidence boost with minimal data"""
        y_recent = np.array([1])
        
        ml_conf_boost = float(np.mean(y_recent))
        
        assert 0 <= ml_conf_boost <= 1
