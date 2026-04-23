"""
API v3 — Clean FastAPI endpoints for the dashboard.

This replaces the 6000-line dashboard_api.py with ~200 lines.
Registers as a router on the existing FastAPI app.
"""
import json
import os
import csv
import logging
from pathlib import Path
from typing import List, Dict

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
    pair: str = ""
    qty: float
    price: float
    pnl: float = 0.0


# ── Status ──────────────────────────────────────

@router.get("/status")
async def get_status():
    """Get current bot status — reads from bot_state.json."""
    import requests

    # Get configured pair
    try:
        from bot.config import TradingConfig
        config = TradingConfig.from_env()
        pair = config.pair
        paper_mode = config.paper_mode
    except Exception:
        pair = "AUTO"
        paper_mode = True

    # Read bot state
    state = {}
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                state = json.load(f)
    except Exception:
        pass

    # Get current price for the configured pair
    price = 0.0
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": pair},
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
    # Count all sell-like actions (SELL, PARTIAL_SELL, etc.)
    sell_trades = [t for t in trades if "SELL" in t.get("action", "").upper() and t.get("pnl", 0) != 0]
    wins = [t for t in sell_trades if t["pnl"] > 0]
    total_pnl = sum(t["pnl"] for t in sell_trades)
    win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0

    # Count today's trades (all types)
    from datetime import date
    today_str = date.today().isoformat()
    today_trades = len([t for t in trades if t.get("timestamp", "").startswith(today_str)])

    # Multi-pair: aggregate balance & positions from pair states
    pair_states = _read_pair_states()
    # Filter out strategy-prefixed pairs (S4_, etc.)
    real_pairs = [p for p in pair_states if not p["pair"].startswith("S")]
    
    # Calculate real equity: sum of all pair balances = total pool value
    try:
        from bot.config import TradingConfig
        starting_balance = TradingConfig.from_env().paper_balance
    except Exception:
        starting_balance = float(os.getenv("PAPER_BASE_USDT", "100000"))
    # SHARED POOL: Equity = starting capital + total P&L from all trades
    # Don't sum per-pair balances (each pair now shows $100k = the full pool!)
    current_equity = starting_balance + total_pnl
    daily_pnl_total = sum(p.get("daily_pnl", 0) for p in real_pairs) if real_pairs else state.get("daily_pnl", 0.0)
    
    # Active positions with unrealized PnL
    open_positions = []
    total_unrealized = 0.0
    for p in real_pairs:
        if p.get("in_position", False):
            entry_px = p.get("entry_price", 0)
            qty = p.get("quantity", 0)
            locked = p.get("paper_locked", 0)
            
            # Try to get current price for unrealized PnL
            unrealized = 0.0
            try:
                import requests
                pair_raw = p["pair"]
                resp = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={pair_raw}", timeout=3)
                if resp.ok:
                    current_px = float(resp.json().get("price", entry_px))
                    if p.get("direction", "LONG") == "SHORT":
                        unrealized = (entry_px - current_px) * qty
                    else:
                        unrealized = (current_px - entry_px) * qty
            except Exception:
                pass
            
            total_unrealized += unrealized
            locked_capital = locked if locked > 0 else round(entry_px * qty, 2)
            open_positions.append({
                "pair": p["pair"].replace("USDT", "/USDT"),
                "daily_pnl": round(p.get("daily_pnl", 0), 2),
                "unrealized_pnl": round(unrealized, 2),
                "locked_capital": locked_capital,
                "entry_price": round(entry_px, 6),
                "quantity": round(qty, 4),
                "direction": p.get("direction", "LONG"),
                "bars_held": p.get("bars_held", 0),
            })
    
    # Active pairs = total being monitored (not just those with state files)
    try:
        from bot.engine import _get_pairs
        all_pairs = _get_pairs()
        active_pairs = len(all_pairs)
    except Exception:
        active_pairs = max(len(real_pairs), 8)  # fallback

    return {
        "is_running": len(trades) > 0 or state.get("today_trades", 0) >= 0,
        "pair": f"{active_pairs} Pairs" if active_pairs > 1 else pair,
        "price": price,
        "today_trades": max(today_trades, state.get("today_trades", 0)),
        "regime": "paper" if paper_mode else "live",
        "daily_pnl": round(daily_pnl_total, 2),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": len(trades),
        "paper_balance": round(current_equity, 2),
        "starting_balance": round(starting_balance, 2),
        "position": position,
        "open_positions": open_positions,
        "active_pairs": active_pairs,
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
    """Get P&L history for charting. Per-trade if <3 days, per-day otherwise."""
    trades = _read_trades()
    sell_trades = [t for t in trades if "SELL" in t.get("action", "").upper() and t.get("pnl", 0) != 0]

    # Group by date to check how many days we have
    daily: Dict[str, float] = {}
    for t in sell_trades:
        date = t["timestamp"][:10]  # YYYY-MM-DD
        daily[date] = daily.get(date, 0) + t["pnl"]

    # If fewer than 3 days of data, return per-trade cumulative PnL
    if len(daily) < 3 and sell_trades:
        result = []
        cumulative = 0.0
        for i, t in enumerate(sell_trades):
            cumulative += t["pnl"]
            result.append({
                "date": f"Trade #{i+1}",
                "daily_pnl": round(t["pnl"], 2),
                "cumulative_pnl": round(cumulative, 2),
            })
        return result

    # Normal: daily aggregation
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
    """Get current trading signal — rotates through all active pairs."""
    try:
        from bot.config import TradingConfig
        from bot.executor import fetch_klines
        from bot.signals import add_indicators, compute_signals
        import time

        config = TradingConfig.from_env()

        # Get all active pairs and rotate through them
        pair_states = _read_pair_states()
        active_pairs = [p["pair"] for p in pair_states if not p["pair"].startswith("S")]

        if not active_pairs:
            active_pairs = [config.pair]

        # Rotate: switch pair every 10 seconds
        idx = int(time.time() / 10) % len(active_pairs)
        current_pair = active_pairs[idx]

        df = fetch_klines(current_pair, config.interval, lookback=100)
        df = add_indicators(df)
        signal = compute_signals(df, entry_score_min=config.entry_score_min)

        return {
            "pair": current_pair.replace("USDT", "/USDT"),
            "pair_raw": current_pair,
            "score": signal.score,
            "should_buy": signal.should_buy,
            "signals": signal.signals,
            "rsi": round(signal.rsi, 1),
            "adx": round(signal.adx, 1),
            "regime": signal.regime,
            "price": round(signal.price, 2),
            "rotating_index": idx,
            "total_pairs": len(active_pairs),
        }
    except Exception as e:
        logger.error(f"Signal computation failed: {e}")
        return {
            "pair": "—",
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
        # Get actual active pair count
        pair_states = _read_pair_states()
        real_pairs = [p for p in pair_states if not p["pair"].startswith("S")]
        active_count = len(real_pairs) if real_pairs else 1
        
        return {
            "pair": f"{active_count} Pairs (Auto-Scan)" if active_count > 1 else config.pair,
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
            "active_pairs": active_count,
            "capital_pool": config.paper_balance,
        }
    except Exception:
        return {"error": "Config not available"}


# ── Brain Intelligence ──────────────────────────

@router.get("/brain")
async def get_brain_status():
    """Get brain learning status — enriched with real trade data."""
    try:
        from bot.brain import get_brain
        brain = get_brain()
        status = brain.get_status()
    except Exception as e:
        status = {"stage": "🔌 Connecting...", "error": str(e)}
    
    # Enrich with real trade data (Brain's own storage is ephemeral)
    trades = _read_trades()
    if trades:
        sell_trades = [t for t in trades if "SELL" in t.get("action", "").upper()]
        wins = [t for t in sell_trades if float(t.get("pnl", 0)) > 0]
        known_pairs = len(set(t.get("pair", "") for t in trades))
        total_pnl = sum(float(t.get("pnl", 0)) for t in sell_trades)
        
        status["total_trades"] = len(trades)
        status["pairs_known"] = known_pairs
        status["lifetime_pnl"] = round(total_pnl, 2)
        status["winrate"] = round(len(wins) / len(sell_trades) * 100, 1) if sell_trades else 0
        
        # Upgrade stage label based on real trade count
        n = len(trades)
        if n >= 100:
            status["stage"] = "🧠 Expert — Deep market knowledge"
        elif n >= 50:
            status["stage"] = "📈 Advanced — Building expertise"
        elif n >= 20:
            status["stage"] = "📊 Learning — Refining patterns"
        elif n >= 5:
            status["stage"] = "🌱 Growing — Analyzing first patterns"
        elif n >= 1:
            status["stage"] = "🐣 Newborn — Collecting first data"
    
    return status


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
    """Get risk shield status — enriched with real position data."""
    try:
        from bot.shield import get_circuit_breaker, get_portfolio_guard, get_cost_simulator
        cb = get_circuit_breaker()
        pg = get_portfolio_guard()
        cs = get_cost_simulator()
        result = {
            "circuit_breaker": cb.get_status(),
            "portfolio_guard": pg.get_status(),
            "costs": cs.get_stats(),
        }
    except Exception as e:
        result = {
            "circuit_breaker": {"tripped": False, "daily_pnl": 0, "consecutive_losses": 0},
            "portfolio_guard": {"open_positions": 0, "max_positions": 8},
            "error": str(e),
        }
    
    # Enrich with real data from pair states
    pair_states = _read_pair_states()
    real_pairs = [p for p in pair_states if not p["pair"].startswith("S")]
    open_count = sum(1 for p in real_pairs if p.get("in_position", False))
    daily_pnl = sum(p.get("daily_pnl", 0) for p in real_pairs)
    
    if "portfolio_guard" in result:
        result["portfolio_guard"]["open_positions"] = open_count
        result["portfolio_guard"]["max_positions"] = max(len(real_pairs), 8)
    if "circuit_breaker" in result:
        if daily_pnl != 0:
            result["circuit_breaker"]["daily_pnl"] = round(daily_pnl, 2)
    
    return result


@router.post("/shield/reset")
async def reset_circuit_breaker():
    """Reset circuit breaker to allow trading to resume."""
    try:
        from bot.shield import get_circuit_breaker
        cb = get_circuit_breaker()
        was_tripped = cb.tripped
        cb.tripped = False
        cb.trip_reason = ""
        cb.consecutive_losses = 0
        cb.save()
        logger.info(f"🔌 Circuit breaker manually reset (was tripped: {was_tripped})")
        return {"status": "ok", "was_tripped": was_tripped, "message": "Circuit breaker reset — trading resumed"}
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
    """Read trades — merge Postgres + CSV (both sources, deduplicated)."""
    all_trades = []
    
    # Source 1: Postgres (persistent across deploys)
    try:
        from trade_store import get_all_trades
        pg_trades = get_all_trades()
        if pg_trades:
            all_trades.extend(pg_trades)
    except Exception:
        pass
    
    # Source 2: CSV (ephemeral but has current session data)
    csv_trades = []
    try:
        if TRADES_CSV.exists():
            with open(TRADES_CSV) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    csv_trades.append({
                        "timestamp": row.get("timestamp", ""),
                        "action": row.get("action", ""),
                        "pair": row.get("pair", "ETHUSDT"),
                        "qty": float(row.get("qty", 0)),
                        "price": float(row.get("price", 0)),
                        "pnl": float(row.get("pnl", 0)),
                    })
    except Exception as e:
        logger.warning(f"Failed to read trades CSV: {e}")
    
    # Merge: add CSV trades that aren't in Postgres (by timestamp+pair+action)
    pg_keys = set()
    for t in all_trades:
        pg_keys.add(f"{t['timestamp']}_{t['pair']}_{t['action']}")
    
    for t in csv_trades:
        key = f"{t['timestamp']}_{t['pair']}_{t['action']}"
        if key not in pg_keys:
            all_trades.append(t)
    
    # Sort by timestamp
    all_trades.sort(key=lambda t: t.get("timestamp", ""))
    return all_trades


def _read_pair_states() -> List[Dict]:
    """Read all pair state files for multi-pair aggregation."""
    pairs = []
    try:
        state_dir = LOG_DIR
        for f in sorted(state_dir.glob("state_*.json")):
            pair = f.stem.replace("state_", "")
            with open(f) as fh:
                data = json.load(fh)
            pos = data.get("position") or {}
            entry_price = pos.get("entry_price", 0) or 0
            quantity = pos.get("quantity", 0) or 0
            pairs.append({
                "pair": pair,
                "in_position": entry_price > 0,
                "daily_pnl": data.get("daily_pnl", 0),
                "today_trades": data.get("today_trades", 0),
                "paper_balance": data.get("paper_balance", 0),
                "paper_locked": data.get("paper_locked", 0),
                "win_streak": data.get("win_streak", 0),
                "loss_streak": data.get("loss_streak", 0),
                "entry_price": entry_price,
                "quantity": quantity,
                "direction": pos.get("direction", "LONG"),
                "bars_held": pos.get("bars_held", 0),
            })
    except Exception as e:
        logger.warning(f"Failed to read pair states: {e}")
    return pairs


# ── Strategy Status Endpoints ────────────────────────────────────

@router.get("/strategies")
async def get_all_strategies():
    """Get status of all 5 trading strategies."""
    statuses = {}
    # S1 FundingArb removed — requires perpetual futures (not available in DE)
    statuses["S1_FundingArb"] = {"status": "DISABLED", "reason": "Futures not available in DE, using Margin"}

    try:
        from bot.strategies.stat_arb import get_stat_arb
        statuses["S2_StatArb"] = get_stat_arb().get_status()
    except Exception as e:
        statuses["S2_StatArb"] = {"error": str(e)}

    try:
        statuses["S3_MarketMaking"] = {"status": "PLANNED", "phase": 4}
    except Exception as e:
        statuses["S3_MarketMaking"] = {"error": str(e)}

    try:
        from bot.strategies.momentum_v2 import get_momentum
        statuses["S4_MomentumV2"] = get_momentum().get_status()
    except Exception as e:
        statuses["S4_MomentumV2"] = {"error": str(e)}

    try:
        from bot.strategies.liquidation_hunter import get_liq_hunter
        statuses["S5_LiqHunter"] = get_liq_hunter().get_status()
    except Exception as e:
        statuses["S5_LiqHunter"] = {"error": str(e)}

    return statuses


@router.get("/allocator")
async def get_allocator_status():
    """Get master allocator portfolio status + risk limits."""
    try:
        from bot.strategies.allocator import get_allocator
        return get_allocator().get_status()
    except Exception as e:
        return {"error": str(e)}


# scan-funding removed — S1 FundingArb disabled (Futures not available in DE)


@router.post("/strategies/scan-cointegration")
async def scan_cointegration():
    """Trigger cointegration pair scan for S2 strategy."""
    try:
        from bot.strategies.stat_arb import get_stat_arb
        pairs = get_stat_arb().find_cointegrated_pairs()
        return {
            "pairs_found": len(pairs),
            "pairs": [
                {
                    "a": p.asset_a, "b": p.asset_b,
                    "pvalue": round(p.pvalue, 4),
                    "hedge_ratio": round(p.hedge_ratio, 4),
                    "zscore": round(p.zscore, 2),
                    "half_life": round(p.half_life, 1),
                }
                for p in pairs
            ]
        }
    except Exception as e:
        return {"error": str(e)}


# ── Emergency Controls ─────────────────────────────────────────

@router.post("/emergency-stop")
async def emergency_stop():
    """
    🚨 KILL SWITCH — Close all positions and cancel all orders.
    Use this in case of emergency (flash crash, bot malfunction, etc.)
    """
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


@router.get("/learning")
async def get_learning():
    """Auto-learning monitor — strategies tested, applied, and evolution."""
    try:
        from learning_store import (
            get_learning_stats,
            get_current_strategy,
            get_all_strategies,
            get_evolution,
        )

        stats = get_learning_stats()
        current = get_current_strategy()
        top_strategies = get_all_strategies(limit=10)
        evolution = get_evolution(days=7)

        return {
            "total_tested": stats.get("total_tested", 0),
            "best_score": stats.get("best_score", 0),
            "applied_count": stats.get("applied_count", 0),
            "avg_score": stats.get("avg_score", 0),
            "this_hour": stats.get("this_hour", 0),
            "learning_rate": stats.get("learning_rate", 0),
            "current_strategy": current,
            "top_strategies": [
                {
                    "params": s.get("params", {}),
                    "score": s.get("score", 0),
                    "metrics": s.get("metrics", {}),
                    "applied": s.get("applied", False),
                }
                for s in top_strategies
            ],
            "evolution": evolution,
            "training_active": stats.get("total_tested", 0) > 0,
        }

    except Exception as e:
        logger.warning(f"Learning endpoint: {e}")
        return {
            "total_tested": 0,
            "best_score": 0,
            "applied_count": 0,
            "avg_score": 0,
            "this_hour": 0,
            "learning_rate": 0,
            "current_strategy": None,
            "top_strategies": [],
            "evolution": [],
            "training_active": False,
        }


@router.get("/db-status")
async def get_db_status():
    """Diagnostic: check database tables and connection."""
    result = {"use_postgres": False, "tables": {}, "errors": []}

    try:
        from db_adapter import USE_POSTGRES, get_db_connection
        result["use_postgres"] = USE_POSTGRES

        if USE_POSTGRES:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # List all tables
                cursor.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                tables = [row[0] for row in cursor.fetchall()]

                for table in tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        result["tables"][table] = count
                    except Exception as e:
                        result["tables"][table] = f"error: {e}"
        else:
            result["errors"].append("DATABASE_URL not set or psycopg2 not available")

    except Exception as e:
        result["errors"].append(str(e))

    return result
