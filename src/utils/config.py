"""
Configuration management module
Centralized configuration with environment variable support
"""
import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class TradingConfig:
    """Trading configuration"""
    pair: str = "ETHUSDT"
    base_asset: str = "ETH"
    quote_asset: str = "USDT"
    interval: str = "5m"
    lookback: int = 400
    max_trades_per_day: int = 15
    trade_capital_pct: float = 1.0
    
    # Entry thresholds
    entry_score_min: float = 0.45
    breakout_pct: float = 0.0001
    rsi_min: float = 40.0
    rsi_max: float = 70.0
    sec_pml_min: float = 0.48


@dataclass
class RiskConfig:
    """Risk management configuration"""
    risk_pct_per_trade: float = 0.006
    max_drawdown_day: float = 0.03
    stop_floor: float = 0.005
    stop_atr_mult: float = 1.5
    tp_min: float = 0.010
    tp_max: float = 0.015
    trail_pct: float = 0.008
    trail_atr_mult: float = 1.0
    break_even_trigger: float = 0.006
    max_hold_bars: int = 48
    loss_streak_cool: int = 2
    cooldown_min: int = 10


@dataclass
class MLConfig:
    """Machine learning configuration"""
    alpha: float = 1e-4
    max_iter: int = 5
    tol: float = 1e-3
    loss: str = "log_loss"
    min_samples: int = 200


@dataclass
class RegimeConfig:
    """Regime detection configuration"""
    use_adx_filter: bool = True
    adx_window: int = 14
    adx_min_trend: float = 15.0


@dataclass
class APIConfig:
    """API configuration"""
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


@dataclass
class SystemConfig:
    """System configuration"""
    dry_run: bool = True
    paper_base_usdt: float = 100000.0
    sleep_seconds: int = 60
    log_level: str = "INFO"


