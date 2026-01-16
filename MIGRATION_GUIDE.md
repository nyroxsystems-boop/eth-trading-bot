# Migration Guide: Old Bot → Modular Bot

## Overview

This guide explains how to migrate from the old monolithic `eth_master_bot.py` to the new modular `eth_bot_modular.py`.

## Architecture Comparison

### Old (Monolithic)
```
eth_master_bot.py (1210 lines)
├── All logic in one file
├── Global variables everywhere
├── Scattered configuration
└── No tests
```

### New (Modular)
```
eth_bot_modular.py (272 lines)
└── Orchestrates components:
    ├── src/core/strategy.py (201 lines)
    ├── src/core/risk_manager.py (232 lines)
    ├── src/core/ml_engine.py (181 lines)
    ├── src/core/market_data.py (245 lines)
    ├── src/core/order_executor.py (260 lines)
    ├── src/utils/config.py (162 lines)
    └── src/utils/logger.py (115 lines)

Total: 1670 lines (well-organized, testable)
```

## Migration Steps

### 1. Install Dependencies

```bash
# Ensure all dependencies are installed
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Configuration

The new bot uses the same environment variables, but they're now managed centrally:

```bash
# Your existing .env file works as-is
# No changes needed to environment variables
```

### 3. Run the New Bot

```bash
# Test in dry-run mode first
python eth_bot_modular.py

# Or use the old bot (still works)
python eth_master_bot.py
```

### 4. Verify Functionality

Both bots should produce identical trading behavior:
- Same entry/exit signals
- Same risk management
- Same ML predictions
- Same order execution

### 5. Switch to Modular Bot

Once verified, update your deployment:

**Railway/Production:**
```bash
# Update Procfile
# Old: worker: python eth_master_bot.py
# New: worker: python eth_bot_modular.py
```

**Local:**
```bash
# Use the new bot
python eth_bot_modular.py
```

## Key Differences

### Logging

**Old:**
```python
print(f"INFO: {message}")
```

**New:**
```python
logger.info(message)  # Structured logging with levels
```

### Configuration

**Old:**
```python
PAIR = os.getenv("PAIR", "ETHUSDT")
```

**New:**
```python
config = get_config()
config.trading.pair  # Type-safe access
```

### Testing

**Old:**
- No tests

**New:**
```bash
# Run tests
pytest tests/ -v

# With coverage
pytest tests/unit/ -v --cov=src --cov-report=html
```

## Benefits of Modular Architecture

1. **Testability** - Each component can be tested independently
2. **Maintainability** - Changes are isolated to specific modules
3. **Readability** - Clear separation of concerns
4. **Extensibility** - Easy to add new features
5. **Type Safety** - Full type hints throughout
6. **Logging** - Structured logging for better debugging

## Rollback Plan

If issues arise, you can always rollback to the old bot:

```bash
# Revert to old bot
python eth_master_bot.py
```

The old bot file remains unchanged and fully functional.

## Next Steps

1. ✅ Run modular bot in dry-run mode
2. ✅ Verify logs and behavior match old bot
3. ✅ Run test suite
4. ✅ Deploy to staging/production
5. ✅ Monitor for 24-48 hours
6. ✅ Remove old bot file once confident

## Support

If you encounter issues:
1. Check logs in `/root/ethbot/logs/ethbot.log`
2. Compare behavior with old bot
3. Run tests: `pytest tests/ -v`
4. Review [walkthrough.md](file:///Users/xaaronvx/.gemini/antigravity/brain/9f301ab1-69a9-4746-b5bb-2c51ef781c05/walkthrough.md)
