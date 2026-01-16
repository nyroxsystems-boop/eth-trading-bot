"""
Order Executor Module
Handles order placement, execution, and balance management
"""
from typing import Optional, Dict, Any
import os

from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OrderExecutor:
    """Executes buy/sell orders and manages balances"""
    
    def __init__(self):
        self.config = get_config()
        self.paper_balance_usdt = self.config.system.paper_base_usdt
        self.paper_balance_eth = 0.0
    
    def get_usdt_balance(self) -> float:
        """
        Get current USDT balance
        
        Returns:
            USDT balance (paper or real)
        """
        if self.config.system.dry_run:
            return self.paper_balance_usdt
        
        if not (self.config.api.binance_api_key and self.config.api.binance_api_secret):
            return 0.0
        
        try:
            from binance.client import Client
            client = Client(
                self.config.api.binance_api_key,
                self.config.api.binance_api_secret
            )
            info = client.get_asset_balance(asset=self.config.trading.quote_asset)
            return float(info["free"]) if info else 0.0
        except Exception as e:
            logger.error(f"Failed to fetch USDT balance: {e}")
            return 0.0
    
    def get_last_price(self) -> Optional[float]:
        """
        Get last price from market data
        
        Returns:
            Last price or None on error
        """
        try:
            from src.core.market_data import MarketDataProvider
            provider = MarketDataProvider()
            return provider.get_last_price()
        except Exception as e:
            logger.error(f"Failed to get last price: {e}")
            return None
    
    def estimate_equity(self, current_price: Optional[float] = None) -> float:
        """
        Estimate total equity (USDT + ETH value)
        
        Args:
            current_price: Current ETH price (fetched if not provided)
            
        Returns:
            Total equity in USDT
        """
        if current_price is None:
            current_price = self.get_last_price() or 0.0
        
        usdt = self.get_usdt_balance()
        
        if self.config.system.dry_run:
            eth_value = self.paper_balance_eth * current_price
        else:
            # In live mode, would need to fetch ETH balance
            eth_value = 0.0
        
        return usdt + eth_value
    
    def run_pre_buy_guards(self) -> bool:
        """
        Run all pre-buy safeguards using consolidated guards module
        
        Returns:
            True if buy is allowed, False if blocked
        """
        try:
            from src.core.guards import TradeGuards
            
            guards = TradeGuards()
            
            # Get config values
            max_losses = int(os.getenv("MAX_CONSEC_LOSSES", "3"))
            cooldown = int(os.getenv("COOLDOWN_AFTER_MAX_LOSSES_MIN", "60"))
            target_pct = float(os.getenv("DAILY_TARGET_PCT", "0.02"))
            equity = self.estimate_equity()
            
            # Run all guards
            blocked, reasons = guards.check_all_guards(
                max_losses=max_losses,
                cooldown_minutes=cooldown,
                target_pct=target_pct,
                equity=equity
            )
            
            if blocked:
                logger.warning(f"[SAFEGUARD] BUY blocked: {reasons[0]}")
                return False
            
            # Log passed guards
            for reason in reasons:
                logger.debug(f"[GUARD] {reason}")
            
            return True
            
        except Exception as e:
            logger.error(f"Guard check failed: {e}")
            # Fail-safe: allow trade if guards error
            return True
    
    def place_buy(self, qty: float, price_hint: float) -> bool:
        """
        Execute buy order
        
        Args:
            qty: Quantity to buy
            price_hint: Estimated price
            
        Returns:
            True if order succeeded, False otherwise
        """
        # Run pre-buy guards
        if not self.run_pre_buy_guards():
            return False
        
        # DRY RUN mode
        if self.config.system.dry_run:
            cost = qty * price_hint
            if cost > self.paper_balance_usdt:
                logger.warning(f"Insufficient paper balance: {self.paper_balance_usdt:.2f} < {cost:.2f}")
                return False
            
            self.paper_balance_usdt -= cost
            self.paper_balance_eth += qty
            
            logger.info(f"[DRY] BUY {qty:.5f} {self.config.trading.base_asset} @ ~{price_hint:.2f}")
            return True
        
        # LIVE mode
        if not (self.config.api.binance_api_key and self.config.api.binance_api_secret):
            logger.error("Binance API credentials not configured")
            return False
        
        try:
            from binance.client import Client
            client = Client(
                self.config.api.binance_api_key,
                self.config.api.binance_api_secret
            )
            
            quote_amount = round(qty * price_hint, 2)
            
            try:
                # Try quote order quantity first
                client.order_market_buy(
                    symbol=self.config.trading.pair,
                    quoteOrderQty=quote_amount
                )
            except Exception:
                # Fallback to base quantity
                client.order_market_buy(
                    symbol=self.config.trading.pair,
                    quantity=round(qty, 5)
                )
            
            logger.info(f"[LIVE] BUY {qty:.5f} {self.config.trading.base_asset} @ ~{price_hint:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Live buy order failed: {e}")
            return False
    
    def place_sell(self, qty: float) -> bool:
        """
        Execute sell order
        
        Args:
            qty: Quantity to sell
            
        Returns:
            True if order succeeded, False otherwise
        """
        price = self.get_last_price() or 0.0
        
        # DRY RUN mode
        if self.config.system.dry_run:
            if qty > self.paper_balance_eth:
                logger.warning(f"Insufficient paper ETH: {self.paper_balance_eth:.5f} < {qty:.5f}")
                return False
            
            proceeds = qty * price
            self.paper_balance_eth -= qty
            self.paper_balance_usdt += proceeds
            
            logger.info(f"[DRY] SELL {qty:.5f} {self.config.trading.base_asset} @ ~{price:.2f}")
            return True
        
        # LIVE mode
        if not (self.config.api.binance_api_key and self.config.api.binance_api_secret):
            logger.error("Binance API credentials not configured")
            return False
        
        try:
            from binance.client import Client
            client = Client(
                self.config.api.binance_api_key,
                self.config.api.binance_api_secret
            )
            
            client.order_market_sell(
                symbol=self.config.trading.pair,
                quantity=round(qty, 5)
            )
            
            logger.info(f"[LIVE] SELL {qty:.5f} {self.config.trading.base_asset} @ ~{price:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Live sell order failed: {e}")
            return False
    
    def send_telegram_notification(self, message: str):
        """
        Send Telegram notification
        
        Args:
            message: Message to send
        """
        if not (self.config.api.telegram_bot_token and self.config.api.telegram_chat_id):
            return
        
        try:
            import requests
            requests.post(
                f"https://api.telegram.org/bot{self.config.api.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": self.config.api.telegram_chat_id,
                    "text": message
                },
                timeout=6
            )
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")
