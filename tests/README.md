# ETH Trading Bot - Test Suite

## Running Tests

### All Tests
```bash
pytest tests/ -v
```

### Unit Tests Only
```bash
pytest tests/unit/ -v --cov=src --cov-report=html
```

### Integration Tests Only
```bash
pytest tests/integration/ -v -m integration
```

### With Coverage Report
```bash
pytest tests/unit/ -v --cov=src --cov-report=term-missing --cov-report=html
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Unit tests (fast, no external dependencies)
│   ├── test_config.py
│   ├── test_indicators.py
│   ├── test_ml_engine.py
│   └── test_risk_manager.py
├── integration/             # Integration tests (real API calls)
│   ├── test_market_data_integration.py
│   └── test_trading_workflow.py
├── e2e/                     # End-to-end tests
└── performance/             # Performance benchmarks
```

## Test Coverage Goals

- **Unit Tests:** >80% code coverage
- **Integration Tests:** All major workflows
- **E2E Tests:** Complete trading cycle
- **Performance Tests:** <100ms indicator calculation

## Writing Tests

### Unit Test Example
```python
def test_position_sizing():
    from src.core.risk_manager import RiskManager
    
    risk_manager = RiskManager()
    qty = risk_manager.position_size_for_risk(3500.0, 0.01, 100000.0)
    
    assert qty > 0
```

### Integration Test Example
```python
@pytest.mark.integration
def test_fetch_real_data():
    from src.core.market_data import MarketDataProvider
    
    provider = MarketDataProvider()
    df = provider.fetch_klines(lookback=10)
    
    assert len(df) > 0
```

## Fixtures Available

- `mock_binance_client` - Mocked Binance client
- `sample_klines_data` - Sample OHLCV data
- `sample_df_features` - Sample DataFrame with indicators
- `mock_env_vars` - Mocked environment variables
- `mock_telegram` - Mocked Telegram notifications
