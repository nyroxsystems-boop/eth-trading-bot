"""
Bot Configuration — Single Source of Truth.
All settings live here. No scattered globals, no ENV surprises.
"""
import os
from dataclasses import dataclass, field


@dataclass
class TradingConfig:
    """All trading parameters in one place."""

    # --- Identity ---
    pair: str = "ETHUSDT"
    base_asset: str = "ETH"
    quote_asset: str = "USDT"
    interval: str = "5m"

    # --- Mode ---
    paper_mode: bool = True
    paper_balance: float = 100_000.0

    # --- Risk Management ---
    risk_per_trade: float = 0.02        # 2% of equity per trade
    max_risk_per_trade: float = 0.06    # Hard cap 6% (with leverage)
    stop_atr_mult: float = 1.5         # SL = 1.5x ATR (tighter)
    stop_floor: float = 0.008          # Minimum SL: 0.8%
    tp_min: float = 0.010              # TP: 1.0% (faster take)
    tp_max: float = 0.020              # TP: 2.0% (was 3.0%)
    max_drawdown_day: float = 0.05     # 5% daily max drawdown → stop

    # --- Leverage ---
    leverage: float = 3.0              # 3x margin leverage
    max_leverage: float = 3.0          # Safety cap

    # --- Entry ---
    entry_score_min: float = 0.25      # Higher bar for better entries
    max_trades_per_day: int = 25       # Aggressive data collection
    rsi_min: float = 25.0
    rsi_max: float = 78.0

    # --- Position Management ---
    break_even_trigger: float = 0.010  # Move SL to BE after +1.0%
    trail_pct: float = 0.006           # Trailing: 0.6% (tighter)
    max_hold_bars: int = 36            # ~3h at 5m (faster turnover)

    # --- ML ---
    use_ml: bool = True
    ml_threshold: float = 0.52         # Min ML confidence for entry

    # --- Cooldowns ---
    loss_streak_cooldown: int = 6      # N losses → cooldown
    cooldown_minutes: int = 60         # 1h pause after streak

    # --- Notifications ---
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # --- Binance API ---
    binance_api_key: str = ""
    binance_api_secret: str = ""

    # --- Timing ---
    loop_sleep_seconds: int = 90       # 90s between loops — faster learning

    @classmethod
    def from_env(cls) -> "TradingConfig":
        """Load config from environment variables with sane defaults."""
        return cls(
            pair=os.getenv("PAIR", "ETHUSDT"),
            base_asset=os.getenv("BASE_ASSET", "ETH"),
            quote_asset=os.getenv("QUOTE_ASSET", "USDT"),
            interval=os.getenv("INTERVAL", "5m"),
            paper_mode=os.getenv("PAPER_MODE", "true").lower() in ("true", "1", "yes"),
            paper_balance=float(os.getenv("PAPER_BASE_USDT", "100000")),
            risk_per_trade=float(os.getenv("RISK_PCT_PER_TRADE", "0.01")),
            stop_atr_mult=float(os.getenv("STOP_ATR_MULT", "2.0")),
            stop_floor=float(os.getenv("STOP_FLOOR", "0.012")),
            tp_min=float(os.getenv("TP_MIN", "0.015")),
            tp_max=float(os.getenv("TP_MAX", "0.025")),
            max_drawdown_day=float(os.getenv("MAX_DRAWDOWN_DAY", "0.03")),
            entry_score_min=float(os.getenv("ENTRY_SCORE_MIN", "0.20")),
            max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", "15")),
            rsi_min=float(os.getenv("RSI_MIN", "30")),
            rsi_max=float(os.getenv("RSI_MAX", "75")),
            loss_streak_cooldown=int(os.getenv("LOSS_STREAK_COOL", "5")),
            cooldown_minutes=int(os.getenv("COOLDOWN_MIN", "120")),
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            binance_api_key=os.getenv("BINANCE_API_KEY", ""),
            binance_api_secret=os.getenv("BINANCE_API_SECRET", "") or os.getenv("BINANCE_SECRET_KEY", ""),
            loop_sleep_seconds=int(os.getenv("LOOP_SLEEP", "120")),
            use_ml=os.getenv("USE_ML", "true").lower() in ("true", "1", "yes"),
            ml_threshold=float(os.getenv("ML_THRESHOLD", "0.52")),
        )

    @property
    def is_live(self) -> bool:
        return not self.paper_mode and bool(self.binance_api_key)
