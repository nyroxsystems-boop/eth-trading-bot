"""
Order Executor — Handles paper and live order placement.
Clean separation between paper mode (local state) and live mode (Binance API).
"""
import logging
import requests
from bot.config import TradingConfig
from bot.state import BotState

logger = logging.getLogger("ethbot.executor")


def execute_buy(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """
    Execute a buy order.

    Paper mode: update state directly
    Live mode: place market order on Binance
    """
    if config.paper_mode:
        return _paper_buy(price, qty, config, state)
    else:
        return _live_buy(price, qty, config, state)


def execute_sell(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """Execute a sell order."""
    if config.paper_mode:
        return _paper_sell(price, qty, config, state)
    else:
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


def _live_buy(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """Place a real market buy on Binance."""
    try:
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

    except Exception as e:
        logger.error(f"[LIVE] BUY failed: {e}")
        return False


def _live_sell(price: float, qty: float, config: TradingConfig, state: BotState) -> bool:
    """Place a real market sell on Binance."""
    try:
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

    except Exception as e:
        logger.error(f"[LIVE] SELL failed: {e}")
        return False


def get_current_price(pair: str = "ETHUSDT") -> float | None:
    """Fetch current price from Binance."""
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": pair},
            timeout=5,
        )
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        return None


def fetch_klines(pair: str = "ETHUSDT", interval: str = "5m", lookback: int = 400) -> "pd.DataFrame":
    """Fetch OHLCV klines from Binance."""
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
