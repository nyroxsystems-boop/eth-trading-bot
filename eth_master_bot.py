#!/usr/bin/env python3
import os as _os
try:
    import exchange_filters as _xf
except Exception:
    _xf=None


def _safe_adx(df_feat, window):
    """Calculate ADX safely. Needs at least 4*window rows for valid output."""
    try:
        import pandas as pd
        from ta.trend import ADXIndicator
        # ADX needs ~2*window rows for smoothing. Take 4*window for safety.
        need = max(window * 4, 60)
        sub = df_feat.tail(need).copy()
        for c in ("high", "low", "close"):
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        sub = sub.dropna()
        if len(sub) < window * 2:
            return 0.0
        w = min(window, max(14, len(sub) // 3))
        adx = ADXIndicator(sub["high"], sub["low"], sub["close"], window=w).adx()
        v = float(adx.iloc[-1])
        if v != v:  # NaN
            return 0.0
        return max(0.0, min(100.0, v))
    except Exception:
        return 0.0

# -*- coding: utf-8 -*-
"""
ETH Master Bot (clean build)
- ETHUSDT
- Breakout + Drawdown + Volatility filter
- ATR Stop, TP 1.5–2.0%, max trades/day
- Online learning (SGDClassifier)
- RSS sentiment (VADER)
- Backtest mode
- Telegram alerts
"""

import os, time, json, math, signal, argparse, threading, statistics
from datetime import datetime, timedelta, timezone
from collections import deque

# --- absolute defensive import of re (never shadowed) ---
import importlib as _importlib
re = _importlib.import_module("re")

import requests
import numpy as np
import pandas as pd

# ML — upgraded from SGDClassifier to MLPClassifier (neural network)
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import SGDClassifier  # Fallback
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

# Indicators
from ta.volatility import AverageTrueRange, BollingerBands
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator

# NLTK VADER
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer

# === Preflight Hook (auto) ===
try:
    import exchange_filters as _xf
except Exception:
    _xf = None

def _preflight(symbol, side, price, qty):
    if _xf is None:
        return True, {"price": float(price), "qty": float(qty)}
    ok, res = _xf.preflight_order(str(symbol), float(price), float(qty))
    return ok, res

def _wrap_order_fn(_fn):
    def _w(*args, **kwargs):
        # symbol/side aus kwargs oder args ziehen
        sym = kwargs.get("symbol") or kwargs.get("pair") or (len(args)>0 and args[0]) or "ETHUSDT"
        side= kwargs.get("side")   or (len(args)>1 and args[1]) or "BUY"
        # Preis & Menge (versch. Namen unterstützen)
        price = kwargs.get("price") or kwargs.get("px") or kwargs.get("rate")
        qty   = (kwargs.get("quantity") or kwargs.get("qty") or
                 kwargs.get("amount")   or kwargs.get("size"))
        # Nur bei echten Limit-Orders prüfen (price+qty vorhanden)
        if price is not None and qty is not None:
            ok, res = _preflight(sym, side, price, qty)
            if not ok:
                try:
                    log(f"[ORDER_FILTER] block: {res.get('reason')} pre={qty}@{price} post={res}")
                except Exception:
                    pass
                return {"status":"blocked","reason":res.get("reason","filter"),
                        "pre":{"price":price,"qty":qty}, "post":res}
            # zurückschreiben (normalisiertes price/qty)
            kwargs["price"] = res["price"]
            for k in ("quantity","qty","amount","size"):
                if k in kwargs: kwargs[k] = res["qty"]
        return _fn(*args, **kwargs)
    return _w

# === Clients patchen: python-binance (Spot/Futures) ===
try:
    from binance.client import Client as _BinanceClient
    for _name in ("create_order","create_test_order","order_limit_buy","order_limit_sell","futures_create_order"):
        if hasattr(_BinanceClient, _name):
            setattr(_BinanceClient, _name, _wrap_order_fn(getattr(_BinanceClient, _name)))
    try:
        from binance.um_futures import UMFutures as _UM
        for _name in ("new_order",):
            if hasattr(_UM, _name):
                setattr(_UM, _name, _wrap_order_fn(getattr(_UM, _name)))
    except Exception:
        pass
except Exception:
    pass

# === Clients patchen: ccxt (createOrder) ===
try:
    import ccxt  # type: ignore
    for clsname in dir(ccxt):
        try:
            _cls = getattr(ccxt, clsname)
            if hasattr(_cls, "create_order"):
                setattr(_cls, "create_order", _wrap_order_fn(getattr(_cls, "create_order")))
            if hasattr(_cls, "createOrder"):
                setattr(_cls, "createOrder", _wrap_order_fn(getattr(_cls, "createOrder")))
        except Exception:
            pass
except Exception:
    pass

print("[Preflight] Hook aktiv – Orders werden vor dem Senden geprüft.")
# === /Preflight Hook (auto) ===

BOT_VERSION = "2.1.0-multiuser"  # Version marker for deploy verification


# ------------------ CONFIG (via ENV) ------------------
PAIR               = _os.getenv("PAIR", "ETHUSDT")
BASE_ASSET         = "ETH"
QUOTE_ASSET        = "USDT"

DRY_RUN            = _os.getenv("DRY_RUN", "true").lower() == "true"

# --- Auto-Optimization Settings ---
AUTO_TRAIN_MODE    = _os.getenv("AUTO_TRAIN_MODE", "false").lower() == "true"
AUTO_OPTIMIZE      = _os.getenv("AUTO_OPTIMIZE", "false").lower() == "true"
DAILY_TARGET_PCT   = float(_os.getenv("DAILY_TARGET_PCT", "1.0"))  # 1% daily target

# Increase limits for training mode
if AUTO_TRAIN_MODE:
    MAX_TRADES_PER_DAY = int(_os.getenv("MAX_TRADES_PER_DAY", "50"))  # More trades for training
else:
    MAX_TRADES_PER_DAY = int(_os.getenv("MAX_TRADES_PER_DAY", "15"))  # Optimized for 1% daily target

INTERVAL           = _os.getenv("INTERVAL", "5m")
LOOKBACK           = int(_os.getenv("LOOKBACK", "400"))
TRADE_CAPITAL_PCT  = float(_os.getenv("TRADE_CAPITAL_PCT", "1.0"))

# CRITICAL: These are HARDCODED — Railway ENV vars were overriding with dangerous values!
TP_MIN             = 0.015      # 1.5% — minimal acceptable profit target
TP_MAX             = 0.025      # 2.5% — good risk/reward ratio
STOP_ATR_MULT      = 2.0        # 2.0x ATR for stops that survive noise
STOP_FLOOR         = 0.015      # 1.5% — MINIMUM stop distance (was 0.5% = death)

# --- Risk/Engine tuning ---
RISK_PCT_PER_TRADE = 0.01       # 1% risk per trade (with 1.5% SL = 67% position size)

TRAIL_PCT       = float(_os.getenv("TRAIL_PCT", "0.008"))   # fallback 0.8%
TAKE_PROFIT_PCT = 0.015  # 1.5% fallback

# Trailing/TP State
TRAIL_STATE = {
    'active': False,
    'entry': 0.0,
    'peak':  0.0,
    'qty':   0.0,
    'tp_pct': TAKE_PROFIT_PCT,
    'trail_pct': TRAIL_PCT,
    'opened_at': 0.0,
}

MAX_DRAWDOWN_DAY   = float(_os.getenv("MAX_DRAWDOWN_DAY", "0.03"))     # 3% Tages-MaxDD -> Pause
LOSS_STREAK_COOL   = int(_os.getenv("LOSS_STREAK_COOL", "3"))          # n Verluste in Folge -> Cooldown
COOLDOWN_MIN       = int(_os.getenv("COOLDOWN_MIN", "10"))             # Minuten Pause nach Loss-Streak

BREAK_EVEN_TRIGGER = 0.012     # +1.2% before moving SL to break-even
TRAIL_ATR_MULT     = 1.5       # ATR * 1.5 for trailing
MAX_HOLD_BARS      = 90        # ~7.5h — gives trades time to develop

# Regime-Filter
USE_ADX_FILTER     = _os.getenv("USE_ADX_FILTER", "true").lower()=="true"
ADX_WINDOW         = int(_os.getenv("ADX_WINDOW", "14"))
ADX_MIN_TREND      = float(_os.getenv("ADX_MIN_TREND", "15.0"))     # Lowered for more opportunities
# --- Entry thresholds (tunable via ENV) ---
ENTRY_SCORE_MIN    = float(_os.getenv("ENTRY_SCORE_MIN", "0.25"))   # Lowered — bot needs to actually trade
BREAKOUT_PCT       = float(_os.getenv("BREAKOUT_PCT", "0.00005"))   # 0.005% über HH20 (easier)
BREAKOUT_WEIGHT    = 0.20   # FIXED — rebalanced for sideways trading (was 0.32)
TREND_WEIGHT       = 0.12   # FIXED — rebalanced for sideways trading (was 0.16)
RSI_MIN            = float(_os.getenv("RSI_MIN", "35"))              # More opportunities
RSI_MAX            = float(_os.getenv("RSI_MAX", "75"))              # Allow higher RSI entries
SEC_PML_MIN        = float(_os.getenv("SEC_PML_MIN", "0.40"))       # Lower ML threshold
_SEC_PML_DEFAULT   = SEC_PML_MIN  # Store original value for reset after trades
        # ab hier gilt 'trendend'

PAPER_BASE_USDT    = float(_os.getenv("PAPER_BASE_USDT", "100000"))
PAPER_MODE         = _os.getenv("PAPER_MODE", "true").lower() in ("true", "1", "yes")
_paper_position_locked = 0.0  # Value locked in open positions
_ENTRY_CEILING     = ENTRY_SCORE_MIN  # Strategy-set ceiling for adaptive threshold
SLEEP_SECONDS      = int(_os.getenv("LOOP_SLEEP", "120"))  # 2min — optimized for 100k ScraperAPI/month

# --- Confidence System ---
win_streak     = 0       # Consecutive winning trades
confidence_lvl = 0.0     # -1.0 (very cautious) to +1.0 (very aggressive)

TG_TOKEN           = _os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT            = _os.getenv("TELEGRAM_CHAT_ID", "")

BINANCE_API_KEY    = _os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = _os.getenv("BINANCE_API_SECRET")

RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss"
]
RSS_POLL_SEC = 300

# ------------------ STATE ------------------
today_trades = 0
last_trade_day = datetime.now(timezone.utc).date().isoformat()
open_position = None   # {"entry":float,"qty":float,"atr":float}
ring = deque(maxlen=2000)
STOP = threading.Event()
# Risk state
day_start_equity = None
loss_streak = 0
cooldown_until_ts = 0.0
bars_in_position = 0

# === DAILY LOSS CIRCUIT BREAKER ===
daily_realized_pnl = 0.0           # Total realized P&L today (in USD)
daily_trade_results = []            # List of trade P&Ls today
circuit_breaker_active = False      # True = NO MORE TRADING until midnight
circuit_breaker_reason = ""

# ML — MLP Neural Network (2 hidden layers: 64, 32 neurons)
clf = Pipeline([
    ("scaler", StandardScaler(with_mean=True)),
    ("mlp", MLPClassifier(
        hidden_layer_sizes=(64, 32),
        activation="relu",
        solver="adam",
        alpha=1e-4,
        learning_rate="adaptive",
        learning_rate_init=0.001,
        max_iter=50,
        warm_start=True,  # Incremental learning — keeps weights between fits
        early_stopping=False,
        tol=1e-4
    ))
])
ml_warm = False
ml_classes = np.array([0,1])
ml_conf_boost = 0.0
# Real ML stats for dashboard display
ml_stats = {
    "accuracy": 0.0,
    "samples": 0,
    "last_trained": None,
    "predictions_made": 0,
    "warm": False
}

# sentiment
nltk_downloaded = False
sia = None
sent_score = 0.0
last_rss_pull = 0.0

# --- Auto-Optimization State ---
performance_history = []  # Track daily performance for optimization
current_params = {
    'risk_pct': RISK_PCT_PER_TRADE,
    'ml_threshold': 0.42,  # Lowered for more trades (was 0.52)
    'position_size_mult': 1.0,
    'tp_min': TP_MIN,
    'tp_max': TP_MAX,
}
last_optimization = 0.0  # Timestamp of last parameter adjustment
_last_strategy_load = 0.0  # Timestamp of last strategy load
_STRATEGY_RELOAD_INTERVAL = 300  # Check for better strategy every 5 minutes

def apply_best_strategy():
    """
    Load the best strategy from PostgreSQL and apply ALL params.
    Called every trading loop — picks up improvements from the backtester in real-time.
    Only reloads every 5 minutes to avoid DB spam.
    Applies ALL 11 backtested parameters to live trading.
    """
    global TP_MIN, TP_MAX, STOP_FLOOR, RISK_PCT_PER_TRADE, current_params
    global _last_strategy_load, SEC_PML_MIN
    global RSI_MIN, RSI_MAX, MAX_TRADES_PER_DAY, _ENTRY_CEILING
    global BREAKOUT_WEIGHT, TREND_WEIGHT
    
    # Only reload every 5 minutes
    if time.time() - _last_strategy_load < _STRATEGY_RELOAD_INTERVAL:
        return
    _last_strategy_load = time.time()
    
    try:
        import learning_store
        best = learning_store.get_current_strategy()
        if not best or not best.get("params"):
            return
        
        p = best["params"]
        old_tp = TP_MAX
        old_stop = STOP_FLOOR
        
        # === Core Risk Parameters ===
        # TP can be adjusted by backtester (within safe limits)
        if "tp_min" in p:
            TP_MIN = max(0.012, min(0.04, float(p["tp_min"])))  # Clamp 1.2-4%
        if "tp_max" in p:
            TP_MAX = max(0.015, min(0.05, float(p["tp_max"])))  # Clamp 1.5-5%
        # STOP_FLOOR and RISK_PCT_PER_TRADE are LOCKED — backtester cannot override!
        # Reason: backtester doesn't account for slippage/spread, sets SL too tight
        # if "stop_floor" in p:  # DISABLED — was setting SL to 0.4%!
        #     STOP_FLOOR = float(p["stop_floor"])
        # if "risk_per_trade" in p:  # DISABLED — was setting risk to 1.2%!
        #     RISK_PCT_PER_TRADE = float(p["risk_per_trade"])
        if "ml_threshold" in p:
            SEC_PML_MIN = max(0.30, float(p["ml_threshold"]))
        
        # === Entry Parameters (NEW — were not applied before!) ===
        if "rsi_oversold" in p:
            RSI_MIN = float(p["rsi_oversold"])
        if "rsi_overbought" in p:
            RSI_MAX = float(p["rsi_overbought"])
        if "max_trades_per_day" in p:
            MAX_TRADES_PER_DAY = int(p["max_trades_per_day"])
        
        # Entry threshold: strategy sets the CEILING, adaptive controls the floor
        if "entry_score_min" in p:
            _ENTRY_CEILING = max(0.15, min(0.30, float(p["entry_score_min"])))  # Cap at 0.30!
        
        # NOTE: BREAKOUT_WEIGHT and TREND_WEIGHT are NOT overridden by backtester
        # Our rebalanced weights (0.20/0.12) are core to sideways-market trading
        
        # Update current_params dict for tracking
        current_params['tp_min'] = TP_MIN
        current_params['tp_max'] = TP_MAX
        current_params['risk_pct'] = RISK_PCT_PER_TRADE
        current_params['ml_threshold'] = SEC_PML_MIN
        
        if old_tp != TP_MAX or old_stop != STOP_FLOOR:
            score = best.get("score", 0)
            log(f"AUTO-APPLY strategy (score={score:.1f}): TP={TP_MIN*100:.2f}-{TP_MAX*100:.2f}% Stop={STOP_FLOOR*100:.2f}% Risk={RISK_PCT_PER_TRADE*100:.2f}% ML={SEC_PML_MIN:.2f} RSI={RSI_MIN:.0f}-{RSI_MAX:.0f} MaxTrades={MAX_TRADES_PER_DAY}")
    except Exception as e:
        pass  # Silently fail — don't break trading loop

# --- Adaptive Entry Threshold ---
# Self-correcting: bot MUST trade to learn and hit 1%/day target
_adaptive_entry_min = ENTRY_SCORE_MIN
_last_trade_ts = time.time()
_ENTRY_FLOOR = 0.05        # Absolute minimum — nearly any signal triggers trade
# _ENTRY_CEILING is set by apply_best_strategy() from backtester results
_NO_TRADE_DECAY_MIN = 30   # Start lowering after 30min of no trades (was 2h)
_DECAY_STEP = 0.03         # Lower by 0.03 each check (was 0.02)
_EMERGENCY_HOURS = 4       # After 4h with 0 trades: emergency mode

def adapt_entry_threshold():
    """
    Self-correcting entry threshold:
    - No trades for 30min+: aggressively lower threshold
    - Emergency mode after 4h: enter on ANY positive signal
    - Winning trades: gently raise threshold
    - Goal: bot MUST trade to learn and hit 1%/day
    """
    global _adaptive_entry_min, ENTRY_SCORE_MIN, _last_trade_ts, SEC_PML_MIN
    
    hours_since_trade = (time.time() - _last_trade_ts) / 3600.0
    min_since_trade = hours_since_trade * 60
    
    if min_since_trade >= _NO_TRADE_DECAY_MIN:
        # No trades = threshold too high, lower it aggressively
        old = _adaptive_entry_min
        # Faster decay the longer we haven't traded
        decay = _DECAY_STEP * max(1, int(hours_since_trade))
        _adaptive_entry_min = max(_ENTRY_FLOOR, _adaptive_entry_min - decay)
        ENTRY_SCORE_MIN = _adaptive_entry_min
        
        # Also lower ML threshold after 1h of no trades
        if hours_since_trade >= 1.0:
            SEC_PML_MIN = max(0.30, SEC_PML_MIN - 0.02)
        
        if old != _adaptive_entry_min:
            log(f"ADAPT⚡ entry threshold: {old:.2f} -> {_adaptive_entry_min:.2f} | ml_min: {SEC_PML_MIN:.2f} | no trades for {min_since_trade:.0f}min")
        
        # EMERGENCY MODE: 4+ hours with 0 trades today
        # BUT only if market regime is OK — don't force trades in a crash!
        if hours_since_trade >= _EMERGENCY_HOURS and today_trades == 0:
            # Check regime before going emergency — need at least basic conditions
            _adaptive_entry_min = max(_ENTRY_FLOOR, 0.10)  # Low but not insane
            ENTRY_SCORE_MIN = _adaptive_entry_min
            SEC_PML_MIN = 0.30
            log(f"⚠️ LOW-THRESHOLD MODE: 0 trades in {hours_since_trade:.1f}h! Threshold={_adaptive_entry_min}, ml_min=0.30")
    elif today_trades > 0 and loss_streak == 0:
        # Winning = gently raise threshold (but cap at 0.30)
        _adaptive_entry_min = min(min(_ENTRY_CEILING, 0.30), _adaptive_entry_min + 0.01)
        ENTRY_SCORE_MIN = _adaptive_entry_min
    
    # HARD CAP: never let threshold rise above 0.25 regardless of strategy/adaptive logic
    if ENTRY_SCORE_MIN > 0.25:
        ENTRY_SCORE_MIN = 0.25
        _adaptive_entry_min = 0.25

# --- Volatility Zone Awareness ---
def get_volatility_boost() -> float:
    """
    Returns a score boost/penalty based on time-of-day volatility patterns.
    Hot zones get a BOOST (easier to enter), dead zones get a small penalty.
    Never blocks trades — strong signals always get through.
    
    Returns: float between -0.05 (dead zone) and +0.10 (peak zone)
    """
    utc_hour = datetime.now(timezone.utc).hour
    
    # US Market Open (13:30-16:00 UTC) — highest ETH volatility
    if 13 <= utc_hour <= 16:
        return 0.10
    
    # Asia Open (00:00-02:00 UTC) — second highest
    if 0 <= utc_hour <= 2:
        return 0.07
    
    # Europe Open (08:00-10:00 UTC)
    if 8 <= utc_hour <= 10:
        return 0.05
    
    # US Afternoon (16:00-20:00 UTC) — still active
    if 16 < utc_hour <= 20:
        return 0.03
    
    # Dead zones (03:00-07:00 UTC) — low volume, choppy
    if 3 <= utc_hour <= 7:
        return -0.05
    
    # Everything else — neutral
    return 0.0

# ------------------ INIT ------------------
def init_env():
    """Initialize environment & libraries safely."""
    global sia, nltk_downloaded
    # Ensure 're' is the real module
    import importlib
    r = importlib.import_module("re")
    if not hasattr(r, "compile"):
        raise RuntimeError("Invalid re module in scope.")

    # NLTK VADER
    sia = SentimentIntensityAnalyzer()
    nltk_downloaded = True

    # quick warnings
    if not (TG_TOKEN and TG_CHAT):
        print("⚠️  Telegram nicht konfiguriert (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
    if DRY_RUN or not (BINANCE_API_KEY and BINANCE_API_SECRET):
        print("ℹ️  Live-Orders deaktiviert (DRY_RUN oder keine Binance Keys).")

# ------------------ UTIL ------------------
def log_px(px, adx=None, rsi=None):
    try:
        msg = f"PX px={px:.2f} adx={adx if adx is not None else 'NA'} rsi={rsi if rsi is not None else 'NA'}"
        log(msg)
    except Exception:
        pass

def log(msg):
    """
    Zentrale Logger-Funktion:
      - Zeitstempel + Print
      - persistentes File-Logging
      - BUY/log_trade_csv('SELL', qty if 'qty' in locals() else 0.0, price if 'price' in locals() else last); SELL aus Logzeilen in /root/ethbot/logs/trades.csv schreiben
    """
    from datetime import datetime, timezone
    import os, re
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"

    # Ringbuffer (falls vorhanden) + Konsole
    try:
        ring.append(line)  # ring evtl. global
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass

    # File-Log
    try:
        os.makedirs("/root/ethbot/logs", exist_ok=True)
        with open("/root/ethbot/logs/ethbot.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    # BUY/SELL -> trades.csv
    try:
        csv_path = "/root/ethbot/logs/trades.csv"
        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("timestamp,action,qty,price\n")

        # Muster:
        # [DRY] BUY  17.96018 ETH @ ~3897.51
        # [DRY] SELL 17.96018 ETH @ ~3890.00   (SELL evtl. ohne Preis)
        m_buy  = re.search(r"\[(?:DRY|LIVE)\]\s*BUY\s+([0-9.]+)\s+\w+(?:\s*@\s*~?([0-9.]+))?", msg)
        m_sell = re.search(r"\[(?:DRY|LIVE)\]\s*SELL\s+([0-9.]+)\s+\w+(?:\s*@\s*~?([0-9.]+))?", msg)

        row = None
        if m_buy:
            qty = float(m_buy.group(1))
            px  = float(m_buy.group(2) or 0.0)
            try:
                _trail_check(float(px))  # falls vorhanden
            except Exception:
                pass
            row = f"{ts},BUY,{qty:.6f},{px:.2f}\n"
        elif m_sell:
            qty = float(m_sell.group(1))
            px  = float(m_sell.group(2) or 0.0)
            row = f"{ts},SELL,{qty:.6f},{px:.2f}\n"

        if row:
            with open(csv_path, "a", encoding="utf-8") as f:
                f.write(row)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
    except Exception:
        pass

def tg(msg):
    if not (TG_TOKEN and TG_CHAT): return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg},
            timeout=6
        )
    except Exception as e:
        log(f"WARN telegram send failed: {e}")
        pass

def now_date():
    return datetime.now(timezone.utc).date().isoformat()

# ------------------ DATA ------------------
# Proxy support for Binance API (rate limit bypass)
try:
    from src.utils.proxy_session import get_binance_proxies, get_ssl_verify
    _binance_proxies = get_binance_proxies()
    _ssl_verify = get_ssl_verify()
    # Suppress InsecureRequestWarning when using ScraperAPI proxy
    if not _ssl_verify:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print("Using proxy for Binance:", _binance_proxies.get("https", "")[:60] + "..." if _binance_proxies else "None")
except ImportError:
    _binance_proxies = None
    _ssl_verify = True

def fetch_klines(interval=INTERVAL, lookback=LOOKBACK, start_ts=None, end_ts=None) -> pd.DataFrame:
    base = "https://api.binance.com/api/v3/klines"
    params = {"symbol": PAIR, "interval": interval, "limit": 1000}
    frames = []
    if start_ts: params["startTime"] = int(start_ts)
    if end_ts:   params["endTime"]   = int(end_ts)

    while True:
        # --- failsafe init (auto-added) ---
        elapsed_bars = 0
        bar_len_min = 1
        elapsed_min = 0.0
        # -----------------------------------
        r = requests.get(base, params=params, timeout=10, proxies=_binance_proxies, verify=_ssl_verify)
        r.raise_for_status()
        data = r.json()
        if not data: break
        df = pd.DataFrame(data, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","qv","trades","taker_base","taker_quote","ignore"
        ])
        frames.append(df)
        if len(data) < 1000: break
        params["startTime"] = int(data[-1][6]) + 1

    if not frames:
        raise RuntimeError("no klines fetched")

    df = pd.concat(frames, ignore_index=True)
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df[["time","open","high","low","close","volume"]]

