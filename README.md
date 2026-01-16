# ETH Trading Bot - Modular Architecture

Automated Ethereum trading bot with machine learning, sentiment analysis, and comprehensive risk management.

## 🎯 Features

- **Machine Learning** - SGDClassifier with online learning
- **Sentiment Analysis** - VADER + RSS news integration
- **Risk Management** - Dynamic position sizing, stop-loss, drawdown protection
- **Real-Time Dashboard** - React + TypeScript web interface
- **Telegram Alerts** - Live trade notifications
- **Modular Architecture** - Clean, testable, maintainable code

## 📊 Performance Target

**Goal**: 1% daily profit (≈365% annually)

## 🏗️ Architecture

### Modular Design

```
src/
├── core/                    # Core trading components
│   ├── strategy.py         # Entry/exit signals, regime detection
│   ├── risk_manager.py     # Position sizing, stop-loss, drawdown
│   ├── ml_engine.py        # ML training, prediction, online learning
│   └── market_data.py      # Data fetching, indicators
├── utils/                   # Shared utilities
│   ├── config.py           # Centralized configuration
│   └── logger.py           # Structured logging
├── ml/                      # ML components
├── api/                     # API components
└── monitoring/              # Monitoring components
```

### Legacy Files (To be refactored)
- `eth_master_bot.py` - Main bot (1210 lines → will be reduced to ~200 lines)
- `dashboard_api.py` - Dashboard backend
- Various guard modules - Will be consolidated

## 🧪 Testing

### Test Coverage

- **Unit Tests**: 36 tests covering indicators, risk management, ML, config
- **Integration Tests**: Market data, trading workflow
- **Target Coverage**: >80%

### Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v --cov=src --cov-report=html

# Integration tests (requires internet)
pytest tests/integration/ -v -m integration

# View coverage report
open htmlcov/index.html
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Virtual environment
- Binance API keys (for live trading)

### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For development

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Running the Bot

```bash
# Dry run mode (paper trading)
python eth_master_bot.py

# Backtest mode
python eth_master_bot.py --backtest --days 30

# Live trading (set DRY_RUN=false in .env)
python eth_master_bot.py
```

### Running the Dashboard

```bash
# Start API server
python dashboard_server.py

# In another terminal, start frontend
cd dashboard
npm install
npm run dev
```

## ⚙️ Configuration

Configuration is managed through environment variables and `src/utils/config.py`.

### Key Settings

```bash
# Trading
PAIR=ETHUSDT
INTERVAL=5m
MAX_TRADES_PER_DAY=15

# Risk Management
RISK_PCT_PER_TRADE=0.006  # 0.6% per trade
MAX_DRAWDOWN_DAY=0.03     # 3% daily max drawdown
STOP_FLOOR=0.005          # 0.5% minimum stop loss

# ML
ENTRY_SCORE_MIN=0.45
SEC_PML_MIN=0.48

# System
DRY_RUN=true
PAPER_BASE_USDT=100000
```

## 📈 Trading Strategy

### Entry Signals

1. **Breakout** - Price breaks above 20-period high
2. **Drawdown** - Hammer/doji candle with long lower wick
3. **Trend** - Price above EMA20, EMA20 above EMA50
4. **Oversold Rebound** - RSI < 40 + drawdown candle
5. **ML Confirmation** - SGD classifier probability > threshold

### Exit Signals

1. **Take Profit** - 1.0-1.5% profit (dynamic based on RSI/ADX)
2. **Stop Loss** - ATR-based or 0.5% floor
3. **Trailing Stop** - ATR-based trailing
4. **Time Exit** - Max 48 bars (4 hours on 5m)

### Risk Management

- **Position Sizing** - Risk 0.6% of equity per trade
- **Daily Drawdown Limit** - Pause trading at -3%
- **Loss Streak Cooldown** - 10-minute pause after 2 consecutive losses
- **Break-Even Stop** - Move SL to BE after +0.6% profit

## 🛠️ Development

### Project Structure

```
ethbot_code/
├── src/                     # New modular code
│   ├── core/               # Core trading logic
│   ├── utils/              # Utilities
│   ├── ml/                 # ML components
│   ├── api/                # API components
│   └── monitoring/         # Monitoring
├── tests/                   # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   ├── e2e/                # End-to-end tests
│   └── performance/        # Performance tests
├── dashboard/               # React frontend
├── docs/                    # Documentation
├── eth_master_bot.py       # Main bot (legacy, being refactored)
├── dashboard_api.py        # Dashboard backend
└── requirements.txt        # Dependencies
```

### Code Style

- **Type Hints** - All new code uses type hints
- **Docstrings** - Google-style docstrings
- **Logging** - Structured logging via `src/utils/logger.py`
- **Testing** - >80% coverage target

### Contributing

1. Create feature branch
2. Write tests first (TDD)
3. Implement feature
4. Ensure tests pass
5. Update documentation
6. Submit PR

## 📊 Monitoring

### Logs

```bash
# View logs
tail -f /root/ethbot/logs/ethbot.log

# View trade log
tail -f /root/ethbot/logs/trades.csv
```

### Metrics

- Trade count
- Win rate
- PnL (daily, total)
- Sharpe ratio
- Max drawdown

## 🔐 Security

- **API Keys** - Never commit to git
- **Environment Variables** - Use `.env` file
- **DRY_RUN Mode** - Test safely before live trading

## 📝 License

Private - All Rights Reserved

## 👤 Author

nyroxsystems

## 🔗 Links

- [Deployment Guide](RAILWAY_ENV_SETUP.md)
- [Telegram Setup](TELEGRAM_REPORT_GUIDE.md)
- [Quick Start](QUICK_START.md)
- [Implementation Plan](/Users/xaaronvx/.gemini/antigravity/brain/9f301ab1-69a9-4746-b5bb-2c51ef781c05/implementation_plan.md)
- [Walkthrough](/Users/xaaronvx/.gemini/antigravity/brain/9f301ab1-69a9-4746-b5bb-2c51ef781c05/walkthrough.md)
# Trigger Railway Rebuild
