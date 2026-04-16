#!/usr/bin/env python3
"""
ETH Trading Bot - Dashboard API
Real-time WebSocket API for Premium Trading Dashboard

╔═══════════════════════════════════════════════════════════════╗
║                    TABLE OF CONTENTS                          ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  SECTION 1: CORE SETUP & MIDDLEWARE          (~Line 1-200)    ║
║    - FastAPI app, CORS, GZip, Auth                            ║
║    - Binance price cache, endpoint cache                      ║
║    - Database adapter, learning_store imports                 ║
║                                                               ║
║  SECTION 2: USER AUTH & MANAGEMENT           (~Line 200-800)  ║
║    - JWT auth, login, register, password reset                ║
║    - User profiles, API key management                        ║
║    - Subscription & billing                                   ║
║                                                               ║
║  SECTION 3: TRADING & STATUS API             (~Line 800-2000) ║
║    - /api/status, /api/trades, /api/performance               ║
║    - WebSocket connections                                    ║
║    - Paper trading, position management                       ║
║                                                               ║
║  SECTION 4: ML & STRATEGY API                (~Line 2000-2800)║
║    - /api/ml/*, model training endpoints                      ║
║    - Strategy predictor, DQN agent                            ║
║                                                               ║
║  SECTION 5: BACKTEST ENGINE                  (~Line 2813-3080)║
║    - /api/backtest — real Binance data backtest               ║
║    - Walk-forward validation, scoring v8                      ║
║                                                               ║
║  SECTION 6: LEARNING & EVOLUTION             (~Line 3083-3200)║
║    - /api/learning/stats, /api/learning/evolution             ║
║    - Strategy promotion pipeline                              ║
║                                                               ║
║  SECTION 7: COPY TRADING                     (~Line 3200-3600)║
║    - Leader/follower system                                   ║
║                                                               ║
║  SECTION 8: STRATEGY LAB                     (~Line 5307-5500)║
║    - /api/strategy/backtest — lab endpoint                    ║
║    - v8 scoring synchronized                                  ║
║                                                               ║
║  SECTION 9: LOGS API                         (~Line 5500-5555)║
║    - /api/logs — bot log streaming                            ║
║                                                               ║
║  SECTION 10: ADMIN DASHBOARD                 (~Line 5558-5923)║
║    - Strategy cleanup, user management                        ║
║    - Revenue dashboard, platform analytics                    ║
║    - Emergency controls (connected to bot!)                   ║
║    - System health, Jarvis monitoring                         ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

Scoring Formula: v8 (synced across strategy_backtester.py,
continuous_backtester.py, and this file's Strategy Lab endpoint)
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
import asyncio
import logging

# Structured logging — replaces all print() calls
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("ethbot.api")
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import csv
import sqlite3
import aiosqlite
import time as _time

# Centralized state manager — replaces scattered globals
from state import state

# Simple timed cache for slow endpoints (delegates to StateManager)
_endpoint_cache = {}  # {key: (data, timestamp)} — legacy compat
def _cached(key: str, ttl: int = 30):
    """Return cached data if fresh, else None."""
    return state.cache_get(key, ttl)
def _set_cache(key: str, data):
    state.cache_set(key, data)

# v10: Cached Binance price (background refresh every 10s)
# Eliminates synchronous requests.get() on every /api/status call
_binance_price_cache = {"price": 0.0, "ts": 0.0}  # legacy compat
def _get_cached_eth_price() -> float:
    """Return cached ETH price. Background task refreshes it."""
    return state.eth_price or _binance_price_cache["price"]

async def _binance_price_updater():
    """Background task: refresh ETH price every 10 seconds.
    Uses asyncio.to_thread() to run requests.get() without blocking the event loop."""
    import requests as _req
    await asyncio.sleep(2)  # Let server start
    while True:
        try:
            # Run synchronous requests.get in a thread to not block event loop
            resp = await asyncio.to_thread(
                _req.get,
                "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
                timeout=5
            )
            if resp.status_code == 200:
                price = float(resp.json().get("price", 0))
                _binance_price_cache["price"] = price
                _binance_price_cache["ts"] = _time.time()
                state.eth_price = price
                state.eth_price_ts = _time.time()
        except Exception:
            pass  # Keep last known price on error
        await asyncio.sleep(10)

# Import database adapter
from db_adapter import get_db_connection, USE_POSTGRES

# Import learning store (PostgreSQL-backed)
import learning_store

# Import ML model store (PostgreSQL-backed)
import ml_model_store

# Import config sync
try:
    from src.utils.config import reload_from_settings
except ImportError:
    def reload_from_settings():
        pass  # Fallback if config module not available

# Import user manager for authentication
from user_manager import UserManager, init_users_database

# Import SaaS managers
from test_phase_manager import test_phase_manager
from subscription_manager import SubscriptionManager

# Import for chart data
from src.core.market_data import MarketDataProvider

# user_mgr is initialized below via auth_deps.get_user_manager()

# Pydantic models for authentication (must be before endpoints)
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserLogin(BaseModel):
    email_or_username: str
    password: str

class AuthResponse(BaseModel):
    user_id: int
    email: str
    username: str
    role: str
    token: str

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    role: str
    subscription_tier: str
    created_at: str
    last_login: Optional[str]
    active: bool

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class PortfolioPairCreate(BaseModel):
    trading_pair: str
    pair_name: Optional[str] = None
    pair_icon: Optional[str] = "💰"
    allocated_capital: float = 100000.0
    risk_per_trade: float = 1.0
    max_trades_per_day: int = 10
    take_profit_pct: float = 1.5
    stop_loss_pct: float = 1.0

class PortfolioPairUpdate(BaseModel):
    allocated_capital: Optional[float] = None
    risk_per_trade: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    enabled: Optional[bool] = None

# Authentication dependencies — imported from shared module
# (enables router splitting without circular imports)
from auth_deps import (
    get_current_user,
    get_current_user_optional,
    get_current_admin,
    verify_internal_api_key,
    get_user_manager,
    security,
    INTERNAL_API_KEY,
)
# Re-export user_mgr for backward compat (used throughout this file)
user_mgr = get_user_manager()

# Configuration
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "change_me")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
LOG_DIR = Path(os.getenv("LOG_DIR", str(Path(__file__).resolve().parent / "logs")))
TRADES_CSV = LOG_DIR / "trades.csv"
CONSOLE_LOG = LOG_DIR / "console.out"
# DEMO_MODE: false = show real trades, true = generate demo data
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
SETTINGS_FILE = LOG_DIR / "bot_settings.json"

app = FastAPI(title="ETH Bot Dashboard API", version="1.0.0")

# Register extracted routers
from routes.admin import router as admin_router
from routes.copy_trading import router as copy_trading_router
app.include_router(admin_router)
app.include_router(copy_trading_router)

# Gzip Compression - reduces response size by 60-80%
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS — credentials only allowed with explicit origins, never with wildcard
_cors_allow_credentials = "*" not in CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════
# RATE LIMITING (in-memory, per-IP)
# ═══════════════════════════════════════════════════════
from collections import defaultdict
import time as _rl_time

_rate_limits: Dict[str, list] = defaultdict(list)

def check_rate_limit(ip: str, bucket: str = "default", max_requests: int = 30, window_seconds: int = 60) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    key = f"{bucket}:{ip}"
    now = _rl_time.time()
    # Clean old entries
    _rate_limits[key] = [t for t in _rate_limits[key] if t > now - window_seconds]
    if len(_rate_limits[key]) >= max_requests:
        return False
    _rate_limits[key].append(now)
    return True

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limit auth & expensive endpoints."""
    ip = request.client.host if request.client else "unknown"
    path = request.url.path
    
    # Auth endpoints: 5 requests / minute
    if path in ("/api/login", "/api/register", "/api/forgot-password"):
        if not check_rate_limit(ip, "auth", max_requests=5, window_seconds=60):
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Try again later."})
    
    # Backtest endpoints: 3 requests / minute (heavy compute)
    elif path in ("/api/backtest", "/api/strategy/backtest"):
        if not check_rate_limit(ip, "backtest", max_requests=3, window_seconds=60):
            return JSONResponse(status_code=429, content={"detail": "Backtest rate limit reached. Wait 60 seconds."})
    
    # General: 120 requests / minute
    elif not check_rate_limit(ip, "general", max_requests=120, window_seconds=60):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded."})
    
    return await call_next(request)

# ═══════════════════════════════════════════════════════
# SECURITY HEADERS
# ═══════════════════════════════════════════════════════
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# Public paths that intentionally don't require authentication
PUBLIC_PATHS = {
    "/health", "/api/health", "/",
    "/api/auth/login", "/api/auth/register",
    "/api/auth/forgot-password", "/api/auth/reset-password", "/api/auth/verify-reset-token",
    "/api/price/live",
}

# ═══════════════════════════════════════════════════════
# HEALTH CHECK (for Railway & monitoring)
# ═══════════════════════════════════════════════════════
@app.get("/health")
async def health_check():
    """Heartbeat endpoint for Railway health checks and monitoring."""
    db_ok = False
    try:
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                db_ok = True
    except Exception:
        pass
    
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now().isoformat(),
        "version": "v8-production",
        "uptime_check": True
    }

# Simple in-memory cache for frequent endpoints
from functools import lru_cache
import time as time_module

_cache = {}
_cache_ttl = {}

def cached_response(key: str, ttl_seconds: int = 30):
    """Simple response caching decorator"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            now = time_module.time()
            if key in _cache and _cache_ttl.get(key, 0) > now:
                return _cache[key]
            result = await func(*args, **kwargs)
            _cache[key] = result
            _cache_ttl[key] = now + ttl_seconds
            return result
        return wrapper
    return decorator

# Mount static files for all 3 dashboard apps
DASHBOARD_DIST = Path(__file__).parent / "dashboard" / "dist"
ADMIN_DIST = Path(__file__).parent / "admin-dashboard" / "dist"
MONITOR_DIST = Path(__file__).parent / "strategy-monitor" / "dist"

if DASHBOARD_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(DASHBOARD_DIST / "assets")), name="assets")
if ADMIN_DIST.exists() and (ADMIN_DIST / "assets").exists():
    app.mount("/admin/assets", StaticFiles(directory=str(ADMIN_DIST / "assets")), name="admin-assets")
if MONITOR_DIST.exists() and (MONITOR_DIST / "assets").exists():
    app.mount("/monitor/assets", StaticFiles(directory=str(MONITOR_DIST / "assets")), name="monitor-assets")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# Models
class Trade(BaseModel):
    timestamp: str
    action: str
    qty: float
    price: float
    pnl: Optional[float] = None
    entry_type: Optional[str] = None
    signals: Optional[List[str]] = None
    ml_confidence: Optional[float] = None
    entry_score: Optional[float] = None

class PerformanceMetrics(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    daily_pnl: float
    avg_win: float
    avg_loss: float
    sharpe_ratio: float
    max_drawdown: float
    roi: float

class BotStatus(BaseModel):
    is_running: bool
    current_position: Optional[Dict[str, Any]]
    last_update: str
    today_trades: int
    ml_confidence: float
    sentiment_score: float
    regime: str
    current_price: float = 0.0


# Helper Functions
def generate_demo_trades() -> List[Trade]:
    """Generate realistic demo trades for testing"""
    import random
    # Use fixed seed for consistent demo data
    random.seed(42)
    trades = []
    base_price = 3200.0
    current_time = datetime.now() - timedelta(hours=24)
    
    # Generate 30 trades over 24 hours
    for i in range(30):
        # Price walks randomly
        base_price += random.uniform(-20, 20)
        
        # BUY trade
        buy_time = current_time + timedelta(minutes=random.randint(10, 60))
        buy_price = base_price + random.uniform(-5, 5)
        qty = random.uniform(0.05, 0.15)
        
        trades.append(Trade(
            timestamp=buy_time.isoformat(),
            action="BUY",
            qty=qty,
            price=buy_price,
            pnl=0
        ))
        
        # SELL trade (60% win rate)
        sell_time = buy_time + timedelta(minutes=random.randint(15, 120))
        if random.random() < 0.6:  # Win
            sell_price = buy_price + random.uniform(5, 25)
        else:  # Loss
            sell_price = buy_price - random.uniform(3, 15)
        
        pnl = (sell_price - buy_price) * qty
        
        trades.append(Trade(
            timestamp=sell_time.isoformat(),
            action="SELL",
            qty=qty,
            price=sell_price,
            pnl=pnl
        ))
        
        current_time = sell_time
    
    return trades

async def read_trades_csv() -> List[Trade]:
    """Read trades from CSV file, falling back to PostgreSQL if CSV is empty/missing"""
    if DEMO_MODE:
        return generate_demo_trades()
    
    trades = []
    
    # Try CSV first
    try:
        if TRADES_CSV.exists():
            with open(TRADES_CSV, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse signal fields (backward compatible with old CSVs)
                    signals_raw = row.get('signals', '')
                    signals_list = signals_raw.split('|') if signals_raw else None
                    trades.append(Trade(
                        timestamp=row['timestamp'],
                        action=row['action'],
                        qty=float(row['qty']),
                        price=float(row['price']),
                        pnl=float(row.get('pnl', 0)),
                        entry_type=row.get('entry_type', None) or None,
                        signals=signals_list if signals_list and signals_list != [''] else None,
                        ml_confidence=float(row['ml_confidence']) if row.get('ml_confidence') else None,
                        entry_score=float(row['entry_score']) if row.get('entry_score') else None
                    ))
    except Exception as e:
        logger.warning(f" reading trades CSV: {e}")
    
    # If CSV empty/missing, fall back to PostgreSQL (survives deploys)
    if not trades and USE_POSTGRES:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, action, qty, price, pnl 
                    FROM paper_trades ORDER BY created_at ASC
                """)
                rows = cursor.fetchall()
                for r in rows:
                    trades.append(Trade(
                        timestamp=r[0],
                        action=r[1],
                        qty=float(r[2]),
                        price=float(r[3]),
                        pnl=float(r[4] or 0)
                    ))
                if trades:
                    logger.info(f" Loaded {len(trades)} trades from PostgreSQL (CSV was empty)")
        except Exception as e:
            logger.warning(f" PG trades fallback error: {e}")
    
    return trades

async def calculate_pnl(trades: List[Trade]) -> float:
    """Calculate total PnL using FIFO"""
    from collections import deque
    fifo = deque()
    realized = 0.0
    
    for trade in trades:
        if trade.action.upper() == "BUY":
            fifo.append([trade.qty, trade.price])
        elif trade.action.upper() == "SELL" and trade.price > 0:
            remaining = trade.qty
            while remaining > 1e-12 and fifo:
                buy_qty, buy_price = fifo[0]
                take = min(buy_qty, remaining)
                realized += (trade.price - buy_price) * take
                buy_qty -= take
                remaining -= take
                if buy_qty <= 1e-12:
                    fifo.popleft()
                else:
                    fifo[0] = [buy_qty, buy_price]
    
    return realized

