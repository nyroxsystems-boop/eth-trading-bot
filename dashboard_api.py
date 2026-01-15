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
import aiosqlite

# Import database adapter
from db_adapter import get_db_connection, USE_POSTGRES

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
        current_position=None,  # TODO: Parse from state
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

@app.get("/api/status", response_model=BotStatus)
async def get_status():
    """Get bot status"""
    return await get_bot_status()

@app.get("/api/chart/data")
async def get_chart_data(interval: str = "5m", limit: int = 500):
    """Get OHLCV data for charts"""
    # This would fetch from Binance or local cache
    # For now, return mock data
    return {
        "symbol": "ETHUSDT",
        "interval": interval,
        "data": []  # TODO: Implement actual data fetching
    }

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
    asyncio.create_task(monitor_trades())

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

# Learning API Endpoints
LEARNING_DB = Path(os.getenv("LOG_DIR", "/root/ethbot/logs")) / "learning.db"

@app.get("/api/learning/stats")
async def get_learning_stats():
    """Get auto-learning statistics"""
    try:
        with get_db_connection('learning') as conn:
            cursor = conn.cursor()
            
            # Total strategies tested
            cursor.execute("SELECT COUNT(*) FROM strategies")
            total_tested = cursor.fetchone()[0] or 0
            
            # Best score ever
            cursor.execute("SELECT MAX(score) FROM strategies")
            best_score = cursor.fetchone()[0] or 0
            
            # Applied strategies
            if USE_POSTGRES:
                cursor.execute("SELECT COUNT(*) FROM strategies WHERE applied = true")
            else:
                cursor.execute("SELECT COUNT(*) FROM strategies WHERE applied = 1")
            total_applied = cursor.fetchone()[0] or 0
            
            # Today's tests (PostgreSQL and SQLite have different date functions)
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT COUNT(*) FROM strategies 
                    WHERE DATE(timestamp) = CURRENT_DATE
                """)
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM strategies 
                    WHERE DATE(timestamp) = DATE('now')
                """)
            today_tested = cursor.fetchone()[0] or 0
            
            # This hour's tests
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT COUNT(*) FROM strategies 
                    WHERE timestamp >= NOW() - INTERVAL '1 hour'
                """)
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM strategies 
                    WHERE datetime(timestamp) >= datetime('now', '-1 hour')
                """)
            this_hour_tested = cursor.fetchone()[0] or 0
        
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
        with get_db_connection('learning') as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                           total_trades, win_rate, roi, sharpe_ratio, max_drawdown, score, timestamp, applied
                    FROM strategies
                    ORDER BY score DESC
                    LIMIT %s
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                           total_trades, win_rate, roi, sharpe_ratio, max_drawdown, score, timestamp, applied
                    FROM strategies
                    ORDER BY score DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
        
        strategies = []
        for row in rows:
            strategies.append({
                "params": {
                    "ml_threshold": round(row[0], 3),
                    "risk_per_trade": round(row[1], 4),
                    "tp_min": round(row[2], 3),
                    "tp_max": round(row[3], 3),
                    "stop_floor": round(row[4], 3),
                    "max_trades_per_day": row[5]
                },
                "metrics": {
                    "total_trades": row[6],
                    "win_rate": round(row[7], 1),
                    "roi": round(row[8], 2),
                    "sharpe_ratio": round(row[9], 2),
                    "max_drawdown": round(row[10], 2)
                },
                "score": round(row[11], 2),
                "timestamp": row[12],
                "applied": bool(row[13])
            })
        
        return strategies
    except Exception as e:
        print(f"Error getting top strategies: {e}")
        return []

@app.get("/api/learning/evolution")
async def get_strategy_evolution(days: int = 7):
    """Get strategy score evolution over time"""
    try:
        with get_db_connection('learning') as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT DATE(timestamp) as date, MAX(score) as best_score
                    FROM strategies
                    WHERE timestamp >= NOW() - INTERVAL '%s days'
                    GROUP BY DATE(timestamp)
                    ORDER BY date ASC
                """, (days,))
            else:
                cursor.execute("""
                    SELECT DATE(timestamp) as date, MAX(score) as best_score
                    FROM strategies
                    WHERE datetime(timestamp) >= datetime('now', '-' || ? || ' days')
                    GROUP BY DATE(timestamp)
                    ORDER BY date ASC
                """, (days,))
            
            rows = cursor.fetchall()
        
        evolution = []
        for row in rows:
            evolution.append({
                "date": row[0],
                "best_score": round(row[1], 2)
            })
        
        return evolution
    except Exception as e:
        print(f"Error getting evolution: {e}")
        return []

@app.get("/api/learning/current")
async def get_current_strategy():
    """Get currently applied strategy"""
    try:
        with get_db_connection('learning') as conn:
            cursor = conn.cursor()
            
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                           total_trades, win_rate, roi, sharpe_ratio, max_drawdown, score, applied_at
                    FROM strategies
                    WHERE applied = true
                    ORDER BY applied_at DESC
                    LIMIT 1
                """)
            else:
                cursor.execute("""
                    SELECT ml_threshold, risk_per_trade, tp_min, tp_max, stop_floor, max_trades_per_day,
                           total_trades, win_rate, roi, sharpe_ratio, max_drawdown, score, applied_at
                    FROM strategies
                    WHERE applied = 1
                    ORDER BY applied_at DESC
                    LIMIT 1
                """)
            
            row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "params": {
                "ml_threshold": round(row[0], 3),
                "risk_per_trade": round(row[1], 4),
                "tp_min": round(row[2], 3),
                "tp_max": round(row[3], 3),
                "stop_floor": round(row[4], 3),
                "max_trades_per_day": row[5]
            },
            "metrics": {
                "total_trades": row[6],
                "win_rate": round(row[7], 1),
                "roi": round(row[8], 2),
                "sharpe_ratio": round(row[9], 2),
                "max_drawdown": round(row[10], 2)
            },
            "score": round(row[11], 2),
            "applied_at": row[12]
        }
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
from user_manager import UserManager

user_mgr = UserManager()
security = HTTPBearer()

# Pydantic models for auth
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserLogin(BaseModel):
    email_or_username: str
    password: str

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

# Authentication dependency
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

# Optional auth dependency (for public endpoints)
async def get_current_user_optional(authorization: Optional[str] = Header(None)):
    """Get current user if token provided, otherwise None"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    payload = user_mgr.verify_jwt(token)
    
    if not payload:
        return None
    
    return user_mgr.get_user(payload['user_id'])

# Admin-only dependency
async def get_current_admin(current_user: dict = Depends(get_current_user)):
    """Verify user is admin"""
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DASHBOARD_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

