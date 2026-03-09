#!/usr/bin/env python3
import os as _os
try:
    import exchange_filters as _xf
except Exception:
    _xf=None


def _safe_adx(df_feat, window):
    try:
        import pandas as pd
        from ta.trend import ADXIndicator
        sub = df_feat.tail(max(window, 14)).copy()
        for c in ("high","low","close"):
    # px heartbeat
    
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        sub = sub.dropna()
        if len(sub) < 14:
            return 0.0
        w = min(window, max(14, len(sub)//2))
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

# ML
from sklearn.linear_model import SGDClassifier
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

TP_MIN             = float(_os.getenv("TARGET_PCT", "0.010"))      # 1.0% (faster exits)
TP_MAX             = float(_os.getenv("TARGET_PCT_MAX", "0.015"))  # 1.5% (optimized)
STOP_ATR_MULT      = float(_os.getenv("STOP_ATR_MULT", "1.5"))
STOP_FLOOR         = float(_os.getenv("STOP_FLOOR", "0.005"))      # 0.5% (tighter SL)

# --- Risk/Engine tuning ---
RISK_PCT_PER_TRADE = float(_os.getenv("RISK_PCT_PER_TRADE", "0.006"))  # 0.6% vom Equity (optimized for 1% target)

TRAIL_PCT       = float(_os.getenv("TRAIL_PCT", "0.008"))   # fallback 0.8%
TAKE_PROFIT_PCT = float(_os.getenv("TAKE_PROFIT_PCT", "0.015"))  # fallback 1.5%

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
LOSS_STREAK_COOL   = int(_os.getenv("LOSS_STREAK_COOL", "2"))          # n Verluste in Folge -> Cooldown
COOLDOWN_MIN       = int(_os.getenv("COOLDOWN_MIN", "10"))             # Minuten Pause nach Loss-Streak

BREAK_EVEN_TRIGGER = float(_os.getenv("BREAK_EVEN_TRIGGER", "0.006"))  # +0.6% -> SL auf BE
TRAIL_ATR_MULT     = float(_os.getenv("TRAIL_ATR_MULT", "1.0"))        # ATR * x als Trailing
MAX_HOLD_BARS      = int(_os.getenv("MAX_HOLD_BARS", "48"))            # Zeit-Exit (z. B. 48 x 5m = 4h)

# Regime-Filter
USE_ADX_FILTER     = _os.getenv("USE_ADX_FILTER", "true").lower()=="true"
ADX_WINDOW         = int(_os.getenv("ADX_WINDOW", "14"))
ADX_MIN_TREND      = float(_os.getenv("ADX_MIN_TREND", "15.0"))     # Lowered for more opportunities
# --- Entry thresholds (tunable via ENV) ---
ENTRY_SCORE_MIN    = float(_os.getenv("ENTRY_SCORE_MIN", "0.25"))   # Lowered — bot needs to actually trade
BREAKOUT_PCT       = float(_os.getenv("BREAKOUT_PCT", "0.00005"))   # 0.005% über HH20 (easier)
RSI_MIN            = float(_os.getenv("RSI_MIN", "35"))              # More opportunities
RSI_MAX            = float(_os.getenv("RSI_MAX", "75"))              # Allow higher RSI entries
SEC_PML_MIN        = float(_os.getenv("SEC_PML_MIN", "0.40"))       # Lower ML threshold
        # ab hier gilt 'trendend'

PAPER_BASE_USDT    = float(_os.getenv("PAPER_BASE_USDT", "100000"))
PAPER_MODE         = _os.getenv("PAPER_MODE", "true").lower() in ("true", "1", "yes")
_paper_position_locked = 0.0  # Value locked in open positions
SLEEP_SECONDS      = int(_os.getenv("LOOP_SLEEP", "120"))  # 2min — optimized for 100k ScraperAPI/month

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

# ML
clf = Pipeline([
    ("scaler", StandardScaler(with_mean=True)),
    ("sgd", SGDClassifier(loss="log_loss", alpha=1e-4, max_iter=5, tol=1e-3))
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
        if "tp_min" in p:
            TP_MIN = float(p["tp_min"])
        if "tp_max" in p:
            TP_MAX = float(p["tp_max"])
        if "stop_floor" in p:
            STOP_FLOOR = float(p["stop_floor"])
        if "risk_per_trade" in p:
            RISK_PCT_PER_TRADE = float(p["risk_per_trade"])
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
            _ENTRY_CEILING = max(0.15, min(0.50, float(p["entry_score_min"])))
        
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
_ENTRY_CEILING = 0.40      # Max threshold after winning streak
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
        if hours_since_trade >= _EMERGENCY_HOURS and today_trades == 0:
            _adaptive_entry_min = _ENTRY_FLOOR
            ENTRY_SCORE_MIN = _ENTRY_FLOOR
            SEC_PML_MIN = 0.25
            log(f"🚨 EMERGENCY MODE: 0 trades in {hours_since_trade:.1f}h! Threshold={_ENTRY_FLOOR}, ml_min=0.25 — MUST TRADE")
    elif today_trades > 0 and loss_streak == 0:
        # Winning = gently raise threshold
        _adaptive_entry_min = min(_ENTRY_CEILING, _adaptive_entry_min + 0.01)
        ENTRY_SCORE_MIN = _adaptive_entry_min

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
    out.dropna(inplace=True)
    return out

def is_drawdown_candle(row):
    body = abs(row["close"] - row["open"])
    range_ = row["high"] - row["low"]
    lower_wick = (min(row["open"], row["close"]) - row["low"])
    cond = (range_ > 0) and (lower_wick / max(range_, 1e-9) > 0.45) and (row["close"] > (row["low"] + 0.5*range_))
    return cond

# ------------------ ML ------------------
def ml_prepare(df_feat: pd.DataFrame):
    X = df_feat[["ret1","ema20","ema50","macd","macd_sig","rsi14","atr","bb_hi","bb_lo"]].values
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
        if not ml_warm:
            # Use full Pipeline.fit() so StandardScaler gets fitted too!
            clf.fit(X[:min(200, len(X))], y[:min(200, len(y))])
            if len(X) > 200:
                X_rest_scaled = clf.named_steps["scaler"].transform(X[200:])
                clf.named_steps["sgd"].partial_fit(X_rest_scaled, y[200:], classes=ml_classes)
            ml_warm = True
            log(f"ML warm! Trained on {len(X)} samples")
        else:
            # Online update: scaler already fitted, just update SGD
            X_scaled = clf.named_steps["scaler"].transform(X[-200:])
            clf.named_steps["sgd"].partial_fit(X_scaled, y[-200:])
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
            requests.post(f"{api_url}/api/ml/stats-sync", json=ml_stats, timeout=5)
        except Exception:
            pass
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
    v = np.array([[row["ret1"], row["ema20"], row["ema50"], row["macd"], row["macd_sig"],
                   row["rsi14"], row["atr"], row["bb_hi"], row["bb_lo"]]])
    try:
        p = clf.predict_proba(v)[0,1]
        ml_stats["predictions_made"] = ml_stats.get("predictions_made", 0) + 1
        return float(p)
    except Exception:
        return 0.5

# --- Trade Outcome Feedback ---
# Buffer of (features, outcome) from real trades for ML retraining
_trade_feedback_buffer = []

def ml_feedback_trade(entry_row, outcome_win: bool):
    """
    Feed trade outcome back into ML model.
    Called after every trade close (TP/SL/TIME).
    outcome_win: True if trade was profitable, False otherwise.
    """
    global _trade_feedback_buffer
    
    if not ml_warm:
        return
    
    try:
        features = [entry_row["ret1"], entry_row["ema20"], entry_row["ema50"],
                     entry_row["macd"], entry_row["macd_sig"], entry_row["rsi14"],
                     entry_row["atr"], entry_row["bb_hi"], entry_row["bb_lo"]]
        label = 1 if outcome_win else 0
        _trade_feedback_buffer.append((features, label))
        
        # Retrain every 5 trade outcomes (small batch for responsiveness)
        if len(_trade_feedback_buffer) >= 5:
            X = np.array([f for f, _ in _trade_feedback_buffer])
            y = np.array([l for _, l in _trade_feedback_buffer])
            
            # Scale features before partial_fit (SGD expects scaled input)
            X_scaled = clf.named_steps["scaler"].transform(X)
            sample_weight = np.ones(len(y)) * 3.0
            clf.named_steps["sgd"].partial_fit(X_scaled, y, classes=ml_classes, sample_weight=sample_weight)
            
            log(f"ML FEEDBACK: retrained on {len(_trade_feedback_buffer)} real trades "
                f"(wins: {sum(y)}, losses: {len(y)-sum(y)})")
            _trade_feedback_buffer.clear()
    except Exception as e:
        log(f"WARN ml feedback failed: {e}")

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
    if DRY_RUN:
        # Subtract value locked in open positions
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
    if DRY_RUN or not (BINANCE_API_KEY and BINANCE_API_SECRET):
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
        return True

    # === LIVE ORDER ===
    try:
        from binance.client import Client
        cli = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        quote = round(float(qty) * float(price_hint), 2)
        try:
            cli.order_market_buy(symbol=PAIR, quoteOrderQty=quote)
        except Exception:
            # Fallback auf Stückzahl
            cli.order_market_buy(symbol=PAIR, quantity=round(float(qty), 5))
        
        log(f"[LIVE] BUY {qty:.5f} {BASE_ASSET} @ ~{price_hint:.2f}")
        
        # Trailing/TP State setzen
        TRAIL_STATE['active']    = True
        TRAIL_STATE['entry']     = float(price_hint)
        TRAIL_STATE['peak']      = float(price_hint)
        TRAIL_STATE['qty']       = float(qty)
        import time as _t
        TRAIL_STATE['opened_at'] = _t.time()
        return True
    except Exception as e:
        log(f'WARN live buy failed: {e}')
        return False

def place_sell(qty: float) -> bool:
    px = last_price() or 0.0
    if DRY_RUN or not (BINANCE_API_KEY and BINANCE_API_SECRET):
        log(f"[DRY] SELL {qty:.5f} {BASE_ASSET} @ ~{px:.2f}")
        return True
    try:
        from binance.client import Client
        cli = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        cli.order_market_sell(symbol=PAIR, quantity=round(qty,5))
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
def position_size_for_risk(px, sl_pct, eq):
    """
    Risiko pro Trade = eq * RISK_PCT_PER_TRADE
    Größe (qty) = (RiskUSD) / (sl_pct * px)
    """
    risk_usd = max(0.0, float(eq) * float(RISK_PCT_PER_TRADE))
    denom = max(sl_pct * px, 1e-9)
    qty = risk_usd / denom
    return max(0.0001, qty)

def update_position_management(px, row, effective_tp):
    """
    Break-even, Trailing & Time-based Exit.
    Nutzt global open_position.
    Time-Exit: echte Kerzenanzahl seit Entry (nicht Loops!)
    """
    global open_position, loss_streak
    entry = open_position["entry"]; qty = open_position["qty"]; atr_in = open_position.get("atr", row["atr"])
    upnl = (px/entry) - 1.0

    # Dynamischer SL: Start = max(Floor, ATR-Mult)
    sl_pct = max(STOP_FLOOR, STOP_ATR_MULT * (atr_in / max(entry,1e-9)))

    # Break-even nach kleinem Gewinn
    if upnl >= BREAK_EVEN_TRIGGER:
        sl_pct = max(sl_pct, 0.0)  # BE = 0%

    # Trailing über ATR
    trail = (TRAIL_ATR_MULT * (row["atr"] / max(entry,1e-9)))
    sl_pct = max(sl_pct, trail)

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
    # ========================================
    # Regel-Exit

    if upnl >= effective_tp:
        return "TP"
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


    if now_date() != last_trade_day:
        last_trade_day = now_date()
        today_trades = 0
        loss_streak = 0
        cooldown_until_ts = 0.0
        day_start_equity = current_equity()
        log(f"INFO new UTC day → reset trade counter | day_start_equity={day_start_equity:.2f}")

    if day_start_equity is None:
        day_start_equity = current_equity()

    eq_now = current_equity()
    dd = (eq_now / max(day_start_equity, 1e-9)) - 1.0
    if dd <= -MAX_DRAWDOWN_DAY:
        log(f"GUARD daily max drawdown reached ({dd*100:.2f}%) → pause")
        return

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

    # Oversold stärker gewichten
    base_score = (
        0.32*(1.0 if breakout_ok else 0.0) +
        0.18*(1.0 if drawdown_ok else 0.0) +
        0.16*(1.0 if trend_ok else 0.0) +
        0.06*(1.0 if rsi_ok_band else 0.0) +
        0.18*(1.0 if oversold_ok else 0.0) +
        0.05*(1.0 if secondary_ok else 0.0) +
        0.05*(1.0 if regime["vol_ok"] else 0.0) +
        boost
    )
    
    # PAPER MODE GUARANTEE: if no trades for 1h+, boost score so bot trades
    hours_idle = (time.time() - _last_trade_ts) / 3600.0
    if PAPER_MODE and today_trades == 0 and hours_idle >= 1.0:
        # Force a trade: any positive signal gets through
        paper_boost = 0.40  # Guaranteed to exceed ENTRY_SCORE_MIN (0.25)
        if trend_ok or rsi_ok_band or p_ml > 0.45 or oversold_ok:
            base_score += paper_boost
            log(f"PAPER-FORCE: boosting entry score by {paper_boost} (idle {hours_idle:.1f}h, 0 trades)")
    
    entry_score = base_score

    # ---------------- Oversold-Fast-Lane ----------------
    os_min = float(_os.getenv("OS_ENTRY_SCORE_MIN", "0.20"))
    if not open_position and oversold_ok and entry_score >= os_min:
        sl_pct = max(STOP_FLOOR, STOP_ATR_MULT * (atr / max(px,1e-9)))
        eq = current_equity(px)
        qty = position_size_for_risk(px, sl_pct, eq)
        if qty * px >= 10 and today_trades < MAX_TRADES_PER_DAY:
            if place_buy(qty, px):
                open_position = __add_open_bar_time({"entry": px, "qty": qty, "atr": atr, "entry_row": dict(row)}, row)
                _paper_position_locked = qty * px  # Lock capital in position
                today_trades += 1
                bars_in_position = 0
                _last_trade_ts = time.time()  # Reset adaptive threshold timer
                sync_paper_trade("BUY", qty, px)
                tg(f"▶️ LONG {BASE_ASSET} (OS-FAST) @ {px:.2f} | size≈${qty*px:.2f} | TP {TP_MIN*100:.1f}–{TP_MAX*100:.1f}% | adx={regime['adx']:.1f} | rsi={rsi14:.1f}")
                return
    # ----------------------------------------------------

    # Manage Open
    if open_position:
        bars_in_position += 1
        decision = update_position_management(px, row, effective_tp)
        if decision == "TP":
            pnl_val = (px - open_position['entry']) * open_position['qty']
            msg = f"✅ TP hit | +{(px/open_position['entry']-1.0)*100:.2f}% | close @{px:.2f}"
            log("INFO "+msg); tg(msg)
            ml_feedback_trade(open_position.get("entry_row", row), outcome_win=True)
            sync_paper_trade("SELL", open_position["qty"], px, pnl_val)
            PAPER_BASE_USDT += pnl_val  # Track paper PnL
            _paper_position_locked = 0.0  # Release locked capital
            _save_paper_balance()  # Persist across deploys
            place_sell(open_position["qty"])
            open_position = None
            bars_in_position = 0
            loss_streak = 0
            return
        elif decision == "SL":
            pnl_val = (px - open_position['entry']) * open_position['qty']
            msg = f"⚠️ SL hit | {(px/open_position['entry']-1.0)*100:.2f}% | close @{px:.2f}"
            log("INFO "+msg); tg(msg)
            ml_feedback_trade(open_position.get("entry_row", row), outcome_win=False)
            sync_paper_trade("SELL", open_position["qty"], px, pnl_val)
            PAPER_BASE_USDT += pnl_val  # Track paper PnL
            _paper_position_locked = 0.0
            _save_paper_balance()
            place_sell(open_position["qty"])
            open_position = None
            bars_in_position = 0
            loss_streak += 1
            if loss_streak >= LOSS_STREAK_COOL:
                cooldown_until_ts = time.time() + COOLDOWN_MIN*60
                log(f"COOLDOWN {COOLDOWN_MIN}m after loss streak ({loss_streak})")
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
            return
        return

    if today_trades >= MAX_TRADES_PER_DAY:
        return

    if entry_score >= ENTRY_SCORE_MIN:
        sl_pct = max(STOP_FLOOR, STOP_ATR_MULT * (atr / max(px,1e-9)))
        eq = current_equity(px)
        qty = position_size_for_risk(px, sl_pct, eq)
        if qty * px < 10:
            log("WARN position too small (<10 USDT) – skip")
            return
        if place_buy(qty, px):
            open_position = __add_open_bar_time({"entry": px, "qty": qty, "atr": atr, "entry_row": dict(row)}, row)
            _paper_position_locked = qty * px  # Lock capital
            today_trades += 1
            bars_in_position = 0
            _last_trade_ts = time.time()  # Reset adaptive threshold timer
            sync_paper_trade("BUY", qty, px)
            tg(f"▶️ LONG {BASE_ASSET} @ {px:.2f} | size≈${qty*px:.2f} | TP {TP_MIN*100:.1f}–{TP_MAX*100:.1f}% | p_ml={p_ml:.2f} | adx={regime['adx']:.1f} | oversold={oversold_ok} sec={secondary_ok}")
    else:
        log(f"INFO no entry | score={entry_score:.2f} p_ml={p_ml:.2f} adx={regime['adx']:.1f} px={px:.2f} rsi={rsi14:.1f} brk={breakout_ok} sec={secondary_ok} tr={trend_ok} dd={drawdown_ok} os={oversold_ok}")
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
    tg("Bot gestartet | DRY_RUN=%s | MaxTrades=%s" % (DRY_RUN, MAX_TRADES_PER_DAY))
    log(f"START ETH Master Bot | DRY_RUN={DRY_RUN} | MaxTrades={MAX_TRADES_PER_DAY}")
    if DRY_RUN:
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
    adx_now = 0.0

    log(f"BACKTEST start: days={days} interval={interval}")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    df = fetch_klines(interval=interval, start_ts=int(start.timestamp()*1000), end_ts=int(end.timestamp()*1000))
    df_feat = add_features(df)
    if len(df_feat) < 200:
        print("Not enough data"); return

    try:
        adx_full = None  # guarded
    except Exception:
        adx_full = pd.Series([0.0] * len(df_feat), index=df_feat.index)

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
        px = float(row["close"]); ema20=float(row["ema20"]); ema50=float(row["ema50"]); rsi14=float(row["rsi14"])
        hh20=float(row["hh20"]); atr=float(row["atr"])

        drawdown_ok = is_drawdown_candle(df.iloc[i-1])
        breakout_ok = px > hh20 * (1.0 + BREAKOUT_PCT)
        trend_ok    = (px > ema20) and (ema20 > ema50)
        rsi_ok      = (RSI_MIN <= rsi14 <= RSI_MAX)

        macd_gain = float(row["macd"] - row["macd_sig"])
        p_ml = 0.5 + np.tanh(macd_gain)*0.2
        secondary_ok = trend_ok and (rsi14 >= RSI_MIN) and (p_ml >= SEC_PML_MIN) and (px > ema20)

        trend_gate = bool(trend_ok_series.iloc[i])
        vol_gate   = bool(vol_ok_series.iloc[i])
        if not (trend_gate or vol_gate):
            if position: bars_in_pos += 1
            continue

        adx_now = float(adx_full.iloc[i]) if not np.isnan(adx_full.iloc[i]) else 0.0
        adx_bonus = max(0.0, min((adx_now - 20.0) / 400.0, 0.15))
        boost = (p_ml - 0.5) * 0.4 + adx_bonus

        score = (
            0.38*(breakout_ok) +
            0.22*(drawdown_ok) +
            0.18*(trend_ok) +
            0.10*(rsi_ok) +
            0.07*(secondary_ok) +
            0.05*(vol_gate) +
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