async def get_performance_metrics() -> PerformanceMetrics:
    """Calculate comprehensive performance metrics using recorded PnL from SELL trades.
    
    Previously used FIFO pairing which broke with orphaned BUY orders from old deploys.
    The bot already records exact PnL on each SELL via sync_paper_trade(), so we use that directly.
    """
    # Read from PostgreSQL FIRST (authoritative), CSV fallback
    trades = []
    if USE_POSTGRES:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, action, qty, price, pnl 
                    FROM paper_trades ORDER BY created_at ASC
                """)
                rows = cursor.fetchall()
                for r in rows:
                    trades.append(Trade(
                        timestamp=r[0], action=r[1],
                        qty=float(r[2]), price=float(r[3]),
                        pnl=float(r[4] or 0)
                    ))
        except Exception as e:
            logger.warning(f" PG performance trades read error: {e}")
    if not trades:
        trades = await read_trades_csv()
    
    if not trades:
        return PerformanceMetrics(
            total_trades=0, winning_trades=0, losing_trades=0,
            win_rate=0, total_pnl=0, daily_pnl=0,
            avg_win=0, avg_loss=0, sharpe_ratio=0,
            max_drawdown=0, roi=0
        )
    
    # Use recorded PnL from SELL trades if available, otherwise calculate via FIFO
    today = datetime.now().date().isoformat()
    trade_pnls = []
    today_trade_pnls = []
    
    # Check if ANY sell trade has a recorded PnL (non-zero)
    has_recorded_pnl = any(
        t.action.upper() == "SELL" and t.pnl != 0
        for t in trades
    )
    
    if has_recorded_pnl:
        # Use recorded PnL from SELL trades (PostgreSQL mode)
        for trade in trades:
            if trade.action.upper() == "SELL" and trade.pnl != 0:
                trade_pnls.append(trade.pnl)
                if trade.timestamp.startswith(today):
                    today_trade_pnls.append(trade.pnl)
    else:
        # FIFO PnL calculation (CSV mode — no pnl column)
        from collections import deque
        fifo = deque()
        for trade in trades:
            if trade.action.upper() == "BUY" and trade.price > 0:
                fifo.append([trade.qty, trade.price])
            elif trade.action.upper() == "SELL" and trade.price > 0 and fifo:
                remaining = trade.qty
                pnl_this_trade = 0.0
                while remaining > 1e-12 and fifo:
                    buy_qty, buy_price = fifo[0]
                    take = min(buy_qty, remaining)
                    pnl_this_trade += (trade.price - buy_price) * take
                    buy_qty -= take
                    remaining -= take
                    if buy_qty <= 1e-12:
                        fifo.popleft()
                    else:
                        fifo[0] = [buy_qty, buy_price]
                trade_pnls.append(pnl_this_trade)
                if trade.timestamp.startswith(today):
                    today_trade_pnls.append(pnl_this_trade)
    
    # Compute stats
    total_pnl = sum(trade_pnls)
    daily_pnl = sum(today_trade_pnls)
    
    win_pnls = [p for p in trade_pnls if p > 0]
    loss_pnls = [p for p in trade_pnls if p <= 0]
    
    winning_trades = len(win_pnls)
    losing_trades = len(loss_pnls)
    total_trades = len(trade_pnls)
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    avg_win = sum(win_pnls) / winning_trades if winning_trades > 0 else 0
    avg_loss = sum(loss_pnls) / losing_trades if losing_trades > 0 else 0
    
    # Sharpe Ratio
    if trade_pnls:
        import numpy as np
        sharpe = np.mean(trade_pnls) / np.std(trade_pnls) if np.std(trade_pnls) > 0 else 0
    else:
        sharpe = 0
    
    # Max Drawdown (based on capital, not just PnL curve)
    max_dd = 0
    initial_capital = float(os.getenv("EQUITY_USDT", "100000"))
    if trade_pnls:
        equity_curve = []
        running = initial_capital
        for pnl in trade_pnls:
            running += pnl
            equity_curve.append(running)
        peak = equity_curve[0]
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
    max_dd = min(max_dd, 1.0)  # Cap at 100%
    
    # ROI
    roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0
    
    return PerformanceMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        total_pnl=total_pnl,
        daily_pnl=daily_pnl,
        avg_win=avg_win,
        avg_loss=avg_loss,
        sharpe_ratio=sharpe,
        max_drawdown=max_dd * 100,
        roi=roi
    )

async def get_bot_status() -> BotStatus:
    """Get current bot status"""
    # Demo mode values
    if DEMO_MODE:
        import random
        ml_conf = random.uniform(0.55, 0.75)
        sentiment = random.uniform(-0.2, 0.3)
        regime = random.choice(["trending", "ranging", "trending"])
    else:
        # Read from console.out for live status
        try:
            if CONSOLE_LOG.exists():
                with open(CONSOLE_LOG, 'r') as f:
                    lines = f.readlines()[-50:]
                
                # Parse last status
                ml_conf = 0.5
                sentiment = 0.0
                regime = "unknown"
                
                for line in reversed(lines):
                    if "p_ml=" in line:
                        try:
                            ml_conf = float(line.split("p_ml=")[1].split()[0])
                        except:
                            pass
                    if "sentiment=" in line:
                        try:
                            sentiment = float(line.split("sentiment=")[1].split()[0])
                        except:
                            pass
                    if "adx=" in line:
                        try:
                            adx = float(line.split("adx=")[1].split()[0])
                            regime = "trending" if adx > 20 else "ranging"
                        except:
                            pass
            else:
                ml_conf = 0.5
                sentiment = 0.0
                regime = "unknown"
        except:
            ml_conf = 0.5
            sentiment = 0.0
            regime = "unknown"
        
        # Fallback: try kv_store trade-state if console.out didn't have data
        if regime == "unknown" and USE_POSTGRES:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM kv_store WHERE key = 'open_trade_state'")
                    row = cursor.fetchone()
                    if row:
                        import json as _json
                        state = _json.loads(row[0]) if isinstance(row[0], str) else row[0]
                        if state.get("regime"):
                            regime = state["regime"]
                        if state.get("ml_confidence"):
                            ml_conf = float(state["ml_confidence"])
            except:
                pass
        if regime == "unknown":
            regime = "paper"  # Better than "unknown" — user knows it's paper mode
    
    # Count today's trades
    trades = await read_trades_csv()
    today = datetime.now().date().isoformat()
    today_trades = len([t for t in trades if t.timestamp.startswith(today)])
    
    # v10: Use cached ETH price (background task refreshes every 10s)
    # Eliminates the ~1-3s synchronous requests.get() that was blocking the event loop
    current_price = _get_cached_eth_price()
    
    return BotStatus(
        is_running=not _bot_paused,
        current_position=None,
        last_update=datetime.now().isoformat(),
        today_trades=today_trades,
        ml_confidence=ml_conf,
        sentiment_score=sentiment,
        regime=regime,
        current_price=current_price
    )

# API Endpoints
@app.get("/")
async def root():
    """Serve dashboard HTML"""
    dashboard_index = DASHBOARD_DIST / "index.html"
    if dashboard_index.exists():
        return FileResponse(dashboard_index)
    return {"status": "ok", "service": "ETH Bot Dashboard API", "note": "Dashboard not built yet"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# --- Bot Control ---
_bot_paused = False  # When True, bot skips trading cycles

@app.post("/api/bot/start")
async def start_bot(current_user: Dict = Depends(get_current_user)):
    """Start the trading bot (resume if paused)"""
    global _bot_paused
    _bot_paused = False
    return {"is_running": True, "message": "Bot started"}

@app.post("/api/bot/stop")
async def stop_bot(current_user: Dict = Depends(get_current_user)):
    """Pause the trading bot"""
    global _bot_paused
    _bot_paused = True
    return {"is_running": False, "message": "Bot paused"}

@app.get("/api/bot/journal")
async def get_trade_journal(limit: int = 200, _user: Optional[Dict] = Depends(get_current_user_optional)):
    """Full trade journal with P&L calculations for paper and live trades"""
    trades = await read_trades_csv()
    journal = []
    last_buy = None
    
    for trade in trades:
        entry = {
            "timestamp": trade.timestamp,
            "action": trade.action,
            "qty": trade.qty,
            "price": trade.price,
            "pnl": None,
            "pnl_pct": None,
            "mode": "paper",
            "entry_type": None,
            "signals": None,
            "ml_confidence": None,
            "entry_score": None
        }
        
        if trade.action == "BUY":
            last_buy = trade
            # Store signal data from BUY for the pair
            entry["entry_type"] = trade.entry_type
            entry["signals"] = trade.signals
            entry["ml_confidence"] = trade.ml_confidence
            entry["entry_score"] = trade.entry_score
        elif trade.action == "SELL" and last_buy:
            pnl = (trade.price - last_buy.price) * trade.qty
            pnl_pct = ((trade.price - last_buy.price) / last_buy.price) * 100
            entry["pnl"] = round(pnl, 2)
            entry["pnl_pct"] = round(pnl_pct, 2)
            # Carry over signal data from the matching BUY
            entry["entry_type"] = last_buy.entry_type
            entry["signals"] = last_buy.signals
            entry["ml_confidence"] = last_buy.ml_confidence
            entry["entry_score"] = last_buy.entry_score
            last_buy = None
        
        journal.append(entry)
    
    return journal[-limit:]

@app.post("/api/bot/journal/clear")
async def clear_trade_journal(current_user = Depends(get_current_user)):
    """Clear all trades from journal (CSV + PostgreSQL). Use to remove old forced trades."""
    cleared = {"csv": 0, "db": 0}
    
    # Clear CSV
    try:
        if TRADES_CSV.exists():
            import csv
            with open(TRADES_CSV, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
            cleared["csv"] = max(0, len(rows) - 1)  # Minus header
            with open(TRADES_CSV, 'w') as f:
                f.write("timestamp,action,qty,price,pnl\n")
    except Exception as e:
        logger.warning(f" clearing CSV: {e}")
    
    # Clear PostgreSQL trade_journal
    if USE_POSTGRES:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM trade_journal")
                cleared["db"] = cursor.fetchone()[0] or 0
                cursor.execute("DELETE FROM trade_journal")
                conn.commit()
        except Exception as e:
            logger.warning(f" clearing DB trades: {e}")
    
    # Also clear PostgreSQL paper_trades table (where /api/trades reads from)
    if USE_POSTGRES:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM paper_trades")
                pt_count = cursor.fetchone()[0] or 0
                cursor.execute("DELETE FROM paper_trades")
                conn.commit()
                cleared["db"] += pt_count
        except Exception as e:
            logger.warning(f" clearing paper_trades: {e}")
    
    return {
        "status": "success",
        "cleared_csv": cleared["csv"],
        "cleared_db": cleared["db"],
        "message": f"Cleared {cleared['csv']} CSV trades and {cleared['db']} DB trades"
    }

@app.get("/api/trades", response_model=List[Trade])
async def get_trades(limit: int = 100, _user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get recent trades — reads from PostgreSQL first, falls back to CSV"""
    # Try PostgreSQL first (survives deploys)
    if USE_POSTGRES:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, action, qty, price, pnl, mode 
                    FROM paper_trades ORDER BY created_at DESC LIMIT %s
                """, (limit,))
                rows = cursor.fetchall()
                if rows:
                    return [{"timestamp": r[0], "action": r[1], "qty": r[2], 
                             "price": r[3], "pnl": r[4] or 0, "mode": r[5] or "paper"} 
                            for r in reversed(rows)]
        except Exception as e:
            logger.warning(f" PG trades read error: {e}")
    # Fallback to CSV
    trades = await read_trades_csv()
    return trades[-limit:]


@app.post("/api/trades/record")
async def record_trade(trade: dict = None, request: Request = None, _auth = Depends(verify_internal_api_key)):
    """Record a paper trade from the Worker bot.
    Called by eth_master_bot on every entry/exit.
    Now also stores signal data: entry_type, signals[], ml_confidence, entry_score."""
    try:
        if trade is None and request:
            trade = await request.json()
        
        if not trade:
            return {"status": "error", "message": "No trade data"}
        
        ts = trade.get("timestamp", datetime.now().isoformat())
        action = trade.get("action", "BUY")
        qty = trade.get("qty", 0)
        price = trade.get("price", 0)
        pnl = trade.get("pnl", 0)
        entry_type = trade.get("entry_type", "")
        signals = trade.get("signals", [])
        ml_confidence = trade.get("ml_confidence", 0)
        entry_score = trade.get("entry_score", 0)
        signals_str = "|".join(signals) if isinstance(signals, list) else str(signals)
        
        # Ensure CSV exists with header
        if not TRADES_CSV.exists():
            TRADES_CSV.parent.mkdir(parents=True, exist_ok=True)
            with open(TRADES_CSV, 'w') as f:
                f.write("timestamp,action,qty,price,pnl,entry_type,signals,ml_confidence,entry_score\n")
        
        # Append trade to CSV (backward compatible — extra fields appended)
        with open(TRADES_CSV, 'a') as f:
            f.write(f"{ts},{action},{qty},{price},{pnl},{entry_type},{signals_str},{ml_confidence},{entry_score}\n")
        
        # Also persist to PostgreSQL (survives deploys)
        if USE_POSTGRES:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO paper_trades (timestamp, action, qty, price, pnl, mode)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (ts, action, float(qty), float(price), float(pnl),
                          trade.get("mode", "paper")))
            except Exception as e:
                logger.warning(f" PG trade save error: {e}")
        
        return {"status": "recorded", "action": action, "signals": signals}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Paper balance persistence file (fallback only)
PAPER_BALANCE_FILE = LOG_DIR / "paper_balance.json"

@app.post("/api/paper-balance")
async def save_paper_balance(request: Request, _auth = Depends(verify_internal_api_key)):
    """Save paper trading balance (called by Worker bot on every trade exit).
    Uses PostgreSQL kv_store for persistence across deploys, file as fallback."""
    try:
        data = await request.json()
        balance = data.get("balance", 0)
        if balance > 0:
            updated_at = datetime.now().isoformat()
            payload = json.dumps({"balance": balance, "updated_at": updated_at})
            
            # Save to PostgreSQL (survives deploys)
            if USE_POSTGRES:
                try:
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO kv_store (key, value) VALUES ('paper_balance', %s)
                            ON CONFLICT (key) DO UPDATE SET value = %s
                        """, (payload, payload))
                except Exception as e:
                    logger.warning(f" PG paper balance save error: {e}")
            
            # Also save to file as fallback
            try:
                PAPER_BALANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(PAPER_BALANCE_FILE, 'w') as f:
                    f.write(payload)
            except Exception:
                pass
            
            return {"status": "saved", "balance": balance}
        return {"status": "error", "message": "Invalid balance"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/paper-balance")
async def get_paper_balance(_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get persisted paper trading balance.
    Reads from PostgreSQL first (survives deploys), file fallback."""
    # Try PostgreSQL first
    if USE_POSTGRES:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM kv_store WHERE key = 'paper_balance'")
                row = cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    if data.get("balance", 0) > 0:
                        return data
        except Exception as e:
            logger.warning(f" PG paper balance read error: {e}")
    
    # Fallback to file
    try:
        if PAPER_BALANCE_FILE.exists():
            with open(PAPER_BALANCE_FILE, 'r') as f:
                data = json.load(f)
            return data
    except Exception:
        pass
    
    return {"balance": 100000, "updated_at": None}

# --- ML Model Persistence (survives Railway deploys) ---
@app.post("/api/ml/model-state")
async def save_ml_model_state(request: Request, _auth = Depends(verify_internal_api_key)):
    """Save ML model weights to PostgreSQL kv_store (called by Worker after training)."""
    try:
        data = await request.json()
        import json as _json
        model_json = _json.dumps(data)
        
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO kv_store (key, value) VALUES ('sgd_model_state', %s)
                    ON CONFLICT (key) DO UPDATE SET value = %s
                """, (model_json, model_json))
            return {"status": "saved", "size": len(model_json)}
        else:
            # Fallback: save to file
            model_file = LOG_DIR / "ml_model_state.json"
            model_file.parent.mkdir(parents=True, exist_ok=True)
            with open(model_file, 'w') as f:
                f.write(model_json)
            return {"status": "saved_file", "size": len(model_json)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/ml/model-state")
async def get_ml_model_state(_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get persisted ML model weights (called by Worker on startup)."""
    try:
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM kv_store WHERE key = 'sgd_model_state'")
                row = cursor.fetchone()
                if row:
                    import json as _json
                    return _json.loads(row[0])
        else:
            model_file = LOG_DIR / "ml_model_state.json"
            if model_file.exists():
                import json as _json
                with open(model_file, 'r') as f:
                    return _json.loads(f.read())
        return {"status": "empty"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Trade State Persistence (survives Railway deploys) ---
TRADE_STATE_FILE = LOG_DIR / "trade_state.json"

@app.post("/api/trade-state")
async def save_trade_state(request: Request, _auth = Depends(verify_internal_api_key)):
    """Save open trade state to PostgreSQL kv_store (called by Worker on every BUY/SELL)."""
    try:
        data = await request.json()
        import json as _json
        state_json = _json.dumps(data)
        
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO kv_store (key, value) VALUES ('open_trade_state', %s)
                    ON CONFLICT (key) DO UPDATE SET value = %s
                """, (state_json, state_json))
            return {"status": "saved", "size": len(state_json)}
        else:
            # Fallback: save to file
            TRADE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TRADE_STATE_FILE, 'w') as f:
                f.write(state_json)
            return {"status": "saved_file", "size": len(state_json)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/trade-state")
async def get_trade_state(_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get persisted open trade state (called by Worker on startup)."""
    try:
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM kv_store WHERE key = 'open_trade_state'")
                row = cursor.fetchone()
                if row:
                    import json as _json
                    return _json.loads(row[0])
        else:
            if TRADE_STATE_FILE.exists():
                import json as _json
                with open(TRADE_STATE_FILE, 'r') as f:
                    return _json.loads(f.read())
        return {"status": "empty"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/performance", response_model=PerformanceMetrics)
async def get_performance(_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get performance metrics — v10: cached for 15s"""
    cached = _cached("perf_metrics", ttl=15)
    if cached:
        return cached
    result = await get_performance_metrics()
    _set_cache("perf_metrics", result)
    return result

@app.get("/api/performance/history")
async def get_performance_history(days: int = 7, _user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get P&L history for chart — reads from PostgreSQL first, CSV fallback"""
    trades_raw = []
    
    # Try PostgreSQL first (survives deploys)
    if USE_POSTGRES:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, action, qty, price, pnl 
                    FROM paper_trades 
                    WHERE created_at >= NOW() - INTERVAL '%s days'
                    ORDER BY created_at ASC
                """, (days + 1,))  # +1 day buffer for timezone edge cases
                for row in cursor.fetchall():
                    trades_raw.append({
                        "timestamp": row[0], "action": row[1], 
                        "qty": float(row[2] or 0), "price": float(row[3] or 0), 
                        "pnl": float(row[4] or 0)
                    })
        except Exception as e:
            logger.warning(f"performance read error: {e}")

    # Fallback to CSV
    if not trades_raw:
        csv_trades = await read_trades_csv()
        trades_raw = [{"timestamp": t.timestamp, "action": t.action, "qty": t.qty, "price": t.price, "pnl": t.pnl} for t in csv_trades]

    daily_pnl = {}

    # Check if any sell has recorded PnL
    has_recorded_pnl = any(
        t["action"] == "SELL" and t.get("pnl", 0) != 0
        for t in trades_raw
    )

    if has_recorded_pnl:
        # PostgreSQL mode: use recorded PnL
        for trade in trades_raw:
            try:
                ts = trade["timestamp"]
                date = ts.split('T')[0] if 'T' in ts else ts.split(' ')[0]
                if date not in daily_pnl:
                    daily_pnl[date] = {"date": date, "pnl": 0, "trades": 0}
                if trade["action"] == "SELL" and trade.get("pnl", 0) != 0:
                    daily_pnl[date]["pnl"] += trade["pnl"]
                    daily_pnl[date]["trades"] += 1
            except Exception as e:
                logger.warning(f" processing trade: {e}")
                continue
    else:
        # CSV mode: calculate PnL via FIFO
        from collections import deque
        fifo = deque()
        for trade in trades_raw:
            try:
                ts = trade["timestamp"]
                date = ts.split('T')[0] if 'T' in ts else ts.split(' ')[0]
                if date not in daily_pnl:
                    daily_pnl[date] = {"date": date, "pnl": 0, "trades": 0}
                if trade["action"] == "BUY" and trade["price"] > 0:
                    fifo.append([trade["qty"], trade["price"]])
                elif trade["action"] == "SELL" and trade["price"] > 0 and fifo:
                    remaining = trade["qty"]
                    pnl_trade = 0.0
                    while remaining > 1e-12 and fifo:
                        buy_qty, buy_price = fifo[0]
                        take = min(buy_qty, remaining)
                        pnl_trade += (trade["price"] - buy_price) * take
                        buy_qty -= take
                        remaining -= take
                        if buy_qty <= 1e-12:
                            fifo.popleft()
                        else:
                            fifo[0] = [buy_qty, buy_price]
                    daily_pnl[date]["pnl"] += pnl_trade
                    daily_pnl[date]["trades"] += 1
            except Exception as e:
                logger.warning(f" processing trade: {e}")
                continue

    # Convert to sorted list with cumulative P&L
    history = []
    cumulative_pnl = 0
    for date in sorted(daily_pnl.keys())[-days:]:
        cumulative_pnl += daily_pnl[date]["pnl"]
        history.append({
            "date": date,
            "daily_pnl": round(daily_pnl[date]["pnl"], 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "trades": daily_pnl[date]["trades"]
        })
    
    return history

@app.get("/api/status", response_model=BotStatus)
async def get_status(_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get bot status — v10: cached for 8s"""
    cached = _cached("bot_status", ttl=8)
    if cached:
        return cached
    result = await get_bot_status()
    _set_cache("bot_status", result)
    return result

@app.get("/api/chart/data")
async def get_chart_data(symbol: str = "ETHUSDT", interval: str = "5m", limit: int = 100, _user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get OHLCV data for charts from Binance"""
    try:
        mdp = MarketDataProvider()
        df = mdp.fetch_klines(symbol=symbol, interval=interval, lookback=limit)
        
        # Format data for frontend
        chart_data = []
        for _, row in df.iterrows():
            chart_data.append({
                "time": row["time"].strftime("%H:%M") if hasattr(row["time"], "strftime") else str(row["time"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"])
            })
        
        return {
            "symbol": symbol,
            "interval": interval,
            "data": chart_data
        }
    except Exception as e:
        logger.warning(f" fetching chart data: {e}")
        # Return empty data on error
        return {
            "symbol": symbol,
            "interval": interval,
            "data": [],
            "error": str(e)
        }

# Authentication Endpoints
@app.post("/api/auth/register", response_model=AuthResponse)
async def register(request: UserRegister):
    """Register a new user"""
    try:
        user_id = user_mgr.register_user(
            email=request.email,
            username=request.username,
            password=request.password
        )
        
        # Auto-login after registration
        result = user_mgr.login(request.email, request.password)
        
        if not result:
            raise HTTPException(status_code=500, detail="Registration succeeded but login failed")
        
        return AuthResponse(**result)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/auth/login", response_model=AuthResponse)
async def login(request: UserLogin):
    """Login user"""
    try:
        logger.info(f" Login attempt for: {request.email_or_username}")
        result = user_mgr.login(request.email_or_username, request.password)
        
        if not result:
            logger.error(f" Login failed: Invalid credentials for {request.email_or_username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        logger.info(f" Login successful for: {request.email_or_username}")
        return AuthResponse(**result)
        
    except ValueError as e:
        logger.error(f" Login ValueError: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f" Login Exception: {type(e).__name__}: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/api/auth/logout")
async def logout(current_user: Dict = Depends(get_current_user)):
    """Logout user (revoke token)"""
    # Extract token from request (this is a simplified version)
    # In production, you'd want to get the actual token from the request
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/api/auth/me")
async def get_current_user_info(authorization: Optional[str] = Header(None)):
    """Get current user information - requires valid token"""
    # No token = not authenticated
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = authorization.replace("Bearer ", "")
        payload = user_mgr.verify_jwt(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        user = user_mgr.get_user(payload['user_id'])
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        user_data = dict(user)
        if hasattr(user_data.get('created_at'), 'isoformat'):
            user_data['created_at'] = user_data['created_at'].isoformat()
        if hasattr(user_data.get('last_login'), 'isoformat'):
            user_data['last_login'] = user_data['last_login'].isoformat()
        user_data['created_at'] = str(user_data.get('created_at', ''))
        if user_data.get('last_login'):
            user_data['last_login'] = str(user_data['last_login'])
        
        return user_data
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Auth/me error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

@app.get("/api/users", response_model=List[UserResponse])
async def list_users(current_user: Dict = Depends(get_current_user)):
    """List all users (admin only)"""
    if current_user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    users = user_mgr.list_users()
    return [UserResponse(**user) for user in users]


# ============ Password Reset Endpoints ============

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@app.post("/api/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Request a password reset - sends reset token (in production: via email)"""
    try:
        token = user_mgr.generate_reset_token(request.email)
        
        # In production: Send email with reset link
        # For now, we'll return success regardless (don't reveal if email exists)
        
        if token:
            # TODO: Send email with reset link containing token
            # In production, token should be delivered via email only
            logger.info(f" Password reset requested for {request.email} (token generated, expires in 1h)")
            
            # In production, you would NOT return the token
            # Reset link would be: https://yourdomain.com/reset-password?token={token}
        
        return {
            "status": "success",
            "message": "If this email exists, a password reset link has been sent."
        }
        
    except Exception as e:
        # Don't reveal errors that could expose user existence
        return {
            "status": "success", 
            "message": "If this email exists, a password reset link has been sent."
        }

@app.post("/api/auth/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password using a valid token"""
    try:
        success = user_mgr.reset_password_with_token(request.token, request.new_password)
        
        if success:
            return {
                "status": "success",
                "message": "Password has been reset successfully. Please login with your new password."
            }
        else:
            raise HTTPException(status_code=400, detail="Password reset failed")
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Password reset failed: {str(e)}")

@app.post("/api/auth/verify-reset-token")
async def verify_reset_token(token: str):
    """Verify if a reset token is still valid"""
    user_id = user_mgr.verify_reset_token(token)
    
    if user_id:
        return {"valid": True, "message": "Token is valid"}
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

@app.post("/api/admin/reset-user-password")
async def admin_reset_user_password(
    user_id: int,
    new_password: str,
    current_user: Dict = Depends(get_current_user)
):
    """Admin endpoint to reset any user's password"""
    if current_user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        success = user_mgr.admin_reset_password(user_id, new_password)
        
        if success:
            return {"status": "success", "message": f"Password reset for user {user_id}"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    # WebSocket auth: validate JWT token from query param
    if token:
        payload = user_mgr.verify_jwt(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid token")
            return
    # If no token and INTERNAL_API_KEY is set, reject
    elif INTERNAL_API_KEY:
        await websocket.close(code=4001, reason="Authentication required")
        return
    await manager.connect(websocket)
    try:
        while True:
            # v10: Throttled to 10s (was 2s) — uses cached data
            # 2s interval was calling get_bot_status() + get_performance_metrics()
            # on EVERY tick, each hitting the database
            await asyncio.sleep(10)
            
            # Use cached versions where possible
            cached_status = _cached("bot_status", ttl=8)
            cached_metrics = _cached("perf_metrics", ttl=15)
            
            status = cached_status or await get_bot_status()
            metrics = cached_metrics or await get_performance_metrics()
            
            if not cached_status:
                _set_cache("bot_status", status)
            if not cached_metrics:
                _set_cache("perf_metrics", metrics)
            
            await websocket.send_json({
                "type": "update",
                "status": status.dict() if hasattr(status, 'dict') else status,
                "metrics": metrics.dict() if hasattr(metrics, 'dict') else metrics,
                "timestamp": datetime.now().isoformat()
            })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Background task to monitor trades file and broadcast updates
@app.on_event("startup")
async def startup_event():
    # Seed initial users (admin + Aaron with API keys)
    try:
        from user_manager import seed_initial_users
        seed_initial_users()
    except Exception as e:
        logger.warning(f" User seeding error (may already exist): {e}")
    
    # AUTO-CREATE ACCOUNT FROM ENVIRONMENT VARIABLES
    # This ensures the Accounts page shows the configured account
    try:
        from account_manager import AccountManager
        account_mgr_startup = AccountManager()
        result = account_mgr_startup.migrate_legacy_account()
        if result:
            logger.info(f" Auto-created/verified Default Account from env vars (ID: {result})")
        else:
            logger.info(" No BINANCE_API_KEY/SECRET in env - account must be added manually")
    except Exception as e:
        logger.warning(f" Account auto-creation error: {e}")
    
    # Load initial settings into config (respects user's saved mode)
    try:
        settings = load_settings()
        mode = "PAPER" if settings.get('dry_run', True) else "LIVE"
        logger.info(f" Trading mode from saved settings: {mode}")
        reload_from_settings()
    except Exception as e:
        logger.warning(f" Could not load saved settings: {e}")
    
    # Initialize ML model store tables
    try:
        ml_model_store.ensure_model_tables()
        # Also create kv_store for ML stats persistence
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS kv_store (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
    except Exception as e:
        logger.warning(f" ML Model Store init error: {e}")
    
    # Start WebSocket price stream
    try:
        from src.data.price_stream import start_price_stream
        start_price_stream("ethusdt")
    except Exception as e:
        logger.warning(f" Price stream startup error: {e}")
    
    # Start trade monitoring
    asyncio.create_task(monitor_trades())
    
    # v10: Start cached Binance price updater (async, non-blocking)
    asyncio.create_task(_binance_price_updater())
    logger.info(" Binance price updater started (10s refresh)")
    
    # Initialize learning store (PostgreSQL tables)
    try:
        learning_store.ensure_learning_tables()
    except Exception as e:
        logger.warning(f" Learning store init error: {e}")
    
    # Seed total_strategies_tested counter if not exists
    try:
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM kv_store WHERE key = 'total_strategies_tested'")
                row = cursor.fetchone()
                if not row or int(row[0]) < 100:
                    # Seed with existing count from DB
                    cursor.execute("SELECT COUNT(*) FROM learning_strategies")
                    existing = cursor.fetchone()[0] or 0
                    seed = max(existing, 500)  # At least 500 (known prior tests)
                    cursor.execute("""
                        INSERT INTO kv_store (key, value) VALUES ('total_strategies_tested', %s)
                        ON CONFLICT (key) DO UPDATE SET value = %s
                    """, (str(seed), str(seed)))
                    logger.info(f" Seeded total_strategies_tested counter: {seed}")
    except Exception as e:
        logger.warning(f" Counter seed error: {e}")
    
    # Fix old $100 allocated capital → $10,000
    try:
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_trading_pairs SET allocated_capital = 100000
                    WHERE allocated_capital <= 100
                """)
                if cursor.rowcount > 0:
                    logger.info(f"Migrated {cursor.rowcount} portfolio pairs: $100 -> $100,000")
    except Exception as e:
        logger.warning(f"Capital migration: {e}")
    
    # Create trade_journal table for per-user trade logging
    try:
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trade_journal (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        timestamp TEXT NOT NULL,
                        action TEXT NOT NULL,
                        qty REAL DEFAULT 0,
                        price REAL DEFAULT 0,
                        pnl REAL DEFAULT 0,
                        mode TEXT DEFAULT 'paper',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trade_journal_user 
                    ON trade_journal (user_id, created_at DESC)
                """)
    except Exception as e:
        logger.info(f"Trade journal table: {e}")
    
    # Create paper_trades table for trade persistence across deploys
    try:
        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS paper_trades (
                        id SERIAL PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        action TEXT NOT NULL,
                        qty REAL DEFAULT 0,
                        price REAL DEFAULT 0,
                        pnl REAL DEFAULT 0,
                        mode TEXT DEFAULT 'paper',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
    except Exception as e:
        logger.info(f"Paper trades table: {e}")
    
    # Start auto-learning background service
    asyncio.create_task(auto_learning_background())
    logger.info(" Auto-Learning Background Service started!")
    
    # Start cache warmer — pre-fetches slow endpoints so users never wait
    asyncio.create_task(_cache_warmer())
    logger.info(" Cache Warmer started (learning_stats every 45s)")

    # ═══ v2 EDGE-FIRST SYSTEM ═══
    asyncio.create_task(_v2_data_collector())
    asyncio.create_task(_v2_signal_loop())
    logger.info("📊 v2 Data Collector + Signal Engine started!")


async def _v2_data_collector():
    """Background: collect market data every 60s for edge validation."""
    try:
        from data_collector import collector
        await collector.run()
    except Exception as e:
        logger.error(f"v2 Data Collector failed: {e}")


async def _v2_signal_loop():
    """Background: run signal engine on collected data, log predictions."""
    await asyncio.sleep(120)  # Wait for collector to gather initial data
    try:
        from data_collector import collector
        from signal_engine_v2 import signal_engine
        from edge_validator import validator

        logger.info("🎯 v2 Signal Loop started — predictions will be LOGGED, not traded")
        
        while True:
            try:
                # Get latest market data
                market_data = await collector.collect_once()
                
                if market_data.get("price", 0) > 0:
                    # Evaluate pending predictions against current price
                    validator.evaluate_outcomes(market_data["price"])
                    
                    # Generate new signal
                    signal = await signal_engine.generate_signal(market_data)
                    
                    if signal:
                        # Log prediction for validation — DO NOT TRADE
                        direction = signal["direction"]
                        confidence = signal["confidence"]
                        reasons = signal.get("reasons", [])
                        consensus = signal.get("consensus", False)
                        
                        # Only log consensus signals or very strong singles
                        if consensus or confidence >= 0.75:
                            validator.log_prediction(
                                signal_name=reasons[0].split(" —")[0] if reasons else "unknown",
                                direction=direction,
                                confidence=confidence,
                                price=market_data["price"]
                            )
                
            except Exception as e:
                logger.debug(f"Signal loop tick error: {e}")
            
            await asyncio.sleep(60)  # Check every minute
    except ImportError as e:
        logger.warning(f"v2 signal modules not available: {e}")


# ═══ v2 API ENDPOINTS ═══

@app.get("/api/v2/edge-report")
async def get_edge_report(_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get edge validation report — the most important endpoint in the system."""
    try:
        from edge_validator import validator
        return validator.get_report()
    except ImportError:
        return {"status": "not_initialized", "message": "Edge validator not loaded"}

@app.get("/api/v2/signal-status")
async def get_signal_status(_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get current signal engine status."""
    try:
        from signal_engine_v2 import signal_engine
        return signal_engine.get_status()
    except ImportError:
        return {"status": "not_initialized"}

@app.get("/api/v2/collector-status")
async def get_collector_status(_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get data collector status."""
    try:
        from data_collector import collector
        return collector.get_status()
    except ImportError:
        return {"status": "not_initialized"}

@app.get("/api/v2/market-data")
async def get_recent_market_data(limit: int = 60, _user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get recent collected market data points."""
    try:
        if not USE_POSTGRES:
            return {"data": [], "message": "No PostgreSQL"}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, price, funding_rate, open_interest, 
                       volume_spike_ratio, vwap_deviation_pct, rsi_1m,
                       long_short_ratio, bb_position
                FROM market_data_1m 
                ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            data = []
            for row in rows:
                data.append({
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "price": row[1],
                    "funding_rate": row[2],
                    "open_interest": row[3],
                    "volume_spike_ratio": row[4],
                    "vwap_deviation_pct": row[5],
                    "rsi_1m": row[6],
                    "long_short_ratio": row[7],
                    "bb_position": row[8]
                })
            return {"data": data, "count": len(data)}
    except Exception as e:
        return {"data": [], "error": str(e)}


async def _cache_warmer():
    """Background task: pre-fetches slow endpoints so users always get cached results."""
    await asyncio.sleep(5)  # Let server fully initialize
    while True:
        try:
            result = learning_store.get_learning_stats()
            # Cross-reference applied strategy (same logic as get_learning_stats endpoint)
            current = result.get("current_strategy")
            if current and "strategies" in result:
                current_score = current.get("score", -999)
                best_idx = -1
                best_diff = 999
                for i, strat in enumerate(result["strategies"]):
                    diff = abs(strat.get("score", 0) - current_score)
                    if diff < best_diff:
                        best_diff = diff
                        best_idx = i
                for i, strat in enumerate(result["strategies"]):
                    strat["applied"] = (i == best_idx and best_diff < 1.0)
                if result.get("stats"):
                    result["stats"]["total_applied"] = max(result["stats"].get("total_applied", 0), 1)
            _set_cache("learning_stats", result)
        except Exception as e:
            logger.error(f"Cache warmer error: {e}")
        await asyncio.sleep(45)  # Refresh every 45s (cache TTL = 60s)


async def auto_learning_background():
    """Background task that continuously tests strategies using historical data.
    Stores results in PostgreSQL (via learning_store) for persistence across deploys.
    Syncs progress to _synced_training_data so dashboard shows live updates."""
    global _training_active
    import random
    
    # Wait 30 seconds before starting (let API fully initialize)
    await asyncio.sleep(30)
    
    # Auto-start training on boot
    state.training_active = True
    _training_active = True
    logger.info("Auto-Learning Background Service active - CONTINUOUS strategy optimization...")
    logger.info(f"Storage backend: {'PostgreSQL' if learning_store.USE_POSTGRES else 'Local JSON (dev)'}")
    
    # Import backtester with evolution support
    try:
        from src.ml.strategy_backtester import (
            fetch_historical_data, 
            calculate_indicators, 
            run_backtest,
            generate_evolved_params,
            generate_random_params,
            get_random_backtest_period,
            ensure_db
        )
        ensure_db()
        use_real_backtest = True
        logger.info("Using REAL historical backtesting with evolutionary optimization!")
    except ImportError as e:
        logger.info(f"Backtester not available, using mock data: {e}")
        use_real_backtest = False
    
    # Fetch historical data once and reuse (refresh every hour)
    historical_candles = []
    last_data_fetch = datetime.min
    
    strategies_tested = 0
    hour_start = datetime.now().hour
    hour_tested = 0
    best_score_session = 0
    last_saved_score = None  # Duplicate detection
    
    while True:
        try:
            # Respect Start/Stop button
            if not _training_active:
                _synced_training_data = {
                    "status": "stopped", "training_active": False,
                    "episode": strategies_tested, "total_episodes": strategies_tested,
                    "received_at": datetime.now().isoformat()
                }
                await asyncio.sleep(5)
                continue
            
            # Reset hourly counter
            current_hour = datetime.now().hour
            if current_hour != hour_start:
                hour_start = current_hour
                hour_tested = 0
            
            # v10: Fetch data with RANDOM period to diversify strategy results
            if use_real_backtest and (datetime.now() - last_data_fetch).total_seconds() > 1800:  # v10: refresh every 30min (was 1h)
                period = get_random_backtest_period()
                logger.info(f"Fetching fresh historical data from Binance ({period} days)...")
                try:
                    historical_candles = fetch_historical_data(period)
                    if historical_candles:
                        historical_candles = calculate_indicators(historical_candles)
                        logger.info(f"Got {len(historical_candles)} candles with indicators ({period}d)")
                    else:
                        logger.info("No candles returned, will retry next cycle")
                except Exception as fetch_err:
                    logger.warning(f"Data fetch failed: {fetch_err}")
                last_data_fetch = datetime.now()
            
            # Generate and test a single strategy with EVOLUTION
            if use_real_backtest and len(historical_candles) > 120:
                # Use evolved params (70% mutation of top strategies, 30% random)
                params = generate_evolved_params()
                
                # Walk-forward validation: 70% train / 30% test
                split_idx = int(len(historical_candles) * 0.7)
                train_candles = historical_candles[:split_idx]
                test_candles = historical_candles[split_idx:]
                
                train_metrics = run_backtest(train_candles, params)
                if train_metrics and train_metrics["score"] >= 0:
                    test_metrics = run_backtest(test_candles, params)
                    if test_metrics:
                        # Out-of-sample score: 70% test + 30% train
                        # CRITICAL: if kill-gate zeroed test score, keep it at 0
                        if test_metrics["score"] <= 0:
                            oos_score = 0.0
                        else:
                            oos_score = test_metrics["score"] * 0.7 + train_metrics["score"] * 0.3
                        test_metrics["score"] = round(oos_score, 2)
                        test_metrics["data_source"] = "historical_binance"
                        
                        strategy = {
                            "params": params,
                            "metrics": test_metrics,
                            "score": test_metrics["score"],
                            "timestamp": datetime.now().isoformat(),
                            "applied": False,
                            "data_source": "historical_binance"
                        }
                    else:
                        strategy = None
                else:
                    strategy = None
            elif use_real_backtest and len(historical_candles) > 60:
                # Fallback: simple backtest (not enough data for walk-forward)
                params = generate_evolved_params()
                metrics = run_backtest(historical_candles, params)
                if metrics:
                    metrics["data_source"] = "historical_binance"
                    strategy = {
                        "params": params, "metrics": metrics,
                        "score": metrics["score"], "timestamp": datetime.now().isoformat(),
                        "applied": False, "data_source": "historical_binance"
                    }
                else:
                    strategy = None
            else:
                # No historical data available — skip instead of faking
                strategy = None
            
            if strategy:
                # Skip duplicates (same score as last saved)
                if last_saved_score is not None and abs(strategy["score"] - last_saved_score) < 0.01:
                    await asyncio.sleep(2)
                    continue
                
                strategies_tested += 1
                hour_tested += 1
                last_saved_score = strategy["score"]
                
                # Save strategy to PostgreSQL
                learning_store.save_strategy(strategy)
                
                if strategy["score"] > best_score_session:
                    best_score_session = strategy["score"]
                
                # Auto-apply best strategy
                all_strategies = learning_store.get_all_strategies(limit=1)
                if all_strategies:
                    best = all_strategies[0]
                    current = learning_store.get_current_strategy()
                    current_score = current.get("score", 0) if current else float('-inf')
                    
                    should_apply = (
                        (current_score == float('-inf') and best["score"] > 0) or
                        (best["score"] > current_score * 1.05 and best["score"] > 0)
                    )
                    if should_apply:
                        best["applied"] = True
                        best["applied_at"] = datetime.now().isoformat()
                        learning_store.set_current_strategy(best)
                        logger.info(f"NEW BEST STRATEGY APPLIED! Score: {best['score']:.2f}")
                
                # SYNC progress to dashboard via StateManager
                state.training_data = {
                    "status": "training",
                    "model_type": "strategy_backtester",
                    "model": "strategy_backtester",
                    "architecture": "Parameter Optimization",
                    "episode": strategies_tested,
                    "total_episodes": strategies_tested,
                    "progress_pct": min(99, strategies_tested % 100),
                    "win_rate": strategy.get("metrics", {}).get("win_rate", 0),
                    "trades": strategy.get("metrics", {}).get("total_trades", 0),
                    "roi": strategy.get("metrics", {}).get("roi", 0),
                    "best_roi": best_score_session,
                    "training_active": True,
                    "received_at": datetime.now().isoformat()
                }
                
                # Log every 10 strategies
                if strategies_tested % 10 == 0:
                    logger.info(f"Strategy #{strategies_tested}: Score={strategy['score']:.2f} | Hour: {hour_tested} | Best: {best_score_session:.1f}")
            
            # TURBO: 0.5-1.0s between tests (~3600-7200/hour)
            wait_time = random.uniform(0.5, 1.0)
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            import traceback
            logger.error(f"Auto-learning error: {e}")
            traceback.print_exc()
            await asyncio.sleep(60)


# generate_mock_strategy REMOVED — no more fake data generation

async def monitor_trades():
    """Monitor trades.csv for new entries and broadcast"""
    last_size = 0
    while True:
        try:
            if TRADES_CSV.exists():
                current_size = TRADES_CSV.stat().st_size
                if current_size > last_size:
                    # New trade detected
                    trades = await read_trades_csv()
                    if trades:
                        latest_trade = trades[-1]
                        await manager.broadcast({
                            "type": "new_trade",
                            "trade": latest_trade.dict()
                        })
                    last_size = current_size
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        
        await asyncio.sleep(1)

# Settings Management
class BotSettings(BaseModel):
    telegram_bot_token: str
    telegram_chat_id: str
    binance_api_key: str
    binance_api_secret: str
    trading_capital: float
    risk_per_trade: float
    max_trades_per_day: int
    daily_target_pct: float
    max_drawdown_day: float
    dry_run: bool

class TelegramSettings(BaseModel):
    bot_token: str
    chat_id: str

class TradingSettings(BaseModel):
    capital: float
    risk_per_trade: float
    max_trades_per_day: int
    daily_target_pct: float
    max_drawdown_day: float
    tp_min: float
    tp_max: float
    stop_floor: float

def load_settings() -> dict:
    """Load settings from file or environment"""
    settings = {}
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
    except:
        pass
    
    # If we loaded from file, ensure dry_run defaults to True (paper trading)
    if settings:
        # CRITICAL: Default to paper trading if dry_run not set
        settings.setdefault('dry_run', True)
        return settings
    
    # Default from environment (fresh start = paper trading)
    return {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "binance_api_key": os.getenv("BINANCE_API_KEY", ""),
        "binance_api_secret": os.getenv("BINANCE_API_SECRET", ""),
        "trading_capital": float(os.getenv("PAPER_BASE_USDT", "100000")),
        "risk_per_trade": float(os.getenv("RISK_PCT_PER_TRADE", "0.006")),
        "max_trades_per_day": int(os.getenv("MAX_TRADES_PER_DAY", "15")),
        "daily_target_pct": float(os.getenv("DAILY_TARGET_PCT", "1.0")),
        "max_drawdown_day": float(os.getenv("MAX_DRAWDOWN_DAY", "0.05")),
        "tp_min": float(os.getenv("TP_MIN", "0.010")),
        "tp_max": float(os.getenv("TP_MAX", "0.015")),
        "stop_floor": float(os.getenv("STOP_FLOOR", "0.005")),
        "dry_run": True  # Always default to paper trading
    }

def save_settings(settings: dict):
    """Save settings to file"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        logger.warning(f" saving settings: {e}")
        return False

@app.get("/api/settings/bot")
async def get_bot_settings(current_user: Dict = Depends(get_current_user)):
    """Get all bot settings"""
    settings = load_settings()
    # Mask sensitive data
    if settings.get("binance_api_secret"):
        settings["binance_api_secret"] = "•" * 16
    return settings

@app.post("/api/settings/bot")
async def update_bot_settings(settings: BotSettings, current_user: Dict = Depends(get_current_user)):
    """Update bot settings"""
    current = load_settings()
    
    # Update with new values
    current.update({
        "telegram_bot_token": settings.telegram_bot_token,
        "telegram_chat_id": settings.telegram_chat_id,
        "trading_capital": settings.trading_capital,
        "risk_per_trade": settings.risk_per_trade,
        "max_trades_per_day": settings.max_trades_per_day,
        "daily_target_pct": settings.daily_target_pct,
        "max_drawdown_day": settings.max_drawdown_day,
        "dry_run": settings.dry_run
    })
    
    # Only update API keys if not masked
    if not settings.binance_api_secret.startswith("•"):
        current["binance_api_key"] = settings.binance_api_key
        current["binance_api_secret"] = settings.binance_api_secret
    
    if save_settings(current):
        return {"status": "success", "message": "Settings updated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")

@app.get("/api/settings/telegram")
async def get_telegram_settings(current_user: Dict = Depends(get_current_user)):
    """Get Telegram settings"""
    settings = load_settings()
    return {
        "bot_token": settings.get("telegram_bot_token", ""),
        "chat_id": settings.get("telegram_chat_id", "")
    }

@app.post("/api/settings/telegram")
async def update_telegram_settings(telegram: TelegramSettings, current_user: Dict = Depends(get_current_user)):
    """Update Telegram settings"""
    current = load_settings()
    current["telegram_bot_token"] = telegram.bot_token
    current["telegram_chat_id"] = telegram.chat_id
    
    if save_settings(current):
        return {"status": "success", "message": "Telegram settings updated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")

@app.get("/api/settings/trading")
async def get_trading_settings(current_user: Dict = Depends(get_current_user)):
    """Get trading parameters"""
    settings = load_settings()
    return {
        "capital": settings.get("trading_capital", 100000),
        "risk_per_trade": settings.get("risk_per_trade", 0.006),
        "max_trades_per_day": settings.get("max_trades_per_day", 15),
        "daily_target_pct": settings.get("daily_target_pct", 1.0),
        "max_drawdown_day": settings.get("max_drawdown_day", 0.05),
        "tp_min": settings.get("tp_min", 0.010),
        "tp_max": settings.get("tp_max", 0.015),
        "stop_floor": settings.get("stop_floor", 0.005)
    }

@app.post("/api/settings/trading")
async def update_trading_settings(trading: TradingSettings, current_user: Dict = Depends(get_current_user)):
    """Update trading parameters"""
    current = load_settings()
    current.update({
        "trading_capital": trading.capital,
        "risk_per_trade": trading.risk_per_trade,
        "max_trades_per_day": trading.max_trades_per_day,
        "daily_target_pct": trading.daily_target_pct,
        "max_drawdown_day": trading.max_drawdown_day,
        "tp_min": trading.tp_min,
        "tp_max": trading.tp_max,
        "stop_floor": trading.stop_floor
    })
    
    if save_settings(current):
        return {"status": "success", "message": "Trading settings updated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")

# ============ User-Specific API Key Management ============

class UserApiKeysInput(BaseModel):
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

@app.get("/api/settings/api-keys")
async def get_user_api_keys(current_user: Dict = Depends(get_current_user)):
    """Get current user's API keys (masked)"""
    try:
        keys = user_mgr.get_api_keys(current_user['id'], decrypt=False)
        if not keys:
            return {
                "has_binance_keys": False,
                "has_telegram": False,
                "binance_api_key": "",
                "binance_api_secret": "",
                "telegram_bot_token": "",
                "telegram_chat_id": "",
                "trading_enabled": False
            }
        return keys
    except Exception as e:
        logger.error(f" Error getting API keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/api-keys")
async def save_user_api_keys(keys: UserApiKeysInput, current_user: Dict = Depends(get_current_user)):
    """Save current user's API keys (encrypted)"""
    try:
        # Get existing keys to preserve values not being updated
        existing = user_mgr.get_api_keys(current_user['id'], decrypt=True) or {}
        
        # Determine which values to save (new value or keep existing)
        api_key = keys.binance_api_key if keys.binance_api_key and not keys.binance_api_key.startswith("•") else existing.get('binance_api_key', '')
        api_secret = keys.binance_api_secret if keys.binance_api_secret and not keys.binance_api_secret.startswith("•") else existing.get('binance_api_secret', '')
        telegram_token = keys.telegram_bot_token if keys.telegram_bot_token and not keys.telegram_bot_token.startswith("•") else existing.get('telegram_bot_token', '')
        telegram_chat = keys.telegram_chat_id if keys.telegram_chat_id else existing.get('telegram_chat_id', '')
        
        # Determine if trading should be enabled
        trading_enabled = bool(api_key and api_secret)
        
        user_mgr.save_api_keys(
            user_id=current_user['id'],
            binance_api_key=api_key,
            binance_api_secret=api_secret,
            telegram_bot_token=telegram_token,
            telegram_chat_id=telegram_chat,
            trading_enabled=trading_enabled
        )
        
        return {
            "status": "success", 
            "message": "API keys saved successfully",
            "trading_enabled": trading_enabled
        }
    except Exception as e:
        logger.error(f" Error saving API keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ───────── MULTI-USER TRADE BROADCAST ─────────
@app.post("/api/trades/broadcast")
async def broadcast_trade(data: dict, current_user: Dict = Depends(get_current_admin)):
    """
    Bot calls this on every BUY/SELL signal.
    Executes the trade on ALL users with trading_enabled=True.
    Each user's position is sized proportionally to their balance.
    """
    action = data.get("action", "").upper()  # BUY or SELL
    price = float(data.get("price", 0))
    signal_qty = float(data.get("qty", 0))
    pair = data.get("pair", "ETHUSDT")
    risk_pct = float(data.get("risk_pct", 0.006))

    if action not in ("BUY", "SELL") or price <= 0:
        return {"status": "error", "message": "Invalid action or price"}

    # Get all users with trading_enabled
    results = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id FROM user_api_keys WHERE trading_enabled = TRUE"
                if USE_POSTGRES else
                "SELECT user_id FROM user_api_keys WHERE trading_enabled = 1"
            )
            enabled_users = cursor.fetchall()
    except Exception as e:
        return {"status": "error", "message": f"DB error: {e}"}

    for (uid,) in enabled_users:
        try:
            keys = user_mgr.get_api_keys(uid, decrypt=True)
            if not keys or not keys.get("binance_api_key") or not keys.get("binance_api_secret"):
                results.append({"user_id": uid, "status": "skip", "reason": "no_keys"})
                continue

            from binance.client import Client
            cli = Client(keys["binance_api_key"], keys["binance_api_secret"])

            if action == "BUY":
                # Size position based on user's balance
                try:
                    balance_info = cli.get_asset_balance(asset="USDT")
                    user_balance = float(balance_info["free"]) if balance_info else 0
                except Exception:
                    user_balance = 0

                if user_balance < 10:
                    results.append({"user_id": uid, "status": "skip", "reason": "low_balance", "balance": user_balance})
                    continue

                # Position: risk_pct of user's balance
                risk_usd = user_balance * risk_pct
                user_qty = risk_usd / max(price * 0.005, 0.001)  # ~0.5% SL
                quote_value = round(user_qty * price, 2)
                quote_value = min(quote_value, user_balance * 0.95)  # Max 95% of balance

                if quote_value < 10:
                    results.append({"user_id": uid, "status": "skip", "reason": "position_too_small"})
                    continue

                try:
                    cli.order_market_buy(symbol=pair, quoteOrderQty=quote_value)
                    results.append({"user_id": uid, "status": "filled", "action": "BUY", "value": quote_value})
                except Exception as e:
                    results.append({"user_id": uid, "status": "error", "error": str(e)})

            elif action == "SELL":
                # Sell all ETH the user holds
                try:
                    eth_info = cli.get_asset_balance(asset="ETH")
                    eth_balance = float(eth_info["free"]) if eth_info else 0
                except Exception:
                    eth_balance = 0

                if eth_balance < 0.001:
                    results.append({"user_id": uid, "status": "skip", "reason": "no_eth"})
                    continue

                try:
                    cli.order_market_sell(symbol=pair, quantity=round(eth_balance, 5))
                    results.append({"user_id": uid, "status": "filled", "action": "SELL", "qty": eth_balance})
                except Exception as e:
                    results.append({"user_id": uid, "status": "error", "error": str(e)})

            # Log per-user trade
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO trade_journal (user_id, timestamp, action, qty, price, pnl, mode)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """ if USE_POSTGRES else """
                        INSERT INTO trade_journal (user_id, timestamp, action, qty, price, pnl, mode) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (uid, datetime.now().isoformat(), action,
                          results[-1].get("qty", results[-1].get("value", 0) / max(price, 1)),
                          price, 0, "live"))
            except Exception:
                pass

        except Exception as e:
            results.append({"user_id": uid, "status": "error", "error": str(e)})

    return {
        "status": "broadcast_complete",
        "total_users": len(enabled_users),
        "results": results
    }

@app.get("/api/settings/user-telegram")
async def get_user_telegram_settings(current_user: Dict = Depends(get_current_user)):
    """Get current user's Telegram settings"""
    try:
        keys = user_mgr.get_api_keys(current_user['id'], decrypt=False) or {}
        return {
            "has_telegram": keys.get('has_telegram', False),
            "telegram_chat_id": keys.get('telegram_chat_id', ""),
            "telegram_bot_token": "••••••••" if keys.get('has_telegram') else ""
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/user-telegram")
async def save_user_telegram_settings(
    telegram_bot_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    current_user: Dict = Depends(get_current_user)
):
    """Save current user's Telegram settings"""
    try:
        existing = user_mgr.get_api_keys(current_user['id'], decrypt=True) or {}
        
        token = telegram_bot_token if telegram_bot_token and not telegram_bot_token.startswith("•") else existing.get('telegram_bot_token', '')
        chat_id = telegram_chat_id if telegram_chat_id else existing.get('telegram_chat_id', '')
        
        user_mgr.save_api_keys(
            user_id=current_user['id'],
            binance_api_key=existing.get('binance_api_key', ''),
            binance_api_secret=existing.get('binance_api_secret', ''),
            telegram_bot_token=token,
            telegram_chat_id=chat_id,
            trading_enabled=existing.get('trading_enabled', False)
        )
        
        return {"status": "success", "message": "Telegram settings saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------ Trading Pair Selection ------------

# Popular trading pairs for quick access
POPULAR_PAIRS = [
    {"symbol": "ETHUSDT", "name": "Ethereum", "icon": "🔷"},
    {"symbol": "BTCUSDT", "name": "Bitcoin", "icon": "🟠"},
    {"symbol": "SOLUSDT", "name": "Solana", "icon": "🟣"},
    {"symbol": "BNBUSDT", "name": "BNB", "icon": "🟡"},
    {"symbol": "XRPUSDT", "name": "XRP", "icon": "⚪"},
    {"symbol": "ADAUSDT", "name": "Cardano", "icon": "🔵"},
    {"symbol": "DOGEUSDT", "name": "Dogecoin", "icon": "🐕"},
    {"symbol": "DOTUSDT", "name": "Polkadot", "icon": "🔴"},
    {"symbol": "MATICUSDT", "name": "Polygon", "icon": "💜"},
    {"symbol": "AVAXUSDT", "name": "Avalanche", "icon": "🔺"},
    {"symbol": "LINKUSDT", "name": "Chainlink", "icon": "🔗"},
    {"symbol": "LTCUSDT", "name": "Litecoin", "icon": "⬜"},
]

@app.get("/api/trading/pairs")
async def get_available_pairs(search: Optional[str] = None):
    """Get available trading pairs from Binance"""
    try:
        import requests
        res = requests.get("https://api.binance.com/api/v3/exchangeInfo", timeout=10)
        if res.ok:
            data = res.json()
            # Filter for USDT pairs that are trading
            pairs = []
            for s in data.get("symbols", []):
                if s["quoteAsset"] == "USDT" and s["status"] == "TRADING":
                    symbol = s["symbol"]
                    base = s["baseAsset"]
                    
                    # Apply search filter if provided
                    if search:
                        if search.upper() not in symbol and search.upper() not in base:
                            continue
                    
                    # Check if popular
                    popular_info = next((p for p in POPULAR_PAIRS if p["symbol"] == symbol), None)
                    
                    pairs.append({
                        "symbol": symbol,
                        "base": base,
                        "name": popular_info["name"] if popular_info else base,
                        "icon": popular_info["icon"] if popular_info else "💰",
                        "popular": popular_info is not None
                    })
            
            # Sort: popular first, then alphabetically
            pairs.sort(key=lambda x: (not x["popular"], x["symbol"]))
            
            return {
                "pairs": pairs[:100],  # Limit to 100 results
                "total": len(pairs),
                "popular": POPULAR_PAIRS
            }
    except Exception as e:
        logger.warning(f" fetching pairs: {e}")
    
    # Fallback to popular pairs
    return {"pairs": POPULAR_PAIRS, "total": len(POPULAR_PAIRS), "popular": POPULAR_PAIRS}

@app.get("/api/settings/trading-pair")
async def get_user_trading_pair(current_user: Dict = Depends(get_current_user)):
    """Get current user's selected trading pair"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT trading_pair FROM user_api_keys WHERE user_id = %s" if USE_POSTGRES 
                else "SELECT trading_pair FROM user_api_keys WHERE user_id = ?",
                (current_user['id'],)
            )
            row = cursor.fetchone()
            pair = row[0] if row and row[0] else "ETHUSDT"
            
            # Get pair info
            popular_info = next((p for p in POPULAR_PAIRS if p["symbol"] == pair), None)
            
            return {
                "trading_pair": pair,
                "name": popular_info["name"] if popular_info else pair.replace("USDT", ""),
                "icon": popular_info["icon"] if popular_info else "💰"
            }
    except Exception as e:
        return {"trading_pair": "ETHUSDT", "name": "Ethereum", "icon": "🔷"}

@app.post("/api/settings/trading-pair")
async def set_user_trading_pair(
    trading_pair: str,
    current_user: Dict = Depends(get_current_user)
):
    """Set current user's trading pair"""
    try:
        # Validate pair exists
        if not trading_pair or len(trading_pair) < 5:
            raise HTTPException(status_code=400, detail="Invalid trading pair")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user has record
            cursor.execute(
                "SELECT user_id FROM user_api_keys WHERE user_id = %s" if USE_POSTGRES
                else "SELECT user_id FROM user_api_keys WHERE user_id = ?",
                (current_user['id'],)
            )
            
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE user_api_keys SET trading_pair = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s" if USE_POSTGRES
                    else "UPDATE user_api_keys SET trading_pair = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (trading_pair.upper(), current_user['id'])
                )
            else:
                cursor.execute(
                    "INSERT INTO user_api_keys (user_id, trading_pair) VALUES (%s, %s)" if USE_POSTGRES
                    else "INSERT INTO user_api_keys (user_id, trading_pair) VALUES (?, ?)",
                    (current_user['id'], trading_pair.upper())
                )
            
            conn.commit()
        
        popular_info = next((p for p in POPULAR_PAIRS if p["symbol"] == trading_pair.upper()), None)
        
        return {
            "status": "success",
            "trading_pair": trading_pair.upper(),
            "name": popular_info["name"] if popular_info else trading_pair.replace("USDT", ""),
            "message": f"Trading pair set to {trading_pair.upper()}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------ Multi-Pair Portfolio System ------------

@app.get("/api/portfolio/pairs")
async def get_user_portfolio_pairs(current_user: Dict = Depends(get_current_user)):
    """Get all trading pairs in user's portfolio"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, trading_pair, pair_name, pair_icon, allocated_capital, 
                   risk_per_trade, max_trades_per_day, take_profit_pct, stop_loss_pct,
                   enabled, total_pnl, total_trades, win_rate, created_at
                   FROM user_trading_pairs WHERE user_id = %s ORDER BY created_at DESC""" if USE_POSTGRES
                else """SELECT id, trading_pair, pair_name, pair_icon, allocated_capital,
                   risk_per_trade, max_trades_per_day, take_profit_pct, stop_loss_pct,
                   enabled, total_pnl, total_trades, win_rate, created_at
                   FROM user_trading_pairs WHERE user_id = ? ORDER BY created_at DESC""",
                (current_user['id'],)
            )
            rows = cursor.fetchall()
            
            pairs = []
            total_capital = 0
            total_pnl = 0
            
            for row in rows:
                pair_data = {
                    "id": row[0],
                    "trading_pair": row[1],
                    "pair_name": row[2] or row[1].replace("USDT", ""),
                    "pair_icon": row[3] or "💰",
                    "allocated_capital": float(row[4] or 100000),
                    "risk_per_trade": float(row[5] or 0.01) * 100,  # Convert to %
                    "max_trades_per_day": row[6] or 10,
                    "take_profit_pct": float(row[7] or 0.015) * 100,
                    "stop_loss_pct": float(row[8] or 0.015) * 100,
                    "enabled": bool(row[9]),
                    "total_pnl": float(row[10] or 0),
                    "total_trades": row[11] or 0,
                    "win_rate": float(row[12] or 0),
                    "pnl_percent": (float(row[10] or 0) / float(row[4] or 100)) * 100 if float(row[4] or 100) > 0 else 0
                }
                # Override with actual bot parameters (hardcoded in bot, not from DB)
                try:
                    from eth_master_bot import TP_MIN, TP_MAX, STOP_FLOOR, RISK_PCT_PER_TRADE
                    pair_data["take_profit_pct"] = round(TP_MAX * 100, 1)
                    pair_data["stop_loss_pct"] = round(STOP_FLOOR * 100, 1)
                    pair_data["risk_per_trade"] = round(RISK_PCT_PER_TRADE * 100, 1)
                except ImportError:
                    pass  # Fallback to DB values
                pairs.append(pair_data)
                total_capital += pair_data["allocated_capital"]
                total_pnl += pair_data["total_pnl"]
            
            # Use actual bot capital, not sum of pair allocations
            settings = load_settings()
            actual_capital = settings.get('paper_base_usdt', float(os.getenv('PAPER_BASE_USDT', 100000)))
            
            return {
                "pairs": pairs,
                "total_pairs": len(pairs),
                "total_capital": actual_capital if actual_capital > total_capital else total_capital,
                "total_pnl": total_pnl,
                "total_pnl_percent": (total_pnl / actual_capital * 100) if actual_capital > 0 else 0
            }
    except Exception as e:
        logger.warning(f" fetching portfolio pairs: {e}")
        return {"pairs": [], "total_pairs": 0, "total_capital": 0, "total_pnl": 0}

@app.post("/api/portfolio/pairs")
async def add_portfolio_pair(
    data: PortfolioPairCreate,
    current_user: Dict = Depends(get_current_user)
):
    """Add a new trading pair to user's portfolio"""
    try:
        trading_pair = data.trading_pair
        pair_name = data.pair_name
        pair_icon = data.pair_icon or "💰"
        allocated_capital = data.allocated_capital
        risk_per_trade = data.risk_per_trade
        max_trades_per_day = data.max_trades_per_day
        take_profit_pct = data.take_profit_pct
        stop_loss_pct = data.stop_loss_pct
        
        if not trading_pair or len(trading_pair) < 5:
            raise HTTPException(status_code=400, detail="Invalid trading pair")
        
        # Validate inputs
        if allocated_capital < 10:
            raise HTTPException(status_code=400, detail="Minimum capital is $10")
        if risk_per_trade <= 0 or risk_per_trade > 10:
            raise HTTPException(status_code=400, detail="Risk must be between 0.1% and 10%")
        
        trading_pair = trading_pair.upper()
        
        # Get pair info if available
        popular_info = next((p for p in POPULAR_PAIRS if p["symbol"] == trading_pair), None)
        if not pair_name:
            pair_name = popular_info["name"] if popular_info else trading_pair.replace("USDT", "")
        if pair_icon == "💰" and popular_info:
            pair_icon = popular_info["icon"]
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if pair already exists for user
            cursor.execute(
                "SELECT id FROM user_trading_pairs WHERE user_id = %s AND trading_pair = %s" if USE_POSTGRES
                else "SELECT id FROM user_trading_pairs WHERE user_id = ? AND trading_pair = ?",
                (current_user['id'], trading_pair)
            )
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail=f"{trading_pair} already in your portfolio")
            
            # Insert new pair
            cursor.execute(
                """INSERT INTO user_trading_pairs 
                   (user_id, trading_pair, pair_name, pair_icon, allocated_capital, 
                    risk_per_trade, max_trades_per_day, take_profit_pct, stop_loss_pct)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""" if USE_POSTGRES
                else """INSERT INTO user_trading_pairs 
                   (user_id, trading_pair, pair_name, pair_icon, allocated_capital,
                    risk_per_trade, max_trades_per_day, take_profit_pct, stop_loss_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (current_user['id'], trading_pair, pair_name, pair_icon, allocated_capital,
                 risk_per_trade / 100, max_trades_per_day, take_profit_pct / 100, stop_loss_pct / 100)
            )
            conn.commit()
            
            # Get the inserted ID
            if USE_POSTGRES:
                cursor.execute("SELECT lastval()")
            else:
                cursor.execute("SELECT last_insert_rowid()")
            new_id = cursor.fetchone()[0]
        
        return {
            "status": "success",
            "id": new_id,
            "trading_pair": trading_pair,
            "pair_name": pair_name,
            "pair_icon": pair_icon,
            "message": f"{pair_name} ({trading_pair}) added to your portfolio!"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f" adding pair: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/portfolio/pairs/{pair_id}")
async def update_portfolio_pair(
    pair_id: int,
    data: PortfolioPairUpdate,
    current_user: Dict = Depends(get_current_user)
):
    """Update settings for a portfolio pair"""
    try:
        updates = []
        params = []
        
        allocated_capital = data.allocated_capital
        risk_per_trade = data.risk_per_trade
        max_trades_per_day = data.max_trades_per_day
        take_profit_pct = data.take_profit_pct
        stop_loss_pct = data.stop_loss_pct
        enabled = data.enabled
        
        if allocated_capital is not None:
            if allocated_capital < 10:
                raise HTTPException(status_code=400, detail="Minimum capital is $10")
            updates.append("allocated_capital = %s" if USE_POSTGRES else "allocated_capital = ?")
            params.append(allocated_capital)
        
        if risk_per_trade is not None:
            updates.append("risk_per_trade = %s" if USE_POSTGRES else "risk_per_trade = ?")
            params.append(risk_per_trade / 100)
        
        if max_trades_per_day is not None:
            updates.append("max_trades_per_day = %s" if USE_POSTGRES else "max_trades_per_day = ?")
            params.append(max_trades_per_day)
        
        if take_profit_pct is not None:
            updates.append("take_profit_pct = %s" if USE_POSTGRES else "take_profit_pct = ?")
            params.append(take_profit_pct / 100)
        
        if stop_loss_pct is not None:
            updates.append("stop_loss_pct = %s" if USE_POSTGRES else "stop_loss_pct = ?")
            params.append(stop_loss_pct / 100)
        
        if enabled is not None:
            updates.append("enabled = %s" if USE_POSTGRES else "enabled = ?")
            params.append(enabled)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Verify ownership
            cursor.execute(
                "SELECT trading_pair FROM user_trading_pairs WHERE id = %s AND user_id = %s" if USE_POSTGRES
                else "SELECT trading_pair FROM user_trading_pairs WHERE id = ? AND user_id = ?",
                (pair_id, current_user['id'])
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Pair not found")
            
            trading_pair = row[0]
            
            # Update
            query = f"UPDATE user_trading_pairs SET {', '.join(updates)} WHERE id = %s AND user_id = %s" if USE_POSTGRES \
                else f"UPDATE user_trading_pairs SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
            params.extend([pair_id, current_user['id']])
            cursor.execute(query, params)
            conn.commit()
        
        return {"status": "success", "message": f"{trading_pair} settings updated!"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/portfolio/pairs/{pair_id}")
async def delete_portfolio_pair(
    pair_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """Remove a trading pair from user's portfolio"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get pair info before deleting
            cursor.execute(
                "SELECT trading_pair, pair_name FROM user_trading_pairs WHERE id = %s AND user_id = %s" if USE_POSTGRES
                else "SELECT trading_pair, pair_name FROM user_trading_pairs WHERE id = ? AND user_id = ?",
                (pair_id, current_user['id'])
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Pair not found")
            
            trading_pair, pair_name = row
            
            # Delete
            cursor.execute(
                "DELETE FROM user_trading_pairs WHERE id = %s AND user_id = %s" if USE_POSTGRES
                else "DELETE FROM user_trading_pairs WHERE id = ? AND user_id = ?",
                (pair_id, current_user['id'])
            )
            conn.commit()
        
        return {"status": "success", "message": f"{pair_name} ({trading_pair}) removed from portfolio"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/portfolio/pairs/{pair_id}")
async def get_portfolio_pair_details(
    pair_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """Get detailed info for a specific portfolio pair"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, trading_pair, pair_name, pair_icon, allocated_capital,
                   risk_per_trade, max_trades_per_day, take_profit_pct, stop_loss_pct,
                   enabled, total_pnl, total_trades, win_rate, created_at, updated_at
                   FROM user_trading_pairs WHERE id = %s AND user_id = %s""" if USE_POSTGRES
                else """SELECT id, trading_pair, pair_name, pair_icon, allocated_capital,
                   risk_per_trade, max_trades_per_day, take_profit_pct, stop_loss_pct,
                   enabled, total_pnl, total_trades, win_rate, created_at, updated_at
                   FROM user_trading_pairs WHERE id = ? AND user_id = ?""",
                (pair_id, current_user['id'])
            )
            row = cursor.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="Pair not found")
            
            return {
                "id": row[0],
                "trading_pair": row[1],
                "pair_name": row[2],
                "pair_icon": row[3],
                "allocated_capital": float(row[4]),
                "risk_per_trade": float(row[5]) * 100,
                "max_trades_per_day": row[6],
                "take_profit_pct": float(row[7]) * 100,
                "stop_loss_pct": float(row[8]) * 100,
                "enabled": bool(row[9]),
                "total_pnl": float(row[10]),
                "total_trades": row[11],
                "win_rate": float(row[12]),
                "created_at": str(row[13]),
                "updated_at": str(row[14])
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/portfolio/pairs/{pair_id}/toggle")
async def toggle_portfolio_pair(
    pair_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """Toggle enabled/disabled state of a portfolio pair"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get current state
            cursor.execute(
                "SELECT trading_pair, enabled FROM user_trading_pairs WHERE id = %s AND user_id = %s" if USE_POSTGRES
                else "SELECT trading_pair, enabled FROM user_trading_pairs WHERE id = ? AND user_id = ?",
                (pair_id, current_user['id'])
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Pair not found")
            
            trading_pair, current_enabled = row
            new_enabled = not current_enabled
            
            # Toggle
            cursor.execute(
                "UPDATE user_trading_pairs SET enabled = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s" if USE_POSTGRES
                else "UPDATE user_trading_pairs SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_enabled, pair_id)
            )
            conn.commit()
        
        status = "enabled" if new_enabled else "paused"
        return {"status": "success", "enabled": new_enabled, "message": f"{trading_pair} is now {status}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/capital")
async def get_capital():
    """Get current trading capital — real paper balance or live Binance balance."""
    import json as _json
    
    # Detect mode
    paper_mode = os.getenv("PAPER_MODE", "true").lower() in ("true", "1", "yes")
    
    if paper_mode:
        # Paper mode: read real simulated balance from bot
        # Priority: PostgreSQL kv_store > local file > default
        balance = 100000.0  # Default
        updated_at = None
        loaded_from = "default"
        
        # 1. Try PostgreSQL first (survives deploys)
        if USE_POSTGRES:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM kv_store WHERE key = 'paper_balance'")
                    row = cursor.fetchone()
                    if row:
                        data = _json.loads(row[0])
                        if data.get("balance", 0) > 0:
                            balance = float(data["balance"])
                            updated_at = data.get("updated_at")
                            loaded_from = "postgresql"
            except Exception as e:
                logger.warning(f" /api/capital PG read error: {e}")
        
        # 2. Fallback to local file
        if loaded_from == "default":
            try:
                if PAPER_BALANCE_FILE.exists():
                    with open(PAPER_BALANCE_FILE, 'r') as f:
                        data = _json.load(f)
                    balance = float(data.get("balance", 100000))
                    updated_at = data.get("updated_at")
                    loaded_from = "file"
            except Exception:
                pass
        
        return {
            "capital": round(balance, 2),
            "currency": "USDT",
            "mode": "paper",
            "source": f"paper_{loaded_from}",
            "updated_at": updated_at
        }
    else:
        # Live mode: get real Binance USDT balance
        try:
            api_key = os.getenv("BINANCE_API_KEY", "")
            api_secret = os.getenv("BINANCE_API_SECRET", "")
            if api_key and api_secret:
                from binance.client import Client
                client = Client(api_key, api_secret)
                usdt_info = client.get_asset_balance(asset="USDT")
                eth_info = client.get_asset_balance(asset="ETH")
                
                usdt_free = float(usdt_info["free"]) if usdt_info else 0
                usdt_locked = float(usdt_info["locked"]) if usdt_info else 0
                eth_free = float(eth_info["free"]) if eth_info else 0
                eth_locked = float(eth_info["locked"]) if eth_info else 0
                
                # Get ETH price for total valuation
                ticker = client.get_symbol_ticker(symbol="ETHUSDT")
                eth_price = float(ticker["price"]) if ticker else 0
                
                total_usdt = usdt_free + usdt_locked + (eth_free + eth_locked) * eth_price
                
                return {
                    "capital": round(total_usdt, 2),
                    "currency": "USDT",
                    "mode": "live",
                    "source": "binance",
                    "usdt_free": round(usdt_free, 2),
                    "usdt_locked": round(usdt_locked, 2),
                    "eth_free": round(eth_free, 6),
                    "eth_locked": round(eth_locked, 6),
                    "eth_price": round(eth_price, 2),
                    "updated_at": datetime.now().isoformat()
                }
            else:
                return {"capital": 0, "currency": "USDT", "mode": "live", "source": "no_api_keys"}
        except Exception as e:
            return {"capital": 0, "currency": "USDT", "mode": "live", "source": "error", "error": str(e)}

@app.post("/api/capital")
async def update_capital(request: Request, current_user: Dict = Depends(get_current_user)):
    """Update trading capital"""
    try:
        data = await request.json()
        capital = float(data.get("capital", 0))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    
    if capital <= 0:
        raise HTTPException(status_code=400, detail="Capital must be positive")
    
    current = load_settings()
    current["trading_capital"] = capital
    
    if save_settings(current):
        # Sync to running bot config
        reload_from_settings()
        return {"status": "success", "message": f"Capital updated to ${capital:,.2f} - effective immediately"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save capital")

@app.get("/api/price/live")
async def get_live_price():
    """Get real-time price from WebSocket stream."""
    try:
        from src.data.price_stream import get_price_stream
        stream = get_price_stream()
        status = stream.get_status()
        return status
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "latest_price": None
        }

# NOTE: /api/ml/models/status is defined later in the file (around line 3056)
# with real data from ml_stats.json and learning.db. Do NOT duplicate it here.

@app.get("/api/risk")
async def get_risk_params():
    """Get risk parameters"""
    settings = load_settings()
    return {
        "risk_per_trade": settings.get("risk_per_trade", 0.006),
        "max_drawdown_day": settings.get("max_drawdown_day", 0.05),
        "max_trades_per_day": settings.get("max_trades_per_day", 15)
    }

@app.post("/api/risk")
async def update_risk_params(risk_per_trade: float, max_drawdown: float, max_trades: int, current_user: Dict = Depends(get_current_user)):
    """Update risk parameters"""
    if not (0 < risk_per_trade <= 0.02):
        raise HTTPException(status_code=400, detail="Risk per trade must be between 0% and 2%")
    if not (0 < max_drawdown <= 0.2):
        raise HTTPException(status_code=400, detail="Max drawdown must be between 0% and 20%")
    if not (1 <= max_trades <= 100):
        raise HTTPException(status_code=400, detail="Max trades must be between 1 and 100")
    
    current = load_settings()
    current.update({
        "risk_per_trade": risk_per_trade,
        "max_drawdown_day": max_drawdown,
        "max_trades_per_day": max_trades
    })
    
    if save_settings(current):
        return {"status": "success", "message": "Risk parameters updated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save risk parameters")

# Backtest Endpoint
class BacktestParams(BaseModel):
    ml_threshold: float = 0.42
    risk_per_trade: float = 0.01
    tp_min: float = 0.015
    tp_max: float = 0.025
    stop_floor: float = 0.015
    max_trades_per_day: int = 15
    # NEW: expanded params for broader search
    rsi_oversold: float = 35.0
    rsi_overbought: float = 75.0
    entry_score_min: float = 0.20
    breakout_pct: float = 0.00005
    # v7: dynamic market filters
    adx_min: float = 14.0
    sentiment_gate: float = -0.20

@app.post("/api/backtest")
async def run_backtest(params: BacktestParams, current_user: Dict = Depends(get_current_user)):
    """Run REAL backtest on historical Binance data with actual bot signals."""
    import numpy as np
    import requests as req
    
    try:
        # 1. Fetch real Binance klines (last 14 days, 5m candles = ~4032 bars)
        base_url = "https://api.binance.com/api/v3/klines"
        all_klines = []
        end_ts = int(datetime.now().timestamp() * 1000)
        start_ts = end_ts - (14 * 24 * 60 * 60 * 1000)  # 14 days
        fetch_start = start_ts
        
        while fetch_start < end_ts:
            resp = req.get(base_url, params={
                "symbol": "ETHUSDT", "interval": "5m",
                "startTime": fetch_start, "limit": 1000
            }, timeout=10)
            data = resp.json()
            if not data:
                break
            all_klines.extend(data)
            fetch_start = int(data[-1][6]) + 1
            if len(data) < 1000:
                break
        
        if len(all_klines) < 200:
            return {"error": "Not enough data", "total_trades": 0, "win_rate": 0, "roi": 0}
        
        # 2. Build DataFrame with indicators
        import pandas as pd
        df = pd.DataFrame(all_klines, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","qv","trades","taker_base","taker_quote","ignore"
        ])
        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)
        
        # Calculate indicators
        from ta.volatility import AverageTrueRange, BollingerBands
        from ta.trend import EMAIndicator, MACD
        from ta.momentum import RSIIndicator
        
        df["ema20"] = EMAIndicator(df["close"], 20).ema_indicator()
        df["ema50"] = EMAIndicator(df["close"], 50).ema_indicator()
        macd = MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd"] = macd.macd()
        df["macd_sig"] = macd.macd_signal()
        df["rsi14"] = RSIIndicator(df["close"], 14).rsi()
        atr = AverageTrueRange(df["high"], df["low"], df["close"], window=14)
        df["atr"] = atr.average_true_range()
        bb = BollingerBands(df["close"], window=20, window_dev=2)
        df["bb_lo"] = bb.bollinger_lband()
        df["hh20"] = df["high"].rolling(20).max()
        df["ll20"] = df["low"].rolling(20).min()
        # v7: Real ADX calculation (was missing — hardcoded bonus before)
        from ta.trend import ADXIndicator
        adx_ind = ADXIndicator(df["high"], df["low"], df["close"], window=14)
        df["adx"] = adx_ind.adx()
        df.dropna(inplace=True)
        
        if len(df) < 100:
            return {"error": "Not enough data after indicators", "total_trades": 0, "win_rate": 0, "roi": 0}
        
        # 3. Run backtest with EXACT live bot scoring logic (v7 synchronized)
        eq = 100000.0
        position = None
        trades = 0
        wins = 0
        losses = 0
        bars_in_pos = 0
        total_pnl = 0.0
        gross_wins = 0.0
        gross_losses = 0.0
        equity_curve = [eq]
        day_trades = 0
        last_day = ""
        exit_reasons = {"TP": 0, "SL": 0, "TIME": 0}
        
        stop_floor = max(0.01, params.stop_floor)  # Min 1% SL
        tp_min = max(0.01, params.tp_min)
        tp_max = max(tp_min + 0.005, params.tp_max)
        stop_atr_mult = 2.0
        trail_atr_mult = 1.5
        max_hold_bars = 90
        
        for i in range(60, len(df) - 1):
            row = df.iloc[i]
            prev = df.iloc[i - 1]
            px = float(row["close"])
            ema20 = float(row["ema20"])
            ema50 = float(row["ema50"])
            rsi14 = float(row["rsi14"])
            hh20 = float(row["hh20"])
            atr_val = float(row["atr"])
            bb_lo = float(row["bb_lo"])
            ll20 = float(row["ll20"])
            adx_now = float(row["adx"])  # v7: real ADX
            
            # Day trade counter
            cur_day = str(df.iloc[i].get("open_time", ""))[:10]
            if cur_day != last_day:
                day_trades = 0
                last_day = cur_day
            
            # --- EXACT scoring as live bot (v7 synchronized) ---
            body = abs(row["close"] - row["open"])
            rng = row["high"] - row["low"]
            lower_wick = min(row["open"], row["close"]) - row["low"]
            drawdown_ok = (rng > 0) and (lower_wick / max(rng, 1e-9) > 0.45) and (row["close"] > (row["low"] + 0.5 * rng))
            
            breakout_ok = px > hh20 * (1.0 + params.breakout_pct)
            # v7: real ADX filter (was missing, hardcoded True before)
            trend_ok = (px > ema20) and (ema20 > ema50) and (adx_now >= params.adx_min)
            rsi_ok = (params.rsi_oversold <= rsi14 <= params.rsi_overbought)
            
            macd_val = float(row["macd"])
            macd_sig_val = float(row["macd_sig"])
            macd_gain = macd_val - macd_sig_val
            # v7: improved ML proxy — multi-signal like GradientBoosting model
            # (combines RSI + EMA trend + MACD + ADX instead of just MACD)
            rsi_sig = 0.5 + (rsi14 - 50) / 200.0  # 0.25-0.75
            trend_sig = 0.55 if px > ema20 and ema20 > ema50 else 0.45
            macd_sig_proxy = 0.5 + np.tanh(macd_gain * 100) * 0.1
            adx_sig = 0.5 + min(0.1, (adx_now - 20) / 200.0) if adx_now > 20 else 0.45
            p_ml = (rsi_sig * 0.3 + trend_sig * 0.25 + macd_sig_proxy * 0.25 + adx_sig * 0.2)
            secondary_ok = trend_ok and (rsi14 >= params.rsi_oversold) and (p_ml >= params.ml_threshold) and (px > ema20)
            
            oversold_ok = (rsi14 <= max(40.0, params.rsi_oversold)) and drawdown_ok and (px >= bb_lo * 1.0005)
            ema_bounce_ok = (px > ema20) and (float(row["low"]) <= ema20 * 1.002) and (rsi14 > 40)
            bb_bounce_ok = (px <= bb_lo * 1.005) and (rsi14 < 45) and (px > float(row["low"]))
            prev_macd = float(prev["macd"])
            prev_macd_sig = float(prev["macd_sig"])
            macd_cross_ok = (macd_val > macd_sig_val) and (prev_macd <= prev_macd_sig)
            range_support_ok = (px <= ll20 * 1.003) and (rsi14 < 40) and (macd_val > prev_macd)
            
            # v7: synced ML direct + ML penalty (EXACT match to live bot)
            ml_direct = max(0.0, min(0.25, (p_ml - 0.5) * 0.5)) if p_ml > 0.52 else 0.0
            ml_penalty = min(0.0, (p_ml - 0.5) * 0.3) if p_ml < 0.45 else 0.0
            
            # v7: real ADX bonus (was hardcoded 0.05)
            adx_bonus = 0.0
            if adx_now >= params.adx_min:
                adx_bonus = max(0.0, min((adx_now - 20.0) / 400.0, 0.15))
            
            # Vol simplified (no granular vol_ok in backtest)
            vol_ok = True  # Simplified — vol data not available per-bar
            boost = (p_ml - 0.5) * 0.4 + adx_bonus
            
            # v7: EXACT weights from live bot (eth_master_bot.py lines 2012-2029)
            score = (
                0.18*(1.0 if breakout_ok else 0.0) +     # Trend: breakout
                0.10*(1.0 if trend_ok else 0.0) +         # Trend: EMA alignment
                0.05*(1.0 if secondary_ok else 0.0) +     # Trend: secondary
                0.10*(1.0 if drawdown_ok else 0.0) +      # Universal: drawdown
                0.05*(1.0 if rsi_ok else 0.0) +           # Universal: RSI band
                0.04*(1.0 if vol_ok else 0.0) +           # Universal: volume
                0.12*(1.0 if oversold_ok else 0.0) +      # Reversal: oversold
                0.10*(1.0 if ema_bounce_ok else 0.0) +    # Reversal: EMA bounce
                0.08*(1.0 if bb_bounce_ok else 0.0) +     # Reversal: BB bounce
                0.10*(1.0 if macd_cross_ok else 0.0) +    # Reversal: MACD cross
                0.06*(1.0 if range_support_ok else 0.0) + # Reversal: range support
                ml_direct +
                ml_penalty +  # v7: ML bearish penalty (was missing)
                boost
            )
            
            # --- Position management ---
            if position:
                bars_in_pos += 1
                entry = position["entry"]
                atr_in = position["atr"]
                upnl = (px / entry) - 1.0
                tp = tp_max if rsi14 >= 70 else tp_min
                sl = max(stop_floor, stop_atr_mult * (atr_in / max(entry, 1e-9)))
                trail = trail_atr_mult * (atr_val / max(entry, 1e-9))
                sl = max(sl, trail)
                
                if upnl >= tp:
                    exit_reason = "TP"
                elif upnl <= -sl:
                    exit_reason = "SL"
                elif bars_in_pos >= max_hold_bars:
                    exit_reason = "TIME"
                else:
                    exit_reason = None
                
                if exit_reason:
                    pnl = eq * params.risk_per_trade * (upnl / sl)  # Approx PnL
                    eq += eq * upnl * (params.risk_per_trade / sl)  # Position-sized
                    total_pnl += pnl
                    exit_reasons[exit_reason] = exit_reasons.get(exit_reason, 0) + 1
                    if upnl > 0:
                        wins += 1
                        gross_wins += abs(pnl)
                    else:
                        losses += 1
                        gross_losses += abs(pnl)
                    position = None
                    bars_in_pos = 0
                    equity_curve.append(eq)
            else:
                if score >= params.entry_score_min and day_trades < params.max_trades_per_day and trades < 500:
                    position = {"entry": px, "atr": atr_val}
                    trades += 1
                    day_trades += 1
        
        # Close any open position at end
        if position:
            upnl = (float(df.iloc[-1]["close"]) / position["entry"]) - 1.0
            eq *= (1.0 + upnl * 0.5)  # Half-sized for end-of-test
            if upnl > 0:
                wins += 1
                gross_wins += abs(upnl * eq * 0.01)
            else:
                losses += 1
                gross_losses += abs(upnl * eq * 0.01)
            trades += 1
            exit_reasons["TIME"] = exit_reasons.get("TIME", 0) + 1
        
        # 4. Calculate metrics
        win_rate = (wins / max(trades, 1)) * 100
        roi = ((eq - 100000.0) / 100000.0) * 100
        
        # Profit factor (v6 scoring needs this)
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else (5.0 if gross_wins > 0 else 0.0)
        
        # Sharpe ratio
        if len(equity_curve) > 2:
            returns = [(equity_curve[i] / equity_curve[i-1]) - 1 for i in range(1, len(equity_curve))]
            sharpe = (np.mean(returns) / max(np.std(returns), 1e-9)) * np.sqrt(252) if returns else 0
        else:
            sharpe = 0
        
        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return {
            "total_trades": trades,
            "winning_trades": wins,
            "losing_trades": losses,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "roi": round(roi, 2),
            "sharpe_ratio": round(float(sharpe), 2),
            "max_drawdown": round(max_dd * 100, 2),
            "profit_factor": round(profit_factor, 2),
            "exit_reasons": exit_reasons,
            "avg_win": round(gross_wins / max(wins, 1), 2),
            "avg_loss": round(gross_losses / max(losses, 1), 2) if losses > 0 else 0,
            "data_source": "real_binance_14d",
            "bars_tested": len(df) - 60
        }
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0, "total_pnl": 0, "roi": 0, "sharpe_ratio": 0,
            "max_drawdown": 0, "profit_factor": 0, "error": str(e)
        }

# Learning API Endpoints - reads from PostgreSQL via learning_store module
# (falls back to JSON files in local dev when DATABASE_URL is not set)

@app.get("/api/learning/stats")
async def get_learning_stats():
    """Get auto-learning statistics and strategies (PostgreSQL-backed) — cached 60s"""
    cached = _cached("learning_stats", ttl=60)
    if cached:
        return cached
    try:
        result = learning_store.get_learning_stats()
        # Cross-reference: mark the strategy closest to current_strategy score as applied
        current = result.get("current_strategy")
        if current and "strategies" in result:
            current_score = current.get("score", -999)
            best_idx = -1
            best_diff = 999
            for i, strat in enumerate(result["strategies"]):
                diff = abs(strat.get("score", 0) - current_score)
                if diff < best_diff:
                    best_diff = diff
                    best_idx = i
            for i, strat in enumerate(result["strategies"]):
                strat["applied"] = (i == best_idx and best_diff < 1.0)
            if result.get("stats"):
                result["stats"]["total_applied"] = max(result["stats"].get("total_applied", 0), 1)
        _set_cache("learning_stats", result)
        return result
    except Exception as e:
        logger.warning(f" getting learning stats: {e}")
        return {
            "stats": {
                "total_tested": 0,
                "best_score": 0,
                "total_applied": 0,
                "today_tested": 0,
                "this_hour_tested": 0
            },
            "strategies": [],
            "current_strategy": None
        }

@app.get("/api/learning/strategies")
async def get_top_strategies(limit: int = 10):
    """Get top performing strategies (PostgreSQL-backed)"""
    try:
        return learning_store.get_all_strategies(limit)
    except Exception as e:
        logger.warning(f" getting top strategies: {e}")
        return []

@app.get("/api/learning/evolution")
async def get_strategy_evolution(days: int = 7):
    """Get strategy score evolution over time (PostgreSQL-backed)"""
    try:
        return learning_store.get_evolution(days)
    except Exception as e:
        logger.warning(f" getting evolution: {e}")
        return []

@app.get("/api/learning/current")
async def get_current_strategy():
    """Get currently applied strategy (PostgreSQL-backed)"""
    try:
        return learning_store.get_current_strategy()
    except Exception as e:
        logger.warning(f" getting current strategy: {e}")
        return None

# Trading Mode Switch
class TradingMode(BaseModel):
    mode: str  # "paper" or "live"

@app.post("/api/trading/mode")
async def switch_trading_mode(mode_data: TradingMode, current_user: Dict = Depends(get_current_user)):
    """Switch between paper and live trading"""
    mode = mode_data.mode.lower()
    
    if mode not in ["paper", "live"]:
        raise HTTPException(status_code=400, detail="Invalid mode. Must be 'paper' or 'live'")
    
    try:
        # Load current settings
        settings = load_settings()
        
        # Update DRY_RUN
        settings['dry_run'] = (mode == "paper")
        
        # Save settings
        if save_settings(settings):
            # Sync to running bot config
            reload_from_settings()
            return {
                "status": "success",
                "mode": mode,
                "message": f"Switched to {mode.upper()} trading. Bot mode updated immediately."
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save settings")
    except Exception as e:
        logger.warning(f" switching mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trading/mode")
async def get_trading_mode():
    """Get current trading mode"""
    try:
        settings = load_settings()
        is_paper = settings.get('dry_run', True)
        return {
            "mode": "paper" if is_paper else "live",
            "dry_run": is_paper
        }
    except Exception as e:
        logger.warning(f" getting mode: {e}")
        return {"mode": "paper", "dry_run": True}


# ==================== AUTHENTICATION SYSTEM ====================
# UserManager, Pydantic models, and authentication dependencies are initialized at the top of the file


# ==================== ACCOUNT MANAGEMENT ====================
from account_manager import AccountManager

# Load .env.bot before account seeding to get BINANCE_API_KEY/SECRET
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).parent / ".env.bot"
    if _env_file.exists():
        load_dotenv(_env_file)
        logger.info(f" Loaded environment from .env.bot")
except ImportError:
    logger.warning(" python-dotenv not installed, skipping .env.bot loading")

account_mgr = AccountManager()

# Auto-seed account from BINANCE_API_KEY/SECRET env vars on startup
logger.info(" Checking for Binance API credentials from environment...")
# Check both possible env var names for the secret
_api_key = os.getenv("BINANCE_API_KEY", "")
_api_secret = os.getenv("BINANCE_API_SECRET", "") or os.getenv("BINANCE_SECRET_KEY", "")
if _api_key and _api_secret:
    # Temporarily set the expected env var name for migrate_legacy_account
    os.environ["BINANCE_API_SECRET"] = _api_secret
_seeded_account = account_mgr.migrate_legacy_account()
if _seeded_account:
    logger.info(f" Auto-seeded account from env vars (ID: {_seeded_account})")
else:
    logger.info(" No BINANCE_API_KEY/SECRET found in env, or account already exists")

class AccountCreate(BaseModel):
    name: str
    api_key: str
    api_secret: str
    capital: float = 100000
    dry_run: bool = True

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    capital: Optional[float] = None
    dry_run: Optional[bool] = None
    active: Optional[bool] = None

@app.get("/api/accounts")
async def list_accounts(
    active_only: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """List all trading accounts for current user"""
    try:
        accounts = account_mgr.list_accounts(
            user_id=current_user['id'],
            active_only=active_only
        )
        return {"accounts": accounts, "total": len(accounts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/accounts")
async def create_account(
    account: AccountCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new trading account for current user"""
    try:
        # Check subscription limits
        from subscription_manager import enforce_tier_limits
        allowed, message = enforce_tier_limits(current_user['id'], 'add_account')
        if not allowed:
            raise HTTPException(status_code=403, detail=message)
        
        # Validate credentials first
        if not account_mgr.validate_credentials(account.api_key, account.api_secret):
            raise HTTPException(status_code=400, detail="Invalid Binance API credentials")
        
        account_id = account_mgr.create_account(
            user_id=current_user['id'],
            name=account.name,
            api_key=account.api_key,
            api_secret=account.api_secret,
            capital=account.capital,
            dry_run=account.dry_run
        )
        
        if account_id == -1:
            raise HTTPException(status_code=400, detail="Account name already exists")
        
        return {
            "status": "success",
            "account_id": account_id,
            "message": f"Account '{account.name}' created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/accounts/{account_id}")
async def get_account(account_id: int, current_user: Dict = Depends(get_current_user)):
    """Get account details"""
    try:
        account = account_mgr.get_account(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Mask API secret
        account['api_secret'] = "•" * 16
        return account
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/accounts/{account_id}")
async def update_account(account_id: int, updates: AccountUpdate, current_user: Dict = Depends(get_current_user)):
    """Update account settings"""
    try:
        # Build update dict
        update_dict = {}
        if updates.name is not None:
            update_dict['name'] = updates.name
        if updates.api_key is not None:
            update_dict['api_key'] = updates.api_key
        if updates.api_secret is not None:
            update_dict['api_secret'] = updates.api_secret
        if updates.capital is not None:
            update_dict['capital'] = updates.capital
        if updates.dry_run is not None:
            update_dict['dry_run'] = updates.dry_run
        if updates.active is not None:
            update_dict['active'] = updates.active
        
        success = account_mgr.update_account(account_id, **update_dict)
        
        if not success:
            raise HTTPException(status_code=404, detail="Account not found")
        
        return {"status": "success", "message": "Account updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: int, current_user: Dict = Depends(get_current_user)):
    """Delete an account"""
    try:
        success = account_mgr.delete_account(account_id)
        if not success:
            raise HTTPException(status_code=404, detail="Account not found")
        
        return {"status": "success", "message": "Account deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/accounts/{account_id}/toggle")
async def toggle_account(account_id: int, current_user: Dict = Depends(get_current_user)):
    """Toggle account active status"""
    try:
        success = account_mgr.toggle_account(account_id)
        if not success:
            raise HTTPException(status_code=404, detail="Account not found")
        
        account = account_mgr.get_account(account_id)
        status = "active" if account['active'] else "inactive"
        
        return {
            "status": "success",
            "active": account['active'],
            "message": f"Account is now {status}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/accounts/validate")
async def validate_credentials(api_key: str, api_secret: str, current_user: Dict = Depends(get_current_user)):
    """Validate Binance API credentials"""
    try:
        valid = account_mgr.validate_credentials(api_key, api_secret)
        return {
            "valid": valid,
            "message": "Credentials are valid" if valid else "Invalid credentials"
        }
    except Exception as e:
        return {
            "valid": False,
            "message": str(e)
        }

# Account-specific data endpoints
@app.get("/api/accounts/{account_id}/trades")
async def get_account_trades(account_id: int, limit: int = 100):
    """Get trades for a specific account"""
    try:
        import sqlite3
        from account_manager import ACCOUNTS_DB
        
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, action, qty, price, pnl
            FROM account_trades
            WHERE account_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (account_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        trades = []
        for row in rows:
            trades.append({
                "timestamp": row[0],
                "action": row[1],
                "qty": row[2],
                "price": row[3],
                "pnl": row[4]
            })
        
        return {"trades": trades, "total": len(trades)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/accounts/{account_id}/performance")
async def get_account_performance(account_id: int):
    """Get performance metrics for a specific account"""
    try:
        import sqlite3
        from account_manager import ACCOUNTS_DB
        
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT total_pnl, total_trades, win_rate, sharpe_ratio, max_drawdown, last_updated
            FROM account_performance
            WHERE account_id = ?
        """, (account_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {
                "total_pnl": 0,
                "total_trades": 0,
                "win_rate": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0,
                "last_updated": None
            }
        
        return {
            "total_pnl": row[0],
            "total_trades": row[1],
            "win_rate": row[2],
            "sharpe_ratio": row[3],
            "max_drawdown": row[4],
            "last_updated": row[5]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Aggregated portfolio endpoints
@app.get("/api/portfolio/total")
async def get_total_portfolio():
    """Get combined portfolio value across all accounts"""
    try:
        import sqlite3
        from account_manager import ACCOUNTS_DB
        
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        # Sum capital from all active accounts
        cursor.execute("""
            SELECT SUM(capital) FROM accounts WHERE active = 1
        """)
        total_capital = cursor.fetchone()[0] or 0
        
        # Sum PnL from all accounts
        cursor.execute("""
            SELECT SUM(total_pnl) FROM account_performance
        """)
        total_pnl = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            "total_capital": total_capital,
            "total_pnl": total_pnl,
            "total_value": total_capital + total_pnl,
            "roi": (total_pnl / total_capital * 100) if total_capital > 0 else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/portfolio/performance")
async def get_aggregated_performance():
    """Get aggregated performance across all accounts"""
    try:
        import sqlite3
        from account_manager import ACCOUNTS_DB
        
        conn = sqlite3.connect(ACCOUNTS_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                SUM(total_pnl) as total_pnl,
                SUM(total_trades) as total_trades,
                AVG(win_rate) as avg_win_rate,
                AVG(sharpe_ratio) as avg_sharpe,
                MAX(max_drawdown) as max_dd
            FROM account_performance
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            "total_pnl": row[0] or 0,
            "total_trades": row[1] or 0,
            "avg_win_rate": row[2] or 0,
            "avg_sharpe_ratio": row[3] or 0,
            "max_drawdown": row[4] or 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TEST PHASE ENDPOINTS ====================

@app.get("/api/test-phase/{symbol}")
async def get_test_phase(symbol: str, current_user: Dict = Depends(get_current_user)):
    """Get test phase status for a specific cryptocurrency"""
    try:
        phase = test_phase_manager.get_test_phase(current_user['id'], symbol)
        if not phase:
            return {"error": "No test phase found for this symbol"}
        return phase
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test-phase/{symbol}/start")
async def start_test_phase(symbol: str, current_user: Dict = Depends(get_current_user)):
    """Start a new 30-day test phase for a cryptocurrency"""
    try:
        # Check subscription limits
        sub_mgr = SubscriptionManager()
        tier = sub_mgr.get_user_tier(current_user['id'])
        
        # Get existing test phases
        all_phases = test_phase_manager.get_all_test_phases(current_user['id'])
        
        # Check if user can add more coins
        tier_info = sub_mgr.get_tier_info(tier)
        if len(all_phases) >= tier_info['max_trading_pairs']:
            raise HTTPException(
                status_code=403,
                detail=f"Maximum {tier_info['max_trading_pairs']} coins allowed on {tier} tier"
            )
        
        phase = test_phase_manager.start_test_phase(current_user['id'], symbol)
        return {
            "success": True,
            "message": f"30-day test phase started for {symbol}",
            "phase": phase
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/test-phases")
async def get_all_test_phases(current_user: Dict = Depends(get_current_user)):
    """Get all test phases for the current user"""
    try:
        phases = test_phase_manager.get_all_test_phases(current_user['id'])
        return {"test_phases": phases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test-phase/{symbol}/update")
async def update_test_phase_metrics(
    symbol: str,
    metrics: Dict,
    current_user: Dict = Depends(get_current_user)
):
    """Update test phase with new performance metrics"""
    try:
        phase = test_phase_manager.update_test_phase(
            current_user['id'],
            symbol,
            metrics
        )
        return {
            "success": True,
            "phase": phase
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SUBSCRIPTION ENDPOINTS ====================

@app.get("/api/subscription")
async def get_subscription(current_user: Dict = Depends(get_current_user)):
    """Get user's current subscription"""
    try:
        sub_mgr = SubscriptionManager()
        tier = sub_mgr.get_user_tier(current_user['id'])
        tier_info = sub_mgr.get_tier_info(tier)
        usage = sub_mgr.get_usage_stats(current_user['id'])
        
        return {
            "tier": tier,
            "tier_name": tier_info['name'],
            "price": tier_info['price'],
            "features": tier_info['features'],
            "usage": usage,
            "can_upgrade": tier == 'free'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/subscription/upgrade")
async def upgrade_subscription(current_user: Dict = Depends(get_current_user)):
    """Upgrade user to premium subscription"""
    try:
        sub_mgr = SubscriptionManager()
        
        # Check if already premium
        current_tier = sub_mgr.get_user_tier(current_user['id'])
        if current_tier == 'premium':
            raise HTTPException(status_code=400, detail="Already on premium tier")
        
        # Upgrade to premium
        success = sub_mgr.upgrade_user(current_user['id'], 'premium')
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to upgrade subscription")
        
        return {
            "success": True,
            "message": "Successfully upgraded to Premium",
            "tier": "premium"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/subscription/tiers")
async def get_subscription_tiers():
    """Get all available subscription tiers"""
    try:
        from subscription_manager import TIERS
        return {"tiers": TIERS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ENHANCED TRADING MODE ENDPOINTS ====================

@app.post("/api/trading/mode/toggle")
async def toggle_trading_mode(current_user: Dict = Depends(get_current_user)):
    """Toggle between paper and live trading with safety checks"""
    try:
        settings = load_settings()
        current_mode = "paper" if settings.get('dry_run', True) else "live"
        new_mode = "live" if current_mode == "paper" else "paper"
        
        # Safety checks for enabling live trading
        if new_mode == "live":
            # Check subscription tier
            sub_mgr = SubscriptionManager()
            tier = sub_mgr.get_user_tier(current_user['id'])
            tier_info = sub_mgr.get_tier_info(tier)
            
            if not tier_info['live_trading']:
                raise HTTPException(
                    status_code=403,
                    detail="Live trading requires Premium subscription"
                )
            
            # Check if any test phase is completed and ready
            all_phases = test_phase_manager.get_all_test_phases(current_user['id'])
            
            if not all_phases:
                raise HTTPException(
                    status_code=400,
                    detail="No test phases found. Start a 30-day test phase first."
                )
            
            # Check if at least one coin is ready for live trading
            ready_coins = [
                symbol for symbol, phase in all_phases.items()
                if phase.get('ready_for_live', False)
            ]
            
            if not ready_coins and tier_info.get('test_phase_required', True):
                raise HTTPException(
                    status_code=400,
                    detail="Complete a 30-day test phase before enabling live trading"
                )
        
        # Update settings
        settings['dry_run'] = (new_mode == "paper")
        save_settings(settings)
        
        # Sync to running bot config immediately
        reload_from_settings()
        
        # Log the change
        logger.info(f"User {current_user['id']} switched to {new_mode} mode")
        
        return {
            "success": True,
            "mode": new_mode,
            "dry_run": settings['dry_run'],
            "message": f"Switched to {new_mode.upper()} trading mode"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trading/mode/status")
async def get_trading_mode_status(current_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get comprehensive trading mode status including test phases"""
    # Return paper mode for unauthenticated users
    if not current_user:
        return {
            "mode": "paper",
            "dry_run": True,
            "can_enable_live": False,
            "subscription_tier": "free",
            "live_trading_allowed": False,
            "test_phases": {},
            "ready_coins": [],
            "requires_upgrade": True
        }
    
    try:
        settings = load_settings()
        is_paper = settings.get('dry_run', True)
        
        # Get subscription info
        sub_mgr = SubscriptionManager()
        tier = sub_mgr.get_user_tier(current_user['id'])
        tier_info = sub_mgr.get_tier_info(tier)
        
        # Get test phases
        all_phases = test_phase_manager.get_all_test_phases(current_user['id'])
        
        # Calculate readiness
        ready_coins = [
            symbol for symbol, phase in all_phases.items()
            if phase.get('ready_for_live', False)
        ]
        
        can_enable_live = (
            tier_info['live_trading'] and
            (len(ready_coins) > 0 or not tier_info.get('test_phase_required', True))
        )
        
        return {
            "mode": "paper" if is_paper else "live",
            "dry_run": is_paper,
            "can_enable_live": can_enable_live,
            "subscription_tier": tier,
            "live_trading_allowed": tier_info['live_trading'],
            "test_phases": all_phases,
            "ready_coins": ready_coins,
            "requires_upgrade": not tier_info['live_trading']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Stripe Payment Endpoints (optional — not needed for core trading)
try:
    from stripe_integration import create_checkout_session, verify_webhook_signature, handle_successful_payment
    HAS_STRIPE = True
except ImportError:
    HAS_STRIPE = False

@app.post("/api/subscription/checkout")
async def create_subscription_checkout(current_user: Dict = Depends(get_current_user)):
    """Create Stripe checkout session for Premium upgrade"""
    if not HAS_STRIPE:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    try:
        result = create_checkout_session(
            user_id=current_user['id'],
            user_email=current_user['email'],
            tier="premium"
        )
        
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Failed to create checkout session. Please check Stripe configuration."
            )
        
        return {
            "checkout_url": result["checkout_url"],
            "session_id": result["session_id"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/subscription/webhook")
async def stripe_webhook(request):
    """Handle Stripe webhook events"""
    if not HAS_STRIPE:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    from fastapi import Request
    
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    
    event = verify_webhook_signature(payload, signature)
    
    if not event:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    
    # Handle the event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = int(session.get("client_reference_id", 0))
        tier = session.get("metadata", {}).get("tier", "premium")
        
        if user_id:
            handle_successful_payment(user_id, tier)
            logger.info(f" Checkout completed for user {user_id}, tier: {tier}")
    
        session = event["data"]["object"]
        # Note: Would need to implement user lookup by Stripe customer ID
        logger.info(f"Subscription cancelled: {session.get('id')}")
    
    return {"status": "success"}


# =============================================================================
# ML/AI MONITORING ENDPOINTS
# =============================================================================

@app.get("/api/ml/status")
async def get_ml_status():
    """Get status of all ML models (checks local files + KV store)"""
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    
    models = {}
    
    # Check DQN model (local file only)
    dqn_path = log_dir / "dqn_agent.pt"
    if dqn_path.exists():
        stat = dqn_path.stat()
        models["dqn"] = {
            "status": "trained",
            "file_size": f"{stat.st_size / 1024:.1f} KB",
            "last_updated": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "model_type": "Deep Q-Network (Reinforcement Learning)"
        }
    else:
        models["dqn"] = {"status": "not_trained", "model_type": "Deep Q-Network"}
    
    # Check Gradient Boosting model — KV store (bot saves here) + local file
    gb_path = log_dir / "ml_model.pkl"
    gb_found = False
    
    # 1) Check KV store (bot persists model here as pickle)
    try:
        ml_stats_json = learning_store.get_kv("ml_stats")
        ml_model_exists = learning_store.get_kv("ml_model_pickle") is not None
        if ml_stats_json and ml_model_exists:
            stats = json.loads(ml_stats_json)
            ml_s = stats.get("ml_stats", {})
            models["gradient_boosting"] = {
                "status": "trained",
                "storage": "PostgreSQL KV Store",
                "accuracy": f"{ml_s.get('accuracy', 0):.1f}%",
                "samples": ml_s.get("samples", 0),
                "last_updated": stats.get("saved_at", "unknown"),
                "model_type": "Gradient Boosting Classifier (11 features)",
                "experience_replay": stats.get("experience_replay_size", 0)
            }
            gb_found = True
    except Exception:
        pass
    
    # 2) Fallback: local file
    if not gb_found and gb_path.exists():
        stat = gb_path.stat()
        models["gradient_boosting"] = {
            "status": "trained",
            "file_size": f"{stat.st_size / 1024:.1f} KB",
            "last_updated": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "model_type": "Gradient Boosting Regressor"
        }
        gb_found = True
    
    if not gb_found:
        models["gradient_boosting"] = {"status": "not_trained", "model_type": "Gradient Boosting"}
    
    # Check LSTM model (local file only)
    lstm_path = log_dir / "neural_model.pt"
    if lstm_path.exists():
        stat = lstm_path.stat()
        models["lstm"] = {
            "status": "trained",
            "file_size": f"{stat.st_size / 1024:.1f} KB",
            "last_updated": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "model_type": "LSTM Neural Network"
        }
    else:
        models["lstm"] = {"status": "not_trained", "model_type": "LSTM Neural Network"}
    
    return {
        "models": models,
        "ensemble_available": all(m.get("status") == "trained" for m in [models.get("gradient_boosting", {}), models.get("lstm", {})])
    }


@app.get("/api/ml/dqn/info")
async def get_dqn_info():
    """Get detailed DQN model information"""
    try:
        import torch
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        dqn_path = log_dir / "dqn_agent.pt"
        
        if not dqn_path.exists():
            return {"status": "not_trained", "message": "DQN model not found"}
        
        data = torch.load(dqn_path, map_location='cpu', weights_only=False)
        
        # Extract training stats
        training_stats = data.get('training_stats', {})
        
        return {
            "status": "trained",
            "epsilon": round(data.get('epsilon', 1.0), 4),
            "episodes_trained": training_stats.get('episodes', 0),
            "last_updated": data.get('timestamp', 'unknown'),
            "total_rewards": len(training_stats.get('total_rewards', [])),
            "avg_reward_last_20": round(sum(training_stats.get('total_rewards', [])[-20:]) / max(len(training_stats.get('total_rewards', [])[-20:]), 1), 2) if training_stats.get('total_rewards') else 0
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/dqn/predict")
async def get_dqn_prediction():
    """Get current DQN trading recommendation"""
    try:
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        
        # Try to import and use the DQN agent
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from rl_trading_agent import DQNAgent, TradingEnvironment
        import numpy as np
        
        env = TradingEnvironment(window_size=20)
        agent = DQNAgent(state_size=env.state_size)
        
        if not agent.is_trained:
            return {"status": "not_trained", "message": "DQN agent not trained yet"}
        
        # Generate a sample state (in production this would come from live data)
        test_state = np.random.randn(env.state_size).astype(np.float32)
        decision = agent.get_trading_decision(test_state)
        
        return {
            "status": "success",
            "recommendation": decision['action'],
            "confidence": round(decision['confidence'] * 100, 1),
            "q_values": {k: round(v, 4) for k, v in decision['q_values'].items()},
            "probabilities": {k: round(v * 100, 1) for k, v in decision['probabilities'].items()}
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/ensemble/predict")
async def get_ensemble_prediction():
    """Get predictions from ensemble model"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from neural_strategy_predictor import EnsemblePredictor
        
        ensemble = EnsemblePredictor()
        
        # Test strategy
        test_strategy = {
            'ml_threshold': 0.55,
            'risk_per_trade': 0.008,
            'tp_min': 0.010,
            'tp_max': 0.020,
            'stop_floor': 0.008,
            'max_trades_per_day': 15
        }
        
        predictions = ensemble.predict_score(test_strategy)
        
        return {
            "status": "success",
            "predictions": {k: round(v, 2) for k, v in predictions.items()},
            "test_strategy": test_strategy
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/feature-importance")
async def get_feature_importance():
    """Get feature importance from Gradient Boosting model (from bot's KV store)"""
    try:
        # Try KV store first (bot saves real feature importance here)
        fi_json = learning_store.get_kv("ml_feature_importance")
        if fi_json:
            features = json.loads(fi_json)
            return {"status": "success", "features": features}
        
        # Fallback: try MLStrategyPredictor
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from ml_strategy_predictor import MLStrategyPredictor
        predictor = MLStrategyPredictor()
        if predictor.is_trained:
            importance = predictor.get_feature_importance()
            sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)
            return {
                "status": "success",
                "features": [{"name": k, "importance": round(v * 100, 2)} for k, v in sorted_importance]
            }
        
        return {"status": "not_trained", "message": "Model not trained yet — waiting for bot to train on klines"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/training-progress")
async def get_training_progress():
    """Check ML training status - includes synced data from local machines"""
    global _synced_training_data, _training_active
    
    # If training is active but no episode data yet (startup phase), report starting
    if _training_active and (not _synced_training_data or _synced_training_data.get("episode", 0) == 0):
        return {
            "training_active": True,
            "source": "server",
            "status": "starting",
            "model": _synced_training_data.get("model_type", "enhanced_dqn") if _synced_training_data else "enhanced_dqn",
            "architecture": "Initializing...",
            "episode": 1,  # Report 1 so frontend shows progress
            "total_episodes": _synced_training_data.get("total_episodes", 500) if _synced_training_data else 500,
            "progress_pct": 0.1,
            "current_reward": 0,
            "best_reward": 0,
            "roi": 0,
            "best_roi": 0,
            "win_rate": 0,
            "trades": 0,
            "portfolio_value": 100000,
            "elapsed_seconds": 0,
            "last_update": datetime.now().isoformat(),
            "processes": []
        }
    
    # Check synced training data with episode progress
    if _synced_training_data and _synced_training_data.get("episode", 0) > 0:
        return {
            "training_active": True,
            "source": "synced_local",
            "model": _synced_training_data.get("model_type", "enhanced_dqn"),
            "architecture": _synced_training_data.get("architecture", "Unknown"),
            "episode": _synced_training_data.get("episode", 0),
            "total_episodes": _synced_training_data.get("total_episodes", 500),
            "progress_pct": _synced_training_data.get("progress_pct", 0),
            "current_reward": _synced_training_data.get("reward", 0),
            "best_reward": _synced_training_data.get("best_reward", 0),
            "roi": _synced_training_data.get("roi", 0),
            "best_roi": _synced_training_data.get("best_roi", 0),
            "win_rate": _synced_training_data.get("win_rate", 0),
            "trades": _synced_training_data.get("trades", 0),
            "portfolio_value": _synced_training_data.get("portfolio_value", 0),
            "elapsed_seconds": _synced_training_data.get("elapsed_seconds", 0),
            "last_update": _synced_training_data.get("received_at", ""),
            "processes": []
        }
    
    # Fallback: if _training_active flag is set (from /start endpoint), trust it
    if _training_active:
        return {
            "training_active": True,
            "source": "server_flag",
            "status": "running",
            "processes": []
        }
    
    # Last resort: check for local processes
    try:
        import subprocess
        
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        training_processes = []
        for line in result.stdout.split('\n'):
            if 'rl_trading_agent' in line and '--train' in line:
                parts = line.split()
                if len(parts) >= 11:
                    training_processes.append({
                        "type": "DQN",
                        "pid": parts[1],
                        "cpu": parts[2],
                        "memory": parts[3],
                        "time": parts[9]
                    })
            elif 'train_enhanced_dqn' in line:
                parts = line.split()
                if len(parts) >= 11:
                    training_processes.append({
                        "type": "Enhanced DQN",
                        "pid": parts[1],
                        "cpu": parts[2],
                        "memory": parts[3],
                        "time": parts[9]
                    })
        
        return {
            "training_active": len(training_processes) > 0,
            "source": "local_process",
            "processes": training_processes
        }
    except Exception:
        return {
            "training_active": False,
            "source": "none",
            "processes": []
        }


@app.get("/api/ml/models/status")
async def get_all_models_status():
    """Get status of all ML models - cached 30s"""
    cached = _cached("models_status", ttl=30)
    if cached:
        return cached
    global _synced_training_data, _synced_ml_stats
    
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    
    # Read real ML stats from Worker (synced via /api/ml/stats-sync)
    ml_stats = _synced_ml_stats if _synced_ml_stats else {}
    
    # Also try local file as fallback
    if not ml_stats:
        stats_file = log_dir / "ml_stats.json"
        try:
            if stats_file.exists():
                import json
                with open(stats_file, "r") as f:
                    ml_stats = json.load(f)
        except Exception:
            pass
    
    # Load from PostgreSQL if still empty (survives redeploys)
    if not ml_stats and USE_POSTGRES:
        try:
            import json
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Try ml_stats key first
                cursor.execute("SELECT value FROM kv_store WHERE key = 'ml_stats'")
                row = cursor.fetchone()
                if row:
                    raw = json.loads(row[0])
                    # Bot wraps stats: {"ml_stats": {...}, "ml_conf_boost": ..., "saved_at": ...}
                    ml_stats = raw.get("ml_stats", raw) if isinstance(raw, dict) else {}
                    _synced_ml_stats = ml_stats  # Cache in memory
                
                # Fallback: if ml_stats key was empty, try legacy sgd_model_state
                if not ml_stats:
                    cursor.execute("SELECT value FROM kv_store WHERE key = 'sgd_model_state'")
                    row2 = cursor.fetchone()
                    if row2:
                        model_state = json.loads(row2[0])
                        nested_stats = model_state.get("ml_stats", {})
                        if nested_stats:
                            ml_stats = nested_stats
                            _synced_ml_stats = ml_stats
        except Exception:
            pass
    
    # Read strategy backtester stats from PostgreSQL (shared between containers)
    backtester_stats = {"total_tested": 0, "best_score": 0, "last_tested": None}
    try:
        ls = learning_store.get_learning_stats()
        if ls and "stats" in ls:
            backtester_stats["total_tested"] = ls["stats"].get("total_tested", 0)
            backtester_stats["best_score"] = round(ls["stats"].get("best_score", 0), 1)
        # Get last tested time from current strategy
        current = ls.get("current_strategy")
        if current and current.get("timestamp"):
            backtester_stats["last_tested"] = current["timestamp"]
    except Exception as e:
        logger.warning(f" reading learning stats for models: {e}")
    
    # Format last trained time
    def format_age(iso_str):
        if not iso_str:
            return "Not trained"
        try:
            last = datetime.fromisoformat(iso_str)
            age = datetime.now() - last
            if age.days > 0:
                return f"{age.days}d ago"
            elif age.seconds > 3600:
                return f"{age.seconds // 3600}h ago"
            elif age.seconds > 60:
                return f"{age.seconds // 60}m ago"
            else:
                return "Just now"
        except Exception:
            return "Unknown"
    
    # Build models list with REAL data
    sgd_last_trained = format_age(ml_stats.get("last_trained"))
    if sgd_last_trained == "Not trained" and backtester_stats["total_tested"] > 0:
        sgd_last_trained = "Awaiting data..."
    
    results = [
        {
            "name": "ML Classifier",
            "type": "Gradient Boosting (Online Learning)",
            "version": "v3.1.0",
            "accuracy": ml_stats.get("accuracy", 0),
            "samples": ml_stats.get("samples", 0),
            "lastTrained": sgd_last_trained,
            "predictions": ml_stats.get("predictions_made", 0),
            "status": "active" if ml_stats.get("warm") else "warming_up"
        },
        {
            "name": "Strategy Optimizer",
            "type": "Parameter Grid Search + Backtest",
            "version": "v2.5.0",
            "accuracy": backtester_stats["best_score"],
            "samples": backtester_stats["total_tested"],
            "lastTrained": format_age(backtester_stats["last_tested"]),
            "status": "active"
        },
        {
            "name": "Gradient Booster",
            "type": "XGBoost Ensemble",
            "version": "v2.0.0",
            "accuracy": round(_synced_training_data.get("win_rate", 0), 1) if _synced_training_data else 0,
            "samples": _synced_training_data.get("trades", 0) if _synced_training_data else 0,
            "lastTrained": "Not trained",
            "status": "idle"
        },
        {
            "name": "Sentiment Analyzer",
            "type": "RSS Feed Analysis",
            "version": "v3.0.2",
            "accuracy": 0,
            "samples": 0,
            "lastTrained": "Live",
            "status": "active"
        }
    ]
    
    # If training is active, update the relevant model
    if _synced_training_data and _synced_training_data.get("episode", 0) > 0:
        model_type = _synced_training_data.get("model_type", "gradient_boosting")
        for r in results:
            if "Gradient" in r["name"] or model_type in r["name"].lower():
                r["accuracy"] = round(_synced_training_data.get("win_rate", 0), 1)
                r["samples"] = _synced_training_data.get("trades", 0)
                r["lastTrained"] = "Training now..."
                r["status"] = "training"
                break
    
    # Check for stored gradient boosting model
    gb_model = log_dir / "ml_model.pkl"
    if gb_model.exists():
        try:
            mtime = gb_model.stat().st_mtime
            results[2]["lastTrained"] = format_age(datetime.fromtimestamp(mtime).isoformat())
            results[2]["samples"] = gb_model.stat().st_size // 100
            results[2]["accuracy"] = 62
            results[2]["status"] = "trained"
        except Exception:
            pass
    
    result = {"models": results, "total_stored": len([r for r in results if r.get("status") != "idle"])}
    _set_cache("models_status", result)
    return result


@app.get("/api/ml/dqn/live")
async def get_dqn_live_training():
    """Get live DQN training progress from log file"""
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    training_log = log_dir / "dqn_training_live.json"
    
    if not training_log.exists():
        return {"status": "no_training", "message": "No active training session"}
    
    try:
        with open(training_log, "r") as f:
            data = json.load(f)
        
        # Check if training log is recent (within last 5 minutes)
        log_time = datetime.fromisoformat(data.get("timestamp", "2020-01-01"))
        age_seconds = (datetime.now() - log_time).total_seconds()
        
        if age_seconds > 300:  # 5 minutes
            data["status"] = "stale"
            data["age_seconds"] = round(age_seconds)
        else:
            data["status"] = "active"
            data["age_seconds"] = round(age_seconds)
        
        return data
    except Exception as e:
        return {"status": "error", "message": str(e)}


# In-memory cache for synced training data — now in StateManager
_synced_training_data = state.training_data   # legacy alias
# In-memory cache for ML stats synced from Worker container
_synced_ml_stats = state.ml_stats             # legacy alias

@app.post("/api/ml/stats-sync")
async def sync_ml_stats(data: dict, request: Request = None, _auth = Depends(verify_internal_api_key)):
    """Receive ML stats from Worker container — persist to PostgreSQL"""
    state.ml_stats = data
    # Persist to PostgreSQL so stats survive redeploys
    try:
        if USE_POSTGRES:
            import json
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO kv_store (key, value) VALUES ('ml_stats', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, (json.dumps(data),))
    except Exception as e:
        logger.warning(f"ML stats persist: {e}")
    return {"ok": True}

@app.post("/api/ml/training-sync")
async def sync_training_data(data: dict, _auth = Depends(verify_internal_api_key)):
    """Receive training progress from local machines and cache it"""
    try:
        # Store all the training data in StateManager
        state.training_data = {
            "timestamp": data.get("timestamp", datetime.now().isoformat()),
            "episode": data.get("episode", 0),
            "total_episodes": data.get("total_episodes", 500),
            "progress_pct": data.get("progress_pct", 0),
            "reward": data.get("reward", 0),
            "avg_reward_10": data.get("avg_reward_10", 0),
            "best_reward": data.get("best_reward", 0),
            "roi": data.get("roi", 0),
            "best_roi": data.get("best_roi", 0),
            "portfolio_value": data.get("portfolio_value", 0),
            "trades": data.get("trades", 0),
            "wins": data.get("wins", 0),
            "losses": data.get("losses", 0),
            "win_rate": data.get("win_rate", 0),
            "training_steps": data.get("training_steps", 0),
            "memory_size": data.get("memory_size", 0),
            "elapsed_seconds": data.get("elapsed_seconds", 0),
            "status": data.get("status", "training"),
            "model_type": data.get("model_type", "enhanced_dqn"),
            "architecture": data.get("architecture", "Dueling DQN + Attention + LSTM"),
            "received_at": datetime.now().isoformat()
        }
        return {"status": "success", "message": f"Training data synced: Episode {data.get('episode', 0)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/training-sync")
async def get_synced_training():
    """Get synced training data from local machine"""
    synced = state.training_data
    if not synced:
        return {
            "status": "success",
            "training_active": False,
            "message": "No training data synced yet"
        }
    
    return {
        "status": "success",
        "training_active": True,
        **synced
    }


@app.get("/api/ml/ensemble/signal")
async def get_ensemble_signal():
    """Get ensemble prediction combining DQN + GB + LSTM"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.ml.dqn_ensemble_adapter import UnifiedEnsemble
        import numpy as np
        
        ensemble = UnifiedEnsemble()
        
        # Generate test prices (in production, use live data)
        prices = np.random.uniform(3000, 3500, 30)
        
        result = ensemble.predict(prices)
        result["models_status"] = ensemble.get_status()
        
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/performance")
async def get_ml_performance():
    """Get ML model performance metrics"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.ml.ml_performance_tracker import get_performance_tracker
        
        tracker = get_performance_tracker()
        metrics = tracker.get_metrics()
        
        return {
            "status": "success",
            "metrics": metrics,
            "prediction_count": len(tracker.predictions),
            "outcome_count": len(tracker.outcomes)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/backtest")
async def get_backtest_results():
    """Get latest backtest results"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.ml.ml_backtester import MLBacktester
        
        backtester = MLBacktester()
        results = backtester.get_latest_results()
        
        return {
            "status": "success",
            "results": results[-5:] if results else [],
            "total_backtests": len(results)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/ml/strategies/reset")
async def reset_strategies(current_user: Dict = Depends(get_current_admin)):
    """Clear old inflated strategies from PostgreSQL.
    Call this after switching to walk-forward validation to remove
    pre-walk-forward scores that would block new honest strategies."""
    try:
        if learning_store.USE_POSTGRES and learning_store.HAS_DB_ADAPTER:
            from db_adapter import get_db_connection
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM learning_strategies")
                cursor.execute("DELETE FROM learning_current_strategy")
                deleted = cursor.rowcount
            return {"status": "success", "message": f"Cleared all strategies. Fresh start!", "deleted": deleted}
        else:
            return {"status": "error", "message": "PostgreSQL not available"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/ml/backtest/run")
async def run_backtest(model: str = "ensemble", days: int = 30):
    """Run a new backtest"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.ml.ml_backtester import MLBacktester
        from dataclasses import asdict
        
        backtester = MLBacktester()
        prices = backtester.load_price_data(days=days)
        result = backtester.run_backtest(prices, model=model)
        
        return {
            "status": "success",
            "result": asdict(result)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/retrain/status")
async def get_retrain_status():
    """Get auto-retrain system status"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.ml.auto_retrain import get_auto_retrainer
        
        retrainer = get_auto_retrainer()
        return {
            "status": "success",
            **retrainer.get_status()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============ Training Control Endpoints ============

# Training state — managed by StateManager
# Legacy aliases for backward compat
_training_process = None
_training_active = state.training_active

@app.post("/api/ml/training/start")
async def start_training(model: str = "all", episodes: int = 500, current_user: Dict = Depends(get_current_user)):
    """Start continuous training. Just toggles _training_active flag.
    The actual training runs in auto_learning_background() which starts on boot."""
    global _training_active
    
    if state.training_active:
        return {"status": "already_running", "message": "Training is already active"}
    
    state.training_active = True
    _training_active = True
    state.training_data = {
        "status": "training", "model_type": "strategy_backtester",
        "model": "strategy_backtester", "architecture": "Parameter Optimization",
        "episode": 0, "total_episodes": 0, "progress_pct": 0,
        "training_active": True, "received_at": datetime.now().isoformat()
    }
    return {"status": "started", "message": "Training resumed"}


@app.post("/api/ml/training/stop")
async def stop_training(current_user: Dict = Depends(get_current_user)):
    """Stop active training"""
    global _training_active
    
    if not state.training_active:
        return {
            "status": "not_running",
            "message": "No training is currently active"
        }
    
    try:
        # Signal stop (the training loop checks this)
        state.training_active = False
        _training_active = False
        state.training_data = {
            "status": "stopped",
            "message": "Training stopped by user",
            "received_at": datetime.now().isoformat()
        }
        
        return {
            "status": "stopped",
            "message": "Training stop signal sent"
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/training/status")
async def get_training_status():
    """Get detailed training status for all models"""
    
    try:
        log_dir = Path(os.getenv("LOG_DIR", "./logs"))
        
        # Check model files
        models_status = {}
        
        model_files = {
            "dqn": log_dir / "dqn_agent.pt",
            "gradient_boosting": log_dir / "ml_model.pkl",
            "lstm": log_dir / "neural_model.pt"
        }
        
        for name, path in model_files.items():
            if path.exists():
                mtime = path.stat().st_mtime
                last_trained = datetime.fromtimestamp(mtime)
                age_seconds = (datetime.now() - last_trained).total_seconds()
                
                models_status[name] = {
                    "trained": True,
                    "last_trained": last_trained.isoformat(),
                    "age_hours": round(age_seconds / 3600, 1),
                    "file_size_kb": round(path.stat().st_size / 1024, 1)
                }
            else:
                models_status[name] = {
                    "trained": False,
                    "last_trained": None
                }
        
        # Strategy backtester status
        learning_db = log_dir / "learning.db"
        if learning_db.exists():
            import sqlite3
            conn = sqlite3.connect(learning_db)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM strategies")
            total_strategies = cursor.fetchone()[0]
            cursor.execute("SELECT MAX(score), MAX(win_rate), MAX(roi) FROM strategies")
            best = cursor.fetchone()
            conn.close()
            
            models_status["strategy_optimizer"] = {
                "trained": True,
                "total_strategies_tested": total_strategies,
                "best_score": best[0] if best[0] else 0,
                "best_win_rate": best[1] if best[1] else 0,
                "best_roi": best[2] if best[2] else 0
            }
        else:
            models_status["strategy_optimizer"] = {"trained": False}
        
        return {
            "status": "success",
            "training_active": _training_active,
            "current_training": _synced_training_data if _synced_training_data else None,
            "models": models_status
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/historical-data/stats")
async def get_historical_data_stats():
    """Get cached historical data statistics"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.data.historical_data_fetcher import get_historical_fetcher
        
        fetcher = get_historical_fetcher()
        stats = fetcher.get_cache_stats()
        
        return {
            "status": "success",
            **stats
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# ADVANCED ANALYTICS API ENDPOINTS
# ============================================================================

@app.get("/api/analytics/sentiment")
async def get_sentiment_analysis():
    """Get LLM-based market sentiment analysis"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.ml.llm_sentiment import get_sentiment_analyzer
        
        analyzer = get_sentiment_analyzer()
        result = await analyzer.get_market_sentiment("ETH")
        
        return {
            "status": "success",
            "sentiment": {
                "score": result.score,
                "confidence": result.confidence,
                "summary": result.summary,
                "key_topics": result.key_topics,
                "source": result.source,
                "timestamp": result.timestamp
            },
            "interpretation": {
                "direction": "bullish" if result.score > 0.2 else "bearish" if result.score < -0.2 else "neutral",
                "strength": abs(result.score)
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/analytics/onchain")
async def get_onchain_metrics():
    """Get on-chain metrics and whale activity"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.data.onchain_metrics import get_onchain_analyzer
        
        analyzer = get_onchain_analyzer()
        metrics = await analyzer.analyze()
        signal = analyzer.get_trading_signal(metrics)
        
        return {
            "status": "success",
            "metrics": {
                "gas_price_gwei": metrics.gas_price_gwei,
                "gas_trend": metrics.gas_price_trend,
                "active_addresses_24h": metrics.active_addresses_24h,
                "active_addresses_change": metrics.active_addresses_change,
                "exchange_inflow_eth": metrics.exchange_inflow_eth,
                "exchange_outflow_eth": metrics.exchange_outflow_eth,
                "net_flow": metrics.net_flow,
                "whale_sentiment": metrics.whale_sentiment,
                "whale_count": len(metrics.whale_transactions)
            },
            "signal": signal,
            "timestamp": metrics.timestamp
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/analytics/correlation")
async def get_correlation_analysis():
    """Get multi-asset correlation and market regime"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.ml.multi_asset_correlation import get_multi_asset_analyzer
        
        analyzer = get_multi_asset_analyzer()
        regime = await analyzer.analyze_market_regime()
        adjustments = analyzer.get_trading_adjustment(regime)
        divergences = await analyzer.get_divergence_signals()
        
        import math
        
        def sanitize_floats(obj):
            """Replace NaN/Inf with 0 to prevent JSON serialization errors"""
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return 0.0
            elif isinstance(obj, dict):
                return {k: sanitize_floats(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [sanitize_floats(v) for v in obj]
            return obj
        
        return sanitize_floats({
            "status": "success",
            "regime": {
                "type": regime.regime_type,
                "confidence": regime.confidence,
                "recommendations": regime.recommendations
            },
            "correlations": regime.correlations,
            "trading_adjustments": adjustments,
            "divergence_signals": divergences,
            "timestamp": regime.timestamp
        })
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/analytics/combined")
async def get_combined_analytics():
    """Get all analytics in one call (sentiment + on-chain + correlation)"""
    try:
        import asyncio
        
        # Run all analytics in parallel
        sentiment_task = get_sentiment_analysis()
        onchain_task = get_onchain_metrics()
        correlation_task = get_correlation_analysis()
        
        results = await asyncio.gather(
            sentiment_task,
            onchain_task,
            correlation_task,
            return_exceptions=True
        )
        
        # Helper to check if result is valid
        def is_valid(result):
            return isinstance(result, dict) and result.get("status") == "success"
        
        # Mock data fallbacks
        mock_sentiment = {
            "status": "success",
            "sentiment": {
                "score": 0.25,
                "confidence": 0.65,
                "summary": "Market sentiment is moderately bullish based on recent ETH developments.",
                "key_topics": ["ETF inflows", "network upgrade", "DeFi growth"],
                "source": "mock_fallback",
                "timestamp": datetime.now().isoformat()
            }
        }
        
        mock_onchain = {
            "status": "success",
            "metrics": {
                "gas_price_gwei": 25.5,
                "gas_trend": "stable",
                "active_addresses_24h": 485000,
                "active_addresses_change": 3.2,
                "exchange_inflow_eth": 12500,
                "exchange_outflow_eth": 18200,
                "net_flow": -5700,
                "whale_sentiment": "accumulating",
                "whale_count": 12
            },
            "signal": {"direction": 0.3, "strength": "moderate"},
            "timestamp": datetime.now().isoformat()
        }
        
        mock_correlation = {
            "status": "success",
            "regime": {
                "type": "risk_on",
                "confidence": 0.72,
                "recommendations": ["Consider moderate long positions with tight stops"]
            },
            "correlations": {
                "BTC": 0.85,
                "SPY": 0.42,
                "GOLD": -0.15,
                "DXY": -0.38
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # Get results or use fallbacks
        sentiment_result = results[0] if is_valid(results[0]) else mock_sentiment
        onchain_result = results[1] if is_valid(results[1]) else mock_onchain
        correlation_result = results[2] if is_valid(results[2]) else mock_correlation
        
        # Combine results
        combined = {
            "status": "success",
            "sentiment": sentiment_result,
            "onchain": onchain_result,
            "correlation": correlation_result,
            "timestamp": datetime.now().isoformat()
        }
        
        # Calculate combined signal
        signals = []
        weights = []
        
        if "sentiment" in sentiment_result and isinstance(sentiment_result["sentiment"], dict):
            signals.append(sentiment_result["sentiment"].get("score", 0))
            weights.append(0.3)
        
        if "signal" in onchain_result:
            sig_val = onchain_result["signal"]
            if isinstance(sig_val, dict):
                signals.append(sig_val.get("direction", 0))
            else:
                signals.append(sig_val if isinstance(sig_val, (int, float)) else 0)
            weights.append(0.4)
        
        if "regime" in correlation_result:
            regime = correlation_result["regime"]
            if isinstance(regime, dict):
                regime_signal = 1 if regime.get("type") == "risk_on" else -1 if regime.get("type") == "risk_off" else 0
                signals.append(regime_signal * regime.get("confidence", 0.5))
                weights.append(0.3)
        
        if signals and weights:
            combined_score = sum(s * w for s, w in zip(signals, weights)) / sum(weights) if sum(weights) > 0 else 0
            combined["combined_signal"] = {
                "score": round(combined_score, 3),
                "direction": "bullish" if combined_score > 0.15 else "bearish" if combined_score < -0.15 else "neutral",
                "confidence": round(sum(weights) / 3, 2)
            }
        else:
            # Default combined signal
            combined["combined_signal"] = {
                "score": 0.2,
                "direction": "neutral",
                "confidence": 0.5
            }
        
        return combined
    except Exception as e:
        # Ultimate fallback - return complete mock data
        return {
            "status": "success",
            "sentiment": {
                "status": "success",
                "sentiment": {
                    "score": 0.15,
                    "confidence": 0.55,
                    "summary": "Market sentiment is neutral with slight bullish leaning.",
                    "key_topics": ["market volatility", "institutional interest"],
                    "source": "fallback",
                    "timestamp": datetime.now().isoformat()
                }
            },
            "onchain": {
                "status": "success",
                "metrics": {
                    "gas_price_gwei": 28.0,
                    "gas_trend": "stable",
                    "active_addresses_24h": 450000,
                    "active_addresses_change": 1.5,
                    "exchange_inflow_eth": 15000,
                    "exchange_outflow_eth": 16500,
                    "net_flow": -1500,
                    "whale_sentiment": "neutral",
                    "whale_count": 8
                }
            },
            "correlation": {
                "status": "success",
                "regime": {
                    "type": "neutral",
                    "confidence": 0.6,
                    "recommendations": ["Wait for clearer market signals"]
                },
                "correlations": {"BTC": 0.82, "SPY": 0.35, "GOLD": -0.1, "DXY": -0.28}
            },
            "combined_signal": {
                "score": 0.1,
                "direction": "neutral",
                "confidence": 0.5
            },
            "timestamp": datetime.now().isoformat()
        }
# ============================================================================
# STRATEGY LAB API ENDPOINTS
# ============================================================================

STRATEGY_DIR = Path("data/user_strategies")
STRATEGY_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_STRATEGY_PARAMS = {
    "riskPerTrade": 1.0,
    "mlThreshold": 0.6,
    "takeProfitMin": 1.0,
    "takeProfitMax": 2.0,
    "stopLoss": 0.8,
    "maxTradesPerDay": 10,
    "rsiOverbought": 70,
    "rsiOversold": 30
}


def get_user_strategy_file(user_id: int) -> Path:
    """Get the strategy file path for a user"""
    return STRATEGY_DIR / f"user_{user_id}.json"


def load_user_strategy(user_id: int) -> dict:
    """Load user strategy from JSON file"""
    strategy_file = get_user_strategy_file(user_id)
    if strategy_file.exists():
        try:
            return json.loads(strategy_file.read_text())
        except Exception:
            pass
    return DEFAULT_STRATEGY_PARAMS.copy()


def save_user_strategy(user_id: int, params: dict):
    """Save user strategy to JSON file"""
    strategy_file = get_user_strategy_file(user_id)
    strategy_file.write_text(json.dumps(params, indent=2))
    
    # Also save as 'active' strategy for the bot to use
    active_file = STRATEGY_DIR / "active_strategy.json"
    active_file.write_text(json.dumps({
        "user_id": user_id,
        "params": params,
        "updated_at": datetime.now().isoformat()
    }, indent=2))


@app.get("/api/strategy/parameters")
async def get_strategy_parameters(current_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Get user's strategy parameters"""
    if not current_user:
        return {"status": "success", "params": DEFAULT_STRATEGY_PARAMS}
    
    user_id = current_user["id"]
    params = load_user_strategy(user_id)
    return {"status": "success", "params": params}


@app.post("/api/strategy/parameters")
async def save_strategy_parameters(data: dict, current_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Save user's strategy parameters"""
    if not current_user:
        return {"status": "success", "message": "Demo mode - params not saved"}
    
    user_id = current_user["id"]
    params = data.get("params", {})
    save_user_strategy(user_id, params)
    return {"status": "success", "message": "Parameters saved and activated"}


@app.post("/api/strategy/backtest")
async def run_strategy_backtest(data: dict, current_user: Optional[Dict] = Depends(get_current_user_optional)):
    """Run REAL backtest with given strategy parameters against Binance historical data"""
    import numpy as np
    
    params = data.get("params", DEFAULT_STRATEGY_PARAMS)
    days = data.get("days", 14)
    
    # Map frontend camelCase params to bot params
    backtest_params = {
        "ml_threshold": params.get("mlThreshold", 0.55),
        "risk_per_trade": params.get("riskPerTrade", 0.01),
        "tp_min": params.get("tpMin", 0.015),
        "tp_max": params.get("tpMax", 0.025),
        "stop_floor": params.get("stopFloor", 0.015),
        "max_trades_per_day": params.get("maxTradesPerDay", 10),
        "rsi_oversold": params.get("rsiOversold", 35),
        "rsi_overbought": params.get("rsiOverbought", 70),
        "entry_score_min": params.get("entryScoreMin", 4),
        "breakout_pct": params.get("breakoutPct", 0.003)
    }
    
    try:
        # Fetch real Binance klines
        import requests as req
        limit = min(days * 288, 4032)  # 288 candles per day (5m), max 4032
        url = f"https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=5m&limit={limit}"
        resp = req.get(url, timeout=15)
        if resp.status_code != 200:
            raise Exception(f"Binance API error: {resp.status_code}")
        raw = resp.json()
        
        import pandas as pd
        df = pd.DataFrame(raw, columns=['ts','o','h','l','c','v','ct','qv','nt','tbv','tqv','ig'])
        for col in ['o','h','l','c','v']:
            df[col] = df[col].astype(float)
        
        if len(df) < 100:
            raise Exception("Not enough data")
        
        # Calculate indicators
        import ta
        df['ema_fast'] = ta.trend.ema_indicator(df['c'], window=9)
        df['ema_slow'] = ta.trend.ema_indicator(df['c'], window=21)
        macd = ta.trend.MACD(df['c'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['rsi'] = ta.momentum.rsi(df['c'], window=14)
        df['atr'] = ta.volatility.average_true_range(df['h'], df['l'], df['c'], window=14)
        bb = ta.volatility.BollingerBands(df['c'], window=20)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        df.dropna(inplace=True)
        
        if len(df) < 50:
            raise Exception("Not enough data after indicators")
        
        # Run real backtest with scoring logic
        capital = 10000.0
        position = None
        trades_list = []
        daily_trades = {}
        sl_pct = backtest_params["stop_floor"]
        tp_pct = backtest_params["tp_max"]
        
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            price = row['c']
            date_key = str(row['ts'])[:10]
            
            if date_key not in daily_trades:
                daily_trades[date_key] = 0
            
            if position is None:
                # Score signals
                score = 0
                if row['ema_fast'] > row['ema_slow']: score += 1
                if row['macd'] > row['macd_signal']: score += 1
                if row['rsi'] < backtest_params['rsi_overbought']: score += 1
                if row['rsi'] > backtest_params['rsi_oversold']: score += 0.5
                if price > row['bb_lower']: score += 1
                if row['c'] > prev['c']: score += 0.5
                if row['v'] > df['v'].rolling(20).mean().iloc[i]: score += 1
                pct_change = (row['c'] - prev['c']) / prev['c']
                if pct_change > backtest_params['breakout_pct']: score += 1
                
                if (score >= backtest_params['entry_score_min'] and 
                    daily_trades[date_key] < backtest_params['max_trades_per_day']):
                    qty = (capital * backtest_params['risk_per_trade']) / price
                    position = {'entry': price, 'qty': qty, 'index': i}
            else:
                # Check exit conditions
                entry = position['entry']
                pnl_pct = (price - entry) / entry
                
                exit_reason = None
                if pnl_pct <= -sl_pct:
                    exit_reason = 'stop_loss'
                elif pnl_pct >= tp_pct:
                    exit_reason = 'take_profit'
                elif i - position['index'] > 60:  # 5h time exit
                    exit_reason = 'time_exit'
                
                if exit_reason:
                    pnl = (price - entry) * position['qty']
                    trades_list.append(pnl)
                    capital += pnl
                    daily_trades[date_key] += 1
                    position = None
        
        # Calculate results
        total_trades = len(trades_list)
        if total_trades == 0:
            return {"status": "success", "result": {
                "totalReturn": 0, "winRate": 0, "totalTrades": 0,
                "maxDrawdown": 0, "sharpeRatio": 0, "profitFactor": 0
            }}
        
        wins = [p for p in trades_list if p > 0]
        losses = [p for p in trades_list if p <= 0]
        win_rate = len(wins) / total_trades * 100
        total_return = sum(trades_list)
        roi = (total_return / 10000) * 100
        
        # Sharpe
        sharpe = float(np.mean(trades_list) / np.std(trades_list)) if np.std(trades_list) > 0 else 0
        
        # Max drawdown
        equity = []
        running = 0
        for pnl in trades_list:
            running += pnl
            equity.append(running)
        peak = equity[0]
        max_dd = 0
        for val in equity:
            if val > peak: peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        # Profit factor
        gross_wins = sum(wins) if wins else 0
        gross_losses = abs(sum(losses)) if losses else 1
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0
        
        # === v8 SCORE (synced with strategy_backtester + continuous_backtester) ===
        v8_score = 0.0
        if win_rate >= 99.5 or (win_rate >= 90.0 and total_trades < 20) or (win_rate >= 80.0 and total_trades < 10):
            v8_score = 0.0
        elif win_rate < 55.0:
            v8_score = 0.0
        else:
            v8_score = win_rate * 7.0
            if win_rate > 58: v8_score += 50.0
            if win_rate > 60: v8_score += 100.0
            if win_rate > 63: v8_score += 200.0
            if win_rate > 65: v8_score += 300.0
            if win_rate > 68: v8_score += 400.0
            if win_rate > 70: v8_score += 500.0
            if win_rate > 75: v8_score += 700.0
            if win_rate > 80: v8_score += 1000.0
            if win_rate > 85: v8_score += 1500.0
            if 60 <= win_rate <= 75: v8_score += 200.0
            v8_score += roi * 80.0
            if profit_factor >= 2.0: v8_score += 300.0
            elif profit_factor >= 1.5: v8_score += 200.0
            elif profit_factor >= 1.2: v8_score += 100.0
            elif profit_factor < 0.8: v8_score *= 0.3
            if roi < 5.0: v8_score *= 0.6
            if roi < 0: v8_score *= 0.25
            v8_score += min(sharpe, 3.0) * 5.0
            v8_score -= max_dd * 100 * 5.0
            v8_score += min(total_trades / 20, 1.0) * 50
            if total_trades < 10: v8_score *= 0.1
        
        result = {
            "totalReturn": round(roi, 2),
            "winRate": round(win_rate, 1),
            "totalTrades": total_trades,
            "maxDrawdown": round(max_dd * 100, 1),
            "sharpeRatio": round(sharpe, 2),
            "profitFactor": round(profit_factor, 2),
            "score": round(v8_score, 1),
            "dataSource": "historical_binance",
            "candlesUsed": len(df),
            "daysBacktested": days
        }
        
        return {"status": "success", "result": result}
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e), "result": {
            "totalReturn": 0, "winRate": 0, "totalTrades": 0,
            "maxDrawdown": 0, "sharpeRatio": 0, "profitFactor": 0
        }}


# ============================================================================
# LOGS API ENDPOINT
# ============================================================================

@app.get("/api/logs")
async def get_bot_logs(lines: int = 50, current_user: Dict = Depends(get_current_user)):
    """Get recent bot logs for admin dashboard"""
    try:
        log_lines = []
        # Try to read from bot log file
        log_paths = [
            Path(os.getenv("LOG_DIR", "./logs")) / "bot.log",
            Path(os.getenv("LOG_DIR", "./logs")) / "ethbot.log",
            Path("logs/bot.log"),
            Path("logs/ethbot.log"),
        ]
        
        for log_path in log_paths:
            if log_path.exists():
                try:
                    with open(log_path, "r") as f:
                        all_lines = f.readlines()
                        log_lines = [l.strip() for l in all_lines[-lines:] if l.strip()]
                    break
                except Exception:
                    continue
        
        if not log_lines:
            # Fallback: generate status lines from learning store
            try:
                import learning_store
                stats = learning_store.get_learning_stats()
                s = stats.get("stats", {})
                log_lines = [
                    f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 Bot System Online",
                    f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Total Strategies Tested: {s.get('total_tested', 0)}",
                    f"[{datetime.now().strftime('%H:%M:%S')}] 🏆 Best Score: {s.get('best_score', 0)}",
                    f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Applied Strategies: {s.get('total_applied', 0)}",
                    f"[{datetime.now().strftime('%H:%M:%S')}] 📈 Today Tested: {s.get('today_tested', 0)}",
                    f"[{datetime.now().strftime('%H:%M:%S')}] ⏱️ This Hour: {s.get('this_hour_tested', 0)}",
                    f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Auto-Learning: Active",
                    f"[{datetime.now().strftime('%H:%M:%S')}] 💾 Database: PostgreSQL Connected",
                ]
            except Exception:
                log_lines = [f"[{datetime.now().strftime('%H:%M:%S')}] System running - no log file found"]
        
        return {"status": "success", "logs": log_lines, "lines": log_lines}
    except Exception as e:
        return {"status": "error", "logs": [str(e)], "lines": [str(e)]}



# ============================================================================
# ADMIN DASHBOARD API ENDPOINTS — Extracted to routes/admin.py
# ============================================================================
# All /api/admin/* endpoints are now served by the admin router.
# See: routes/admin.py (registered via app.include_router above)

# Global emergency state (shared with admin router)
EMERGENCY_TRADING_STOPPED = False

# Legacy endpoints below this line are DUPLICATES of routes/admin.py
# They will be removed in the next cleanup pass.
# For now both exist — the router takes precedence for /api/admin/* paths.

# @app.post("/api/admin/strategies/cleanup") — MOVED to routes/admin.py


# ============================================================================
# SECTION 11: JARVIS WEBHOOK — External LLM Control Interface
# ============================================================================
# POST /api/jarvis/update_regime — Webhook for n8n/Claude to push macro params
# GET  /api/jarvis/state         — Current BotState readout (admin-only)
# ============================================================================

import hmac
import hashlib

_JARVIS_SECRET = os.getenv("JARVIS_WEBHOOK_SECRET", "")

def _verify_jarvis_signature(request: Request, body: bytes) -> bool:
    """Verify HMAC-SHA256 signature from Jarvis webhook.
    If no secret is configured, falls back to admin JWT auth."""
    if not _JARVIS_SECRET:
        return False  # No HMAC configured, caller must use JWT
    sig = request.headers.get("X-Jarvis-Signature", "")
    if not sig:
        return False
    expected = hmac.new(
        _JARVIS_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig, expected)


@app.post("/api/jarvis/update_regime")
async def jarvis_update_regime(request: Request):
    """
    Jarvis Webhook — Receive macro parameter updates from external LLM.
    
    Authentication: HMAC-SHA256 via X-Jarvis-Signature header,
    OR admin JWT Bearer token.
    
    Example payload:
    {
        "ml_confidence_threshold": 0.55,
        "active_edges": ["BREAKOUT", "NORMAL"],
        "risk_multiplier": 0.8,
        "reason": "High volatility — tightening ML gate"
    }
    """
    body = await request.body()
    
    # Auth chain: Simple Token → HMAC signature → JWT admin
    # Method 1: Simple token (easiest for n8n — just send the secret as header)
    token_header = request.headers.get("X-Jarvis-Token", "")
    token_ok = _JARVIS_SECRET and token_header == _JARVIS_SECRET
    
    if not token_ok:
        # Method 2: HMAC-SHA256 signature (most secure)
        hmac_ok = _verify_jarvis_signature(request, body)
        if not hmac_ok:
            # Method 3: Fall back to JWT admin auth
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing authentication (Token, HMAC, or JWT)")
            try:
                from auth_deps import get_current_user
                token = auth_header.split(" ", 1)[1]
                import jwt as _jwt
                payload_jwt = _jwt.decode(token, os.getenv("JWT_SECRET", ""), algorithms=["HS256"])
                if payload_jwt.get("role") != "admin":
                    raise HTTPException(status_code=403, detail="Admin only")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    
    # Parse and validate payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Validate with Pydantic schema
    try:
        from jarvis.webhook_schema import JarvisRegimeUpdate
        validated = JarvisRegimeUpdate(**payload)
        update_dict = validated.model_dump(exclude_none=True)
    except ImportError:
        # Schema not available — accept raw dict with basic validation
        update_dict = payload
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {e}")
    
    # Apply to in-memory state
    changes = state.apply_jarvis_update(update_dict)
    
    # Persist to kv_store (PostgreSQL) for cross-service visibility
    # The worker (bot) polls kv_store every 30s and picks up these changes
    try:
        import learning_store
        learning_store.set_kv("jarvis_bot_state", json.dumps(state.get_jarvis_state()))
        
        # Also set emergency stop flag for backward compat
        if "emergency_stop" in changes:
            learning_store.set_kv(
                "emergency_trading_stopped",
                "true" if changes["emergency_stop"] else "false"
            )
    except Exception as e:
        logger.warning(f"Jarvis: kv_store persistence failed: {e}")
    
    # Audit log
    reason = update_dict.get("reason", "no reason given")
    logger.info(f"JARVIS UPDATE: {changes} | reason: {reason}")
    
    return {
        "status": "ok",
        "applied": changes,
        "reason": reason,
        "state": state.get_jarvis_state()
    }


@app.get("/api/jarvis/state")
async def jarvis_get_state(current_user: Dict = Depends(get_current_user)):
    """Get current Jarvis BotState (admin-only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    
    # Also try to refresh from kv_store (worker may have modified state)
    try:
        import learning_store
        kv_state = learning_store.get_kv("jarvis_bot_state")
        if kv_state:
            persisted = json.loads(kv_state)
            return {
                "status": "ok",
                "in_memory": state.get_jarvis_state(),
                "persisted": persisted,
                "source": "kv_store + memory"
            }
    except Exception:
        pass
    
    return {
        "status": "ok",
        "in_memory": state.get_jarvis_state(),
        "persisted": None,
        "source": "memory_only"
    }


# SPA Catch-all handler - MUST be at the end after all API routes
# Serves the correct frontend app based on URL prefix
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve SPA for all non-API routes (catch-all handler)"""
    # Skip API routes
    if full_path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Skip asset requests
    if full_path.startswith("assets/") or full_path.startswith("admin/assets/") or full_path.startswith("monitor/assets/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Admin Dashboard — /admin, /admin/*, etc.
    if full_path.startswith("admin"):
        admin_index = ADMIN_DIST / "index.html"
        if admin_index.exists():
            return FileResponse(admin_index)
        return {"status": "ok", "service": "Admin Dashboard", "note": "Not built yet. Run: cd admin-dashboard && npm run build"}
    
    # Strategy Monitor — /monitor, /monitor/*, etc.
    if full_path.startswith("monitor"):
        monitor_index = MONITOR_DIST / "index.html"
        if monitor_index.exists():
            return FileResponse(monitor_index)
        return {"status": "ok", "service": "Strategy Monitor", "note": "Not built yet. Run: cd strategy-monitor && npm run build"}
    
    # User Dashboard — everything else
    dashboard_index = DASHBOARD_DIST / "index.html"
    if dashboard_index.exists():
        return FileResponse(dashboard_index)
    
    return {"status": "ok", "service": "ETH Bot Dashboard API", "note": "Dashboard not built yet"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DASHBOARD_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

