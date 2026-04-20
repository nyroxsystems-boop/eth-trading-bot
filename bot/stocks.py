"""
Stock Executor — Handles US stock trading via Alpaca Markets API.

Supports:
- Paper & Live trading modes
- Historical bar data (OHLCV) like Binance klines
- Current price fetching
- Market orders (buy/sell)

Requires: pip install alpaca-py
Environment variables:
  ALPACA_API_KEY
  ALPACA_SECRET_KEY
  ALPACA_PAPER=True  (default: paper mode)
"""
import os
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("ethbot.stocks")

# ── Alpaca Configuration ──────────────────────────────────────────────────

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "True").lower() in ("true", "1", "yes")

# Default US stock universe (Top by volume + relevance)
DEFAULT_STOCK_PAIRS = [
    {"pair": "SPY", "base": "SPY", "market": "stock", "name": "S&P 500 ETF"},
    {"pair": "QQQ", "base": "QQQ", "market": "stock", "name": "Nasdaq 100 ETF"},
    {"pair": "AAPL", "base": "AAPL", "market": "stock", "name": "Apple"},
    {"pair": "MSFT", "base": "MSFT", "market": "stock", "name": "Microsoft"},
    {"pair": "NVDA", "base": "NVDA", "market": "stock", "name": "NVIDIA"},
    {"pair": "TSLA", "base": "TSLA", "market": "stock", "name": "Tesla"},
    {"pair": "AMZN", "base": "AMZN", "market": "stock", "name": "Amazon"},
    {"pair": "META", "base": "META", "market": "stock", "name": "Meta"},
    {"pair": "GOOG", "base": "GOOG", "market": "stock", "name": "Alphabet"},
    {"pair": "AMD", "base": "AMD", "market": "stock", "name": "AMD"},
]


def is_alpaca_configured() -> bool:
    """Check if Alpaca API keys are set."""
    return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)


def is_market_open() -> bool:
    """
    Check if US stock market is currently open.
    NYSE/NASDAQ: Mon-Fri, 9:30 AM - 4:00 PM ET
    """
    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=ALPACA_PAPER)
        clock = client.get_clock()
        return clock.is_open
    except Exception:
        # Fallback: simple timezone check
        import pytz
        et = pytz.timezone("US/Eastern")
        now = datetime.now(et)
        # Weekday check (0=Mon, 6=Sun)
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=30, second=0)
        market_close = now.replace(hour=16, minute=0, second=0)
        return market_open <= now <= market_close


def get_stock_price(symbol: str) -> float:
    """Fetch current stock price from Alpaca."""
    if not is_alpaca_configured():
        return _fallback_price(symbol)

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest

        client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trade = client.get_stock_latest_trade(req)

        if isinstance(trade, dict):
            return float(trade[symbol].price)
        return float(trade.price)

    except Exception as e:
        logger.warning(f"Alpaca price fetch failed for {symbol}: {e}")
        return _fallback_price(symbol)


def _fallback_price(symbol: str) -> float:
    """Get price from free Yahoo Finance API as fallback."""
    try:
        import urllib.request
        import json
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EthBot/3.0)"
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return float(price)
    except Exception as e:
        logger.error(f"Yahoo price fallback failed for {symbol}: {e}")
        return 0.0


def fetch_stock_klines(symbol: str, interval: str = "5m", lookback: int = 200):
    """
    Fetch historical OHLCV bars for a stock from Alpaca.
    Returns pandas DataFrame matching Binance klines format.
    """

    # If Alpaca not configured, use Yahoo Finance
    if not is_alpaca_configured():
        return _yahoo_klines(symbol, interval, lookback)

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

        # Map interval string to Alpaca TimeFrame
        tf_map = {
            "1m": TimeFrame.Minute,
            "5m": TimeFrame(5, "Min"),
            "15m": TimeFrame(15, "Min"),
            "1h": TimeFrame.Hour,
            "1d": TimeFrame.Day,
        }
        timeframe = tf_map.get(interval, TimeFrame(5, "Min"))

        # Calculate start time
        days_back = max(3, lookback // 78)  # ~78 5min bars per trading day
        start = datetime.now(timezone.utc) - timedelta(days=days_back)

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
            limit=lookback,
        )
        bars = client.get_stock_bars(req)
        df = bars.df.reset_index()

        # Normalize column names to match our format
        df = df.rename(columns={"timestamp": "time"})
        df = df[["time", "open", "high", "low", "close", "volume"]]
        df = df.tail(lookback)

        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)

        return df

    except Exception as e:
        logger.warning(f"Alpaca bars fetch failed for {symbol}: {e}")
        return _yahoo_klines(symbol, interval, lookback)


