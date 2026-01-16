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
