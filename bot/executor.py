from __future__ import annotations
"""
Order Executor — Hardened for Live Trading.

Safety features:
  - Retry with exponential backoff on all API calls
  - Exchange-side Stop-Loss orders (OCO on Binance)
  - Position reconciliation on startup
  - Proper error logging (no bare except: pass)
"""
import logging
import time
import functools
import requests
from bot.config import TradingConfig
from bot.state import BotState

logger = logging.getLogger("ethbot.executor")


# ═══════════════════════════════════════════════════════════════════
#  RETRY DECORATOR — Exponential Backoff
# ═══════════════════════════════════════════════════════════════════

def retry_api(max_retries: int = 3, base_delay: float = 1.0, exceptions=(Exception,)):
    """
    Decorator: retry on failure with exponential backoff.
    Delays: 1s, 2s, 4s (default).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_err = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"[RETRY] {func.__name__} failed (attempt {attempt+1}/{max_retries+1}): "
                            f"{e} — retrying in {delay:.1f}s"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[RETRY] {func.__name__} FINAL FAILURE after {max_retries+1} attempts: {e}"
                        )
            return None  # Safe default for price fetches
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════
#  ORDER EXECUTION
# ═══════════════════════════════════════════════════════════════════

def execute_buy(price: float, qty: float, config: TradingConfig, state: BotState,
                stop_price: float | None = None) -> bool:
    """
    Execute a buy order.

    Paper mode: update state directly
    Live mode: place market order on Binance + exchange stop-loss
    """
    if config.paper_mode:
        return _paper_buy(price, qty, config, state)
    else:
        success = _live_buy(price, qty, config, state)
        # Place exchange-side stop-loss after successful buy
        if success and stop_price and stop_price > 0:
            place_stop_loss_on_exchange(config, state, qty, stop_price)
        return success


def execute_sell(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """Execute a sell order."""
    if config.paper_mode:
        return _paper_sell(price, qty, config, state)
    else:
        # Cancel existing stop-loss before selling
        cancel_exchange_orders(config, state)
        return _live_sell(price, qty, config, state)


def _paper_buy(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """Simulate a buy order."""
    cost = price * qty
    if cost > state.available_balance:
        logger.warning(f"Paper BUY blocked: cost ${cost:.2f} > available ${state.available_balance:.2f}")
        return False

    logger.info(f"[PAPER] BUY {qty:.5f} {config.base_asset} @ ${price:.2f} (${cost:.2f})")
    return True


def _paper_sell(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """Simulate a sell order."""
    logger.info(f"[PAPER] SELL {qty:.5f} {config.base_asset} @ ${price:.2f}")
    return True


@retry_api(max_retries=3, base_delay=1.0)
def _live_buy(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """Place a real market buy on Binance with retry logic."""
    from binance.client import Client
    client = Client(config.binance_api_key, config.binance_api_secret)

    # Check balance
    bal = client.get_asset_balance(asset=config.quote_asset)
    available = float(bal["free"]) if bal else 0.0
    needed = qty * price
    if available < needed * 0.95:
        logger.warning(f"[LIVE] BUY blocked: ${available:.2f} < ${needed:.2f}")
        return False

    # Market buy
    quote_qty = round(qty * price, 2)
    resp = client.order_market_buy(symbol=config.pair, quoteOrderQty=quote_qty)

    # Extract fill price
    fills = resp.get("fills", [])
    if fills:
        total_cost = sum(float(f["price"]) * float(f["qty"]) for f in fills)
        total_qty = sum(float(f["qty"]) for f in fills)
        fill_price = total_cost / total_qty if total_qty > 0 else price
        logger.info(f"[LIVE] BUY {total_qty:.5f} {config.base_asset} @ ${fill_price:.2f}")
    else:
        logger.info(f"[LIVE] BUY {qty:.5f} {config.base_asset} @ ~${price:.2f}")

    return True


@retry_api(max_retries=3, base_delay=1.0)
def _live_sell(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """Place a real market sell on Binance with retry logic."""
    from binance.client import Client
    client = Client(config.binance_api_key, config.binance_api_secret)

    # Check balance
    bal = client.get_asset_balance(asset=config.base_asset)
    available = float(bal["free"]) if bal else 0.0
    if available < qty * 0.95:
        logger.warning(f"[LIVE] SELL blocked: {available:.5f} < {qty:.5f}")
        return False

    resp = client.order_market_sell(symbol=config.pair, quantity=round(qty, 5))
    logger.info(f"[LIVE] SELL {qty:.5f} {config.base_asset} @ ~${price:.2f}")
    return True


# ═══════════════════════════════════════════════════════════════════
#  EXCHANGE STOP-LOSS (OCO Orders)
# ═══════════════════════════════════════════════════════════════════

def place_stop_loss_on_exchange(config: TradingConfig, state: BotState,
                                qty: float, stop_price: float) -> bool:
    """
    Place a STOP_LOSS_LIMIT order on Binance exchange.
    This protects the position even if the bot crashes.
    """
    if config.paper_mode:
        logger.info(f"[PAPER] Exchange SL would be placed @ ${stop_price:.2f}")
        return True

    try:
        from binance.client import Client
        client = Client(config.binance_api_key, config.binance_api_secret)

        # Stop-loss limit price slightly below stop trigger (0.1% slippage allowance)
        limit_price = round(stop_price * 0.999, 2)

        resp = client.create_order(
            symbol=config.pair,
            side="SELL",
            type="STOP_LOSS_LIMIT",
            timeInForce="GTC",
            quantity=round(qty, 5),
            price=str(limit_price),
            stopPrice=str(round(stop_price, 2)),
        )
        order_id = resp.get("orderId", "?")
        logger.info(
            f"[LIVE] 🛡️ Exchange SL placed: #{order_id} "
            f"trigger=${stop_price:.2f} limit=${limit_price:.2f} qty={qty:.5f}"
        )
        return True

    except Exception as e:
        logger.error(f"[LIVE] Exchange SL FAILED: {e} — position unprotected!")
        return False


def cancel_exchange_orders(config: TradingConfig, state: BotState) -> bool:
    """Cancel all open orders for the pair (cleanup before sell)."""
    if config.paper_mode:
        return True

    try:
        from binance.client import Client
        client = Client(config.binance_api_key, config.binance_api_secret)

        open_orders = client.get_open_orders(symbol=config.pair)
        for order in open_orders:
            try:
                client.cancel_order(symbol=config.pair, orderId=order["orderId"])
                logger.info(f"[LIVE] Cancelled order #{order['orderId']} ({order.get('type', '?')})")
            except Exception as e:
                logger.warning(f"[LIVE] Cancel order #{order['orderId']} failed: {e}")

        return True

    except Exception as e:
        logger.error(f"[LIVE] Cancel orders failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#  POSITION RECONCILIATION
# ═══════════════════════════════════════════════════════════════════

def reconcile_positions(config: TradingConfig, state: BotState) -> dict:
    """
    Compare bot state with actual Binance positions on startup.
    Returns: { "status": "ok"|"mismatch", "details": [...] }
    """
    result = {"status": "ok", "details": [], "ghost_positions": 0}

    if config.paper_mode:
        logger.info("[RECON] Paper mode — skipping reconciliation")
        return result

    try:
        from binance.client import Client
        client = Client(config.binance_api_key, config.binance_api_secret)

        # Get actual Binance balance for our base asset
        bal = client.get_asset_balance(asset=config.base_asset)
        actual_qty = float(bal["free"]) + float(bal.get("locked", 0)) if bal else 0.0

        bot_thinks_qty = state.position_qty if state.in_position else 0.0

        # Check for mismatches
        if state.in_position and actual_qty < bot_thinks_qty * 0.5:
            result["status"] = "mismatch"
            result["ghost_positions"] = 1
            result["details"].append(
                f"⚠️ GHOST POSITION: Bot thinks {bot_thinks_qty:.5f} {config.base_asset} "
                f"but Binance shows {actual_qty:.5f}"
            )
            logger.warning(f"[RECON] Ghost position detected! Bot={bot_thinks_qty:.5f} Exchange={actual_qty:.5f}")
            # Auto-fix: clear the ghost position
            state.in_position = False
            state.position_qty = 0.0
            state.entry_price = 0.0
            logger.info("[RECON] Ghost position cleared from bot state")

        elif not state.in_position and actual_qty > 0.001:
            result["status"] = "mismatch"
            result["details"].append(
                f"⚠️ ORPHAN POSITION: Bot thinks no position but Binance has "
                f"{actual_qty:.5f} {config.base_asset}"
            )
            logger.warning(f"[RECON] Orphan position on exchange: {actual_qty:.5f} {config.base_asset}")

        else:
            result["details"].append("✅ Positions match")
            logger.info(f"[RECON] ✅ Positions match: bot={bot_thinks_qty:.5f} exchange={actual_qty:.5f}")

        # Check for stale stop-loss orders
        open_orders = client.get_open_orders(symbol=config.pair)
        if open_orders and not state.in_position:
            for order in open_orders:
                try:
                    client.cancel_order(symbol=config.pair, orderId=order["orderId"])
                    result["details"].append(f"Cancelled stale order #{order['orderId']}")
                except Exception as e:
                    logger.warning(f"[RECON] Cancel stale order failed: {e}")

    except Exception as e:
        result["status"] = "error"
        result["details"].append(f"Reconciliation error: {e}")
        logger.error(f"[RECON] Failed: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════
#  MARKET DATA (with retry)
# ═══════════════════════════════════════════════════════════════════

@retry_api(max_retries=3, base_delay=0.5)
def get_current_price(pair: str = "ETHUSDT") -> float | None:
    """Fetch current price from Binance (with retry)."""
    resp = requests.get(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": pair},
        timeout=5,
    )
    resp.raise_for_status()
    return float(resp.json()["price"])


@retry_api(max_retries=3, base_delay=1.0)
def fetch_klines(pair: str = "ETHUSDT", interval: str = "5m", lookback: int = 400) -> "pd.DataFrame":
    """Fetch OHLCV klines from Binance (with retry)."""
    import pandas as pd

    base = "https://api.binance.com/api/v3/klines"
    params = {"symbol": pair, "interval": interval, "limit": min(lookback, 1000)}

    resp = requests.get(base, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        raise RuntimeError("No klines data received from Binance")

    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qv", "trades", "taker_base", "taker_quote", "ignore"
    ])

    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)

    df["time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df[["time", "open", "high", "low", "close", "volume"]]


# ═══════════════════════════════════════════════════════════════════
#  EMERGENCY STOP — Close all positions
# ═══════════════════════════════════════════════════════════════════

def emergency_close_all(config: TradingConfig, state: BotState) -> dict:
    """
    Emergency: close all open positions and cancel all orders.
    Called by kill-switch API endpoint.
    """
    result = {"closed": 0, "cancelled": 0, "errors": []}

    if config.paper_mode:
        if state.in_position:
            state.in_position = False
            state.position_qty = 0.0
            result["closed"] = 1
            logger.info("[EMERGENCY] Paper position closed")
        return result

    try:
        from binance.client import Client
        client = Client(config.binance_api_key, config.binance_api_secret)

        # Cancel all open orders first
        try:
            open_orders = client.get_open_orders(symbol=config.pair)
            for order in open_orders:
                try:
                    client.cancel_order(symbol=config.pair, orderId=order["orderId"])
                    result["cancelled"] += 1
                except Exception as e:
                    result["errors"].append(f"Cancel #{order['orderId']}: {e}")
        except Exception as e:
            result["errors"].append(f"Get orders: {e}")

        # Market sell everything
        bal = client.get_asset_balance(asset=config.base_asset)
        available = float(bal["free"]) if bal else 0.0
        if available > 0.001:
            try:
                client.order_market_sell(symbol=config.pair, quantity=round(available, 5))
                result["closed"] = 1
                logger.info(f"[EMERGENCY] Sold {available:.5f} {config.base_asset}")
            except Exception as e:
                result["errors"].append(f"Emergency sell: {e}")

        # Clear bot state
        state.in_position = False
        state.position_qty = 0.0
        state.entry_price = 0.0

    except Exception as e:
        result["errors"].append(f"Emergency close: {e}")
        logger.error(f"[EMERGENCY] CRITICAL FAILURE: {e}")

    return result