def _yahoo_klines(symbol: str, interval: str = "5m", lookback: int = 200):
    """Fallback: get OHLCV from Yahoo Finance (no API key needed)."""
    import pandas as pd
    import urllib.request
    import json

    # Yahoo interval mapping
    yf_interval = {
        "1m": "1m", "5m": "5m", "15m": "15m",
        "1h": "1h", "1d": "1d",
    }.get(interval, "5m")

    # Range mapping
    yf_range = {
        "1m": "1d", "5m": "5d", "15m": "5d",
        "1h": "1mo", "1d": "1y",
    }.get(interval, "5d")

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={yf_interval}&range={yf_range}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EthBot/3.0)"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())

        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quotes = result["indicators"]["quote"][0]

        df = pd.DataFrame({
            "time": pd.to_datetime(timestamps, unit="s"),
            "open": quotes["open"],
            "high": quotes["high"],
            "low": quotes["low"],
            "close": quotes["close"],
            "volume": quotes["volume"],
        })

        df = df.dropna()
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)

        return df.tail(lookback)

    except Exception as e:
        logger.error(f"Yahoo klines failed for {symbol}: {e}")
        return None


def execute_stock_buy(symbol: str, qty: float, paper: bool = True) -> bool:
    """Execute a stock buy order via Alpaca."""
    if paper or not is_alpaca_configured():
        logger.info(f"[PAPER-STOCK] BUY {qty:.2f} {symbol}")
        return True

    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=ALPACA_PAPER)
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        result = client.submit_order(order)
        logger.info(f"[LIVE-STOCK] BUY {qty} {symbol} → {result.status}")
        return True

    except Exception as e:
        logger.error(f"[STOCK] BUY failed {symbol}: {e}")
        return False


def execute_stock_sell(symbol: str, qty: float, paper: bool = True) -> bool:
    """Execute a stock sell order via Alpaca."""
    if paper or not is_alpaca_configured():
        logger.info(f"[PAPER-STOCK] SELL {qty:.2f} {symbol}")
        return True

    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=ALPACA_PAPER)
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        result = client.submit_order(order)
        logger.info(f"[LIVE-STOCK] SELL {qty} {symbol} → {result.status}")
        return True

    except Exception as e:
        logger.error(f"[STOCK] SELL failed {symbol}: {e}")
        return False


def get_top_stocks(n: int = 10) -> list:
    """
    Get top N stocks for trading.
    Uses Alpaca most-active endpoint if available, else defaults.
    """
    if not is_alpaca_configured():
        return DEFAULT_STOCK_PAIRS[:n]

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import MostActivesRequest

        client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        most_active = client.get_most_actives(MostActivesRequest(top=n))

        pairs = []
        for stock in most_active.most_actives:
            pairs.append({
                "pair": stock.symbol,
                "base": stock.symbol,
                "market": "stock",
                "name": stock.symbol,
            })
        return pairs if pairs else DEFAULT_STOCK_PAIRS[:n]

    except Exception:
        return DEFAULT_STOCK_PAIRS[:n]


# ─── CLI Test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("\n" + "=" * 60)
    print("   ALPACA STOCK TRADING MODULE")
    print("=" * 60)

    print(f"\nAlpaca configured: {is_alpaca_configured()}")

    stocks = DEFAULT_STOCK_PAIRS
    for s in stocks:
        price = get_stock_price(s["pair"])
        print(f"  {s['pair']:>6} ({s['name']:<12}) → ${price:,.2f}")

    print(f"\nMarket open: {is_market_open()}")
    print("=" * 60)
