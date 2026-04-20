"""
Unit tests for configuration management
"""


class TestBotConfig:
    """Test bot configuration loading"""
    
    def test_default_config(self):
        """Test default configuration values"""
        from src.utils.config import BotConfig
        
        config = BotConfig()
        
        assert config.trading.pair == "ETHUSDT"
        assert config.trading.interval == "5m"
        assert config.risk.risk_pct_per_trade == 0.006
        assert config.system.dry_run is True
    
    def test_config_from_env(self, mock_env_vars):
        """Test configuration loading from environment"""
        from src.utils.config import BotConfig
        
        config = BotConfig.from_env()
        
        assert config.trading.pair == "ETHUSDT"
        assert config.trading.max_trades_per_day == 15
        assert config.risk.risk_pct_per_trade == 0.006
        assert config.system.paper_base_usdt == 100000.0
    
    def test_config_reload(self, monkeypatch):
        """Test configuration reload"""
        from src.utils.config import reload_config
        
        # Set new env var
        monkeypatch.setenv("MAX_TRADES_PER_DAY", "20")
        
        config = reload_config()
        
        assert config.trading.max_trades_per_day == 20
    
    def test_trading_config_values(self):
        """Test trading config has all required fields"""
        from src.utils.config import TradingConfig
        
        config = TradingConfig()
        
        assert hasattr(config, 'pair')
        assert hasattr(config, 'interval')
        assert hasattr(config, 'max_trades_per_day')
        assert hasattr(config, 'entry_score_min')
    
    def test_risk_config_values(self):
        """Test risk config has all required fields"""
        from src.utils.config import RiskConfig
        
        config = RiskConfig()
        
        assert hasattr(config, 'risk_pct_per_trade')
        assert hasattr(config, 'max_drawdown_day')
        assert hasattr(config, 'stop_floor')
        assert hasattr(config, 'tp_min')
        assert hasattr(config, 'tp_max')


class TestConfigTypes:
    """Test configuration type validation"""
    
    def test_trading_config_types(self):
        """Test trading config field types"""
        from src.utils.config import TradingConfig
        
        config = TradingConfig()
        
        assert isinstance(config.pair, str)
        assert isinstance(config.max_trades_per_day, int)
        assert isinstance(config.entry_score_min, float)
    
    def test_risk_config_types(self):
        """Test risk config field types"""
        from src.utils.config import RiskConfig
        
        config = RiskConfig()
        
        assert isinstance(config.risk_pct_per_trade, float)
        assert isinstance(config.max_hold_bars, int)
        assert isinstance(config.stop_floor, float)
