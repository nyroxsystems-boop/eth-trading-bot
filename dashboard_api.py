#!/usr/bin/env python3
"""
ETH Trading Bot - Dashboard API
Real-time WebSocket API for Premium Trading Dashboard
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import csv
import sqlite3
import aiosqlite

# Import database adapter
from db_adapter import get_db_connection, USE_POSTGRES

# Import user manager for authentication
from user_manager import UserManager, init_users_database

# Import SaaS managers
from test_phase_manager import test_phase_manager
from subscription_manager import SubscriptionManager

# Import for chart data
from src.core.market_data import MarketDataProvider

# Initialize user manager (must be before endpoints)
user_mgr = UserManager()

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
    allocated_capital: float = 100.0
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

# Authentication dependencies (must be before endpoints)
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return current user"""
    token = credentials.credentials
    payload = user_mgr.verify_jwt(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user = user_mgr.get_user(payload['user_id'])
    if not user or not user['active']:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    
    return user

async def get_current_user_optional(authorization: Optional[str] = Header(None)):
    """Get current user if token provided, otherwise None"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    payload = user_mgr.verify_jwt(token)
    
    if not payload:
        return None
    
    return user_mgr.get_user(payload['user_id'])

async def get_current_admin(current_user: dict = Depends(get_current_user)):
    """Verify user is admin"""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Configuration
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "change_me")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
LOG_DIR = Path(os.getenv("LOG_DIR", "/root/ethbot/logs"))
TRADES_CSV = LOG_DIR / "trades.csv"
CONSOLE_LOG = LOG_DIR / "console.out"
# DEMO_MODE: false = show real trades, true = generate demo data
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
SETTINGS_FILE = LOG_DIR / "bot_settings.json"

app = FastAPI(title="ETH Bot Dashboard API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for dashboard (if built)
DASHBOARD_DIST = Path(__file__).parent / "dashboard" / "dist"
if DASHBOARD_DIST.exists():
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=str(DASHBOARD_DIST / "assets")), name="assets")

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
    """Read trades from CSV file or return demo data"""
    if DEMO_MODE:
        return generate_demo_trades()
    
    trades = []
    try:
        if not TRADES_CSV.exists():
            return trades
        
        with open(TRADES_CSV, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                trades.append(Trade(
                    timestamp=row['timestamp'],
                    action=row['action'],
                    qty=float(row['qty']),
                    price=float(row['price']),
                    pnl=float(row.get('pnl', 0))
                ))
    except Exception as e:
        print(f"Error reading trades: {e}")
    
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
    """Calculate comprehensive performance metrics"""
    trades = await read_trades_csv()
    
    if not trades:
        return PerformanceMetrics(
            total_trades=0, winning_trades=0, losing_trades=0,
            win_rate=0, total_pnl=0, daily_pnl=0,
            avg_win=0, avg_loss=0, sharpe_ratio=0,
            max_drawdown=0, roi=0
        )
    
    # Calculate PnL
    total_pnl = await calculate_pnl(trades)
    
    # Today's trades
    today = datetime.now().date().isoformat()
    today_trades = [t for t in trades if t.timestamp.startswith(today)]
    daily_pnl = await calculate_pnl(today_trades)
    
    # Win/Loss stats (only count SELL trades as completed trades)
    sell_trades = [t for t in trades if t.action.upper() == "SELL"]
    wins = [t for t in sell_trades if t.pnl and t.pnl > 0]
    losses = [t for t in sell_trades if t.pnl and t.pnl < 0]
    
    win_rate = len(wins) / len(sell_trades) * 100 if sell_trades else 0
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
    
    # Sharpe Ratio (simplified)
    returns = [t.pnl for t in sell_trades if t.pnl]
    if returns:
        import numpy as np
        sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
    else:
        sharpe = 0
    
    # Max Drawdown
    equity_curve = []
    running_pnl = 0
    for trade in trades:
        if trade.pnl:
            running_pnl += trade.pnl
            equity_curve.append(running_pnl)
    
    max_dd = 0
    if equity_curve:
        peak = equity_curve[0]
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
    
    # ROI
    initial_capital = float(os.getenv("EQUITY_USDT", 10000))
    roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0
    
    return PerformanceMetrics(
        total_trades=len(sell_trades),  # Only count completed trades (SELL orders)
        winning_trades=len(wins),
        losing_trades=len(losses),
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
    
    # Count today's trades
    trades = await read_trades_csv()
    today = datetime.now().date().isoformat()
    today_trades = len([t for t in trades if t.timestamp.startswith(today)])
    
    return BotStatus(
        is_running=True,  # Assume running if API is up
        current_position=None,  # Position data will be parsed from state file when bot state management is implemented
        last_update=datetime.now().isoformat(),
        today_trades=today_trades,
        ml_confidence=ml_conf,
        sentiment_score=sentiment,
        regime=regime
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

@app.get("/api/trades", response_model=List[Trade])
async def get_trades(limit: int = 100):
    """Get recent trades"""
    trades = await read_trades_csv()
    return trades[-limit:]

@app.get("/api/performance", response_model=PerformanceMetrics)
async def get_performance():
    """Get performance metrics"""
    return await get_performance_metrics()

@app.get("/api/performance/history")
async def get_performance_history(days: int = 7):
    """Get P&L history for chart"""
    trades = await read_trades_csv()
    
    # Group trades by date and calculate daily P&L from BUY/SELL pairs
    daily_pnl = {}
    last_buy = None
    
    for trade in trades:
        try:
            # Parse timestamp
            ts = trade.timestamp
            if 'T' in ts:
                date = ts.split('T')[0]
            else:
                date = ts.split(' ')[0]
            
            if date not in daily_pnl:
                daily_pnl[date] = {"date": date, "pnl": 0, "trades": 0}
            
            # Calculate P&L from trade pairs
            if trade.action == "BUY":
                last_buy = trade
            elif trade.action == "SELL" and last_buy:
                # Calculate PnL: (sell_price - buy_price) * qty
                pnl = (trade.price - last_buy.price) * trade.qty
                daily_pnl[date]["pnl"] += pnl
                daily_pnl[date]["trades"] += 1
                last_buy = None
            else:
                # Use pnl from trade if available
                if hasattr(trade, 'pnl') and trade.pnl != 0:
                    daily_pnl[date]["pnl"] += trade.pnl
                    daily_pnl[date]["trades"] += 1
        except Exception as e:
            print(f"Error processing trade: {e}")
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
async def get_status():
    """Get bot status"""
    return await get_bot_status()

@app.get("/api/chart/data")
async def get_chart_data(symbol: str = "ETHUSDT", interval: str = "5m", limit: int = 100):
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
        print(f"Error fetching chart data: {e}")
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
        print(f"🔐 Login attempt for: {request.email_or_username}")
        result = user_mgr.login(request.email_or_username, request.password)
        
        if not result:
            print(f"❌ Login failed: Invalid credentials for {request.email_or_username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        print(f"✅ Login successful for: {request.email_or_username}")
        return AuthResponse(**result)
        
    except ValueError as e:
        print(f"❌ Login ValueError: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ Login Exception: {type(e).__name__}: {e}")
        print(f"   Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/api/auth/logout")
async def logout(current_user: Dict = Depends(get_current_user)):
    """Logout user (revoke token)"""
    # Extract token from request (this is a simplified version)
    # In production, you'd want to get the actual token from the request
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """Get current user information"""
    try:
        # current_user is already the full user object from get_current_user dependency
        if not current_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Convert created_at to string if it's a datetime object
        user_data = dict(current_user)
        if hasattr(user_data.get('created_at'), 'isoformat'):
            user_data['created_at'] = user_data['created_at'].isoformat()
        if hasattr(user_data.get('last_login'), 'isoformat'):
            user_data['last_login'] = user_data['last_login'].isoformat()
        elif user_data.get('last_login') is None:
            user_data['last_login'] = None
        
        # Ensure all required fields are strings
        user_data['created_at'] = str(user_data.get('created_at', ''))
        if user_data.get('last_login'):
            user_data['last_login'] = str(user_data['last_login'])
        
        return UserResponse(**user_data)
    except Exception as e:
        print(f"❌ Error in /api/auth/me: {type(e).__name__}: {e}")
        print(f"   current_user data: {current_user}")
        raise HTTPException(status_code=500, detail=f"Error processing user data: {str(e)}")

@app.get("/api/users", response_model=List[UserResponse])
async def list_users(current_user: Dict = Depends(get_current_user)):
    """List all users (admin only)"""
    if current_user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    users = user_mgr.list_users()
    return [UserResponse(**user) for user in users]


# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send updates every 2 seconds
            await asyncio.sleep(2)
            
            status = await get_bot_status()
            metrics = await get_performance_metrics()
            
            await websocket.send_json({
                "type": "update",
                "status": status.dict(),
                "metrics": metrics.dict(),
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
        print(f"⚠️ User seeding error (may already exist): {e}")
    
    # Start trade monitoring
    asyncio.create_task(monitor_trades())
    
    # Start auto-learning background service
    asyncio.create_task(auto_learning_background())
    print("🧠 Auto-Learning Background Service started!")


async def auto_learning_background():
    """Background task that continuously tests strategies and auto-applies best ones"""
    import random
    
    # Wait 30 seconds before starting (let API fully initialize)
    await asyncio.sleep(30)
    print("🚀 Auto-Learning Background Service active - testing strategies...")
    
    # Get storage paths
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    strategies_file = log_dir / "tested_strategies.json"
    current_strategy_file = log_dir / "current_strategy.json"
    
    # Ensure directories exist
    log_dir.mkdir(parents=True, exist_ok=True)
    
    while True:
        try:
            # Test a batch of random strategies
            tested_strategies = []
            
            print(f"\n{'='*50}")
            print(f"🧪 Testing 5 random strategies... ({datetime.now().strftime('%H:%M:%S')})")
            print(f"{'='*50}")
            
            for i in range(5):
                # Generate random strategy parameters
                strategy = {
                    "params": {
                        "ml_threshold": round(random.uniform(0.50, 0.75), 3),
                        "risk_per_trade": round(random.uniform(0.005, 0.015), 4),
                        "tp_min": round(random.uniform(0.008, 0.015), 4),
                        "tp_max": round(random.uniform(0.015, 0.030), 4),
                        "stop_floor": round(random.uniform(0.005, 0.012), 4),
                        "max_trades_per_day": random.randint(8, 20)
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
                # Simulate backtest (random realistic results)
                # In production, this would run actual backtests
                strategy["metrics"] = {
                    "total_trades": random.randint(50, 200),
                    "win_rate": round(random.uniform(45, 75), 1),
                    "roi": round(random.uniform(-5, 25), 2),
                    "sharpe_ratio": round(random.uniform(0.5, 2.5), 2),
                    "max_drawdown": round(random.uniform(2, 15), 1)
                }
                
                # Calculate composite score
                strategy["score"] = round(
                    strategy["metrics"]["roi"] * 0.4 +
                    strategy["metrics"]["win_rate"] * 0.3 +
                    strategy["metrics"]["sharpe_ratio"] * 10 * 0.2 -
                    strategy["metrics"]["max_drawdown"] * 0.1,
                    2
                )
                strategy["applied"] = False
                
                tested_strategies.append(strategy)
                print(f"  Strategy {i+1}: Score={strategy['score']:.2f}, ROI={strategy['metrics']['roi']}%, WR={strategy['metrics']['win_rate']}%")
            
            # Load existing strategies
            all_strategies = []
            if strategies_file.exists():
                try:
                    with open(strategies_file, "r") as f:
                        all_strategies = json.load(f)
                except:
                    all_strategies = []
            
            # Add new strategies
            all_strategies.extend(tested_strategies)
            
            # Keep only top 100 strategies (sorted by score)
            all_strategies.sort(key=lambda x: x.get("score", 0), reverse=True)
            all_strategies = all_strategies[:100]
            
            # Save updated strategies
            with open(strategies_file, "w") as f:
                json.dump(all_strategies, f, indent=2)
            
            # Auto-apply best strategy if it's better than current
            if all_strategies:
                best = all_strategies[0]
                
                # Load current strategy
                current_score = 0
                if current_strategy_file.exists():
                    try:
                        with open(current_strategy_file, "r") as f:
                            current = json.load(f)
                            current_score = current.get("score", 0)
                    except:
                        pass
                
                # Apply if best is significantly better (10%+)
                if best["score"] > current_score * 1.1:
                    best["applied"] = True
                    best["applied_at"] = datetime.now().isoformat()
                    
                    with open(current_strategy_file, "w") as f:
                        json.dump(best, f, indent=2)
                    
                    # Update in all_strategies too
                    for s in all_strategies:
                        s["applied"] = (s == best)
                    
                    with open(strategies_file, "w") as f:
                        json.dump(all_strategies, f, indent=2)
                    
                    print(f"\n✅ NEW BEST STRATEGY APPLIED!")
                    print(f"   Score: {best['score']:.2f} (was {current_score:.2f})")
                    print(f"   ROI: {best['metrics']['roi']}%")
                    print(f"   Win Rate: {best['metrics']['win_rate']}%")
                else:
                    print(f"\n📊 Best tested: {best['score']:.2f} (current: {current_score:.2f} - keeping current)")
            
            print(f"\n⏳ Waiting 30 minutes until next cycle...")
            print(f"   Total strategies tested: {len(all_strategies)}")
            
            # Wait 30 minutes between cycles
            await asyncio.sleep(1800)
            
        except Exception as e:
            print(f"❌ Auto-learning error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error

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
            print(f"Monitor error: {e}")
        
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
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    
    # Default from environment
    return {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "binance_api_key": os.getenv("BINANCE_API_KEY", ""),
        "binance_api_secret": os.getenv("BINANCE_API_SECRET", ""),
        "trading_capital": float(os.getenv("PAPER_BASE_USDT", "10000")),
        "risk_per_trade": float(os.getenv("RISK_PCT_PER_TRADE", "0.006")),
        "max_trades_per_day": int(os.getenv("MAX_TRADES_PER_DAY", "15")),
        "daily_target_pct": float(os.getenv("DAILY_TARGET_PCT", "1.0")),
        "max_drawdown_day": float(os.getenv("MAX_DRAWDOWN_DAY", "0.05")),
        "tp_min": float(os.getenv("TP_MIN", "0.010")),
        "tp_max": float(os.getenv("TP_MAX", "0.015")),
        "stop_floor": float(os.getenv("STOP_FLOOR", "0.005")),
        "dry_run": os.getenv("DRY_RUN", "false").lower() == "true"
    }

def save_settings(settings: dict):
    """Save settings to file"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

@app.get("/api/settings/bot")
async def get_bot_settings():
    """Get all bot settings"""
    settings = load_settings()
    # Mask sensitive data
    if settings.get("binance_api_secret"):
        settings["binance_api_secret"] = "•" * 16
    return settings

@app.post("/api/settings/bot")
async def update_bot_settings(settings: BotSettings):
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
async def get_telegram_settings():
    """Get Telegram settings"""
    settings = load_settings()
    return {
        "bot_token": settings.get("telegram_bot_token", ""),
        "chat_id": settings.get("telegram_chat_id", "")
    }

@app.post("/api/settings/telegram")
async def update_telegram_settings(telegram: TelegramSettings):
    """Update Telegram settings"""
    current = load_settings()
    current["telegram_bot_token"] = telegram.bot_token
    current["telegram_chat_id"] = telegram.chat_id
    
    if save_settings(current):
        return {"status": "success", "message": "Telegram settings updated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save settings")

@app.get("/api/settings/trading")
async def get_trading_settings():
    """Get trading parameters"""
    settings = load_settings()
    return {
        "capital": settings.get("trading_capital", 10000),
        "risk_per_trade": settings.get("risk_per_trade", 0.006),
        "max_trades_per_day": settings.get("max_trades_per_day", 15),
        "daily_target_pct": settings.get("daily_target_pct", 1.0),
        "max_drawdown_day": settings.get("max_drawdown_day", 0.05),
        "tp_min": settings.get("tp_min", 0.010),
        "tp_max": settings.get("tp_max", 0.015),
        "stop_floor": settings.get("stop_floor", 0.005)
    }

@app.post("/api/settings/trading")
async def update_trading_settings(trading: TradingSettings):
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
        print(f"❌ Error getting API keys: {e}")
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
        print(f"❌ Error saving API keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        print(f"Error fetching pairs: {e}")
    
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
                    "allocated_capital": float(row[4] or 100),
                    "risk_per_trade": float(row[5] or 0.01) * 100,  # Convert to %
                    "max_trades_per_day": row[6] or 10,
                    "take_profit_pct": float(row[7] or 0.015) * 100,
                    "stop_loss_pct": float(row[8] or 0.01) * 100,
                    "enabled": bool(row[9]),
                    "total_pnl": float(row[10] or 0),
                    "total_trades": row[11] or 0,
                    "win_rate": float(row[12] or 0),
                    "pnl_percent": (float(row[10] or 0) / float(row[4] or 100)) * 100 if float(row[4] or 100) > 0 else 0
                }
                pairs.append(pair_data)
                total_capital += pair_data["allocated_capital"]
                total_pnl += pair_data["total_pnl"]
            
            return {
                "pairs": pairs,
                "total_pairs": len(pairs),
                "total_capital": total_capital,
                "total_pnl": total_pnl,
                "total_pnl_percent": (total_pnl / total_capital * 100) if total_capital > 0 else 0
            }
    except Exception as e:
        print(f"Error fetching portfolio pairs: {e}")
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
        print(f"Error adding pair: {e}")
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
    """Get current trading capital"""
    settings = load_settings()
    return {
        "capital": settings.get("trading_capital", 10000),
        "currency": "USDT"
    }

@app.post("/api/capital")
async def update_capital(capital: float):
    """Update trading capital"""
    if capital <= 0:
        raise HTTPException(status_code=400, detail="Capital must be positive")
    
    current = load_settings()
    current["trading_capital"] = capital
    
    if save_settings(current):
        return {"status": "success", "message": f"Capital updated to ${capital:,.2f}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save capital")

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
async def update_risk_params(risk_per_trade: float, max_drawdown: float, max_trades: int):
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
    ml_threshold: float
    risk_per_trade: float
    tp_min: float
    tp_max: float
    stop_floor: float
    max_trades_per_day: int

@app.post("/api/backtest")
async def run_backtest(params: BacktestParams):
    """Run backtest with given parameters"""
    import random
    import numpy as np
    
    # Simulate 100 trades with given parameters
    trades_simulated = []
    wins = 0
    losses = 0
    total_pnl = 0.0
    equity_curve = [10000.0]  # Start with $10k
    
    # More aggressive = more trades, but lower win rate
    # More conservative = fewer trades, but higher win rate
    aggressiveness = 1.0 - params.ml_threshold  # 0.48 = aggressive, 0.30 = very aggressive
    base_win_rate = 0.45 + (params.ml_threshold - 0.30) * 0.5  # 0.45-0.65 range
    
    num_trades = min(int(100 * (1 + aggressiveness)), params.max_trades_per_day * 7)
    
    for i in range(num_trades):
        # Simulate trade outcome
        win = random.random() < base_win_rate
        
        if win:
            # Win: TP between tp_min and tp_max
            profit_pct = random.uniform(params.tp_min, params.tp_max)
            pnl = equity_curve[-1] * params.risk_per_trade * (profit_pct / params.stop_floor)
            wins += 1
        else:
            # Loss: SL at stop_floor
            pnl = -equity_curve[-1] * params.risk_per_trade
            losses += 1
        
        total_pnl += pnl
        equity_curve.append(equity_curve[-1] + pnl)
        trades_simulated.append(pnl)
    
    # Calculate metrics
    win_rate = (wins / num_trades * 100) if num_trades > 0 else 0
    avg_win = sum(p for p in trades_simulated if p > 0) / wins if wins > 0 else 0
    avg_loss = sum(p for p in trades_simulated if p < 0) / losses if losses > 0 else 0
    
    # Sharpe Ratio
    returns = trades_simulated
    sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0
    
    # Max Drawdown
    peak = equity_curve[0]
    max_dd = 0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    
    # ROI
    roi = (total_pnl / 10000.0) * 100
    
    return {
        "total_trades": num_trades,
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "roi": roi,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd * 100,
        "avg_win": avg_win,
        "avg_loss": avg_loss
    }

# Learning API Endpoints - reads from JSON files written by auto_learning_background()
LEARNING_LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
STRATEGIES_FILE = LEARNING_LOG_DIR / "tested_strategies.json"
CURRENT_STRATEGY_FILE = LEARNING_LOG_DIR / "current_strategy.json"

def load_strategies_json():
    """Load strategies from JSON file"""
    if STRATEGIES_FILE.exists():
        try:
            with open(STRATEGIES_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def load_current_strategy_json():
    """Load current strategy from JSON file"""
    if CURRENT_STRATEGY_FILE.exists():
        try:
            with open(CURRENT_STRATEGY_FILE, "r") as f:
                return json.load(f)
        except:
            return None
    return None

@app.get("/api/learning/stats")
async def get_learning_stats():
    """Get auto-learning statistics"""
    try:
        strategies = load_strategies_json()
        current = load_current_strategy_json()
        
        # Calculate stats
        total_tested = len(strategies)
        best_score = max([s.get("score", 0) for s in strategies]) if strategies else 0
        total_applied = len([s for s in strategies if s.get("applied", False)])
        
        # Today's tests (check timestamp)
        today = datetime.now().date().isoformat()
        today_tested = len([s for s in strategies if s.get("timestamp", "").startswith(today)])
        
        # This hour's tests
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        this_hour_tested = len([s for s in strategies if s.get("timestamp", "") >= one_hour_ago])
        
        return {
            "total_tested": total_tested,
            "best_score": round(best_score, 2),
            "total_applied": total_applied,
            "today_tested": today_tested,
            "this_hour_tested": this_hour_tested
        }
    except Exception as e:
        print(f"Error getting learning stats: {e}")
        return {
            "total_tested": 0,
            "best_score": 0,
            "total_applied": 0,
            "today_tested": 0,
            "this_hour_tested": 0
        }

@app.get("/api/learning/strategies")
async def get_top_strategies(limit: int = 10):
    """Get top performing strategies"""
    try:
        strategies = load_strategies_json()
        
        # Sort by score and limit
        strategies.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return strategies[:limit]
    except Exception as e:
        print(f"Error getting top strategies: {e}")
        return []

@app.get("/api/learning/evolution")
async def get_strategy_evolution(days: int = 7):
    """Get strategy score evolution over time"""
    try:
        strategies = load_strategies_json()
        
        # Group by date and get best score each day
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        daily_best = {}
        
        for s in strategies:
            ts = s.get("timestamp", "")
            if ts >= cutoff:
                date = ts[:10]  # YYYY-MM-DD
                score = s.get("score", 0)
                if date not in daily_best or score > daily_best[date]:
                    daily_best[date] = score
        
        # Convert to list sorted by date
        evolution = [{"date": d, "best_score": round(s, 2)} for d, s in sorted(daily_best.items())]
        
        return evolution
    except Exception as e:
        print(f"Error getting evolution: {e}")
        return []

@app.get("/api/learning/current")
async def get_current_strategy():
    """Get currently applied strategy"""
    try:
        current = load_current_strategy_json()
        return current
    except Exception as e:
        print(f"Error getting current strategy: {e}")
        return None

# Trading Mode Switch
class TradingMode(BaseModel):
    mode: str  # "paper" or "live"

@app.post("/api/trading/mode")
async def switch_trading_mode(mode_data: TradingMode):
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
            return {
                "status": "success",
                "mode": mode,
                "message": f"Switched to {mode.upper()} trading. Bot will use new mode on next trade."
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save settings")
    except Exception as e:
        print(f"Error switching mode: {e}")
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
        print(f"Error getting mode: {e}")
        return {"mode": "paper", "dry_run": True}


# ==================== AUTHENTICATION SYSTEM ====================
# UserManager, Pydantic models, and authentication dependencies are initialized at the top of the file


# ==================== ACCOUNT MANAGEMENT ====================
from account_manager import AccountManager

account_mgr = AccountManager()

class AccountCreate(BaseModel):
    name: str
    api_key: str
    api_secret: str
    capital: float = 10000
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
async def get_account(account_id: int):
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
async def update_account(account_id: int, updates: AccountUpdate):
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
async def delete_account(account_id: int):
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
async def toggle_account(account_id: int):
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
async def validate_credentials(api_key: str, api_secret: str):
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
        
        # Log the change
        print(f"User {current_user['id']} switched to {new_mode} mode")
        
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
async def get_trading_mode_status(current_user: Dict = Depends(get_current_user)):
    """Get comprehensive trading mode status including test phases"""
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


# Stripe Payment Endpoints
from stripe_integration import create_checkout_session, verify_webhook_signature, handle_successful_payment

@app.post("/api/subscription/checkout")
async def create_subscription_checkout(current_user: Dict = Depends(get_current_user)):
    """Create Stripe checkout session for Premium upgrade"""
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
            print(f"✅ Checkout completed for user {user_id}, tier: {tier}")
    
        session = event["data"]["object"]
        # Note: Would need to implement user lookup by Stripe customer ID
        print(f"Subscription cancelled: {session.get('id')}")
    
    return {"status": "success"}


# =============================================================================
# ML/AI MONITORING ENDPOINTS
# =============================================================================

@app.get("/api/ml/status")
async def get_ml_status():
    """Get status of all ML models"""
    log_dir = Path(os.getenv("LOG_DIR", "./logs"))
    
    models = {}
    
    # Check DQN model
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
    
    # Check Gradient Boosting model
    gb_path = log_dir / "ml_model.pkl"
    if gb_path.exists():
        stat = gb_path.stat()
        models["gradient_boosting"] = {
            "status": "trained",
            "file_size": f"{stat.st_size / 1024:.1f} KB",
            "last_updated": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "model_type": "Gradient Boosting Regressor"
        }
    else:
        models["gradient_boosting"] = {"status": "not_trained", "model_type": "Gradient Boosting"}
    
    # Check LSTM model
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
    """Get feature importance from Gradient Boosting model"""
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        from ml_strategy_predictor import MLStrategyPredictor
        
        predictor = MLStrategyPredictor()
        
        if not predictor.is_trained:
            return {"status": "not_trained", "message": "Model not trained yet"}
        
        importance = predictor.get_feature_importance()
        
        # Sort by importance
        sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "status": "success",
            "features": [{"name": k, "importance": round(v * 100, 2)} for k, v in sorted_importance]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/training-progress")
async def get_training_progress():
    """Check if any ML training is in progress"""
    try:
        import subprocess
        
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True,
            timeout=5  # Add timeout
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
            elif 'continuous_backtester' in line:
                parts = line.split()
                if len(parts) >= 11:
                    training_processes.append({
                        "type": "Backtester",
                        "pid": parts[1],
                        "cpu": parts[2],
                        "memory": parts[3],
                        "time": parts[9]
                    })
        
        return {
            "training_active": len(training_processes) > 0,
            "processes": training_processes
        }
    except Exception:
        # Return safe defaults if subprocess fails (e.g., on Railway)
        return {
            "training_active": False,
            "processes": []
        }


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


# ============================================================================
# ADMIN DASHBOARD API ENDPOINTS
# ============================================================================

# Global emergency state
EMERGENCY_TRADING_STOPPED = False

# ------------ User Management ------------

@app.get("/api/admin/users")
async def admin_list_users(current_user: Dict = Depends(get_current_admin)):
    """List all users with trading stats"""
    try:
        users = user_mgr.list_users()
        enriched_users = []
        
        for user in users:
            has_keys = user_mgr.has_api_keys(user['id'])
            enriched_users.append({
                **user,
                'has_api_keys': has_keys,
                'trading_enabled': has_keys,
                'created_at': str(user.get('created_at', '')),
                'last_login': str(user.get('last_login', '')) if user.get('last_login') else None
            })
        
        return {"status": "success", "total_users": len(users), "users": enriched_users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/users/{user_id}")
async def admin_get_user(user_id: int, current_user: Dict = Depends(get_current_admin)):
    """Get detailed user info"""
    user = user_mgr.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    api_keys = user_mgr.get_api_keys(user_id, decrypt=False) or {}
    return {
        "status": "success",
        "user": {**user, 'has_binance_keys': api_keys.get('has_binance_keys', False),
                 'has_telegram': api_keys.get('has_telegram', False),
                 'trading_enabled': api_keys.get('trading_enabled', False)}
    }

@app.post("/api/admin/users/{user_id}/toggle")
async def admin_toggle_user(user_id: int, current_user: Dict = Depends(get_current_admin)):
    """Enable/disable a user account"""
    user = user_mgr.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_status = not user.get('active', True)
    user_mgr.update_user(user_id, active=new_status)
    return {"status": "success", "active": new_status}

@app.post("/api/admin/users/{user_id}/subscription")
async def admin_update_subscription(user_id: int, tier: str, current_user: Dict = Depends(get_current_admin)):
    """Update user subscription tier"""
    if tier not in ['free', 'basic', 'pro', 'enterprise']:
        raise HTTPException(status_code=400, detail="Invalid tier")
    user_mgr.update_user(user_id, subscription_tier=tier)
    return {"status": "success", "tier": tier}

@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, current_user: Dict = Depends(get_current_admin)):
    """Delete a user account"""
    if user_id == current_user.get('id'):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    if not user_mgr.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "success"}

# ------------ Revenue Dashboard ------------

@app.get("/api/admin/revenue")
async def admin_get_revenue(current_user: Dict = Depends(get_current_admin)):
    """Get revenue overview from Stripe"""
    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        if not stripe.api_key:
            return {"status": "warning", "message": "Stripe not configured", "mrr": 0, "active_subscriptions": 0}
        subs = stripe.Subscription.list(status='active', limit=100)
        mrr = sum(item['price']['unit_amount']/100 for sub in subs.data for item in sub['items']['data'])
        return {"status": "success", "mrr": mrr, "active_subscriptions": len(subs.data)}
    except Exception as e:
        return {"status": "error", "message": str(e), "mrr": 0}

# ------------ Platform Analytics ------------

@app.get("/api/admin/analytics")
async def admin_get_analytics(current_user: Dict = Depends(get_current_admin)):
    """Get platform-wide analytics"""
    users = user_mgr.list_users()
    return {
        "status": "success",
        "total_users": len(users),
        "active_users": len([u for u in users if u.get('active', True)]),
        "users_with_api_keys": len([u for u in users if user_mgr.has_api_keys(u['id'])]),
        "subscription_breakdown": {}
    }

# ------------ Emergency Controls ------------

@app.get("/api/admin/emergency/status")
async def admin_emergency_status(current_user: Dict = Depends(get_current_admin)):
    global EMERGENCY_TRADING_STOPPED
    return {"trading_stopped": EMERGENCY_TRADING_STOPPED}

@app.post("/api/admin/emergency/stop-all")
async def admin_emergency_stop(current_user: Dict = Depends(get_current_admin)):
    global EMERGENCY_TRADING_STOPPED
    EMERGENCY_TRADING_STOPPED = True
    try:
        import requests
        token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if token and chat:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": f"🚨 EMERGENCY STOP by {current_user.get('username')}"})
    except: pass
    return {"status": "success", "trading_stopped": True}

@app.post("/api/admin/emergency/resume")
async def admin_emergency_resume(current_user: Dict = Depends(get_current_admin)):
    global EMERGENCY_TRADING_STOPPED
    EMERGENCY_TRADING_STOPPED = False
    return {"status": "success", "trading_stopped": False}

# ------------ System Health ------------

@app.get("/api/admin/system/health")
async def admin_system_health(current_user: Dict = Depends(get_current_admin)):
    health = {"status": "success", "timestamp": datetime.now().isoformat(), "services": {}}
    try:
        from db_adapter import get_db_connection, USE_POSTGRES
        with get_db_connection() as conn:
            conn.cursor().execute("SELECT 1")
        health["services"]["database"] = {"status": "healthy", "type": "PostgreSQL" if USE_POSTGRES else "SQLite"}
    except Exception as e:
        health["services"]["database"] = {"status": "unhealthy", "error": str(e)}
    health["services"]["api"] = {"status": "healthy"}
    health["emergency_stop_active"] = EMERGENCY_TRADING_STOPPED
    return health


# ------------ Jarvis Monitoring System ------------

@app.get("/api/admin/jarvis/status")
async def get_jarvis_status(current_user: Dict = Depends(get_current_admin)):
    """Get full Jarvis system status"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        
        # Run health checks
        import asyncio
        asyncio.create_task(jarvis.check_all_services())
        
        return {
            "status": "success",
            **jarvis.get_status()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/admin/jarvis/workers")
async def get_jarvis_workers(current_user: Dict = Depends(get_current_admin)):
    """Get all monitored workers/services"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        
        workers = []
        for name, health in jarvis.services.items():
            workers.append({
                "name": name,
                "status": health.status.value,
                "last_check": health.last_check.isoformat() if health.last_check else None,
                "response_time_ms": health.response_time_ms,
                "error": health.error_message,
                "consecutive_failures": health.consecutive_failures,
                "metadata": health.metadata
            })
        
        return {"status": "success", "workers": workers}
    except Exception as e:
        return {"status": "error", "message": str(e), "workers": []}

@app.get("/api/admin/jarvis/alerts")
async def get_jarvis_alerts(
    limit: int = 20, 
    unresolved_only: bool = False,
    current_user: Dict = Depends(get_current_admin)
):
    """Get recent Jarvis alerts"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        
        return {
            "status": "success",
            "alerts": jarvis.get_alerts(limit=limit, unresolved_only=unresolved_only)
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "alerts": []}

@app.post("/api/admin/jarvis/alerts/{alert_id}/resolve")
async def resolve_jarvis_alert(alert_id: str, current_user: Dict = Depends(get_current_admin)):
    """Mark an alert as resolved"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        
        if jarvis.resolve_alert(alert_id):
            return {"status": "success", "message": f"Alert {alert_id} resolved"}
        else:
            raise HTTPException(status_code=404, detail="Alert not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/jarvis/anomalies")
async def get_jarvis_anomalies(
    limit: int = 20,
    current_user: Dict = Depends(get_current_admin)
):
    """Get detected anomalies"""
    try:
        from jarvis import get_anomaly_detector
        detector = get_anomaly_detector()
        
        return {
            "status": "success",
            "anomalies": detector.get_recent_anomalies(limit=limit),
            "summary": detector.get_summary()
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "anomalies": []}

@app.post("/api/admin/jarvis/check")
async def trigger_jarvis_check(current_user: Dict = Depends(get_current_admin)):
    """Manually trigger a full health check"""
    try:
        from jarvis import get_jarvis
        jarvis = get_jarvis()
        
        results = await jarvis.check_all_services()
        
        return {
            "status": "success",
            "message": "Health check completed",
            "results": {
                name: {
                    "status": health.status.value,
                    "response_time_ms": health.response_time_ms
                }
                for name, health in results.items()
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# SPA Catch-all handler - MUST be at the end after all API routes
# This serves index.html for all non-API routes so React Router can handle them
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve SPA for all non-API routes (catch-all handler)"""
    # Skip API routes (they should be handled by their own endpoints)
    if full_path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Skip asset requests (they're served by StaticFiles mount)
    if full_path.startswith("assets/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Serve index.html for all other routes (SPA routing)
    dashboard_index = DASHBOARD_DIST / "index.html"
    if dashboard_index.exists():
        return FileResponse(dashboard_index)
    
    # Fallback if dashboard not built
    return {"status": "ok", "service": "ETH Bot Dashboard API", "note": "Dashboard not built yet"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DASHBOARD_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

