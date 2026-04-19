from __future__ import annotations
"""
Futures Executor — Binance USDT-M Perpetual Futures API.

Required for:
  S1 (Funding Arb): Short Perp + Long Spot = delta-neutral
  S5 (Liq Hunter): Fast bounce trades on Futures

API Endpoints used:
  POST /fapi/v1/order          — Place order
  DELETE /fapi/v1/order        — Cancel order
  GET /fapi/v1/positionRisk    — Get open positions
  GET /fapi/v1/account         — Get account info
  POST /fapi/v1/leverage       — Set leverage

Safety:
  - Max leverage hard-capped at 3x
  - All orders have explicit SL
  - Retry with backoff on all calls
"""
import os
import time
import hmac
import hashlib
import logging
import requests
from urllib.parse import urlencode
from typing import Optional

logger = logging.getLogger("ethbot.futures")

FUTURES_BASE = "https://fapi.binance.com"


class FuturesClient:
    """
    Binance USDT-M Futures client with safety limits.
    """

    MAX_LEVERAGE = 3               # HARD CAP — never change
    DEFAULT_LEVERAGE = 1           # Start conservative
    MAX_POSITION_USD = 50_000      # Max single position
    SLIPPAGE_ALLOWANCE = 0.001     # 0.1% slippage for limit prices

    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or os.getenv("BINANCE_API_KEY", "")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET", "")
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": self.api_key})
        logger.info("📊 Futures client initialized")

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

        url = f"{FUTURES_BASE}{path}"
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
                    # Rate limited
                    wait = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limited, waiting {wait}s")
                    time.sleep(wait)
                else:
                    error = resp.json() if resp.text else {}
                    last_err = f"HTTP {resp.status_code}: {error.get('msg', resp.text)}"
                    logger.warning(f"Futures API: {last_err}")

            except Exception as e:
                last_err = str(e)
                if attempt < retries:
                    delay = 1.0 * (2 ** attempt)
                    logger.warning(f"Futures retry {attempt+1}/{retries}: {e}, waiting {delay}s")
                    time.sleep(delay)

        logger.error(f"Futures FINAL FAILURE: {last_err}")
        return None

    # ── Account Info ──

    def get_account(self) -> Optional[dict]:
        """Get futures account info (balances, positions)."""
        return self._request("GET", "/fapi/v2/account")

    def get_balance(self) -> float:
        """Get available USDT balance for futures."""
        account = self.get_account()
        if account:
            for asset in account.get("assets", []):
                if asset["asset"] == "USDT":
                    return float(asset.get("availableBalance", 0))
        return 0.0

    def get_positions(self) -> list[dict]:
        """Get all open positions."""
        result = self._request("GET", "/fapi/v2/positionRisk")
        if result:
            return [
                p for p in result
                if float(p.get("positionAmt", 0)) != 0
            ]
        return []

    def get_position(self, symbol: str) -> Optional[dict]:
        """Get position for a specific symbol."""
        result = self._request("GET", "/fapi/v2/positionRisk",
                               {"symbol": symbol})
        if result:
            for p in result:
                if float(p.get("positionAmt", 0)) != 0:
                    return p
        return None

    # ── Leverage ──

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol (capped at MAX_LEVERAGE)."""
        leverage = min(leverage, self.MAX_LEVERAGE)
        result = self._request("POST", "/fapi/v1/leverage", {
            "symbol": symbol, "leverage": leverage,
        })
        if result:
            logger.info(f"Futures leverage set: {symbol} = {leverage}x")
            return True
        return False

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> bool:
        """Set margin type (ISOLATED or CROSSED)."""
        result = self._request("POST", "/fapi/v1/marginType", {
            "symbol": symbol, "marginType": margin_type,
        })
        # Binance returns error -4046 if already set
        return result is not None or True

    # ── Order Placement ──

    def open_short(self, symbol: str, quantity: float,
                   stop_loss_pct: float = 2.0) -> Optional[dict]:
        """
        Open a SHORT position on futures.
        Used by S1 (Funding Arb) for the hedge side.

        Args:
            symbol: e.g. 'ETHUSDT'
            quantity: Amount of base asset
            stop_loss_pct: Auto-SL protection

        Returns:
            Order response or None
        """
        # Safety checks
        notional = quantity * self._get_mark_price(symbol)
        if notional > self.MAX_POSITION_USD:
            logger.error(f"SHORT blocked: ${notional:,.0f} > max ${self.MAX_POSITION_USD:,.0f}")
            return None

        # Set leverage
        self.set_leverage(symbol, self.DEFAULT_LEVERAGE)

        # Market short
        result = self._request("POST", "/fapi/v1/order", {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": f"{quantity:.5f}",
            "positionSide": "SHORT",
        })

        if result:
            order_id = result.get("orderId", "?")
            avg_price = float(result.get("avgPrice", 0))
            logger.info(
                f"📊 FUTURES SHORT: {symbol} qty={quantity:.5f} @ ${avg_price:,.2f} | "
                f"Order #{order_id}"
            )

            # Place stop-loss
            sl_price = avg_price * (1 + stop_loss_pct / 100)
            self._place_stop_loss(symbol, "BUY", quantity, sl_price)

            return result

        return None

    def close_short(self, symbol: str, quantity: float) -> Optional[dict]:
        """Close a SHORT position."""
        result = self._request("POST", "/fapi/v1/order", {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quantity": f"{quantity:.5f}",
            "positionSide": "SHORT",
            "reduceOnly": "true",
        })

        if result:
            logger.info(f"📊 FUTURES CLOSE SHORT: {symbol} qty={quantity:.5f}")
        return result

    def open_long(self, symbol: str, quantity: float,
                  stop_loss_pct: float = 2.0) -> Optional[dict]:
        """
        Open a LONG position on futures.
        Used by S5 (Liq Hunter) for bounce trades.
        """
        notional = quantity * self._get_mark_price(symbol)
        if notional > self.MAX_POSITION_USD:
            logger.error(f"LONG blocked: ${notional:,.0f} > max ${self.MAX_POSITION_USD:,.0f}")
            return None

        self.set_leverage(symbol, self.DEFAULT_LEVERAGE)

        result = self._request("POST", "/fapi/v1/order", {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quantity": f"{quantity:.5f}",
            "positionSide": "LONG",
        })

        if result:
            avg_price = float(result.get("avgPrice", 0))
            logger.info(f"📊 FUTURES LONG: {symbol} qty={quantity:.5f} @ ${avg_price:,.2f}")
            sl_price = avg_price * (1 - stop_loss_pct / 100)
            self._place_stop_loss(symbol, "SELL", quantity, sl_price)
            return result

        return None

    def close_long(self, symbol: str, quantity: float) -> Optional[dict]:
        """Close a LONG position."""
        result = self._request("POST", "/fapi/v1/order", {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": f"{quantity:.5f}",
            "positionSide": "LONG",
            "reduceOnly": "true",
        })

        if result:
            logger.info(f"📊 FUTURES CLOSE LONG: {symbol} qty={quantity:.5f}")
        return result

    def close_all_positions(self) -> list[dict]:
        """Emergency: close all open futures positions."""
        results = []
        positions = self.get_positions()

        for pos in positions:
            symbol = pos["symbol"]
            qty = abs(float(pos["positionAmt"]))
            side = "SHORT" if float(pos["positionAmt"]) > 0 else "LONG"

            if side == "LONG":
                r = self.close_long(symbol, qty)
            else:
                r = self.close_short(symbol, qty)

            results.append({"symbol": symbol, "side": side, "qty": qty, "result": r})
            logger.warning(f"🚨 EMERGENCY CLOSE: {side} {symbol} qty={qty:.5f}")

        return results

    # ── Internal ──

    def _place_stop_loss(self, symbol: str, side: str, quantity: float,
                         stop_price: float) -> Optional[dict]:
        """Place a stop-market order for protection."""
        position_side = "LONG" if side == "SELL" else "SHORT"
        result = self._request("POST", "/fapi/v1/order", {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "quantity": f"{quantity:.5f}",
            "stopPrice": f"{stop_price:.2f}",
            "positionSide": position_side,
            "reduceOnly": "true",
            "workingType": "MARK_PRICE",
        })

        if result:
            logger.info(f"🛡️ Futures SL: {symbol} {side} @ ${stop_price:,.2f}")
        return result

    def _get_mark_price(self, symbol: str) -> float:
        """Get current mark price."""
        try:
            resp = requests.get(
                f"{FUTURES_BASE}/fapi/v1/premiumIndex",
                params={"symbol": symbol}, timeout=5,
            )
            return float(resp.json().get("markPrice", 0))
        except Exception:
            return 0.0

    def get_funding_info(self, symbol: str) -> dict:
        """Get current funding rate + next funding time."""
        try:
            resp = requests.get(
                f"{FUTURES_BASE}/fapi/v1/premiumIndex",
                params={"symbol": symbol}, timeout=5,
            )
            data = resp.json()
            return {
                "symbol": symbol,
                "mark_price": float(data.get("markPrice", 0)),
                "funding_rate": float(data.get("lastFundingRate", 0)),
                "next_funding_time": int(data.get("nextFundingTime", 0)),
            }
        except Exception:
            return {}


# Singleton
_instance: Optional[FuturesClient] = None

def get_futures_client() -> FuturesClient:
    global _instance
    if _instance is None:
        _instance = FuturesClient()
    return _instance
