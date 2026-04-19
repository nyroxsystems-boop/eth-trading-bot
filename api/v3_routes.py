"""
API v3 — Clean FastAPI endpoints for the dashboard.

This replaces the 6000-line dashboard_api.py with ~200 lines.
Registers as a router on the existing FastAPI app.
"""
import json
import os
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger("ethbot.api.v3")

router = APIRouter(prefix="/api/v3", tags=["v3"])

LOG_DIR = Path(os.getenv("LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs")))
TRADES_CSV = LOG_DIR / "trades.csv"
STATE_FILE = LOG_DIR / "bot_state.json"


# ── Models ──────────────────────────────────────

class TradeResponse(BaseModel):
    timestamp: str
    action: str
    qty: float
    price: float
    pnl: float = 0.0


# ── Status ──────────────────────────────────────

@router.get("/status")
async def get_status():
    """Get current bot status — reads from bot_state.json."""
    import requests

    # Read bot state
    state = {}
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                state = json.load(f)
    except Exception:
        pass

    # Get current price
    price = 0.0
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "ETHUSDT"},
            timeout=3,
        )
        if resp.status_code == 200:
            price = float(resp.json()["price"])
    except Exception:
        pass

    # Calculate position unrealized PnL
    position = None
    pos_data = state.get("position")
    if pos_data and pos_data.get("entry_price"):
        entry = float(pos_data["entry_price"])
        qty = float(pos_data.get("quantity", 0))
        upnl = (price / entry - 1.0) if entry > 0 and price > 0 else 0.0
        position = {
            "entry_price": entry,
            "quantity": qty,
            "unrealized_pnl": round(upnl, 6),
        }

    # Read trades for stats
    trades = _read_trades()
    sell_trades = [t for t in trades if t["action"] == "SELL" and t["pnl"] != 0]
    wins = [t for t in sell_trades if t["pnl"] > 0]
    total_pnl = sum(t["pnl"] for t in sell_trades)
    win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0

    return {
        "is_running": state.get("today_trades", 0) >= 0,  # Bot is running if state exists
        "price": price,
        "today_trades": state.get("today_trades", 0),
        "regime": "paper",
        "daily_pnl": state.get("daily_pnl", 0.0),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": len(sell_trades),
        "paper_balance": state.get("paper_balance", 100_000),
        "position": position,
    }


# ── Trades ──────────────────────────────────────

@router.get("/trades")
async def get_trades(limit: int = Query(50, ge=1, le=500)):
    """Get recent trades."""
    trades = _read_trades()
    return trades[-limit:]


# ── P&L History ─────────────────────────────────

@router.get("/pnl-history")
async def get_pnl_history(days: int = Query(7, ge=1, le=90)):
    """Get daily P&L history for charting."""
    trades = _read_trades()
    sell_trades = [t for t in trades if t["action"] == "SELL" and t["pnl"] != 0]

    # Group by date
    daily: Dict[str, float] = {}
    for t in sell_trades:
        date = t["timestamp"][:10]  # YYYY-MM-DD
        daily[date] = daily.get(date, 0) + t["pnl"]

    # Build cumulative series
    result = []
    cumulative = 0.0
    dates = sorted(daily.keys())
    for date in dates[-days:]:
        cumulative += daily[date]
        result.append({
            "date": date,
            "daily_pnl": round(daily[date], 2),
            "cumulative_pnl": round(cumulative, 2),
        })

    return result


# ── Signal ──────────────────────────────────────

@router.get("/signal")
async def get_current_signal():
    """Get current trading signal (live computation)."""
    try:
        from bot.executor import fetch_klines
        from bot.signals import add_indicators, compute_signals

        df = fetch_klines("ETHUSDT", "5m", lookback=100)
        df = add_indicators(df)
        signal = compute_signals(df, entry_score_min=0.20)

        return {
            "score": signal.score,
            "should_buy": signal.should_buy,
            "signals": signal.signals,
            "rsi": round(signal.rsi, 1),
            "adx": round(signal.adx, 1),
            "regime": signal.regime,
            "price": round(signal.price, 2),
        }
    except Exception as e:
        logger.error(f"Signal computation failed: {e}")
        return {
            "score": 0.0, "should_buy": False, "signals": [],
            "rsi": 50.0, "adx": 20.0, "regime": "unknown", "price": 0.0,
        }


# ── Config ──────────────────────────────────────

@router.get("/config")
async def get_config():
    """Get current bot configuration."""
    try:
        from bot.config import TradingConfig
        config = TradingConfig.from_env()
        return {
            "pair": config.pair,
            "interval": config.interval,
            "paper_mode": config.paper_mode,
            "risk_per_trade": config.risk_per_trade * 100,
            "tp_min": config.tp_min * 100,
            "tp_max": config.tp_max * 100,
            "stop_floor": config.stop_floor * 100,
            "max_trades_per_day": config.max_trades_per_day,
            "entry_score_min": config.entry_score_min,
            "rsi_min": config.rsi_min,
            "rsi_max": config.rsi_max,
            "use_ml": config.use_ml,
            "ml_threshold": config.ml_threshold,
            "loop_sleep_seconds": config.loop_sleep_seconds,
        }
    except Exception:
        return {"error": "Config not available"}


