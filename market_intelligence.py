#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market Intelligence Module — ScraperAPI-Powered Signal Enrichment

Provides 4 external market signals to enhance the bot's entry scoring:
1. Fear & Greed Index (alternative.me free API)
2. Crypto News Sentiment (CoinDesk/CoinTelegraph via ScraperAPI)
3. Whale Alert Monitoring (RSS feed)
4. Funding Rate Signal (Binance Futures free API)

Credit budget: ~200 ScraperAPI credits/day (news scraping only)
"""

import os
import json
import time
import re
import math
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "").strip()
MARKET_INTEL_ENABLED = os.getenv("MARKET_INTEL_ENABLED", "0").strip() in ("1", "true", "yes")

CACHE_DIR = Path(os.getenv("LOG_DIR", "./logs")) / "intel_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# TTLs (seconds) — how often each signal refreshes
TTL_FEAR_GREED = 1800     # 30 min
TTL_NEWS       = 900      # 15 min
TTL_WHALE      = 600      # 10 min
TTL_FUNDING    = 1800     # 30 min

# Composite score weights
W_FEAR_GREED = 0.35
W_NEWS       = 0.30
W_WHALE      = 0.15
W_FUNDING    = 0.20

# ─── Keyword Dictionaries for News Sentiment ─────────────────────────────
POS_KEYWORDS = {
    "bull", "rally", "breakout", "surge", "pump", "soar", "gain", "recover",
    "adoption", "etf", "approval", "upgrade", "partnership", "institutional",
    "all-time high", "ath", "flippening", "inflow", "accumulation",
    "mainnet", "launch", "milestone", "record", "optimism",
}
NEG_KEYWORDS = {
    "bear", "crash", "dump", "plunge", "selloff", "liquidation", "hack",
    "exploit", "ban", "restrict", "fine", "lawsuit", "sec", "delay",
    "outage", "vulnerability", "fraud", "ponzi", "rug pull", "exit scam",
    "outflow", "capitulation", "fear", "contagion", "insolvency",
}


# ─── Cache Helpers ────────────────────────────────────────────────────────
def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def _read_cache(name: str, ttl: int) -> Optional[dict]:
    """Read cached data if fresh enough."""
    p = _cache_path(name)
    try:
        if p.exists():
            data = json.loads(p.read_text())
            if time.time() - data.get("_ts", 0) < ttl:
                return data
    except Exception:
        pass
    return None


def _write_cache(name: str, data: dict):
    """Write data to cache with timestamp."""
    data["_ts"] = time.time()
    try:
        _cache_path(name).write_text(json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"INTEL cache write failed ({name}): {e}")


# ─── 1. Fear & Greed Index ───────────────────────────────────────────────
def fetch_fear_greed() -> dict:
    """
    Fetch Crypto Fear & Greed Index from alternative.me (free, 0 credits).
    Returns: { "value": 0-100, "label": "Extreme Fear"|..., "signal": -1.0 to +1.0 }
    """
    cached = _read_cache("fear_greed", TTL_FEAR_GREED)
    if cached:
        return cached

    import urllib.request
    result = {"value": 50, "label": "Neutral", "signal": 0.0, "source": "fear_greed"}

    try:
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EthBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())

        entry = data.get("data", [{}])[0]
        value = int(entry.get("value", 50))
        label = entry.get("value_classification", "Neutral")

        # Contrarian signal: extreme fear = bullish, extreme greed = bearish
        # 0-25: Extreme Fear → positive signal (+0.5 to +1.0)
        # 25-45: Fear → mild positive (+0.1 to +0.5)
        # 45-55: Neutral → 0
        # 55-75: Greed → mild negative (-0.1 to -0.5)
        # 75-100: Extreme Greed → negative signal (-0.5 to -1.0)
        signal = (50 - value) / 50.0  # Linear contrarian: 0→+1, 50→0, 100→-1

        result = {"value": value, "label": label, "signal": round(signal, 3), "source": "fear_greed"}
        logger.info(f"INTEL Fear&Greed: {value} ({label}) → signal={signal:.3f}")

    except Exception as e:
        logger.warning(f"INTEL Fear&Greed fetch failed: {e}")

    _write_cache("fear_greed", result)
    return result


# ─── 2. Crypto News Sentiment (ScraperAPI) ────────────────────────────────
def _scrape_with_scraperapi(url: str) -> str:
    """Fetch a page via ScraperAPI web scraping API (1 credit per request)."""
    if not SCRAPERAPI_KEY:
        return ""
    import urllib.request, urllib.parse
    api_url = "https://api.scraperapi.com?" + urllib.parse.urlencode({
        "api_key": SCRAPERAPI_KEY,
        "url": url,
        "render": "false",  # No JS rendering needed for news sites = cheaper
    })
    try:
        req = urllib.request.Request(api_url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EthBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"INTEL ScraperAPI fetch failed ({url[:60]}): {e}")
        return ""


def _extract_headlines(html: str) -> list:
    """Extract headline-like text from HTML using simple regex."""
    headlines = []
    # <h1>...<h4>, <title>, common headline patterns
    patterns = [
        r'<h[1-4][^>]*>(.*?)</h[1-4]>',
        r'<title[^>]*>(.*?)</title>',
        r'"headline"\s*:\s*"([^"]+)"',      # JSON-LD
        r'class="[^"]*title[^"]*"[^>]*>(.*?)</',
        r'class="[^"]*headline[^"]*"[^>]*>(.*?)</',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html, re.IGNORECASE | re.DOTALL):
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if 10 < len(text) < 300:
                headlines.append(text)

    return headlines[:50]  # Cap at 50 headlines


def _keyword_sentiment(texts: list) -> float:
    """Score a list of texts using keyword matching. Returns -1.0 to +1.0."""
    if not texts:
        return 0.0
    pos_count = 0
    neg_count = 0
    for text in texts:
        lower = text.lower()
        pos = sum(1 for k in POS_KEYWORDS if k in lower)
        neg = sum(1 for k in NEG_KEYWORDS if k in lower)
        pos_count += pos
        neg_count += neg
    total = pos_count + neg_count
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos_count - neg_count) / max(total, 1)))


def fetch_news_sentiment() -> dict:
    """
    Scrape crypto news headlines and compute sentiment.
    Uses ScraperAPI for CoinDesk/CoinTelegraph (~2 credits per call).
    Returns: { "sentiment": -1.0 to +1.0, "headlines_count": int, "signal": float }
    """
    cached = _read_cache("news_sentiment", TTL_NEWS)
    if cached:
        return cached

    result = {"sentiment": 0.0, "headlines_count": 0, "signal": 0.0, "source": "news"}
    all_headlines = []

    # Source 1: CoinDesk RSS (free, no ScraperAPI needed)
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
            headers={"User-Agent": "Mozilla/5.0 (compatible; EthBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            rss_text = r.read().decode("utf-8", errors="replace")
        # Extract titles from RSS
        for m in re.finditer(r'<title[^>]*>(.*?)</title>', rss_text, re.DOTALL):
            t = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', m.group(1)).strip()
            if 10 < len(t) < 300:
                all_headlines.append(t)
    except Exception as e:
        logger.warning(f"INTEL CoinDesk RSS failed: {e}")

    # Source 2: CoinTelegraph RSS (free)
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://cointelegraph.com/rss",
            headers={"User-Agent": "Mozilla/5.0 (compatible; EthBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            rss_text = r.read().decode("utf-8", errors="replace")
        for m in re.finditer(r'<title[^>]*>(.*?)</title>', rss_text, re.DOTALL):
            t = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', m.group(1)).strip()
            if 10 < len(t) < 300:
                all_headlines.append(t)
    except Exception as e:
        logger.warning(f"INTEL CoinTelegraph RSS failed: {e}")

    # Source 3: CryptoPanic via ScraperAPI (1 credit) — only if RSS gave <10 headlines
    if len(all_headlines) < 10 and SCRAPERAPI_KEY:
        html = _scrape_with_scraperapi("https://cryptopanic.com/news/")
        if html:
            scraped = _extract_headlines(html)
            all_headlines.extend(scraped)
            logger.info(f"INTEL CryptoPanic scraped: {len(scraped)} headlines (1 credit)")

    if all_headlines:
        sentiment = _keyword_sentiment(all_headlines)
        result = {
            "sentiment": round(sentiment, 3),
            "headlines_count": len(all_headlines),
            "signal": round(sentiment * 0.8, 3),  # Dampen slightly
            "source": "news",
        }
        logger.info(f"INTEL News: {len(all_headlines)} headlines → sentiment={sentiment:.3f}")

    _write_cache("news_sentiment", result)
    return result


# ─── 3. Whale Alert Monitoring ────────────────────────────────────────────
def fetch_whale_activity() -> dict:
    """
    Monitor large crypto transactions via Whale Alert RSS/social feeds.
    Free, 0 credits.
    Returns: { "large_txns": int, "signal": float }
    """
    cached = _read_cache("whale_activity", TTL_WHALE)
    if cached:
        return cached

    result = {"large_txns": 0, "signal": 0.0, "source": "whale"}

    try:
        import urllib.request
        # Whale Alert Twitter — check for large ETH/BTC transfers
        # Using Nitter RSS as a free proxy for Whale Alert tweets
        urls_to_try = [
            "https://nitter.net/whale_alert/rss",
            "https://nitter.privacydev.net/whale_alert/rss",
        ]
        whale_texts = []

        for nitter_url in urls_to_try:
            try:
                req = urllib.request.Request(nitter_url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; EthBot/1.0)"
                })
                with urllib.request.urlopen(req, timeout=8) as r:
                    rss = r.read().decode("utf-8", errors="replace")
                for m in re.finditer(r'<title[^>]*>(.*?)</title>', rss, re.DOTALL):
                    whale_texts.append(m.group(1).strip())
                if whale_texts:
                    break
            except Exception:
                continue

        # Count large transactions (mentions of millions)
        large_count = 0
        eth_related = 0
        for txt in whale_texts:
            lower = txt.lower()
            # Look for large amounts
            if any(w in lower for w in ["million", "billion", "mln", "bln"]):
                large_count += 1
                if any(w in lower for w in ["eth", "ethereum"]):
                    eth_related += 1

        # High whale activity → increased volatility → slight negative (caution)
        # But ETH-specific large buys → positive
        if large_count > 5:
            signal = -0.2  # High activity = caution
        elif eth_related > 2:
            signal = 0.15  # ETH accumulation = mild bullish
        else:
            signal = 0.0

        result = {
            "large_txns": large_count,
            "eth_related": eth_related,
            "total_alerts": len(whale_texts),
            "signal": round(signal, 3),
            "source": "whale",
        }
        if large_count > 0:
            logger.info(f"INTEL Whale: {large_count} large txns ({eth_related} ETH) → signal={signal:.3f}")

    except Exception as e:
        logger.warning(f"INTEL Whale fetch failed: {e}")

    _write_cache("whale_activity", result)
    return result


# ─── 4. Funding Rate Signal ──────────────────────────────────────────────
def fetch_funding_rate() -> dict:
    """
    Fetch current funding rate from Binance Futures API (free, 0 credits).
    Contrarian: high positive rate → market overleveraged long → bearish
                high negative rate → market overleveraged short → bullish
    Returns: { "rate": float, "signal": -1.0 to +1.0 }
    """
    cached = _read_cache("funding_rate", TTL_FUNDING)
    if cached:
        return cached

    result = {"rate": 0.0, "signal": 0.0, "source": "funding"}

    try:
        import urllib.request
        url = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=ETHUSDT&limit=1"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; EthBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())

        if data:
            rate = float(data[0].get("fundingRate", 0))

            # Contrarian signal:
            # Normal rate ~0.01% (0.0001) → neutral
            # >0.05% (0.0005) → overleveraged longs → bearish
            # <-0.01% (-0.0001) → overleveraged shorts → bullish
            if abs(rate) < 0.0001:
                signal = 0.0  # Normal range
            else:
                # Scale: ±0.001 maps to ∓1.0 (contrarian)
                signal = -rate / 0.001
                signal = max(-1.0, min(1.0, signal))

            result = {
                "rate": round(rate, 6),
                "rate_pct": round(rate * 100, 4),
                "signal": round(signal, 3),
                "source": "funding",
            }
            logger.info(f"INTEL Funding: rate={rate*100:.4f}% → signal={signal:.3f}")

    except Exception as e:
        logger.warning(f"INTEL Funding rate fetch failed: {e}")

    _write_cache("funding_rate", result)
    return result


# ─── Composite Signal ────────────────────────────────────────────────────
class MarketIntelligence:
    """Main interface for the market intelligence module."""

    def __init__(self):
        self.enabled = MARKET_INTEL_ENABLED
        self._last_log = 0

    def get_market_intelligence(self) -> Dict[str, dict]:
        """
        Fetch all 4 signals. Returns dict with keys:
        fear_greed, news_sentiment, whale_activity, funding_rate
        """
        if not self.enabled:
            return {
                "fear_greed": {"value": 50, "signal": 0.0},
                "news_sentiment": {"sentiment": 0.0, "signal": 0.0},
                "whale_activity": {"large_txns": 0, "signal": 0.0},
                "funding_rate": {"rate": 0.0, "signal": 0.0},
            }

        return {
            "fear_greed": fetch_fear_greed(),
            "news_sentiment": fetch_news_sentiment(),
            "whale_activity": fetch_whale_activity(),
            "funding_rate": fetch_funding_rate(),
        }

    def get_composite_score(self) -> float:
        """
        Weighted composite signal from all sources.
        Returns: float in range [-1.0, +1.0]
        Positive = bullish market conditions
        Negative = bearish market conditions
        """
        if not self.enabled:
            return 0.0

        data = self.get_market_intelligence()

        fg_sig = data["fear_greed"].get("signal", 0.0)
        ns_sig = data["news_sentiment"].get("signal", 0.0)
        wh_sig = data["whale_activity"].get("signal", 0.0)
        fr_sig = data["funding_rate"].get("signal", 0.0)

        composite = (
            W_FEAR_GREED * fg_sig +
            W_NEWS * ns_sig +
            W_WHALE * wh_sig +
            W_FUNDING * fr_sig
        )

        composite = max(-1.0, min(1.0, composite))

        # Log every 10 minutes
        now = time.time()
        if now - self._last_log > 600:
            self._last_log = now
            logger.info(
                f"MARKET_INTEL composite={composite:.3f} "
                f"[FG={fg_sig:.2f} News={ns_sig:.2f} Whale={wh_sig:.2f} Fund={fr_sig:.2f}]"
            )

        return round(composite, 4)

    def get_entry_score_adjustment(self) -> float:
        """
        Convert composite score to an entry_score adjustment.
        Returns: float in range [-0.05, +0.05] to add to entry_score.
        """
        composite = self.get_composite_score()
        # Scale to ±0.05 range
        adjustment = composite * 0.05
        return round(adjustment, 4)

    def is_extreme_fear_block(self) -> Tuple[bool, str]:
        """
        Check if Fear & Greed is at extreme levels that warrant blocking.
        Returns: (should_block, reason)
        """
        if not self.enabled:
            return False, ""

        fg = fetch_fear_greed()
        value = fg.get("value", 50)

        # Extreme Fear (≤10) — market could crash further, be cautious
        if value <= 10:
            return True, f"Extreme Fear (F&G={value}): market panic — blocking entries"

        return False, ""


# ─── Singleton instance ──────────────────────────────────────────────────
_instance = None

def get_intel() -> MarketIntelligence:
    """Get the singleton MarketIntelligence instance."""
    global _instance
    if _instance is None:
        _instance = MarketIntelligence()
    return _instance


# ─── CLI Test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Force enable for testing
    MARKET_INTEL_ENABLED = True

    mi = MarketIntelligence()
    mi.enabled = True

    print("\n" + "=" * 60)
    print("   MARKET INTELLIGENCE TEST")
    print("=" * 60)

    data = mi.get_market_intelligence()

    print(f"\n📊 Fear & Greed Index:")
    fg = data["fear_greed"]
    print(f"   Value: {fg.get('value', '?')} ({fg.get('label', '?')})")
    print(f"   Signal: {fg.get('signal', 0):.3f}")

    print(f"\n📰 News Sentiment:")
    ns = data["news_sentiment"]
    print(f"   Headlines: {ns.get('headlines_count', 0)}")
    print(f"   Sentiment: {ns.get('sentiment', 0):.3f}")
    print(f"   Signal: {ns.get('signal', 0):.3f}")

    print(f"\n🐳 Whale Activity:")
    wa = data["whale_activity"]
    print(f"   Large Txns: {wa.get('large_txns', 0)}")
    print(f"   ETH-Related: {wa.get('eth_related', 0)}")
    print(f"   Signal: {wa.get('signal', 0):.3f}")

    print(f"\n💰 Funding Rate:")
    fr = data["funding_rate"]
    print(f"   Rate: {fr.get('rate_pct', 0):.4f}%")
    print(f"   Signal: {fr.get('signal', 0):.3f}")

    composite = mi.get_composite_score()
    adjustment = mi.get_entry_score_adjustment()
    print(f"\n🎯 COMPOSITE SCORE: {composite:.4f}")
    print(f"   Entry Score Adjustment: {'+' if adjustment >= 0 else ''}{adjustment:.4f}")

    blocked, reason = mi.is_extreme_fear_block()
    if blocked:
        print(f"\n🛑 BLOCK: {reason}")
    else:
        print(f"\n✅ No extreme conditions — trading allowed")

    print("\n" + "=" * 60)
