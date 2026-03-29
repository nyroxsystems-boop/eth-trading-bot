"""
Order Executor Module
Handles order placement, execution, and balance management
"""
from typing import Optional, Dict, Any
import os
import random
import time
import math
import csv
from datetime import datetime
from pathlib import Path

from src.utils.config import get_config, reload_from_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OrderExecutor:
    """Executes buy/sell orders and manages balances"""
    
    def __init__(self):
        self.config = get_config()
        self.paper_balance_usdt = self.config.system.paper_base_usdt
        self.paper_balance_eth = 0.0
        self._last_capital = self.config.system.paper_base_usdt
        self.total_fees_paid = 0.0  # Track cumulative fees
        self._exchange_info: Optional[Dict] = None  # Cache for Binance symbol info
        self._trade_log_path = Path(os.getenv("LOG_DIR", "./logs")) / "trades.csv"
    
    def _simulate_execution_price(self, price: float, side: str) -> float:
        """
        Simulate realistic execution price with spread, fees, and slippage.
        Makes paper trading results more realistic.
        
        Costs per trade:
        - Bid-ask spread: 0.05%
        - Binance taker fee: 0.1%
        - Random slippage: 0-0.05% (order book depth)
        Total per round-trip: ~0.4%
        """
        spread = 0.0005           # 0.05% bid-ask spread
        fee = 0.001               # 0.1% Binance taker fee
        slippage = random.uniform(0, 0.0005)  # 0-0.05% random
        
        total_cost = spread + fee + slippage
        
        if side == "BUY":
            # Buyer pays more
            exec_price = price * (1 + total_cost)
        else:
            # Seller receives less
            exec_price = price * (1 - total_cost)
        
        # Track fees
        fee_amount = price * fee
        self.total_fees_paid += fee_amount
        
        logger.debug(
            f"[SLIPPAGE] {side} {price:.2f} -> {exec_price:.2f} "
            f"(spread={spread*100:.2f}%, fee={fee*100:.1f}%, slip={slippage*100:.3f}%)"
        )
        
        return exec_price
    
    def _fetch_exchange_info(self) -> Dict:
        """Fetch and cache Binance symbol exchange info (lot size, min qty)."""
        if self._exchange_info:
            return self._exchange_info
        
        try:
            import requests
            resp = requests.get(
                "https://api.binance.com/api/v3/exchangeInfo",
                params={"symbol": self.config.trading.pair},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            
            for s in data.get("symbols", []):
                if s["symbol"] == self.config.trading.pair:
                    for f in s.get("filters", []):
                        if f["filterType"] == "LOT_SIZE":
                            self._exchange_info = {
                                "min_qty": float(f["minQty"]),
                                "max_qty": float(f["maxQty"]),
                                "step_size": float(f["stepSize"])
                            }
                            logger.info(
                                f"Exchange info: min={self._exchange_info['min_qty']}, "
                                f"step={self._exchange_info['step_size']}"
                            )
                            return self._exchange_info
        except Exception as e:
            logger.warning(f"Failed to fetch exchange info: {e}")
        
        # Safe defaults for ETHUSDT
        self._exchange_info = {"min_qty": 0.0001, "max_qty": 9000.0, "step_size": 0.0001}
        return self._exchange_info
    
    def _validate_quantity(self, qty: float) -> float:
        """
        Validate and adjust quantity to match Binance LOT_SIZE filter.
        Prevents 'Filter failure: LOT_SIZE' rejections on live orders.
        """
        info = self._fetch_exchange_info()
        
        # Check minimum
        if qty < info["min_qty"]:
            logger.warning(f"Qty {qty:.6f} below min {info['min_qty']}. Order rejected.")
            return 0.0
        
        # Round down to step size
        step = info["step_size"]
        if step > 0:
            qty = math.floor(qty / step) * step
        
        # Check maximum
        qty = min(qty, info["max_qty"])
        
        return round(qty, 8)
    
    def _log_paper_trade(self, action: str, qty: float, price: float, exec_price: float):
        """Log paper trade to CSV for P&L dashboard chart.
        
        Uses canonical format: timestamp,action,qty,price (same as eth_master_bot).
        Extra columns appended for richer analytics but guards only read first 4.
        """
        try:
            self._trade_log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_exists = self._trade_log_path.exists()
            with open(self._trade_log_path, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'action', 'qty', 'price', 'exec_price',
                                     'balance_usdt', 'balance_eth', 'fees_paid'])
                
                # Use fixed timestamp format matching guards parser (%Y-%m-%d %H:%M:%S)
                from datetime import timezone
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                
                writer.writerow([
                    ts,
                    action, round(qty, 6), round(price, 2), round(exec_price, 2),
                    round(self.paper_balance_usdt, 2), round(self.paper_balance_eth, 6),
                    round(self.total_fees_paid, 2)
                ])
        except Exception as e:
            logger.debug(f"Trade log write error: {e}")
    
    def sync_from_settings(self):
        """
        Sync config from dashboard settings.json.
        Called before each trade to pick up mode/capital changes.
        """
        try:
            reload_from_settings()
            
            # If capital changed and we haven't traded yet, update paper balance
            new_capital = self.config.system.paper_base_usdt
            if new_capital != self._last_capital:
                # Scale paper balance proportionally
                if self._last_capital > 0:
                    ratio = new_capital / self._last_capital
                    self.paper_balance_usdt *= ratio
                else:
                    self.paper_balance_usdt = new_capital
                self._last_capital = new_capital
                logger.info(f"💰 Capital updated to ${new_capital:,.2f} (paper balance: ${self.paper_balance_usdt:,.2f})")
        except Exception as e:
            logger.debug(f"Settings sync skipped: {e}")
    
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
            # In live mode, fetch actual ETH balance from Binance
            eth_value = 0.0
            try:
                if self.config.api.binance_api_key and self.config.api.binance_api_secret:
                    from binance.client import Client
                    client = Client(
                        self.config.api.binance_api_key,
                        self.config.api.binance_api_secret
                    )
                    info = client.get_asset_balance(asset=self.config.trading.base_asset)
                    if info:
                        eth_value = float(info['free']) * current_price
            except Exception as e:
                logger.debug(f"Could not fetch ETH balance: {e}")
        
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
        # Sync latest settings from dashboard
        self.sync_from_settings()
        
        # Run pre-buy guards
        if not self.run_pre_buy_guards():
            return False
        
        # DRY RUN mode
        if self.config.system.dry_run:
            exec_price = self._simulate_execution_price(price_hint, "BUY")
            cost = qty * exec_price
            if cost > self.paper_balance_usdt:
                logger.warning(f"Insufficient paper balance: {self.paper_balance_usdt:.2f} < {cost:.2f}")
                return False
            
            self.paper_balance_usdt -= cost
            self.paper_balance_eth += qty
            
            logger.info(
                f"[DRY] BUY {qty:.5f} {self.config.trading.base_asset} "
                f"@ ~{price_hint:.2f} (exec: {exec_price:.2f}, cost: {cost:.2f})"
            )
            self._log_paper_trade("BUY", qty, price_hint, exec_price)
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
            
            # Validate quantity against Binance LOT_SIZE
            valid_qty = self._validate_quantity(qty)
            if valid_qty <= 0:
                logger.error(f"Order qty {qty} failed validation")
                return False
            
            try:
                # Try quote order quantity first
                client.order_market_buy(
                    symbol=self.config.trading.pair,
                    quoteOrderQty=quote_amount
                )
            except Exception:
                # Fallback to base quantity (validated)
                client.order_market_buy(
                    symbol=self.config.trading.pair,
                    quantity=valid_qty
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
        # Sync latest settings from dashboard
        self.sync_from_settings()
        
        price = self.get_last_price() or 0.0
        
        # DRY RUN mode
        if self.config.system.dry_run:
            if qty > self.paper_balance_eth:
                logger.warning(f"Insufficient paper ETH: {self.paper_balance_eth:.5f} < {qty:.5f}")
                return False
            
            exec_price = self._simulate_execution_price(price, "SELL")
            proceeds = qty * exec_price
            self.paper_balance_eth -= qty
            self.paper_balance_usdt += proceeds
            
            logger.info(
                f"[DRY] SELL {qty:.5f} {self.config.trading.base_asset} "
                f"@ ~{price:.2f} (exec: {exec_price:.2f}, proceeds: {proceeds:.2f})"
            )
            self._log_paper_trade("SELL", qty, price, exec_price)
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
            
            # Validate quantity against Binance LOT_SIZE
            valid_qty = self._validate_quantity(qty)
            if valid_qty <= 0:
                logger.error(f"Sell qty {qty} failed validation")
                return False
            
            client.order_market_sell(
                symbol=self.config.trading.pair,
                quantity=valid_qty
            )
            
            logger.info(f"[LIVE] SELL {qty:.5f} {self.config.trading.base_asset} @ ~{price:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Live sell order failed: {e}")
            return False
    
    def place_smart_buy(self, qty: float, price_hint: float, timeout: int = 30) -> bool:
        """
        Smart buy: tries limit order first, falls back to market if not filled.
        Saves ~0.05-0.1% per trade vs market orders.
        
        Args:
            qty: Quantity to buy
            price_hint: Current market price
            timeout: Seconds to wait for limit fill before market fallback
        """
        if self.config.system.dry_run:
            return self.place_buy(qty, price_hint)
        
        if not (self.config.api.binance_api_key and self.config.api.binance_api_secret):
            logger.error("Binance API credentials not configured")
            return False
        
        try:
            from binance.client import Client
            client = Client(
                self.config.api.binance_api_key,
                self.config.api.binance_api_secret
            )
            
            # Place limit order slightly above best bid
            limit_price = round(price_hint * 1.0001, 2)  # 0.01% above market
            
            order = client.order_limit_buy(
                symbol=self.config.trading.pair,
                quantity=round(qty, 5),
                price=str(limit_price),
                timeInForce='GTC'
            )
            
            order_id = order['orderId']
            logger.info(f"[SMART] Limit BUY placed @ {limit_price:.2f} (order {order_id})")
            
            # Wait for fill
            filled = self._wait_for_order(client, order_id, timeout)
            
            if filled:
                logger.info(f"[SMART] Limit BUY filled @ {limit_price:.2f}")
                return True
            
            # Cancel unfilled limit, fall back to market
            try:
                client.cancel_order(
                    symbol=self.config.trading.pair,
                    orderId=order_id
                )
                logger.info(f"[SMART] Limit order cancelled, falling back to market")
            except Exception:
                pass
            
            # Market fallback
            return self.place_buy(qty, price_hint)
            
        except Exception as e:
            logger.error(f"Smart buy failed: {e}, falling back to market")
            return self.place_buy(qty, price_hint)
    
    def place_smart_sell(self, qty: float, timeout: int = 30) -> bool:
        """
        Smart sell: tries limit order first, falls back to market if not filled.
        """
        if self.config.system.dry_run:
            return self.place_sell(qty)
        
        price = self.get_last_price() or 0.0
        
        if not (self.config.api.binance_api_key and self.config.api.binance_api_secret):
            logger.error("Binance API credentials not configured")
            return False
        
        try:
            from binance.client import Client
            client = Client(
                self.config.api.binance_api_key,
                self.config.api.binance_api_secret
            )
            
            # Place limit slightly below best ask
            limit_price = round(price * 0.9999, 2)  # 0.01% below market
            
            order = client.order_limit_sell(
                symbol=self.config.trading.pair,
                quantity=round(qty, 5),
                price=str(limit_price),
                timeInForce='GTC'
            )
            
            order_id = order['orderId']
            logger.info(f"[SMART] Limit SELL placed @ {limit_price:.2f} (order {order_id})")
            
            filled = self._wait_for_order(client, order_id, timeout)
            
            if filled:
                logger.info(f"[SMART] Limit SELL filled @ {limit_price:.2f}")
                return True
            
            # Cancel and market fallback
            try:
                client.cancel_order(
                    symbol=self.config.trading.pair,
                    orderId=order_id
                )
            except Exception:
                pass
            
            return self.place_sell(qty)
            
        except Exception as e:
            logger.error(f"Smart sell failed: {e}, falling back to market")
            return self.place_sell(qty)
    
    def _wait_for_order(self, client, order_id: int, timeout: int = 30) -> bool:
        """Wait for a limit order to fill, checking every 2 seconds."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                status = client.get_order(
                    symbol=self.config.trading.pair,
                    orderId=order_id
                )
                if status['status'] == 'FILLED':
                    return True
                if status['status'] in ['CANCELED', 'REJECTED', 'EXPIRED']:
                    return False
            except Exception:
                pass
            time.sleep(2)
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
