from __future__ import annotations
"""
Margin Executor — Binance Cross Margin API.

Replaces futures_executor.py for Germany (Futures not available on Binance DE).
Uses Binance Margin Trading to enable shorting via asset borrowing.

API Endpoints used:
  POST /sapi/v1/margin/order     — Place margin order (with AUTO_BORROW_REPAY)
  DELETE /sapi/v1/margin/order   — Cancel margin order
  GET /sapi/v1/margin/account    — Get cross margin account info
  POST /sapi/v1/margin/transfer  — Transfer between spot ↔ margin
  POST /sapi/v1/margin/loan      — Borrow asset
  POST /sapi/v1/margin/repay     — Repay borrowed asset

Safety:
  - Max position hard-capped at $50k
  - All shorts use AUTO_BORROW_REPAY (auto-borrows + auto-repays)
  - Retry with exponential backoff on all calls
  - autoRepayAtCancel=true (cancel = auto-repay debt)
"""
import os
import time
import hmac
import hashlib
import logging
import requests
from urllib.parse import urlencode
from typing import Optional

logger = logging.getLogger("ethbot.margin")

MARGIN_BASE = "https://api.binance.com"


class MarginClient:
    """
    Binance Cross Margin client with safety limits.
    Enables shorting via borrowing on the spot margin account.
    """

    MAX_POSITION_USD = 50_000      # Max single position
    SLIPPAGE_ALLOWANCE = 0.001     # 0.1% slippage for limit prices

    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or os.getenv("BINANCE_API_KEY", "")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET", "")
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": self.api_key})
        logger.info("📊 Margin client initialized (Cross Margin)")

    def _sign(self, params: dict) -> dict:
        """Add timestamp + HMAC-SHA256 signature."""
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(self, method: str, path: str, params: dict = None,
                 signed: bool = True, retries: int = 3) -> Optional[dict]:
        """Make API request with retry."""
        params = params or {}
        if signed:
            params = self._sign(params)

        url = f"{MARGIN_BASE}{path}"
        last_err = None

        for attempt in range(retries + 1):
            try:
                if method == "GET":
                    resp = self._session.get(url, params=params, timeout=10)
                elif method == "POST":
                    resp = self._session.post(url, params=params, timeout=10)
                elif method == "DELETE":
                    resp = self._session.delete(url, params=params, timeout=10)
                else:
                    raise ValueError(f"Unknown method: {method}")

                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limited, waiting {wait}s")
                    time.sleep(wait)
                else:
                    error = resp.json() if resp.text else {}
                    last_err = f"HTTP {resp.status_code}: {error.get('msg', resp.text)}"
                    logger.warning(f"Margin API: {last_err}")

            except Exception as e:
                last_err = str(e)
                if attempt < retries:
                    delay = 1.0 * (2 ** attempt)
                    logger.warning(f"Margin retry {attempt+1}/{retries}: {e}, waiting {delay}s")
                    time.sleep(delay)

        logger.error(f"Margin FINAL FAILURE: {last_err}")
        return None

    # ── Account Info ──

    def get_account(self) -> Optional[dict]:
        """Get cross margin account info (balances, borrowed amounts)."""
        return self._request("GET", "/sapi/v1/margin/account")

    def get_balance(self, asset: str = "USDT") -> float:
        """Get available balance for an asset in margin account."""
        account = self.get_account()
        if account:
            for user_asset in account.get("userAssets", []):
                if user_asset["asset"] == asset:
                    return float(user_asset.get("free", 0))
        return 0.0

    def get_borrowed(self, asset: str) -> float:
        """Get borrowed amount for an asset."""
        account = self.get_account()
        if account:
            for user_asset in account.get("userAssets", []):
                if user_asset["asset"] == asset:
                    return float(user_asset.get("borrowed", 0))
        return 0.0

    def get_margin_level(self) -> float:
        """Get current margin level (must stay > 1.3 to avoid liquidation)."""
        account = self.get_account()
        if account:
            return float(account.get("marginLevel", 0))
        return 0.0

    # ── Transfer: Spot ↔ Margin ──

    def transfer_to_margin(self, asset: str, amount: float) -> bool:
        """Transfer asset from spot to cross margin account."""
        result = self._request("POST", "/sapi/v1/margin/transfer", {
            "asset": asset,
            "amount": f"{amount:.8f}",
            "type": 1,  # 1 = spot → margin
        })
        if result:
            logger.info(f"📊 Transfer to margin: {amount:.8f} {asset}")
            return True
        return False

    def transfer_to_spot(self, asset: str, amount: float) -> bool:
        """Transfer asset from cross margin to spot account."""
        result = self._request("POST", "/sapi/v1/margin/transfer", {
            "asset": asset,
            "amount": f"{amount:.8f}",
            "type": 2,  # 2 = margin → spot
        })
        if result:
            logger.info(f"📊 Transfer to spot: {amount:.8f} {asset}")
            return True
        return False

    # ── Order Placement ──

    def open_short(self, symbol: str, quantity: float,
                   stop_loss_pct: float = 2.0) -> Optional[dict]:
        """
        Open a SHORT position via margin borrowing.

        Flow: AUTO_BORROW_REPAY borrows the base asset → sells it at market.
        To close: buy it back with AUTO_REPAY.

        Args:
            symbol: e.g. 'ETHUSDT'
            quantity: Amount of base asset to short
            stop_loss_pct: Auto-SL protection

        Returns:
            Order response or None
        """
        # Safety: check notional value
        price = self._get_price(symbol)
        notional = quantity * price
        if notional > self.MAX_POSITION_USD:
            logger.error(f"SHORT blocked: ${notional:,.0f} > max ${self.MAX_POSITION_USD:,.0f}")
            return None

        # Check margin level is safe (>2.0 for new positions)
        margin_level = self.get_margin_level()
        if margin_level > 0 and margin_level < 2.0:
            logger.error(f"SHORT blocked: margin level {margin_level:.2f} too low (min 2.0)")
            return None

        # Place margin sell order with auto-borrow
        result = self._request("POST", "/sapi/v1/margin/order", {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": f"{quantity:.5f}",
            "sideEffectType": "AUTO_BORROW_REPAY",
            "autoRepayAtCancel": "true",
        })

        if result:
            order_id = result.get("orderId", "?")
            fills = result.get("fills", [])
            avg_price = price
            if fills:
                total_cost = sum(float(f["price"]) * float(f["qty"]) for f in fills)
                total_qty = sum(float(f["qty"]) for f in fills)
                avg_price = total_cost / total_qty if total_qty > 0 else price

            logger.info(
                f"📊 MARGIN SHORT: {symbol} qty={quantity:.5f} @ ${avg_price:,.2f} | "
                f"Order #{order_id}"
            )

            # Place stop-loss (buy back at higher price)
            sl_price = avg_price * (1 + stop_loss_pct / 100)
            self._place_stop_loss(symbol, "BUY", quantity, sl_price)

            return result

        return None

    def close_short(self, symbol: str, quantity: float) -> Optional[dict]:
        """
        Close a SHORT position (buy back + auto-repay borrowed asset).
        """
        result = self._request("POST", "/sapi/v1/margin/order", {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quantity": f"{quantity:.5f}",
            "sideEffectType": "AUTO_BORROW_REPAY",
        })

        if result:
            logger.info(f"📊 MARGIN CLOSE SHORT: {symbol} qty={quantity:.5f}")
        return result

    def open_long(self, symbol: str, quantity: float,
                  stop_loss_pct: float = 2.0) -> Optional[dict]:
        """
        Open a LONG position on margin (with optional borrowing).
        Used by S5 (Liq Hunter) for bounce trades.
        """
        price = self._get_price(symbol)
        notional = quantity * price
        if notional > self.MAX_POSITION_USD:
            logger.error(f"LONG blocked: ${notional:,.0f} > max ${self.MAX_POSITION_USD:,.0f}")
            return None

        result = self._request("POST", "/sapi/v1/margin/order", {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quantity": f"{quantity:.5f}",
            "sideEffectType": "AUTO_BORROW_REPAY",
            "autoRepayAtCancel": "true",
        })

        if result:
            fills = result.get("fills", [])
            avg_price = price
            if fills:
                total_cost = sum(float(f["price"]) * float(f["qty"]) for f in fills)
                total_qty = sum(float(f["qty"]) for f in fills)
                avg_price = total_cost / total_qty if total_qty > 0 else price

            logger.info(f"📊 MARGIN LONG: {symbol} qty={quantity:.5f} @ ${avg_price:,.2f}")

            sl_price = avg_price * (1 - stop_loss_pct / 100)
            self._place_stop_loss(symbol, "SELL", quantity, sl_price)
            return result

        return None

    def close_long(self, symbol: str, quantity: float) -> Optional[dict]:
        """Close a LONG position (sell + auto-repay if borrowed)."""
        result = self._request("POST", "/sapi/v1/margin/order", {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": f"{quantity:.5f}",
            "sideEffectType": "AUTO_BORROW_REPAY",
        })

        if result:
            logger.info(f"📊 MARGIN CLOSE LONG: {symbol} qty={quantity:.5f}")
        return result

    def close_all_positions(self) -> list[dict]:
        """Emergency: repay all borrowed assets and close positions."""
        results = []
        account = self.get_account()
        if not account:
            return results

        for user_asset in account.get("userAssets", []):
            borrowed = float(user_asset.get("borrowed", 0))
            interest = float(user_asset.get("interest", 0))
            asset = user_asset["asset"]

            if borrowed > 0:
                # Repay all borrowed + interest
                total_owed = borrowed + interest
                try:
                    result = self._request("POST", "/sapi/v1/margin/repay", {
                        "asset": asset,
                        "amount": f"{total_owed:.8f}",
                    })
                    results.append({
                        "asset": asset, "action": "REPAY",
                        "amount": total_owed, "result": result
                    })
                    logger.warning(f"🚨 EMERGENCY REPAY: {total_owed:.8f} {asset}")
                except Exception as e:
                    logger.error(f"Emergency repay {asset}: {e}")

        return results

    # ── Internal ──

    def _place_stop_loss(self, symbol: str, side: str, quantity: float,
                         stop_price: float) -> Optional[dict]:
        """Place a stop-loss order on margin."""
        limit_price = stop_price * (0.999 if side == "SELL" else 1.001)
        result = self._request("POST", "/sapi/v1/margin/order", {
            "symbol": symbol,
            "side": side,
            "type": "STOP_LOSS_LIMIT",
            "timeInForce": "GTC",
            "quantity": f"{quantity:.5f}",
            "price": f"{limit_price:.2f}",
            "stopPrice": f"{stop_price:.2f}",
            "sideEffectType": "AUTO_BORROW_REPAY",
        })

        if result:
            logger.info(f"🛡️ Margin SL: {symbol} {side} @ ${stop_price:,.2f}")
        return result

    def _get_price(self, symbol: str) -> float:
        """Get current price from Binance Spot API."""
        try:
            resp = requests.get(
                f"{MARGIN_BASE}/api/v3/ticker/price",
                params={"symbol": symbol}, timeout=5,
            )
            return float(resp.json().get("price", 0))
        except Exception:
            return 0.0


# Singleton
_instance: Optional[MarginClient] = None

def get_margin_client() -> MarginClient:
    global _instance
    if _instance is None:
        _instance = MarginClient()
    return _instance