def last_price() -> float|None:
    try:
        df = fetch_klines(lookback=2)
        return float(df["close"].iloc[-1])
    except Exception as e:
        log(f"ERR last_price: {e}")
        return None

# ------------------ INDICATORS ------------------
def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ret1"] = out["close"].pct_change()
    out["ema20"] = EMAIndicator(out["close"], 20).ema_indicator()
    out["ema50"] = EMAIndicator(out["close"], 50).ema_indicator()
    macd = MACD(out["close"], window_slow=26, window_fast=12, window_sign=9)
    out["macd"] = macd.macd()
    out["macd_sig"] = macd.macd_signal()
    out["rsi14"] = RSIIndicator(out["close"], 14).rsi()
    atr = AverageTrueRange(out["high"], out["low"], out["close"], window=14)
    out["atr"] = atr.average_true_range()
    bb = BollingerBands(out["close"], window=20, window_dev=2)
    out["bb_hi"] = bb.bollinger_hband()
    out["bb_lo"] = bb.bollinger_lband()
    out["hh20"] = out["high"].rolling(20).max()
    out["ll20"] = out["low"].rolling(20).min()
    # --- NEW: Volume ratio + ADX for ML ---
    vol_med = out["volume"].rolling(20).median()
    out["volume_ratio"] = out["volume"] / vol_med.clip(lower=1e-9)
    try:
        out["adx14"] = ADXIndicator(out["high"], out["low"], out["close"], window=14).adx()
    except Exception:
        out["adx14"] = 25.0  # Neutral fallback
    out.dropna(inplace=True)
    return out

