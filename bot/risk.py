from __future__ import annotations
"""
Risk Manager — Position sizing, stop loss, take profit.
Simple, transparent, no 7-layer guard stacking.
"""
from bot.config import TradingConfig
from bot.state import BotState


def position_size(
    price: float,
    atr: float,
    config: TradingConfig,
    state: BotState,
    confidence: float = 0.5,
    swarm_pct: float = 0.5,
    total_pool_equity: float = 0.0,
) -> float:
    """
    Dynamic position sizing based on trend confidence.

    Uses the TOTAL CAPITAL POOL for sizing, not per-pair splits.
    The bot decides how much of the full pool to allocate per trade
    based on signal quality. Strong trends → bigger bets.

    Args:
        confidence: Signal score / entry quality (0.0 to 1.0+)
        swarm_pct: Swarm consensus percentage (0.0 to 1.0)
        total_pool_equity: Total available capital pool (total - locked)
                          If 0, falls back to state.available_balance

    Sizing tiers:
        ★★★★★ Elite (90%+ consensus, strong trend) → 50-60% of pool
        ★★★★  Strong (75%+ consensus)              → 30-40% of pool
        ★★★   Normal (60%+ consensus)               → 15-25% of pool
        ★★    Weak   (50%+ consensus)                → 8-12% of pool
        ★     Minimum (barely passes)                → 5% of pool
    """
    # Use total pool if provided, otherwise fall back to per-pair balance
    equity = total_pool_equity if total_pool_equity > 0 else state.available_balance
    sl_pct = stop_loss_pct(price, atr, config)

    # ── Base risk scaled by confidence ──
    # Combine swarm consensus and signal score into a confidence multiplier
    combined_confidence = (swarm_pct * 0.6) + (min(confidence, 1.0) * 0.4)

    # Map confidence to equity allocation percentage
    if combined_confidence >= 0.85:
        alloc_pct = 0.55  # Elite: 55% of pool
    elif combined_confidence >= 0.70:
        alloc_pct = 0.35  # Strong: 35%
    elif combined_confidence >= 0.55:
        alloc_pct = 0.20  # Normal: 20%
    elif combined_confidence >= 0.40:
        alloc_pct = 0.10  # Weak: 10%
    else:
        alloc_pct = 0.05  # Minimum: 5%

    risk_usd = equity * alloc_pct

    # Loss streak reduction: halve size after 2+ consecutive losses
    if state.loss_streak >= 3:
        risk_usd *= 0.3
    elif state.loss_streak >= 2:
        risk_usd *= 0.5

    # Win streak boost (modest)
    if state.win_streak >= 3:
        risk_usd *= 1.2

    # Hard cap
    risk_usd = min(risk_usd, equity * config.max_risk_per_trade)

    denom = sl_pct * price
    if denom <= 0:
        return 0.0

    qty = risk_usd / denom

    # Cap position at the allocation percentage of equity
    max_qty = (equity * min(alloc_pct + 0.05, 0.60)) / max(price, 1)
    qty = min(qty, max_qty)

    return max(0.0001, qty)


def stop_loss_pct(price: float, atr: float, config: TradingConfig) -> float:
    """
    Calculate stop loss as a percentage.
    SL = max(floor, ATR × multiplier / price)
    """
    atr_based = config.stop_atr_mult * atr / max(price, 1e-9)
    return max(config.stop_floor, atr_based)


def take_profit_pct(regime: str, rsi: float, atr_pct: float, config: TradingConfig) -> float:
    """
    Dynamic TP based on regime.
    - Trending: wider TP (let winners run)
    - Ranging: tight TP (take quick profits)
    - Volatile: ATR-scaled TP
    """
    if regime == "trending":
        base = config.tp_max * 1.3
    elif regime == "volatile":
        base = max(config.tp_max, atr_pct * 1.5)
    else:  # ranging
        base = config.tp_min

    return max(config.tp_min * 0.8, min(base, 0.06))


def should_close_position(
    entry_price: float,
    current_price: float,
    atr: float,
    bars_held: int,
    peak_pnl: float,
    trailing_active: bool,
    config: TradingConfig,
    partial_taken: bool = False,
    macd_bearish: bool = False,
) -> str | None:
    """
    Check if position should be closed.

    Returns:
        "TP" — take profit hit
        "SL" — stop loss hit
        "TIME" — max hold time exceeded
        "PARTIAL" — take partial profit (50%)
        "MOMENTUM" — momentum reversal exit
        None — hold
    """
    if entry_price <= 0:
        return None

    upnl = (current_price / entry_price) - 1.0
    sl = stop_loss_pct(entry_price, atr, config)

    # --- Stop Loss ---
    if upnl <= -sl:
        return "SL"

    # --- Time Exit (tighter: no free rides) ---
    if bars_held >= config.max_hold_bars:
        return "TIME"

    # --- Break Even: move SL to entry after +1.2% ---
    if upnl >= config.break_even_trigger:
        if upnl <= -0.001:  # Price dropped back below entry
            return "SL"

    # --- PARTIAL PROFIT: Close 50% at +1.5% ---
    if not partial_taken and upnl >= 0.015:
        return "PARTIAL"

    # --- MOMENTUM EXIT: MACD turned bearish while in profit ---
    if macd_bearish and upnl > 0.005 and bars_held >= 5:
        return "MOMENTUM"

    # --- Take Profit (with trailing) ---
    tp = config.tp_max  # Use the wider TP

    if trailing_active:
        # Lock in 70% of peak gains (tighter than before)
        trail_floor = peak_pnl * 0.70
        if upnl <= trail_floor and peak_pnl > tp * 0.8:
            return "TP"
        # Hard cap at 3x TP
        if upnl >= tp * 3.0:
            return "TP"
    else:
        # Standard TP — activate trailing instead of immediate exit
        if upnl >= tp:
            return None  # Will activate trailing in engine

    return None


def check_guards(config: TradingConfig, state: BotState) -> str | None:
    """
    Pre-trade guards. Returns reason string if blocked, None if OK.

    Only 3 guards (was 7+):
    1. Daily max trades
    2. Daily drawdown limit
    3. Cooldown active
    """
    # 1. Max trades per day
    if state.today_trades >= config.max_trades_per_day:
        return "max_trades_reached"

    # 2. Daily drawdown circuit breaker
    if state.circuit_breaker:
        return "circuit_breaker_active"

    equity = state.paper_balance
    if equity > 0 and state.daily_pnl < 0:
        dd_pct = abs(state.daily_pnl) / equity
        if dd_pct >= config.max_drawdown_day:
            state.circuit_breaker = True
            return f"daily_drawdown_{dd_pct*100:.1f}%"

    # 3. Cooldown after loss streak
    if not state.is_cooled_down:
        return "cooldown_active"

    return None  # All clear
