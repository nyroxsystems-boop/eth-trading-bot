"""
Ethbot Unified Configuration Manager.

Single source of truth for ALL environment variables and configuration.
Every module should import from here instead of calling os.getenv() directly.

Usage:
    from config import config
    secret = config.JWT_SECRET
    db_url = config.DATABASE_URL
"""

import os
import logging

logger = logging.getLogger("ethbot.config")


class Config:
    """Centralized configuration — reads from environment once, validates, and exposes."""

    def __init__(self):
        # ─── Database ───
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        self.USE_POSTGRES: bool = bool(self.DATABASE_URL)

        # ─── Authentication ───
        self.JWT_SECRET: str = os.getenv("JWT_SECRET", "")
        self.ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
        self.ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
        self.USER_PASSWORD: str = os.getenv("USER_PASSWORD", "")
        self.INTERNAL_API_KEY: str = os.getenv("INTERNAL_API_KEY", "")
        self.DASHBOARD_SECRET: str = os.getenv("DASHBOARD_SECRET", "ethbot_secret")

        # ─── Binance ───
        self.BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
        self.BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

        # ─── Telegram ───
        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

        # ─── Stripe ───
        self.STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
        self.STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

        # ─── Trading ───
        self.TRADING_PAIR: str = os.getenv("TRADING_PAIR", "ETHUSDT")
        self.TRADING_MODE: str = os.getenv("TRADING_MODE", "paper")  # paper | live
        self.INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "100000"))

        # ─── Server ───
        self.PORT: int = int(os.getenv("PORT", "8000"))
        self.CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
        self.LOG_DIR: str = os.getenv("LOG_DIR", "logs")
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

        # ─── Feature Flags ───
        self.ENABLE_AUTO_LEARNING: bool = os.getenv("ENABLE_AUTO_LEARNING", "true").lower() == "true"
        self.ENABLE_COPY_TRADING: bool = os.getenv("ENABLE_COPY_TRADING", "false").lower() == "true"

        # Generate ephemeral keys for dev if not set
        self._ensure_dev_secrets()

    def _ensure_dev_secrets(self):
        """Generate temporary secrets for local development."""
        if not self.JWT_SECRET:
            import secrets
            self.JWT_SECRET = secrets.token_hex(32)
            logger.warning("JWT_SECRET not set — generated ephemeral key (OK for dev, WILL break sessions on restart)")

        if not self.ENCRYPTION_KEY:
            from cryptography.fernet import Fernet
            self.ENCRYPTION_KEY = Fernet.generate_key().decode()
            logger.warning("ENCRYPTION_KEY not set — generated ephemeral key (OK for dev, encrypted data WILL be lost)")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production" or bool(self.DATABASE_URL)

    def validate_production(self) -> list:
        """Returns list of missing critical vars for production."""
        required = {
            "JWT_SECRET": self.JWT_SECRET,
            "ENCRYPTION_KEY": self.ENCRYPTION_KEY,
            "DATABASE_URL": self.DATABASE_URL,
            "ADMIN_PASSWORD": self.ADMIN_PASSWORD,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            logger.warning(f"Missing production config: {', '.join(missing)}")
        return missing

    def __repr__(self):
        return (
            f"Config(env={self.ENVIRONMENT}, db={'postgres' if self.USE_POSTGRES else 'sqlite'}, "
            f"pair={self.TRADING_PAIR}, mode={self.TRADING_MODE})"
        )


# Singleton — import this everywhere
config = Config()