def is_drawdown_candle(row):
    body = abs(row["close"] - row["open"])
    range_ = row["high"] - row["low"]
    lower_wick = (min(row["open"], row["close"]) - row["low"])
    cond = (range_ > 0) and (lower_wick / max(range_, 1e-9) > 0.45) and (row["close"] > (row["low"] + 0.5*range_))
    return cond

# --- ML Feature columns (11 features) ---
ML_FEATURES = ["ret1","ema20","ema50","macd","macd_sig","rsi14","atr","bb_hi","bb_lo","volume_ratio","adx14"]

# ------------------ ML ------------------
def ml_prepare(df_feat: pd.DataFrame):
    X = df_feat[ML_FEATURES].values
    future = df_feat["close"].pct_change().shift(-1)
    thr = (df_feat["atr"] / df_feat["close"]) * 0.2
    y = (future > thr).astype(int).values
    X = X[:-1]; y = y[:-1]
    return X, y

def ml_online_update(df_feat: pd.DataFrame):
    global ml_warm, ml_conf_boost, ml_stats
    try:
        X, y = ml_prepare(df_feat)
        if X.shape[0] < 60:
            return
        
        # Detect feature dimension mismatch (e.g., 9→11 feature upgrade)
        if ml_warm:
            try:
                scaler_n = clf.named_steps["scaler"].n_features_in_
                if scaler_n != X.shape[1]:
                    log(f"ML COLD RESTART: scaler has {scaler_n} features, data has {X.shape[1]} → re-fitting")
                    ml_warm = False  # Force re-fit below
            except Exception:
                pass
        
        if not ml_warm:
            # Use full Pipeline.fit() so StandardScaler gets fitted too!
            clf.fit(X[:min(200, len(X))], y[:min(200, len(y))])
            if len(X) > 200:
                X_rest_scaled = clf.named_steps["scaler"].transform(X[200:])
                clf.named_steps["mlp"].partial_fit(X_rest_scaled, y[200:], classes=ml_classes)
            ml_warm = True
            log(f"ML warm! Trained on {len(X)} samples ({X.shape[1]} features)")
        else:
            # Online update: scaler already fitted, just update MLP
            X_scaled = clf.named_steps["scaler"].transform(X[-200:])
            clf.named_steps["mlp"].partial_fit(X_scaled, y[-200:])
        recent = y[-500:] if len(y) >= 500 else y
        ml_conf_boost = float(np.mean(recent))
        # Track real ML stats
        try:
            acc = clf.score(X[-200:], y[-200:]) * 100
        except Exception:
            acc = ml_conf_boost * 100
        ml_stats["accuracy"] = round(acc, 1)
        ml_stats["samples"] = int(X.shape[0])
        ml_stats["last_trained"] = datetime.now().isoformat()
        ml_stats["warm"] = ml_warm
        # Persist to JSON for dashboard API
        try:
            import json
            stats_file = Path(os.getenv("LOG_DIR", "./logs")) / "ml_stats.json"
            stats_file.parent.mkdir(exist_ok=True)
            with open(stats_file, "w") as f:
                json.dump(ml_stats, f)
            # Sync to Web container via API (try internal networking first, then public URL)
            api_url = os.getenv("RAILWAY_URL", os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
            if not api_url:
                api_url = "https://web-production-d57ac.up.railway.app"
            if api_url and not api_url.startswith("http"):
                api_url = f"https://{api_url}"
            # Retry up to 2 times for reliability
            for _attempt in range(2):
                try:
                    resp = requests.post(f"{api_url}/api/ml/stats-sync", json=ml_stats, timeout=5)
                    if resp.status_code == 200:
                        break
                except Exception:
                    if _attempt == 1:
                        log(f"WARN ml stats-sync failed after 2 attempts (url={api_url})")
        except Exception:
            pass
        # Persist model weights to survive deploys
        save_ml_model()
    except Exception as e:
        log(f"WARN ml update failed: {e}")

def ml_predict_row(row) -> float:
    global ml_stats
    if not ml_warm:
        # Fallback: use technical indicators instead of flat 0.5
        try:
            rsi = float(row.get("rsi14", 50))
            ema20 = float(row.get("ema20", 0))
            close = float(row.get("close", 0))
            macd = float(row.get("macd", 0))
            # Simple TA-based signal: combine RSI + EMA trend + MACD
            rsi_sig = 0.5 + (rsi - 50) / 200.0  # 0.25 to 0.75
            trend_sig = 0.55 if close > ema20 else 0.45
            macd_sig = 0.5 + np.tanh(macd * 100) * 0.1
            p_ml = (rsi_sig * 0.4 + trend_sig * 0.3 + macd_sig * 0.3)
            return float(np.clip(p_ml, 0.3, 0.7))
        except Exception:
            return 0.5
    v = np.array([[row.get(f, 0.0) for f in ML_FEATURES]])
    try:
        p = clf.predict_proba(v)[0,1]
        ml_stats["predictions_made"] = ml_stats.get("predictions_made", 0) + 1
        return float(p)
    except Exception:
        return 0.5

# --- Trade Outcome Feedback + Experience Replay ---
_trade_feedback_buffer = []
_experience_replay = deque(maxlen=100)  # Persistent memory of last 100 trades
_replay_counter = 0

def ml_feedback_trade(entry_row, outcome_win: bool):
    """
    Feed trade outcome back into ML model.
    Uses Experience Replay: stores last 100 trades and replays every 10 trades.
    """
    global _trade_feedback_buffer, _replay_counter
    
    if not ml_warm:
        return
    
    try:
        features = [entry_row.get(f, 0.0) for f in ML_FEATURES]
        label = 1 if outcome_win else 0
        _trade_feedback_buffer.append((features, label))
        _experience_replay.append((features, label))  # Never forget
        _replay_counter += 1
        
        # Retrain every 5 trade outcomes (small batch for responsiveness)
        if len(_trade_feedback_buffer) >= 5:
            X = np.array([f for f, _ in _trade_feedback_buffer])
            y = np.array([l for _, l in _trade_feedback_buffer])
            
            X_scaled = clf.named_steps["scaler"].transform(X)
            sample_weight = np.ones(len(y)) * 3.0  # Real trades worth 3x
            clf.named_steps["mlp"].partial_fit(X_scaled, y, classes=ml_classes, sample_weight=sample_weight)
            
            log(f"ML FEEDBACK: retrained on {len(_trade_feedback_buffer)} real trades "
                f"(wins: {sum(y)}, losses: {len(y)-sum(y)})")
            _trade_feedback_buffer.clear()
            save_ml_model()
        
        # EXPERIENCE REPLAY: every 10 trades, replay ALL stored outcomes
        if _replay_counter >= 10 and len(_experience_replay) >= 10:
            X_replay = np.array([f for f, _ in _experience_replay])
            y_replay = np.array([l for _, l in _experience_replay])
            X_scaled = clf.named_steps["scaler"].transform(X_replay)
            # Replay with lower weight (1.5x) — reinforcement, not override
            weight = np.ones(len(y_replay)) * 1.5
            clf.named_steps["mlp"].partial_fit(X_scaled, y_replay, classes=ml_classes, sample_weight=weight)
            _replay_counter = 0
            wins = sum(y_replay)
            log(f"EXPERIENCE REPLAY: {len(_experience_replay)} trades replayed "
                f"(win_rate={wins/len(y_replay)*100:.0f}%)")
            save_ml_model()
    except Exception as e:
        log(f"WARN ml feedback failed: {e}")

# --- ML Model Persistence (survive Railway deploys) ---
_last_model_save = 0.0  # Throttle: save at most every 60s

def save_ml_model():
    """Serialize SGD pipeline weights and sync to web API for persistence."""
    global _last_model_save
    if not ml_warm:
        return
    
    # Throttle saves to avoid API spam
    if time.time() - _last_model_save < 60:
        return
    _last_model_save = time.time()
    
    try:
        mlp = clf.named_steps["mlp"]
        scaler = clf.named_steps["scaler"]
        
        state = {
            "mlp_coefs": [c.tolist() for c in mlp.coefs_],
            "mlp_intercepts": [i.tolist() for i in mlp.intercepts_],
            "mlp_classes": mlp.classes_.tolist(),
            "mlp_n_layers": mlp.n_layers_,
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
            "scaler_var": scaler.var_.tolist(),
            "scaler_n_samples": int(scaler.n_samples_seen_) if hasattr(scaler, 'n_samples_seen_') else 200,
            "ml_stats": ml_stats,
            "ml_conf_boost": ml_conf_boost,
            "model_type": "mlp",
            "saved_at": datetime.now().isoformat()
        }
        
        api_url = os.getenv("RAILWAY_URL", os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
        if not api_url:
            api_url = "https://web-production-d57ac.up.railway.app"
        if api_url and not api_url.startswith("http"):
            api_url = f"https://{api_url}"
        
        resp = requests.post(f"{api_url}/api/ml/model-state", json=state, timeout=10)
        if resp.status_code == 200:
            log(f"ML MODEL SAVED: {len(str(state))} bytes, acc={ml_stats.get('accuracy', 0):.1f}%")
        else:
            log(f"WARN ml model save failed: HTTP {resp.status_code}")
    except Exception as e:
        log(f"WARN ml model save failed: {e}")

def load_ml_model():
    """Load persisted ML model weights from web API on startup."""
    global ml_warm, ml_conf_boost, ml_stats
    
    try:
        api_url = os.getenv("RAILWAY_URL", os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
        if not api_url:
            api_url = "https://web-production-d57ac.up.railway.app"
        if api_url and not api_url.startswith("http"):
            api_url = f"https://{api_url}"
        
        resp = requests.get(f"{api_url}/api/ml/model-state", timeout=10)
        if resp.status_code != 200:
            log("ML MODEL: no saved state found (fresh start)")
            return False
        
        state = resp.json()
        if state.get("status") in ("empty", "error"):
            log("ML MODEL: no saved state found (fresh start)")
            return False
        
        # Restore scaler
        scaler = clf.named_steps["scaler"]
        scaler.mean_ = np.array(state["scaler_mean"])
        scaler.scale_ = np.array(state["scaler_scale"])
        scaler.var_ = np.array(state["scaler_var"])
        scaler.n_features_in_ = len(state["scaler_mean"])
        scaler.n_samples_seen_ = np.float64(state.get("scaler_n_samples", 200))
        
        # Restore MLP (or skip if old SGD format)
        mlp = clf.named_steps["mlp"]
        if "mlp_coefs" in state:
            mlp.coefs_ = [np.array(c) for c in state["mlp_coefs"]]
            mlp.intercepts_ = [np.array(i) for i in state["mlp_intercepts"]]
            mlp.classes_ = np.array(state["mlp_classes"])
            mlp.n_layers_ = state.get("mlp_n_layers", 4)
            mlp._no_improvement_count = 0
            mlp.best_loss_ = np.inf
        elif "sgd_coef" in state:
            log("ML MODEL: old SGD format detected — skipping load, will retrain")
            return False
        
        # Restore stats
        if state.get("ml_stats"):
            ml_stats.update(state["ml_stats"])
        ml_conf_boost = state.get("ml_conf_boost", 0.0)
        ml_warm = True
        
        saved_at = state.get("saved_at", "unknown")
        acc = ml_stats.get("accuracy", 0)
        samples = ml_stats.get("samples", 0)
        log(f"✅ ML MODEL LOADED: acc={acc:.1f}% samples={samples} saved_at={saved_at}")
        return True
        
    except Exception as e:
        log(f"WARN ml model load failed: {e} (will train from scratch)")
        return False

# ------------------ SENTIMENT ------------------
def ensure_vader():
    global nltk_downloaded, sia
    if sia is not None: return
    try:
        nltk.data.find("sentiment/vader_lexicon.zip")
    except LookupError:
        nltk.download("vader_lexicon", quiet=True)
    sia = SentimentIntensityAnalyzer()
    nltk_downloaded = True

def poll_rss_sentiment():
    global sent_score, last_rss_pull
    t = time.time()
    if t - last_rss_pull < RSS_POLL_SEC: return
    last_rss_pull = t
    try:
        ensure_vader()
        texts = []
        for url in RSS_FEEDS:
            try:
                r = requests.get(url, timeout=6)
                r.raise_for_status()
                txt = r.text
                texts.append(txt[:200000])
            except Exception:
                pass
        if not texts: return
        s = 0.0; n = 0
        for txt in texts:
            score = sia.polarity_scores(txt)["compound"]
            s += score; n += 1
        sent_score = max(min(s / max(n,1), 0.5), -0.5)
    except Exception as e:
        log(f"WARN sentiment poll failed: {e}")

# --- Auto-Optimization ---
if AUTO_OPTIMIZE:
    try:
        from auto_optimizer import auto_optimize_parameters
    except ImportError:
        AUTO_OPTIMIZE = False
        log("WARN auto_optimizer module not found, disabling auto-optimization")

# ------------------ BALANCE / ORDERS ------------------
def _save_paper_balance():
    """Persist paper balance to PostgreSQL so it survives deploys."""
    try:
        api_url = _os.getenv("RAILWAY_URL", _os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
        if not api_url:
            api_url = "https://web-production-d57ac.up.railway.app"
        if api_url and not api_url.startswith("http"):
            api_url = f"https://{api_url}"
        requests.post(f"{api_url}/api/paper-balance",
                      json={"balance": round(PAPER_BASE_USDT, 2)}, timeout=5)
    except Exception:
        pass

def _load_paper_balance():
    """Load persisted paper balance from web API."""
    global PAPER_BASE_USDT
    try:
        api_url = _os.getenv("RAILWAY_URL", _os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
        if not api_url:
            api_url = "https://web-production-d57ac.up.railway.app"
        if api_url and not api_url.startswith("http"):
            api_url = f"https://{api_url}"
        r = requests.get(f"{api_url}/api/paper-balance", timeout=5)
        data = r.json()
        if data.get("balance") and data["balance"] > 0:
            PAPER_BASE_USDT = float(data["balance"])
            log(f"Loaded paper balance from DB: ${PAPER_BASE_USDT:.2f}")
    except Exception:
        pass  # Use default from env

def usdt_balance() -> float:
    if PAPER_MODE or DRY_RUN:
        # Paper mode: use paper balance
        available = PAPER_BASE_USDT - _paper_position_locked
        return max(0, available)
    if not (BINANCE_API_KEY and BINANCE_API_SECRET):
        return 0.0
    try:
        from binance.client import Client
        cli = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        info = cli.get_asset_balance(asset=QUOTE_ASSET)
        return float(info["free"]) if info else 0.0
    except Exception as e:
        log(f"WARN balance fetch: {e}")
        return 0.0
def sync_paper_trade(action: str, qty: float, price: float, pnl: float = 0):
    """Sync paper trade to Web container Dashboard.
    Posts to /api/trades/record so trades appear on the UI."""
    try:
        api_url = _os.getenv("RAILWAY_URL", _os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
        if not api_url:
            api_url = "https://web-production-d57ac.up.railway.app"
        if api_url and not api_url.startswith("http"):
            api_url = f"https://{api_url}"
        
        trade_data = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "qty": round(qty, 6),
            "price": round(price, 2),
            "pnl": round(pnl, 2)
        }
        requests.post(f"{api_url}/api/trades/record", json=trade_data, timeout=5)
        log(f"PAPER-TRADE synced: {action} {qty:.5f} @ {price:.2f} PnL={pnl:.2f}")
    except Exception as e:
        log(f"WARN paper trade sync failed: {e}")


def place_buy(qty: float, price_hint: float) -> bool:
    """
    BUY ausführen mit Pre-BUY-Guards und Trailing-State.
    DRY_RUN: nur Log + State
    LIVE   : Market-Order + State
    """
    # === Pre-BUY Guards (fail-safe for Railway) ===
    import subprocess
    import os
    
    # Helper: Run guard only if script exists
    def run_guard_safe(script_path, guard_name):
        if not os.path.exists(script_path):
            return True  # Skip guard if script doesn't exist (Railway)
        try:
            result = subprocess.run([script_path], capture_output=True, text=True, timeout=5)
            print((result.stdout or '').strip())
            return result.returncode == 0
        except Exception as e:
            log(f"WARN {guard_name} failed: {e} - allowing trade")
            return True  # Allow trade on guard failure
    
    # 1) Max-Consecutive-Losses (optional)
    if not run_guard_safe('/root/ethbot/max_losses_guard.py', 'max_losses_guard'):
        log('[SAFEGUARD] BUY blocked by max consecutive losses')
        return False
    
    # 2) Daily PnL Target (optional)
    if not run_guard_safe('/root/ethbot/daily_target_guard.py', 'daily_target_guard'):
        log('[SAFEGUARD] BUY blocked by daily profit target reached')
        return False
    
    # 3) Entry Edge (optional) - SKIP for more trades
    # if not run_guard_safe('/root/ethbot/entry_edge_guard.py', 'entry_edge_guard'):
    #     log('[SAFEGUARD] BUY blocked by weak edge')
    #     return False
    
    # 4) News / Twitter Kill-Switch (optional)
    if not run_guard_safe('/root/ethbot/news_guard_check.py', 'news_guard'):
        log('[SAFEGUARD] BUY blocked by news event')
        return False

    # === DRY MODE ===
    if DRY_RUN or PAPER_MODE or not (BINANCE_API_KEY and BINANCE_API_SECRET):
        log(f"[DRY] BUY {qty:.5f} {BASE_ASSET} @ ~{price_hint:.2f}")
        
        # Trailing/TP State setzen
        TRAIL_STATE['active']    = True
        TRAIL_STATE['entry']     = float(price_hint)
        TRAIL_STATE['peak']      = float(price_hint)
        TRAIL_STATE['qty']       = float(qty)
        TRAIL_STATE['tp_pct']    = float(TAKE_PROFIT_PCT)
        TRAIL_STATE['trail_pct'] = float(TRAIL_PCT)
        import time as _t
        TRAIL_STATE['opened_at'] = _t.time()
        
        # Broadcast to all connected users (multi-user live trading)
        try:
            api_url = _os.getenv("RAILWAY_URL", _os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
            if not api_url:
                api_url = "https://web-production-d57ac.up.railway.app"
            if api_url and not api_url.startswith("http"):
                api_url = f"https://{api_url}"
            resp = requests.post(f"{api_url}/api/trades/broadcast", json={
                "action": "BUY", "price": price_hint, "qty": qty,
                "pair": PAIR, "risk_pct": float(RISK_PCT_PER_TRADE)
            }, timeout=15)
            log(f"BROADCAST BUY: {resp.json()}")
        except Exception as e:
            log(f"WARN broadcast failed: {e}")
        
        return True

    # === LIVE ORDER ===
    try:
        from binance.client import Client
        cli = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        
        # Pre-check: sufficient balance?
        try:
            bal_info = cli.get_asset_balance(asset=QUOTE_ASSET)
            available = float(bal_info['free']) if bal_info else 0.0
            needed = float(qty) * float(price_hint)
            if available < needed * 0.95:  # 5% buffer for fees
                log(f'[LIVE] BUY BLOCKED: insufficient balance ${available:.2f} < ${needed:.2f}')
                return False
        except Exception as e:
            log(f'WARN balance pre-check failed: {e} — proceeding anyway')
        
        quote = round(float(qty) * float(price_hint), 2)
        try:
            resp = cli.order_market_buy(symbol=PAIR, quoteOrderQty=quote)
        except Exception:
            # Fallback auf Stückzahl
            resp = cli.order_market_buy(symbol=PAIR, quantity=round(float(qty), 5))
        
        # Extract actual fill price from Binance response
        fill_price = float(price_hint)
        fill_qty = float(qty)
        try:
            fills = resp.get('fills', [])
            if fills:
                total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
                total_qty = sum(float(f['qty']) for f in fills)
                if total_qty > 0:
                    fill_price = total_cost / total_qty
                    fill_qty = total_qty
                    log(f'[LIVE] Fill price: ${fill_price:.2f} (hint was ${price_hint:.2f})')
        except Exception:
            pass  # Use price_hint as fallback
        
        log(f"[LIVE] BUY {fill_qty:.5f} {BASE_ASSET} @ ~{fill_price:.2f}")
        
        # Trailing/TP State setzen (use actual fill price)
        TRAIL_STATE['active']    = True
        TRAIL_STATE['entry']     = float(fill_price)
        TRAIL_STATE['peak']      = float(fill_price)
        TRAIL_STATE['qty']       = float(fill_qty)
        import time as _t
        TRAIL_STATE['opened_at'] = _t.time()
        return True
    except Exception as e:
        log(f'WARN live buy failed: {e}')
        return False

def place_sell(qty: float) -> bool:
    px = last_price() or 0.0
    if DRY_RUN or PAPER_MODE or not (BINANCE_API_KEY and BINANCE_API_SECRET):
        log(f"[DRY] SELL {qty:.5f} {BASE_ASSET} @ ~{px:.2f}")
        
        # Broadcast SELL to all connected users
        try:
            api_url = _os.getenv("RAILWAY_URL", _os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
            if not api_url:
                api_url = "https://web-production-d57ac.up.railway.app"
            if api_url and not api_url.startswith("http"):
                api_url = f"https://{api_url}"
            resp = requests.post(f"{api_url}/api/trades/broadcast", json={
                "action": "SELL", "price": px, "qty": qty, "pair": PAIR
            }, timeout=15)
            log(f"BROADCAST SELL: {resp.json()}")
        except Exception as e:
            log(f"WARN broadcast sell failed: {e}")
        
        return True
    try:
        from binance.client import Client
        cli = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        
        # Pre-check: sufficient ETH balance?
        try:
            bal_info = cli.get_asset_balance(asset=BASE_ASSET)
            available = float(bal_info['free']) if bal_info else 0.0
            if available < float(qty) * 0.95:
                log(f'[LIVE] SELL BLOCKED: insufficient {BASE_ASSET} balance {available:.5f} < {qty:.5f}')
                return False
        except Exception as e:
            log(f'WARN balance pre-check failed: {e} — proceeding anyway')
        
        resp = cli.order_market_sell(symbol=PAIR, quantity=round(qty, 5))
        
        # Extract actual fill price
        fill_price = px
        try:
            fills = resp.get('fills', [])
            if fills:
                total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
                total_qty = sum(float(f['qty']) for f in fills)
                if total_qty > 0:
                    fill_price = total_cost / total_qty
                    log(f'[LIVE] Sell fill price: ${fill_price:.2f} (last was ${px:.2f})')
        except Exception:
            pass
        
        log(f"[LIVE] SELL {qty:.5f} {BASE_ASSET} @ ~{fill_price:.2f}")
        return True
    except Exception as e:
        log(f"WARN sell failed: {e}")
        return False

def estimate_equity(px: float|None = None) -> float:
    if px is None: px = last_price() or 0.0
    eq = usdt_balance()
    if open_position and px > 0:
        eq += open_position.get("qty",0.0) * px
    return float(eq)

# ------------------ RISK & REGIME HELPERS ------------------
def current_equity(px: float|None=None) -> float:
    try:
        return estimate_equity(px)
    except Exception:
        return estimate_equity()

def compute_regime(df_feat):
    adx_now = 0.0

    """
    Einfache Regime-Erkennung:
    - ADX (Trendstärke)
    - ATR-Median (Volatility)
    Performance: berechnet ADX nur auf kleinem Tail.
    """
    try:
        tail_n = max(ADX_WINDOW * 4, 60)
        sub = df_feat.tail(tail_n)
        if len(sub) < ADX_WINDOW + 1:
            # nicht genug Daten -> neutral
            adx_now = 0.0
        else:
            adx_now = float(_safe_adx(df_feat, ADX_WINDOW))
    except Exception as e:
        log(f"WARN regime ADX calc failed: {e}")
        adx_now = 0.0

    atr_series = df_feat["atr"].iloc[-200:] if len(df_feat) >= 200 else df_feat["atr"]
    atr_med = float(atr_series.median()) if len(atr_series) > 0 else 0.0
    atr_now = float(df_feat["atr"].iloc[-1]) if len(df_feat) > 0 else 0.0
    vol_ok = atr_now >= atr_med if atr_med > 0 else True
    trend_ok = (adx_now >= ADX_MIN_TREND) if USE_ADX_FILTER else True
    return {"adx": adx_now, "trend_ok": trend_ok, "vol_ok": vol_ok}

# --- VOLUME FILTER: reject low-liquidity entries ---
def check_volume_filter(df_feat):
    """Only trade when current volume is above 80% of 20-bar median."""
    try:
        vol_now = float(df_feat["volume"].iloc[-1])
        vol_median = float(df_feat["volume"].iloc[-20:].median())
        return vol_now >= vol_median * 0.80
    except Exception:
        return True  # Don't block on error

# --- MULTI-TIMEFRAME: 15m trend confirmation (cached) ---
_15m_cache = {"trend_ok": True, "ts": 0}
def check_15m_trend():
    """Check 15m timeframe for trend confirmation. Cached for 10 min."""
    global _15m_cache
    if time.time() - _15m_cache["ts"] < 600:  # 10 min cache
        return _15m_cache["trend_ok"]
    try:
        df_15m = fetch_klines(interval="15m", lookback=50)
        if len(df_15m) < 20:
            _15m_cache = {"trend_ok": True, "ts": time.time()}
            return True
        ema20_15m = df_15m["close"].ewm(span=20).mean().iloc[-1]
        ema50_15m = df_15m["close"].ewm(span=50).mean().iloc[-1]
        px_15m = float(df_15m["close"].iloc[-1])
        
        # 15m trend is bullish if price > EMA20 and EMA20 > EMA50
        ok = (px_15m > ema20_15m) and (ema20_15m > ema50_15m * 0.998)
        _15m_cache = {"trend_ok": ok, "ts": time.time()}
        return ok
    except Exception as e:
        log(f"WARN 15m trend check failed: {e}")
        _15m_cache = {"trend_ok": True, "ts": time.time()}
        return True  # Don't block on error

# --- MULTI-TIMEFRAME: 1h directional bias (the big picture) ---
_1h_cache = {"bias": "NEUTRAL", "strength": 0.0, "rsi": 50.0, "ts": 0, "detail": ""}

def get_1h_context() -> dict:
    """
    Fetch 1h candles and determine the big-picture directional bias.
    
    Returns dict with:
      bias: OVERSOLD_BOUNCE | TREND_UP | TREND_DOWN | NEUTRAL
      strength: 0.0-1.0 (how strong the signal is)
      rsi: current 1h RSI
    
    Cached for 5 minutes.
    """
    global _1h_cache
    if time.time() - _1h_cache["ts"] < 300:  # 5 min cache
        return _1h_cache
    
    try:
        df_1h = fetch_klines(interval="1h", lookback=100)
        if len(df_1h) < 50:
            _1h_cache = {"bias": "NEUTRAL", "strength": 0.0, "rsi": 50.0, "ts": time.time(), "detail": "not enough data"}
            return _1h_cache
        
        close = df_1h["close"]
        px = float(close.iloc[-1])
        
        # 1h RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi_1h = float((100 - 100 / (1 + rs)).iloc[-1])
        
        # 1h EMAs
        ema20_1h = float(close.ewm(span=20).mean().iloc[-1])
        ema50_1h = float(close.ewm(span=50).mean().iloc[-1])
        
        # 1h Bollinger Bands (20, 2)
        sma20 = float(close.rolling(20).mean().iloc[-1])
        std20 = float(close.rolling(20).std().iloc[-1])
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        bb_width = (bb_upper - bb_lower) / max(sma20, 1)
        
        # 1h ATR for volatility context
        high = df_1h["high"]
        low = df_1h["low"]
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        atr_1h = float(tr.rolling(14).mean().iloc[-1])
        
        # === DETERMINE BIAS ===
        bias = "NEUTRAL"
        strength = 0.0
        detail = ""
        
        # OVERSOLD_BOUNCE: RSI < 30 AND price near/below lower BB
        if rsi_1h < 30 and px <= bb_lower * 1.01:
            bias = "OVERSOLD_BOUNCE"
            strength = min(1.0, (30 - rsi_1h) / 15)  # Lower RSI = stronger signal
            detail = f"RSI={rsi_1h:.0f} below BB({bb_lower:.0f})"
        elif rsi_1h < 35 and px < sma20:
            bias = "OVERSOLD_BOUNCE"
            strength = min(0.7, (35 - rsi_1h) / 15)
            detail = f"RSI={rsi_1h:.0f} below SMA20({sma20:.0f})"
        
        # TREND_UP: price > EMA20 > EMA50
        elif px > ema20_1h and ema20_1h > ema50_1h:
            bias = "TREND_UP"
            # Strength based on how far above EMAs
            spread = (ema20_1h - ema50_1h) / max(ema50_1h, 1) * 100
            strength = min(1.0, spread / 2)  # 2% spread = max strength
            detail = f"price>{ema20_1h:.0f}>{ema50_1h:.0f} spread={spread:.2f}%"
        
        # TREND_DOWN: price < EMA20 < EMA50
        elif px < ema20_1h and ema20_1h < ema50_1h:
            bias = "TREND_DOWN"
            spread = (ema50_1h - ema20_1h) / max(ema50_1h, 1) * 100
            strength = min(1.0, spread / 2)
            detail = f"price<{ema20_1h:.0f}<{ema50_1h:.0f}"
        
        # NEUTRAL: no clear direction
        else:
            bias = "NEUTRAL"
            strength = 0.3
            detail = f"range px={px:.0f} ema20={ema20_1h:.0f} ema50={ema50_1h:.0f}"
        
        _1h_cache = {
            "bias": bias,
            "strength": round(strength, 2),
            "rsi": round(rsi_1h, 1),
            "ts": time.time(),
            "detail": detail,
            "bb_lower": round(bb_lower, 2),
            "bb_upper": round(bb_upper, 2),
            "ema20": round(ema20_1h, 2),
            "ema50": round(ema50_1h, 2),
            "atr": round(atr_1h, 2)
        }
        
        log(f"1H CONTEXT: {bias} (strength={strength:.2f}) | {detail} | RSI={rsi_1h:.1f}")
        return _1h_cache
        
    except Exception as e:
        log(f"WARN 1h context failed: {e}")
        _1h_cache = {"bias": "NEUTRAL", "strength": 0.0, "rsi": 50.0, "ts": time.time(), "detail": f"error: {e}"}
        return _1h_cache

# --- DYNAMIC RISK: scale position size 1%-5% based on market conditions ---
# --- FUNDING RATE: contrarian signal from Binance Futures ---
_funding_cache = {"rate": 0.0, "ts": 0, "signal": "NEUTRAL"}

def get_funding_rate() -> dict:
    """
    Fetch funding rate from Binance Futures.
    Extreme negative = everyone is short → contrarian LONG signal.
    Extreme positive = everyone is long → be cautious.
    
    Cached for 5 minutes.
    """
    global _funding_cache
    if time.time() - _funding_cache["ts"] < 300:  # 5 min cache
        return _funding_cache
    
    try:
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/premiumIndex",
            params={"symbol": "ETHUSDT"},
            timeout=5
        )
        data = resp.json()
        rate = float(data.get("lastFundingRate", 0))
        
        signal = "NEUTRAL"
        if rate < -0.0005:        # -0.05% = extremely negative
            signal = "EXTREME_SHORT"  # Everyone shorting → contrarian long
        elif rate < -0.0001:      # -0.01%
            signal = "SHORT_HEAVY"    # More shorts than usual
        elif rate > 0.0005:       # +0.05%
            signal = "EXTREME_LONG"   # Everyone longing → be cautious
        elif rate > 0.0001:
            signal = "LONG_HEAVY"
        
        _funding_cache = {
            "rate": rate,
            "rate_pct": round(rate * 100, 4),
            "signal": signal,
            "ts": time.time()
        }
        
        if signal != "NEUTRAL":
            log(f"FUNDING RATE: {rate*100:.4f}% → {signal}")
        
        return _funding_cache
    except Exception as e:
        log(f"WARN funding rate fetch failed: {e}")
        _funding_cache = {"rate": 0.0, "rate_pct": 0.0, "signal": "NEUTRAL", "ts": time.time()}
        return _funding_cache

# --- 4H CONTEXT: overrides 1h when strongly bearish ---
_4h_cache = {"bias": "NEUTRAL", "ts": 0}

def get_4h_bias() -> str:
    """
    Quick 4h trend check. If 4h EMA20 < EMA50 → strong downtrend override.
    Cached for 15 minutes (4h candles change slowly).
    """
    global _4h_cache
    if time.time() - _4h_cache["ts"] < 900:  # 15 min cache
        return _4h_cache["bias"]
    
    try:
        df_4h = fetch_klines(interval="4h", lookback=60)
        if len(df_4h) < 50:
            _4h_cache = {"bias": "NEUTRAL", "ts": time.time()}
            return "NEUTRAL"
        
        close = df_4h["close"]
        px = float(close.iloc[-1])
        ema20 = float(close.ewm(span=20).mean().iloc[-1])
        ema50 = float(close.ewm(span=50).mean().iloc[-1])
        
        if px > ema20 and ema20 > ema50:
            bias = "TREND_UP"
        elif px < ema20 and ema20 < ema50:
            bias = "TREND_DOWN"
        else:
            bias = "NEUTRAL"
        
        _4h_cache = {"bias": bias, "ts": time.time()}
        log(f"4H BIAS: {bias} (px={px:.0f} ema20={ema20:.0f} ema50={ema50:.0f})")
        return bias
    except Exception as e:
        log(f"WARN 4h bias failed: {e}")
        _4h_cache = {"bias": "NEUTRAL", "ts": time.time()}
        return "NEUTRAL"

RISK_MIN = 0.01   # 1% — conservative baseline
RISK_MAX = 0.05   # 5% — maximum on high-conviction setups

def dynamic_risk_factor(p_ml, entry_score=0.0, vol_ok=False, trend_15m_ok=False):
    """Scale risk between 1x (1%) and 5x (5%) based on market conditions.
    
    Factors that INCREASE risk (toward 5%):
      - High entry score (strong signal)
      - ML confidence > 70%
      - Volume confirms the move
      - 15m trend aligns
      - Win streak (bot is calibrated)
    
    Factors that DECREASE risk (toward 1%):
      - Low entry score
      - ML bearish or uncertain
      - Against 15m trend
      - Loss streak (bot is off-calibration)
    """
    # Start at 1x (= 1%)
    factor = 1.0
    
    # Entry score strength: +0.0 to +2.0
    if entry_score >= 0.7:
        factor += 2.0    # Very strong setup
    elif entry_score >= 0.55:
        factor += 1.5    # Strong setup
    elif entry_score >= 0.45:
        factor += 1.0    # Decent setup
    elif entry_score >= 0.35:
        factor += 0.5    # Weak setup
    # Below 0.35: no bonus (minimum quality)
    
    # ML confidence: +0.0 to +1.0
    if p_ml >= 0.80:
        factor += 1.0
    elif p_ml >= 0.70:
        factor += 0.5
    elif p_ml < 0.45:
        factor -= 0.5    # ML bearish → reduce
    
    # Volume confirmation: +0.5
    if vol_ok:
        factor += 0.5
    
    # 15m trend alignment: +0.5 or -0.5
    if trend_15m_ok:
        factor += 0.5
    else:
        factor -= 0.5
    
    # Win/loss streak adjustment
    if win_streak >= 3:
        factor += 0.5    # Hot hand → slightly more aggressive
    elif loss_streak >= 2:
        factor -= 1.0    # Losing → pull back hard
    elif loss_streak >= 1:
        factor -= 0.5    # Recent loss → cautious
    
    # Clamp to 1x-5x range (= 1%-5%)
    factor = max(1.0, min(5.0, factor))
    
    return factor

def position_size_for_risk(px, sl_pct, eq, risk_factor=1.0):
    """
    Risiko pro Trade = eq * RISK_MIN * risk_factor
    risk_factor ranges from 1.0 (1%) to 5.0 (5%)
    Größe (qty) = (RiskUSD) / (sl_pct * px)
    """
    effective_risk_pct = RISK_MIN * risk_factor  # 1% * 1..5 = 1%-5%
    risk_usd = max(0.0, float(eq) * effective_risk_pct)
    denom = max(sl_pct * px, 1e-9)
    qty = risk_usd / denom
    return max(0.0001, qty)

def update_position_management(px, row, effective_tp):
    """
    Break-even, Trailing TP & Time-based Exit.
    When price hits TP → don't exit, activate trailing mode instead.
    Trailing SL follows at 40% of peak gains.
    """
    global open_position, loss_streak
    entry = open_position["entry"]; qty = open_position["qty"]; atr_in = open_position.get("atr", row["atr"])
    upnl = (px/entry) - 1.0

    # Dynamischer SL: Start = max(Floor, ATR-Mult)
    sl_pct = max(STOP_FLOOR, STOP_ATR_MULT * (atr_in / max(entry,1e-9)))

    # ==== Time-based Exit (safe & clean) ====
    elapsed_bars = 0
    bar_len_min = 1
    elapsed_min = 0.0
    try:
        bar_time = row["time"]
        opened_at = open_position.get("open_bar_time", bar_time)
        if isinstance(opened_at, str):
            from pandas import to_datetime
            opened_at = to_datetime(opened_at)
        elapsed_min = (bar_time - opened_at).total_seconds() / 60.0
        bar_len_min = _interval_minutes(INTERVAL) or 1
        elapsed_bars = int(max(0, elapsed_min // max(bar_len_min, 1)))
    except Exception as e:
        try:
            log(f"WARN elapsed_bars failsafe: {e}")
        except Exception:
            pass
        elapsed_bars = 0

    if elapsed_bars >= MAX_HOLD_BARS:
        return "TIME"

    # ==== Trailing Take-Profit System ====
    peak_pnl = open_position.get("peak_pnl", 0.0)
    trailing_active = open_position.get("trailing_active", False)
    
    # Track peak PnL
    if upnl > peak_pnl:
        open_position["peak_pnl"] = upnl
        peak_pnl = upnl
    
    # Phase 1: Break-even after small gain
    if upnl >= BREAK_EVEN_TRIGGER:
        sl_pct = 0.001  # BE + tiny buffer (0.1%)
    
    # Phase 2: Price hits TP level → activate trailing mode (DON'T exit)
    if peak_pnl >= effective_tp and not trailing_active:
        open_position["trailing_active"] = True
        trailing_active = True
        log(f"TRAILING ACTIVATED: peak={peak_pnl*100:.2f}% tp={effective_tp*100:.2f}%")
    
    # Phase 3: Trailing mode — SL follows at 40% of peak gains
    if trailing_active:
        # Trail distance: keep 60% of peak gains locked in
        trail_floor = peak_pnl * 0.60  # Lock in 60% of peak
        trail_sl = max(trail_floor, effective_tp * 0.50)  # At minimum, lock in 50% of TP
        
        if upnl <= trail_sl and peak_pnl > effective_tp * 0.8:
            # Price dropped from peak but still in profit → take the gain
            log(f"TRAILING TP: exit at +{upnl*100:.2f}% (peak was +{peak_pnl*100:.2f}%)")
            return "TP"
        
        # Hard cap: if we've hit 3x the original TP, take profits regardless
        if upnl >= effective_tp * 3.0:
            log(f"TRAILING CAP: exit at +{upnl*100:.2f}% (3x TP reached)")
            return "TP"
    else:
        # Not in trailing mode yet — use standard TP for safety
        # But only exit on standard TP if price is actively falling
        if upnl >= effective_tp:
            # Check momentum: is price pulling back or still pushing?
            try:
                macd_val = float(row.get("macd", 0))
                macd_sig_val = float(row.get("macd_sig", 0))
                rsi_val = float(row.get("rsi14", 50))
                
                # Strong momentum → let it run (activate trailing)
                if macd_val > macd_sig_val and rsi_val < 75:
                    open_position["trailing_active"] = True
                    log(f"TRAILING ACTIVATED (momentum): +{upnl*100:.2f}% MACD bullish, RSI={rsi_val:.0f}")
                    return None  # Hold — don't exit
                else:
                    # Weak momentum → take the TP
                    return "TP"
            except Exception:
                return "TP"
    
    # Standard SL (only if not in trailing mode or trailing hasn't locked gains yet)
    if upnl <= -sl_pct:
        return "SL"
    return None
def compute_effective_tp(rsi14, regime, row):
    """
    Baseline: TP_MIN … TP_MAX.
    Booster: Wenn Trend stark (ADX >= TP_STRETCH_ADX) -> TP_STRETCH (z.B. 2.0%).
    """
    import os
    try:
        stretch_adx = float(_os.getenv("TP_STRETCH_ADX", "22.0"))
        stretch_tp  = float(_os.getenv("TP_STRETCH", "0.02"))
    except Exception:
        stretch_adx, stretch_tp = 22.0, 0.02

    base = TP_MAX if rsi14 >= 70 else TP_MIN
    if regime.get("adx", 0.0) >= stretch_adx:
        return max(base, stretch_tp)
    return base

def should_one_and_done(today_trades, loss_streak):
    import os
    flag = _os.getenv("ONE_AND_DONE","false").lower()=="true"
    return flag and today_trades>=1 and loss_streak==0

# ------------------ STRATEGY CORE ------------------
def decide_and_trade():
    global today_trades, last_trade_day, open_position
    global day_start_equity, loss_streak, cooldown_until_ts, bars_in_position
    global _last_trade_ts, _paper_position_locked, PAPER_BASE_USDT
    global win_streak, confidence_lvl
    global daily_realized_pnl, daily_trade_results, circuit_breaker_active, circuit_breaker_reason


    if now_date() != last_trade_day:
        last_trade_day = now_date()
        today_trades = 0
        # DON'T reset loss_streak at midnight — it should only reset on a winning trade
        # loss_streak = 0  # BUG FIX: was resetting streak, allowing immediate aggressive trading after midnight
        cooldown_until_ts = 0.0
        day_start_equity = current_equity()
        # Reset circuit breaker at midnight
        daily_realized_pnl = 0.0
        daily_trade_results = []
        if circuit_breaker_active:
            log(f"🔄 CIRCUIT BREAKER RESET — new day, trading resumed")
            tg("🔄 Circuit Breaker zurückgesetzt — neuer Tag, Trading wieder aktiv")
        circuit_breaker_active = False
        circuit_breaker_reason = ""
        log(f"INFO new UTC day → reset trade counter | day_start_equity={day_start_equity:.2f}")

    if day_start_equity is None:
        day_start_equity = current_equity()

    eq_now = current_equity()
    dd = (eq_now / max(day_start_equity, 1e-9)) - 1.0
    if dd <= -MAX_DRAWDOWN_DAY:
        if not circuit_breaker_active:
            circuit_breaker_active = True
            circuit_breaker_reason = f"Daily drawdown {dd*100:.2f}% exceeded -{MAX_DRAWDOWN_DAY*100:.0f}% limit"
            log(f"🛑 CIRCUIT BREAKER: {circuit_breaker_reason}")
            tg(f"🛑 CIRCUIT BREAKER AKTIV — {circuit_breaker_reason}. Kein Trading bis morgen.")
        return
    
    # === CIRCUIT BREAKER CHECK ===
    if circuit_breaker_active:
        # Only allow managing existing positions, no new entries
        if open_position:
            pass  # Let position management continue below
        else:
            return  # No new trades

    if time.time() < cooldown_until_ts:
        return

    if today_trades >= MAX_TRADES_PER_DAY and not open_position:
        log("INFO max trades reached – no new entries")
        return

    df = fetch_klines(interval=INTERVAL, lookback=max(LOOKBACK, 240))
    df_feat = add_features(df)
    if len(df_feat) < 60:
        log("INFO waiting for more data...")
        return

    ml_online_update(df_feat)
    
    # Adaptive entry threshold: auto-lower if not trading
    adapt_entry_threshold()
    
    # Auto-apply best strategy from backtester (every 5 min)
    apply_best_strategy()

    row   = df_feat.iloc[-1]
    px    = float(row["close"])
    ema20 = float(row["ema20"])
    ema50 = float(row["ema50"])
    rsi14 = float(row["rsi14"])
    hh20  = float(row["hh20"])
    atr   = float(row["atr"])
    bb_lo = float(row["bb_lo"])

    regime = compute_regime(df_feat)
    # CRITICAL FIX: Don't block trades on soft-warn, just log and continue
    if not (regime["trend_ok"] or regime["vol_ok"]):
        log(f"INFO regime soft-warn (CONTINUING) | adx={regime['adx']:.1f} trend_ok={regime['trend_ok']} vol_ok={regime['vol_ok']}")
        # Don't return! Continue with entry logic - previously blocked ALL trades

    prev         = df.iloc[-2]
    drawdown_ok  = is_drawdown_candle(prev)
    breakout_ok  = px > hh20 * (1.0 + BREAKOUT_PCT)
    trend_ok     = (px > ema20) and (ema20 > ema50)

    # Oversold-Rebound
    rsi_ok_band  = (RSI_MIN <= rsi14 <= RSI_MAX)
    oversold_ok  = (rsi14 <= max(40.0, RSI_MIN)) and drawdown_ok and (px >= bb_lo * 1.0005)

    # --- NEW: Sideways-market signals (trigger when breakout/trend don't) ---
    # EMA20 bounce: price dips near EMA20 and closes above it
    ema_bounce_ok = (px > ema20) and (float(row["low"]) <= ema20 * 1.002) and (rsi14 > 40)
    
    # Bollinger band bounce: price near lower band and RSI not extreme
    bb_bounce_ok = (px <= bb_lo * 1.005) and (rsi14 < 45) and (px > float(row["low"]))
    
    # MACD bullish crossover: MACD just crossed above signal
    macd_val = float(row.get("macd", 0))
    macd_sig_val = float(row.get("macd_sig", 0))
    prev_macd = float(prev.get("macd", 0)) if hasattr(prev, 'get') else float(prev["macd"]) if "macd" in prev.index else 0
    prev_macd_sig = float(prev.get("macd_sig", 0)) if hasattr(prev, 'get') else float(prev["macd_sig"]) if "macd_sig" in prev.index else 0
    macd_cross_ok = (macd_val > macd_sig_val) and (prev_macd <= prev_macd_sig)
    
    # Range support: price near 20-bar low with momentum turning up
    ll20 = float(row.get("ll20", px))
    range_support_ok = (px <= ll20 * 1.003) and (rsi14 < 40) and (macd_val > prev_macd)

    p_ml         = ml_predict_row(row)
    # In paper mode or when adapting: relax secondary check
    if PAPER_MODE or ENTRY_SCORE_MIN <= 0.15:
        secondary_ok = trend_ok and (px > ema20)  # Skip p_ml requirement
    else:
        secondary_ok = trend_ok and (rsi14 >= RSI_MIN) and (p_ml >= SEC_PML_MIN) and (px > ema20)

    adx_bonus = 0.0
    if regime["trend_ok"]:
        adx_bonus = max(0.0, min((regime["adx"] - 20.0) / 400.0, 0.15))

    vol_zone_boost = get_volatility_boost()
    boost = (p_ml - 0.5) * 0.4 + (sent_score * 0.1) + adx_bonus + vol_zone_boost
    effective_tp = compute_effective_tp(rsi14, regime, row)

    # --- REBALANCED scoring (works in trending AND sideways markets) ---
    ml_direct = max(0.0, min(0.15, (p_ml - 0.5) * 0.3)) if p_ml > 0.55 else 0.0
    base_score = (
        # Trend signals (work in trending markets)
        0.20*(1.0 if breakout_ok else 0.0) +      # Was 0.32 — reduced
        0.12*(1.0 if trend_ok else 0.0) +          # Was 0.16 — reduced
        0.05*(1.0 if secondary_ok else 0.0) +
        # Universal signals (work in any market)
        0.12*(1.0 if drawdown_ok else 0.0) +       # Was 0.18
        0.06*(1.0 if rsi_ok_band else 0.0) +
        0.05*(1.0 if regime["vol_ok"] else 0.0) +
        # Sideways/reversal signals (NEW — work when trend doesn't)
        0.15*(1.0 if oversold_ok else 0.0) +
        0.12*(1.0 if ema_bounce_ok else 0.0) +     # NEW
        0.10*(1.0 if bb_bounce_ok else 0.0) +      # NEW
        0.12*(1.0 if macd_cross_ok else 0.0) +     # NEW
        0.08*(1.0 if range_support_ok else 0.0) +  # NEW
        ml_direct +
        boost
    )
    
    # CONFIDENCE BOOST: winning streak → lower entry barrier
    conf_boost = 0.0
    if win_streak >= 5:
        conf_boost = 0.15  # Hot streak: very aggressive
        confidence_lvl = min(1.0, confidence_lvl + 0.1)
    elif win_streak >= 3:
        conf_boost = 0.10  # Good run: more aggressive
        confidence_lvl = min(1.0, confidence_lvl + 0.05)
    elif win_streak >= 1:
        conf_boost = 0.03  # Recent win: slight boost
    
    if loss_streak >= 3:
        conf_boost = -0.10  # Bad streak: more cautious
        confidence_lvl = max(-1.0, confidence_lvl - 0.1)
    elif loss_streak >= 2:
        conf_boost = -0.05
    
    base_score += conf_boost
    
    # --- 1H MULTI-TIMEFRAME CONTEXT ---
    ctx_1h = get_1h_context()
    hourly_bias = ctx_1h["bias"]
    hourly_strength = ctx_1h["strength"]
    
    # --- 4H OVERRIDE: strongest timeframe wins ---
    bias_4h = get_4h_bias()
    if bias_4h == "TREND_DOWN" and not open_position:
        log(f"4H OVERRIDE: TREND_DOWN blocks all entries (1h was {hourly_bias})")
        return  # 4h says NO — absolute block
    
    # HARD BLOCK: 1h downtrend (unless 4h is bullish)
    if hourly_bias == "TREND_DOWN" and bias_4h != "TREND_UP" and not open_position:
        return  # Skip — 1h says bearish, 4h doesn't disagree
    
    # --- FUNDING RATE SIGNAL ---
    funding = get_funding_rate()
    funding_signal = funding["signal"]
    
    # Contrarian funding bonuses
    if funding_signal == "EXTREME_SHORT":
        base_score += 0.12  # Everyone shorting → contrarian long opportunity
        log(f"FUNDING BOOST: +0.12 (extreme shorts, rate={funding['rate_pct']}%)")
    elif funding_signal == "SHORT_HEAVY":
        base_score += 0.06  # More shorts than usual
    elif funding_signal == "EXTREME_LONG":
        base_score -= 0.10  # Everyone longing → be cautious
    elif funding_signal == "LONG_HEAVY":
        base_score -= 0.05  # Slightly long-heavy
    
    # 1H SCORE BONUS: reward entries that align with 1h bias
    if hourly_bias == "OVERSOLD_BOUNCE":
        base_score += 0.15 * hourly_strength  # Big bonus for mean reversion
    elif hourly_bias == "TREND_UP":
        base_score += 0.10 * hourly_strength  # Trend alignment bonus
    elif hourly_bias == "NEUTRAL":
        base_score -= 0.03  # Small penalty for unclear direction
    
    # 4h bonus stacks with 1h
    if bias_4h == "TREND_UP":
        base_score += 0.08  # 4h confirms → extra confidence
    
    # Entry threshold: use 1h context instead of idle-time reduction
    effective_entry_min = ENTRY_SCORE_MIN
    if hourly_bias == "OVERSOLD_BOUNCE":
        effective_entry_min = ENTRY_SCORE_MIN * 0.60  # Lower bar for high-conviction 1h setups
    elif hourly_bias == "TREND_UP" and hourly_strength > 0.5:
        effective_entry_min = ENTRY_SCORE_MIN * 0.80  # Slightly lower for strong uptrend
    # No more idle-time threshold reduction — that was forcing bad trades
    
    entry_score = base_score

    # --- QUALITY FILTERS: volume + 15m trend ---
    vol_ok = check_volume_filter(df_feat)
    trend_15m_ok = check_15m_trend()
    
    # Add filter bonuses to score (don't block, but reward quality setups)
    if vol_ok:
        entry_score += 0.03  # Volume confirms
    if trend_15m_ok:
        entry_score += 0.05  # 15m trend aligns
    elif not trend_15m_ok and not oversold_ok:
        entry_score -= 0.08  # Against 15m trend (except oversold reversals)
    
    r_factor = dynamic_risk_factor(p_ml, entry_score=entry_score, vol_ok=vol_ok, trend_15m_ok=trend_15m_ok)

    # ---------------- Oversold-Fast-Lane ----------------
    os_min = float(_os.getenv("OS_ENTRY_SCORE_MIN", "0.20"))
    if not open_position and oversold_ok and entry_score >= os_min:
        sl_pct = max(STOP_FLOOR, STOP_ATR_MULT * (atr / max(px,1e-9)))
        eq = current_equity(px)
        qty = position_size_for_risk(px, sl_pct, eq, risk_factor=r_factor)
        if qty * px < 10 and (PAPER_MODE or DRY_RUN):
            qty = max(qty, 50.0 / max(px, 1))  # Paper safety net
        if qty * px >= 10 and today_trades < MAX_TRADES_PER_DAY:
            if place_buy(qty, px):
                open_position = __add_open_bar_time({"entry": px, "qty": qty, "atr": atr, "entry_row": dict(row)}, row)
                _paper_position_locked = qty * px  # Lock capital in position
                today_trades += 1
                bars_in_position = 0
                _last_trade_ts = time.time()  # Reset adaptive threshold timer
                sync_paper_trade("BUY", qty, px)
                tg(f"▶️ LONG {BASE_ASSET} (OS-FAST) @ {px:.2f} | size≈${qty*px:.2f} | TP {TP_MIN*100:.1f}–{TP_MAX*100:.1f}% | adx={regime['adx']:.1f} | rsi={rsi14:.1f} | vol={vol_ok} 15m={trend_15m_ok}")
                return
    # ----------------------------------------------------

    # Manage Open
    if open_position:
        bars_in_position += 1
        decision = update_position_management(px, row, effective_tp)
        if decision == "TP":
            orig_qty = open_position['qty']
            # PARTIAL EXIT: sell 50% at TP, let rest trail for bigger gains
            if not open_position.get("partial_taken") and orig_qty > 0.001:
                sell_qty = orig_qty * 0.5
                keep_qty = orig_qty - sell_qty
                pnl_partial = (px - open_position['entry']) * sell_qty
                msg = f"✅ PARTIAL TP | +{(px/open_position['entry']-1.0)*100:.2f}% | sold 50% @{px:.2f} | keeping {keep_qty:.4f}"
                log("INFO "+msg); tg(msg)
                ml_feedback_trade(open_position.get("entry_row", row), outcome_win=True)
                sync_paper_trade("SELL", sell_qty, px, pnl_partial)
                PAPER_BASE_USDT += pnl_partial
                _save_paper_balance()
                place_sell(sell_qty)
                open_position["qty"] = keep_qty
                open_position["partial_taken"] = True
                open_position["trailing_active"] = True
                open_position["peak_pnl"] = (px/open_position['entry']) - 1.0
                _paper_position_locked = keep_qty * px
                win_streak += 1
                loss_streak = 0
                log(f"TRAILING REMAINDER: {keep_qty:.4f} units, waiting for bigger move")
                return
            else:
                pnl_val = (px - open_position['entry']) * orig_qty
                msg = f"✅ TP hit | +{(px/open_position['entry']-1.0)*100:.2f}% | close @{px:.2f}"
                log("INFO "+msg); tg(msg)
                ml_feedback_trade(open_position.get("entry_row", row), outcome_win=True)
                sync_paper_trade("SELL", orig_qty, px, pnl_val)
                PAPER_BASE_USDT += pnl_val
                _paper_position_locked = 0.0
                _save_paper_balance()
                place_sell(orig_qty)
                open_position = None
                bars_in_position = 0
                loss_streak = 0
                win_streak += 1
                daily_realized_pnl += pnl_val  # Track daily PnL on TP
                daily_trade_results.append(pnl_val)
                log(f"CONFIDENCE: win_streak={win_streak} conf_lvl={confidence_lvl:.2f} | daily_pnl=${daily_realized_pnl:.2f}")
                # Reset ML threshold after winning trade (was permanently decaying)
                SEC_PML_MIN = _SEC_PML_DEFAULT
                return
        elif decision == "SL":
            pnl_val = (px - open_position['entry']) * open_position['qty']
            msg = f"⚠️ SL hit | {(px/open_position['entry']-1.0)*100:.2f}% | close @{px:.2f}"
            log("INFO "+msg); tg(msg)
            ml_feedback_trade(open_position.get("entry_row", row), outcome_win=False)
            sync_paper_trade("SELL", open_position["qty"], px, pnl_val)
            PAPER_BASE_USDT += pnl_val
            _paper_position_locked = 0.0
            _save_paper_balance()
            place_sell(open_position["qty"])
            open_position = None
            bars_in_position = 0
            loss_streak += 1
            win_streak = 0
            # Track daily realized PnL
            daily_realized_pnl += pnl_val
            daily_trade_results.append(pnl_val)
            log(f"CONFIDENCE: loss_streak={loss_streak} conf_lvl={confidence_lvl:.2f} | daily_pnl=${daily_realized_pnl:.2f}")
            if loss_streak >= LOSS_STREAK_COOL:
                # === CIRCUIT BREAKER: stop trading for REST OF DAY ===
                circuit_breaker_active = True
                circuit_breaker_reason = f"{loss_streak} consecutive losses (daily PnL: ${daily_realized_pnl:.2f})"
                log(f"🛑 CIRCUIT BREAKER: {circuit_breaker_reason} — no more trading today")
                tg(f"🛑 CIRCUIT BREAKER — {loss_streak}x Verlust in Folge. Tages-PnL: ${daily_realized_pnl:.2f}. Kein Trading bis morgen.")
            return
        elif decision == "TIME":
            pnl_val = (px - open_position['entry']) * open_position['qty']
            msg = f"⏱️ Time exit | close @{px:.2f}"
            log("INFO "+msg); tg(msg)
            upnl_time = (px / open_position["entry"]) - 1.0
            ml_feedback_trade(open_position.get("entry_row", row), outcome_win=(upnl_time > 0))
            sync_paper_trade("SELL", open_position["qty"], px, pnl_val)
            PAPER_BASE_USDT += pnl_val  # Track paper PnL
            _paper_position_locked = 0.0
            _save_paper_balance()
            place_sell(open_position["qty"])
            open_position = None
            bars_in_position = 0
            # Track win/loss on time exit too
            if upnl_time > 0:
                win_streak += 1
                loss_streak = 0
            else:
                loss_streak += 1
                win_streak = 0
            daily_realized_pnl += pnl_val  # Track daily PnL on time exit
            daily_trade_results.append(pnl_val)
            log(f"CONFIDENCE: win_streak={win_streak} loss_streak={loss_streak} conf_lvl={confidence_lvl:.2f} | daily_pnl=${daily_realized_pnl:.2f}")
            # Check if time-exit losses trigger circuit breaker
            if loss_streak >= LOSS_STREAK_COOL:
                circuit_breaker_active = True
                circuit_breaker_reason = f"{loss_streak} consecutive losses (daily PnL: ${daily_realized_pnl:.2f})"
                log(f"🛑 CIRCUIT BREAKER: {circuit_breaker_reason} — no more trading today")
                tg(f"🛑 CIRCUIT BREAKER — {loss_streak}x Verlust in Folge. Tages-PnL: ${daily_realized_pnl:.2f}. Kein Trading bis morgen.")
            return
        return

    if today_trades >= MAX_TRADES_PER_DAY:
        return

    if entry_score >= effective_entry_min:
        sl_pct = max(STOP_FLOOR, STOP_ATR_MULT * (atr / max(px,1e-9)))
        eq = current_equity(px)
        qty = position_size_for_risk(px, sl_pct, eq, risk_factor=r_factor)
        log(f"DEBUG entry: eq=${eq:.2f} risk={RISK_MIN*r_factor*100:.1f}% sl={sl_pct:.4f} px={px:.2f} qty={qty:.6f} val=${qty*px:.2f} vol={vol_ok} 15m={trend_15m_ok} r_factor={r_factor:.1f}")
        if qty * px < 10:
            if PAPER_MODE or DRY_RUN:
                # Paper mode safety net: force minimum position
                qty = max(qty, 50.0 / max(px, 1))  # At least $50
                log(f"PAPER-FIX: forced min qty={qty:.6f} val=${qty*px:.2f}")
            else:
                log("WARN position too small (<10 USDT) – skip")
                return
        if place_buy(qty, px):
            open_position = __add_open_bar_time({"entry": px, "qty": qty, "atr": atr, "entry_row": dict(row)}, row)
            _paper_position_locked = qty * px  # Lock capital
            today_trades += 1
            bars_in_position = 0
            _last_trade_ts = time.time()  # Reset adaptive threshold timer
            sync_paper_trade("BUY", qty, px)
            tg(f"▶️ LONG {BASE_ASSET} @ {px:.2f} | size≈${qty*px:.2f} | TP {TP_MIN*100:.1f}–{TP_MAX*100:.1f}% | p_ml={p_ml:.2f} | adx={regime['adx']:.1f} | vol={vol_ok} 15m={trend_15m_ok} risk={r_factor:.1f}x")
    else:
        log(f"INFO no entry | score={entry_score:.2f}/{effective_entry_min:.2f} p_ml={p_ml:.2f} adx={regime['adx']:.1f} px={px:.2f} rsi={rsi14:.1f} brk={breakout_ok} ema_b={ema_bounce_ok} bb_b={bb_bounce_ok} macd_x={macd_cross_ok} vol={vol_ok} 15m={trend_15m_ok}")
def rss_thread():
    while not STOP.is_set():
        try:
            poll_rss_sentiment()
        except Exception:
            pass
        for _ in range(15):
            if STOP.wait(0.2):
                break

def main_loop():
    tg("Bot gestartet | DRY_RUN=%s | PAPER_MODE=%s | MaxTrades=%s | Version=%s" % (DRY_RUN, PAPER_MODE, MAX_TRADES_PER_DAY, BOT_VERSION))
    log(f"START ETH Master Bot | DRY_RUN={DRY_RUN} | PAPER_MODE={PAPER_MODE} | MaxTrades={MAX_TRADES_PER_DAY} | Version={BOT_VERSION}")
    if DRY_RUN or PAPER_MODE:
        _load_paper_balance()  # Load persisted balance from PostgreSQL
        log(f"Paper USDT: {PAPER_BASE_USDT:.2f}")
    if not (TG_TOKEN and TG_CHAT):
        log("HINWEIS: Telegram nicht konfiguriert (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")

    threading.Thread(target=rss_thread, daemon=True).start()

    while not STOP.is_set():
        t0 = time.time()
        try:
            decide_and_trade()
        except Exception as e:
            log(f"ERROR cycle: {e}")
        remaining = max(0.0, float(SLEEP_SECONDS) - (time.time() - t0))
        steps = int(remaining / 0.2) if remaining > 0 else 0
        for _ in range(steps):
            if STOP.wait(0.2):
                return
        if remaining - steps * 0.2 > 1e-6:
            STOP.wait(remaining - steps * 0.2)

def handle_sigterm(sig, frame):
    STOP.set()
    log("STOP signal – exiting...")

# ------------------ BACKTEST ------------------
def backtest(days=30, interval="5m"):
    log(f"BACKTEST start: days={days} interval={interval}")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    df = fetch_klines(interval=interval, start_ts=int(start.timestamp()*1000), end_ts=int(end.timestamp()*1000))
    df_feat = add_features(df)
    if len(df_feat) < 200:
        print("Not enough data"); return

    # Use adx14 from add_features() — was broken: adx_full = None
    adx_full = df_feat["adx14"].fillna(0.0)

    atr_med_rolling = df_feat["atr"].rolling(200, min_periods=20).median()
    vol_ok_series = (df_feat["atr"] >= atr_med_rolling).fillna(True)
    trend_ok_series = (adx_full >= ADX_MIN_TREND) if USE_ADX_FILTER else pd.Series([True]*len(df_feat), index=df_feat.index)

    eq = 100000.0
    position = None
    trades = 0
    wins = 0
    bars_in_pos = 0

    for i in range(60, len(df_feat)-1):
        row = df_feat.iloc[i]
        prev = df_feat.iloc[i-1]
        px = float(row["close"]); ema20=float(row["ema20"]); ema50=float(row["ema50"]); rsi14=float(row["rsi14"])
        hh20=float(row["hh20"]); atr=float(row["atr"]); bb_lo=float(row["bb_lo"]); ll20=float(row.get("ll20", px))

        drawdown_ok = is_drawdown_candle(df.iloc[i-1])
        breakout_ok = px > hh20 * (1.0 + BREAKOUT_PCT)
        trend_ok    = (px > ema20) and (ema20 > ema50)
        rsi_ok      = (RSI_MIN <= rsi14 <= RSI_MAX)

        macd_gain = float(row["macd"] - row["macd_sig"])
        p_ml = 0.5 + np.tanh(macd_gain)*0.2
        secondary_ok = trend_ok and (rsi14 >= RSI_MIN) and (p_ml >= SEC_PML_MIN) and (px > ema20)

        # --- Sideways signals (SYNCHRONIZED with live trading) ---
        oversold_ok = (rsi14 <= max(40.0, RSI_MIN)) and drawdown_ok and (px >= bb_lo * 1.0005)
        ema_bounce_ok = (px > ema20) and (float(row["low"]) <= ema20 * 1.002) and (rsi14 > 40)
        bb_bounce_ok = (px <= bb_lo * 1.005) and (rsi14 < 45) and (px > float(row["low"]))
        macd_val = float(row.get("macd", 0))
        macd_sig_val = float(row.get("macd_sig", 0))
        prev_macd = float(prev.get("macd", 0)) if hasattr(prev, 'get') else float(prev["macd"]) if "macd" in prev.index else 0
        prev_macd_sig = float(prev.get("macd_sig", 0)) if hasattr(prev, 'get') else float(prev["macd_sig"]) if "macd_sig" in prev.index else 0
        macd_cross_ok = (macd_val > macd_sig_val) and (prev_macd <= prev_macd_sig)
        range_support_ok = (px <= ll20 * 1.003) and (rsi14 < 40) and (macd_val > prev_macd)

        trend_gate = bool(trend_ok_series.iloc[i])
        vol_gate   = bool(vol_ok_series.iloc[i])
        if not (trend_gate or vol_gate):
            if position: bars_in_pos += 1
            continue

        adx_now = float(adx_full.iloc[i]) if not np.isnan(adx_full.iloc[i]) else 0.0
        adx_bonus = max(0.0, min((adx_now - 20.0) / 400.0, 0.15))
        ml_direct = max(0.0, min(0.15, (p_ml - 0.5) * 0.3)) if p_ml > 0.55 else 0.0
        boost = (p_ml - 0.5) * 0.4 + adx_bonus

        # SYNCHRONIZED scoring weights (matches live trading exactly)
        score = (
            0.20*(1.0 if breakout_ok else 0.0) +
            0.12*(1.0 if trend_ok else 0.0) +
            0.05*(1.0 if secondary_ok else 0.0) +
            0.12*(1.0 if drawdown_ok else 0.0) +
            0.06*(1.0 if rsi_ok else 0.0) +
            0.05*(1.0 if vol_gate else 0.0) +
            0.15*(1.0 if oversold_ok else 0.0) +
            0.12*(1.0 if ema_bounce_ok else 0.0) +
            0.10*(1.0 if bb_bounce_ok else 0.0) +
            0.12*(1.0 if macd_cross_ok else 0.0) +
            0.08*(1.0 if range_support_ok else 0.0) +
            ml_direct +
            boost
        )

        if position:
            bars_in_pos += 1
            entry = position["entry"]; atr_in=position["atr"]
            upnl = (px/entry)-1.0
            tp = TP_MAX if rsi14 >= 70 else TP_MIN
            sl = max(STOP_FLOOR, STOP_ATR_MULT*(atr_in/max(entry,1e-9)))
            trail = (TRAIL_ATR_MULT * (row["atr"] / max(entry,1e-9)))
            sl = max(sl, trail)
            if upnl >= tp or upnl <= -sl or bars_in_pos >= MAX_HOLD_BARS:
                eq *= (1.0 + upnl)
                wins += 1 if upnl>0 else 0
                position=None
                bars_in_pos = 0
        else:
            if trades < 3*days and score >= ENTRY_SCORE_MIN:
                qty = eq/px
                position={"entry":px,"qty":qty,"atr":atr}
                trades += 1

    print(json.dumps({"equity_end":eq, "trades":trades, "winrate": (wins/max(trades,1))}, indent=2))
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true", help="run backtest and exit")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--interval", type=str, default=INTERVAL)
    return ap.parse_args()

# ------------------ INTERNAL UTILITIES ------------------
def _interval_minutes(interval_str: str) -> int:
    import re as _re
    m = _re.match(r"^(\d+)([mhd])$", interval_str.strip())
    if not m:
        return 5
    n, u = int(m.group(1)), m.group(2)
    mult = {'m': 1, 'h': 60, 'd': 1440}.get(u, 1)
    return n * mult

# ------------------ ENTRY HELPERS ------------------
def __add_open_bar_time(open_pos_dict, row):
    """Speichert exakte Kerzenzeit beim Entry."""
    try:
        open_pos_dict["open_bar_time"] = row["time"]
    except Exception:
        pass
    return open_pos_dict

# ------------------ PERSISTENT TRADE LOG ------------------
def log_trade(action: str, qty: float, price: float):
    """Schreibt Trades nach /root/ethbot/logs/trades.csv (UTC,CSV)."""
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        path = "/root/ethbot/logs/trades.csv"
        header_needed = False
        import os
        if not os.path.exists(path):
            header_needed = True
        with open(path, "a", encoding="utf-8") as f:
            if header_needed:
                f.write("timestamp,action,qty,price\n")
            f.write(f"{ts},{action},{qty:.6f},{price:.2f}\n")
    except Exception as e:
        log(f"WARN trade log failed: {e}")

# ------------------ TRADE LOG WRAPPERS ------------------
def _install_trade_logging_wrappers():
    """Wrappt place_buy/place_sell, um Trades persistent zu loggen."""
    # Originale referenzieren
    _orig_buy = place_buy
    _orig_sell = place_sell

    def _wrapped_buy(qty, price_hint):
        ok = _orig_buy(qty, price_hint)
        try:
            # price_hint als Proxy; bei Live könnte man Fill-Preis aus resp nehmen
            log_trade("BUY", float(qty), float(price_hint))
        except Exception:
            pass
        return ok

    def _wrapped_sell(qty):
        px = float(last_price() or 0.0)
        ok = _orig_sell(qty)
        try:
            log_trade("SELL", float(qty), float(px))
        except Exception:
            pass
        return ok

    # Monkey-Patch aktivieren
    globals()['place_buy'] = _wrapped_buy
    globals()['place_sell'] = _wrapped_sell

def main():
    # harden re import in scope
    import re  # noqa: F401
    init_env()
    
    # Restore ML model from last session (survives Railway deploys)
    load_ml_model()
    _load_paper_balance()
    
    args = parse_args()
    if args.backtest:
        backtest(days=args.days, interval=args.interval)
        return
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    main_loop()

if __name__ == "__main__":
    main()

def _atr_pct(symbol="ETHUSDT", interval="5m", n=48):
    """
    Grobe ATR%%-Schätzung auf Basis Binance-Klines (5m, n=48 ≈ 4h).
    Rückgabe: ATR in Prozent vom letzten Close (z.B. 0.018 = 1.8%%)
    """
    import json, urllib.request
    url=f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={n+1}"
    with urllib.request.urlopen(url, timeout=10) as r:
        kl=json.load(r)
    highs=[float(k[2]) for k in kl]
    lows =[float(k[3]) for k in kl]
    closes=[float(k[4]) for k in kl]
    trs=[]
    for i in range(1,len(closes)):
        h=highs[i]; l=lows[i]; pc=closes[i-1]
        tr=max(h-l, abs(h-pc), abs(l-pc))
        trs.append(tr)
    atr=sum(trs)/len(trs) if trs else 0.0
    last=closes[-1]
    return (atr/last) if last>0 else 0.0
def pre_buy_guards() -> bool:
    """
    Führt alle Pre-BUY-Safeguards aus. Rückgabe:
    True = BUY erlaubt, False = blockiert.
    """
    import subprocess
    # 1) Loss Cooldown
    g1 = subprocess.run(["/root/ethbot/loss_cooldown.py"], capture_output=True, text=True)
    if g1.returncode != 0:
        log("[SAFEGUARD] BUY blocked by loss cooldown"); return False
    # 2) Max Consecutive Losses
    g2 = subprocess.run(["/root/ethbot/max_losses_guard.py"], capture_output=True, text=True)
    if g2.returncode != 0:
        log("[SAFEGUARD] BUY blocked by max consecutive losses"); return False
    # 3) Daily Profit Target
    g3 = subprocess.run(["/root/ethbot/daily_target_guard.py"], capture_output=True, text=True)
    if g3.returncode != 0:
        log("[SAFEGUARD] BUY blocked by daily profit target reached"); return False
    # 4) News / Twitter Kill-Switch
    g4 = subprocess.run(["/root/ethbot/news_guard_check.py"], capture_output=True, text=True)
    if g4.returncode != 0:
        log("[SAFEGUARD] BUY blocked by news event"); return False
    return True
# ===== LIVE EDGE PARAMS (Auto-Reload from .env.bot) =====
from pathlib import Path

def get_edge_params():
    """Read latest adaptive thresholds from .env.bot (live reload)."""
    env_path = Path("/root/ethbot/.env.bot")
    adx_min, rsi_lo, rsi_hi, vwap_tol = 18, 30, 58, 1.000  # defaults
    try:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k == "ADX_MIN": adx_min = float(v)
                    elif k == "RSI_LO": rsi_lo = float(v)
                    elif k == "RSI_HI": rsi_hi = float(v)
                    elif k == "VWAP_TOL": vwap_tol = float(v)
    except Exception as e:
        print(f"[WARN] get_edge_params failed: {e}")
    return adx_min, rsi_lo, rsi_hi, vwap_tol


def _wrap_limit_func(_fn):
    """Wrappt eine Limit-Order-Funktion: preflight & quantize vor Orderversand.
    Erwartet Signatur (_symbol, _side, _price, _qty, *args, **kwargs). Gibt Ergebnis von _fn zurück
    oder ein Block-Objekt mit status='blocked'.
    """
    def _w(_symbol, _side, _price, _qty, *args, **kwargs):
        try:
            if _xf is not None:
                ok, res = _xf.preflight_order(_symbol, float(_price), float(_qty))
                if not ok:
                    try:
                        log(f"[ORDER_FILTER] block: {res.get('reason')} (pre={_qty}@{_price} -> post={res.get('qty')}@{res.get('price')})")
                    except Exception:
                        pass
                    return {"status":"blocked", "reason": res.get("reason","filter"), "pre": {"price":_price,"qty":_qty}, "post": res}
                _price, _qty = res["price"], res["qty"]
        except Exception as e:
            try:
                log(f"[ORDER_FILTER] warn: preflight_error {e}")
            except Exception:
                pass
        return _fn(_symbol, _side, _price, _qty, *args, **kwargs)
    return _w

# === Append-only Trade CSV Logger (DRY & LIVE) ===
import csv, datetime, os, pathlib
def log_trade_csv(action:str, qty:float, price:float, path="/root/ethbot/logs/trades.csv"):
    try:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        header = "timestamp,action,qty,price\n"
        if not p.exists() or p.stat().st_size == 0:
            p.write_text(header)
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with p.open("a", newline="") as f:
            w = csv.writer(f)
            w.writerow([ts, action, f"{qty:.6f}", f"{price:.2f}"])
    except Exception as e:
        print("[trade_log_error]", e)
