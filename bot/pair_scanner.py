"""
Dynamic Pair Scanner — Fetches top-volume USDT pairs from Binance.

Instead of hardcoded pairs, the bot now dynamically selects the most
actively traded pairs on Binance, ensuring it always trades where
liquidity and opportunity are highest.
"""
import json
import time
import logging
import urllib.request
from typing import List, Dict
from pathlib import Path

logger = logging.getLogger("ethbot.pair_scanner")

# Cache settings
CACHE_DIR = Path("logs/intel_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PAIR_CACHE_TTL = 3600  # Refresh top pairs every 1 hour

# Blacklist: leveraged tokens, stablecoins, and low-quality pairs
BLACKLIST = {
    # Leveraged tokens
    "BTCUPUSDT", "BTCDOWNUSDT", "ETHUPUSDT", "ETHDOWNUSDT",
    "BNBUPUSDT", "BNBDOWNUSDT", "ADAUPUSDT", "ADADOWNUSDT",
    "XRPUPUSDT", "XRPDOWNUSDT", "DOTUPUSDT", "DOTDOWNUSDT",
    "LINKUPUSDT", "LINKDOWNUSDT", "TRXUPUSDT", "TRXDOWNUSDT",
    "EOSUPUSDT", "EOSDOWNUSDT", "LTCUPUSDT", "LTCDOWNUSDT",
    "UNIUPUSDT", "UNIDOWNUSDT", "SXPUPUSDT", "SXPDOWNUSDT",
    "FILUSDT", "FILUPUSDT", "FILDOWNUSDT",
    "XLMUPUSDT", "XLMDOWNUSDT", "AAVEUPUSDT", "AAVEDOWNUSDT",
    "1000SHIBUPUSDT", "1000SHIBDOWNUSDT",
    # Stablecoins (don't trade stable-to-stable)
    "BUSDUSDT", "USDCUSDT", "TUSDUSDT", "DAIUSDT", "FDUSDUSDT",
    "USDPUSDT", "EURUSDT", "GBPUSDT",
    # Wrapped tokens
    "WBTCUSDT", "WBETHUSDT",
}

# Minimum 24h volume in USDT to be eligible
MIN_VOLUME_USDT = 10_000_000  # $10M minimum daily volume


def fetch_all_binance_pairs() -> List[Dict]:
    """
    Fetch all active USDT spot pairs from Binance with 24h volume.
    Returns sorted list by volume (highest first).
    """
    try:
        # Get exchange info for active symbols
        url = "https://api.binance.com/api/v3/exchangeInfo"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EthBot/3.0)"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            exchange_info = json.loads(r.read().decode())

        # Filter USDT spot pairs that are TRADING
        active_usdt = set()
        for sym in exchange_info.get("symbols", []):
            if (sym.get("status") == "TRADING" and
                sym.get("quoteAsset") == "USDT" and
                sym.get("isSpotTradingAllowed", False)):
                symbol = sym["symbol"]
                if symbol not in BLACKLIST:
                    active_usdt.add(symbol)

        logger.info(f"Binance: {len(active_usdt)} active USDT pairs found")

        # Get 24h ticker for all pairs (single API call)
        url2 = "https://api.binance.com/api/v3/ticker/24hr"
        req2 = urllib.request.Request(url2, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EthBot/3.0)"
        })
        with urllib.request.urlopen(req2, timeout=20) as r2:
            tickers = json.loads(r2.read().decode())

        # Build sorted list
        pairs = []
        for t in tickers:
            symbol = t.get("symbol", "")
            if symbol not in active_usdt:
                continue

            volume_usdt = float(t.get("quoteVolume", 0))
            if volume_usdt < MIN_VOLUME_USDT:
                continue

            base = symbol.replace("USDT", "")
            pairs.append({
                "pair": symbol,
                "base": base,
                "volume_24h": volume_usdt,
                "price": float(t.get("lastPrice", 0)),
                "change_pct": float(t.get("priceChangePercent", 0)),
            })

        # Sort by 24h volume (highest first)
        pairs.sort(key=lambda x: x["volume_24h"], reverse=True)
        return pairs

    except Exception as e:
        logger.error(f"Binance pair scan failed: {e}")
        return []


def get_top_pairs(n: int = 20) -> List[Dict]:
    """
    Get top N USDT pairs by volume from Binance.
    Cached for 1 hour to avoid API spam.
    """
    cache_path = CACHE_DIR / "top_pairs.json"

    # Check cache
    try:
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
            if time.time() - data.get("_ts", 0) < PAIR_CACHE_TTL:
                cached_pairs = data.get("pairs", [])[:n]
                if cached_pairs:
                    return cached_pairs
    except Exception:
        pass

    # Fetch fresh
    all_pairs = fetch_all_binance_pairs()
    top = all_pairs[:n]

    # Cache
    try:
        cache_path.write_text(json.dumps({
            "pairs": all_pairs[:50],  # Cache top 50 for flexibility
            "_ts": time.time(),
            "total_eligible": len(all_pairs),
        }, ensure_ascii=False))
    except Exception:
        pass

    if top:
        symbols = [p["pair"] for p in top]
        logger.info(f"Top {n} pairs by volume: {symbols}")

    return top


def get_pair_info() -> Dict:
    """Get summary info about available Binance pairs."""
    all_pairs = fetch_all_binance_pairs()
    return {
        "total_eligible": len(all_pairs),
        "total_volume_24h": sum(p["volume_24h"] for p in all_pairs),
        "top_10": [
            {"pair": p["pair"], "vol": f"${p['volume_24h']:,.0f}", "chg": f"{p['change_pct']:+.1f}%"}
            for p in all_pairs[:10]
        ],
    }


# ─── CLI Test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("\n" + "=" * 70)
    print("   BINANCE DYNAMIC PAIR SCANNER")
    print("=" * 70)

    pairs = get_top_pairs(30)

    print(f"\nTop {len(pairs)} USDT Trading Pairs:")
    print(f"{'#':>3} {'Pair':<12} {'Price':>12} {'24h Vol (USDT)':>18} {'Change':>8}")
    print("-" * 58)

    for i, p in enumerate(pairs, 1):
        print(
            f"{i:>3} {p['pair']:<12} "
            f"${p['price']:>10,.2f} "
            f"${p['volume_24h']:>14,.0f} "
            f"{p['change_pct']:>+7.1f}%"
        )

    print(f"\nTotal eligible pairs: {len(fetch_all_binance_pairs())}")
    print("=" * 70)
