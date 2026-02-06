#!/usr/bin/env python3
"""
Proxy Session Helper for Binance API
Provides session with optional proxy support to bypass rate limits.
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

# Proxy configuration from environment
BINANCE_PROXY = os.getenv("BINANCE_PROXY", "")


def get_binance_session(timeout: int = 30) -> requests.Session:
    """
    Get a requests session configured for Binance API with optional proxy.
    
    Environment Variables:
        BINANCE_PROXY: Proxy URL (e.g., "http://user:pass@proxy.example.com:8080")
    
    Returns:
        Configured requests.Session object
    """
    session = requests.Session()
    
    if BINANCE_PROXY:
        session.proxies = {
            "http": BINANCE_PROXY,
            "https": BINANCE_PROXY
        }
        logger.info(f"🔀 Using proxy for Binance: {BINANCE_PROXY[:30]}...")
    
    # Set common headers
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    
    return session


def get_binance_proxies() -> dict:
    """
    Get proxy dict for direct requests.get() calls.
    
    Returns:
        Dict with http/https proxy config, or None if no proxy set
    """
    if BINANCE_PROXY:
        return {"http": BINANCE_PROXY, "https": BINANCE_PROXY}
    return None


# Test
if __name__ == "__main__":
    session = get_binance_session()
    print(f"Proxy configured: {bool(BINANCE_PROXY)}")
    if session.proxies:
        print(f"Proxies: {session.proxies}")