@dataclass
class BotConfig:
    """Complete bot configuration"""
    trading: TradingConfig = field(default_factory=TradingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    api: APIConfig = field(default_factory=APIConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    
    def apply_user_strategy(self, params: dict):
        """
        Apply user strategy parameters from Strategy Lab.
        Maps Strategy Lab parameter names to config fields.
        """
        if not params:
            return
        
        # Risk settings
        if "riskPerTrade" in params:
            # Convert percentage to decimal (1.0% -> 0.01)
            self.risk.risk_pct_per_trade = params["riskPerTrade"] / 100.0
        
        if "stopLoss" in params:
            self.risk.stop_floor = params["stopLoss"] / 100.0
        
        if "takeProfitMin" in params:
            self.risk.tp_min = params["takeProfitMin"] / 100.0
        
        if "takeProfitMax" in params:
            self.risk.tp_max = params["takeProfitMax"] / 100.0
        
        # Trading settings
        if "maxTradesPerDay" in params:
            self.trading.max_trades_per_day = int(params["maxTradesPerDay"])
        
        if "rsiOversold" in params:
            self.trading.rsi_min = float(params["rsiOversold"])
        
        if "rsiOverbought" in params:
            self.trading.rsi_max = float(params["rsiOverbought"])
        
        # ML threshold (stored as ml_threshold attribute)
        if "mlThreshold" in params:
            self.ml.threshold = float(params["mlThreshold"])
    
    @classmethod
    def from_env(cls) -> 'BotConfig':
        """Load configuration from environment variables"""
        return cls(
            trading=TradingConfig(
                pair=os.getenv("PAIR", "ETHUSDT"),
                interval=os.getenv("INTERVAL", "5m"),
                lookback=int(os.getenv("LOOKBACK", "400")),
                max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", "15")),
                trade_capital_pct=float(os.getenv("TRADE_CAPITAL_PCT", "1.0")),
                entry_score_min=float(os.getenv("ENTRY_SCORE_MIN", "0.45")),
                breakout_pct=float(os.getenv("BREAKOUT_PCT", "0.0001")),
                rsi_min=float(os.getenv("RSI_MIN", "40.0")),
                rsi_max=float(os.getenv("RSI_MAX", "70.0")),
                sec_pml_min=float(os.getenv("SEC_PML_MIN", "0.48")),
            ),
            risk=RiskConfig(
                risk_pct_per_trade=float(os.getenv("RISK_PCT_PER_TRADE", "0.006")),
                max_drawdown_day=float(os.getenv("MAX_DRAWDOWN_DAY", "0.03")),
                stop_floor=float(os.getenv("STOP_FLOOR", "0.005")),
                stop_atr_mult=float(os.getenv("STOP_ATR_MULT", "1.5")),
                tp_min=float(os.getenv("TARGET_PCT", "0.010")),
                tp_max=float(os.getenv("TARGET_PCT_MAX", "0.015")),
                trail_pct=float(os.getenv("TRAIL_PCT", "0.008")),
                trail_atr_mult=float(os.getenv("TRAIL_ATR_MULT", "1.0")),
                break_even_trigger=float(os.getenv("BREAK_EVEN_TRIGGER", "0.006")),
                max_hold_bars=int(os.getenv("MAX_HOLD_BARS", "48")),
                loss_streak_cool=int(os.getenv("LOSS_STREAK_COOL", "2")),
                cooldown_min=int(os.getenv("COOLDOWN_MIN", "10")),
            ),
            ml=MLConfig(
                alpha=float(os.getenv("ML_ALPHA", "1e-4")),
                max_iter=int(os.getenv("ML_MAX_ITER", "5")),
            ),
            regime=RegimeConfig(
                use_adx_filter=os.getenv("USE_ADX_FILTER", "true").lower() == "true",
                adx_window=int(os.getenv("ADX_WINDOW", "14")),
                adx_min_trend=float(os.getenv("ADX_MIN_TREND", "15.0")),
            ),
            api=APIConfig(
                binance_api_key=os.getenv("BINANCE_API_KEY"),
                binance_api_secret=os.getenv("BINANCE_API_SECRET"),
                telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
                telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            ),
            system=SystemConfig(
                dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
                paper_base_usdt=float(os.getenv("PAPER_BASE_USDT", "100000")),
                sleep_seconds=int(os.getenv("LOOP_SLEEP", "60")),
                log_level=os.getenv("LOG_LEVEL", "INFO"),
            ),
        )


# Global config instance
config: Optional[BotConfig] = None


def get_config() -> BotConfig:
    """Get or create global configuration"""
    global config
    if config is None:
        config = BotConfig.from_env()
    return config


def reload_config() -> BotConfig:
    """Reload configuration from environment"""
    global config
    config = BotConfig.from_env()
    return config


# Settings file path (must match dashboard_api.py)
_SETTINGS_FILE = None

def _get_settings_file():
    """Get settings file path lazily"""
    global _SETTINGS_FILE
    if _SETTINGS_FILE is None:
        from pathlib import Path
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        _SETTINGS_FILE = log_dir / "bot_settings.json"
    return _SETTINGS_FILE


def reload_from_settings() -> bool:
    """
    Reload config from settings.json (written by dashboard API).
    Updates dry_run, trading_capital, and risk parameters in the live config.
    
    Returns True if settings were loaded, False otherwise.
    """
    import json
    
    settings_file = _get_settings_file()
    
    if not settings_file.exists():
        return False
    
    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
        
        cfg = get_config()
        
        # Sync trading mode
        if 'dry_run' in settings:
            old_mode = cfg.system.dry_run
            cfg.system.dry_run = settings['dry_run']
            if old_mode != cfg.system.dry_run:
                mode_name = "PAPER" if cfg.system.dry_run else "LIVE"
                print(f"🔄 Config sync: Trading mode changed to {mode_name}")
        
        # Sync trading capital
        if 'trading_capital' in settings:
            old_capital = cfg.system.paper_base_usdt
            cfg.system.paper_base_usdt = float(settings['trading_capital'])
            if old_capital != cfg.system.paper_base_usdt:
                print(f"🔄 Config sync: Capital changed to ${cfg.system.paper_base_usdt:,.2f}")
        
        # Sync risk parameters
        if 'risk_per_trade' in settings:
            cfg.risk.risk_pct_per_trade = float(settings['risk_per_trade'])
        if 'tp_min' in settings:
            cfg.risk.tp_min = float(settings['tp_min'])
        if 'tp_max' in settings:
            cfg.risk.tp_max = float(settings['tp_max'])
        if 'stop_floor' in settings:
            cfg.risk.stop_floor = float(settings['stop_floor'])
        if 'max_drawdown_day' in settings:
            cfg.risk.max_drawdown_day = float(settings['max_drawdown_day'])
        if 'max_trades_per_day' in settings:
            cfg.trading.max_trades_per_day = int(settings['max_trades_per_day'])
        
        # Sync API keys if present
        if settings.get('binance_api_key'):
            cfg.api.binance_api_key = settings['binance_api_key']
        if settings.get('binance_api_secret'):
            cfg.api.binance_api_secret = settings['binance_api_secret']
        
        return True
        
    except Exception as e:
        print(f"⚠️ Failed to reload from settings.json: {e}")
        return False


def load_active_strategy() -> bool:
    """
    Load active strategy from JSON file created by Strategy Lab.
    Returns True if strategy was loaded, False otherwise.
    """
    import json
    from pathlib import Path
    
    strategy_file = Path("data/user_strategies/active_strategy.json")
    
    if not strategy_file.exists():
        return False
    
    try:
        data = json.loads(strategy_file.read_text())
        params = data.get("params", {})
        
        if params:
            cfg = get_config()
            cfg.apply_user_strategy(params)
            return True
    except Exception as e:
        print(f"Warning: Failed to load active strategy: {e}")
    
    return False


# Hot reload state
_last_strategy_mtime: float = 0.0


def check_strategy_changed() -> bool:
    """
    Check if the active strategy file has been modified since last check.
    Returns True if file was modified, False otherwise.
    """
    global _last_strategy_mtime
    from pathlib import Path
    
    strategy_file = Path("data/user_strategies/active_strategy.json")
    
    if not strategy_file.exists():
        return False
    
    try:
        current_mtime = strategy_file.stat().st_mtime
        
        if _last_strategy_mtime == 0.0:
            # First check - just record mtime
            _last_strategy_mtime = current_mtime
            return False
        
        if current_mtime > _last_strategy_mtime:
            _last_strategy_mtime = current_mtime
            return True
    except Exception:
        pass
    
    return False


def hot_reload_strategy() -> bool:
    """
    Check for strategy changes and reload if needed.
    Returns True if strategy was reloaded, False otherwise.
    
    Call this periodically in the bot main loop.
    """
    if check_strategy_changed():
        if load_active_strategy():
            return True
    return False