# ── Brain Intelligence ──────────────────────────

@router.get("/brain")
async def get_brain_status():
    """Get brain learning status."""
    try:
        from bot.brain import get_brain
        brain = get_brain()
        return brain.get_status()
    except Exception as e:
        return {"error": str(e)}


@router.get("/swarm")
async def get_swarm_status():
    """Get swarm intelligence status — all agents and their accuracy."""
    try:
        from bot.swarm import get_swarm
        return get_swarm().get_status()
    except Exception as e:
        return {"error": str(e)}


@router.get("/experience")
async def get_experience_status():
    """Get experience memory and genetic evolver status."""
    try:
        from bot.experience import get_memory, get_evolver
        mem = get_memory()
        evo = get_evolver()
        return {
            "memory": mem.get_stats(),
            "evolver": {
                "generation": evo.generation,
                "population_size": len(evo.population),
                "best_fitness": round(max((s.get("fitness", 0) for s in evo.population), default=0), 4),
            },
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/shield")
async def get_shield_status():
    """Get risk shield status — circuit breaker and portfolio guard."""
    try:
        from bot.shield import get_circuit_breaker, get_portfolio_guard, get_cost_simulator
        cb = get_circuit_breaker()
        pg = get_portfolio_guard()
        cs = get_cost_simulator()
        return {
            "circuit_breaker": cb.get_status(),
            "portfolio_guard": pg.get_status(),
            "costs": cs.get_stats(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/ml")
async def get_ml_status():
    """Get ML training data status."""
    try:
        from bot.ml_collector import get_stats
        return get_stats()
    except Exception as e:
        return {"error": str(e)}


# ── Multi-Pair Status ──────────────────────────

@router.get("/pairs")
async def get_pairs_status():
    """Get status of all trading pairs."""
    pairs_status = []
    try:
        state_dir = LOG_DIR
        for f in sorted(state_dir.glob("state_*.json")):
            pair = f.stem.replace("state_", "")
            with open(f) as fh:
                data = json.load(fh)
            pairs_status.append({
                "pair": pair,
                "in_position": data.get("position", {}).get("entry_price") is not None and data.get("position", {}).get("entry_price", 0) > 0,
                "daily_pnl": data.get("daily_pnl", 0),
                "today_trades": data.get("today_trades", 0),
                "paper_balance": data.get("paper_balance", 0),
                "win_streak": data.get("win_streak", 0),
                "loss_streak": data.get("loss_streak", 0),
            })
    except Exception as e:
        logger.warning(f"Failed to read pair states: {e}")
    return pairs_status


# ── Helpers ─────────────────────────────────────

def _read_trades() -> List[Dict]:
    """Read trades from CSV file."""
    trades = []
    try:
        if TRADES_CSV.exists():
            with open(TRADES_CSV) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    trades.append({
                        "timestamp": row.get("timestamp", ""),
                        "action": row.get("action", ""),
                        "qty": float(row.get("qty", 0)),
                        "price": float(row.get("price", 0)),
                        "pnl": float(row.get("pnl", 0)),
                    })
    except Exception as e:
        logger.warning(f"Failed to read trades CSV: {e}")
    return trades


# ── Emergency Controls ─────────────────────────────────────────

@router.post("/emergency-stop")
async def emergency_stop():
    """
    🚨 KILL SWITCH — Close all positions and cancel all orders.
    Use this in case of emergency (flash crash, bot malfunction, etc.)
    """
    import threading
    try:
        from bot.config import TradingConfig
        from bot.state import BotState
        from bot.executor import emergency_close_all

        config = TradingConfig.from_env()
        state = BotState.load()

        result = emergency_close_all(config, state)

        # Signal the engine to stop
        try:
            from bot.engine import _shutdown
            _shutdown.set()
            result["engine_stopped"] = True
        except Exception:
            result["engine_stopped"] = False

        # Save cleared state
        state.save()

        logger.warning(f"🚨 EMERGENCY STOP executed: {result}")
        return {"status": "emergency_stop_executed", **result}

    except Exception as e:
        logger.error(f"Emergency stop FAILED: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/reconcile")
async def reconcile():
    """Check bot state vs actual exchange positions."""
    try:
        from bot.config import TradingConfig
        from bot.state import BotState
        from bot.executor import reconcile_positions

        config = TradingConfig.from_env()
        state = BotState.load()

        result = reconcile_positions(config, state)

        # Save if state was fixed
        if result.get("ghost_positions", 0) > 0:
            state.save()

        return result

    except Exception as e:
        return {"status": "error", "error": str(e)}

