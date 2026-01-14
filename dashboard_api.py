#!/usr/bin/env python3
"""
ETH Trading Bot - Dashboard API
Real-time WebSocket API for Premium Trading Dashboard
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import csv
import aiosqlite

# Configuration
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "change_me")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
LOG_DIR = Path(os.getenv("LOG_DIR", "/root/ethbot/logs"))
TRADES_CSV = LOG_DIR / "trades.csv"
CONSOLE_LOG = LOG_DIR / "console.out"
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DASHBOARD_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
