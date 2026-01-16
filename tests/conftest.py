"""
Test configuration and fixtures
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def mock_binance_client(mocker):
    """Mock Binance client for testing"""
    mock_client = mocker.MagicMock()
    mock_client.get_asset_balance.return_value = {"free": "1000.0", "locked": "0.0"}
    mock_client.get_symbol_ticker.return_value = {"symbol": "ETHUSDT", "price": "3500.00"}
    return mock_client


@pytest.fixture
def sample_klines_data():
    """Sample klines data for testing"""
    return [
        [1609459200000, "3500.0", "3550.0", "3480.0", "3520.0", "1000.0",
         1609459500000, "3510000.0", 100, "500.0", "1755000.0", "0"],
        [1609459500000, "3520.0", "3560.0", "3500.0", "3540.0", "1100.0",
         1609459800000, "3894000.0", 110, "550.0", "1947000.0", "0"],
        [1609459800000, "3540.0", "3580.0", "3520.0", "3560.0", "1050.0",
         1609460100000, "3738000.0", 105, "525.0", "1869000.0", "0"],
    ]


@pytest.fixture
def sample_df_features():
    """Sample DataFrame with features for testing"""
    import pandas as pd
    import numpy as np
    
    data = {
        'time': pd.date_range('2024-01-01', periods=100, freq='5min'),
        'open': np.random.uniform(3400, 3600, 100),
        'high': np.random.uniform(3450, 3650, 100),
        'low': np.random.uniform(3350, 3550, 100),
        'close': np.random.uniform(3400, 3600, 100),
        'volume': np.random.uniform(1000, 2000, 100),
        'ret1': np.random.uniform(-0.01, 0.01, 100),
        'ema20': np.random.uniform(3400, 3600, 100),
        'ema50': np.random.uniform(3400, 3600, 100),
        'macd': np.random.uniform(-10, 10, 100),
        'macd_sig': np.random.uniform(-10, 10, 100),
        'rsi14': np.random.uniform(30, 70, 100),
        'atr': np.random.uniform(20, 40, 100),
        'bb_hi': np.random.uniform(3500, 3700, 100),
        'bb_lo': np.random.uniform(3300, 3500, 100),
        'hh20': np.random.uniform(3500, 3650, 100),
        'll20': np.random.uniform(3350, 3500, 100),
    }
    
    return pd.DataFrame(data)


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables"""
    env_vars = {
        'DRY_RUN': 'true',
        'PAIR': 'ETHUSDT',
        'INTERVAL': '5m',
        'MAX_TRADES_PER_DAY': '15',
        'RISK_PCT_PER_TRADE': '0.006',
        'PAPER_BASE_USDT': '100000',
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


@pytest.fixture
def mock_telegram(mocker):
    """Mock Telegram notifications"""
    return mocker.patch('requests.post')
