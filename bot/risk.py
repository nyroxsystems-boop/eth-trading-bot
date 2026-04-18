"""
Risk Manager — Position sizing, stop loss, take profit.
Simple, transparent, no 7-layer guard stacking.
"""
from bot.config import TradingConfig
from bot.state import BotState


def position_size(price: float, atr: float, config: TradingConfig, state: BotState) -> float:
    """
    Calculate position size based on risk-per-trade.

    Logic:
    - Risk USD = equity × risk_per_trade
    - SL distance = max(stop_floor, ATR × stop_atr_mult / price)
    - Quantity = Risk USD / (SL distance × price)

    Returns quantity in base asset (e.g. ETH).
    """
    equity = state.available_balance
    sl_pct = stop_loss_pct(price, atr, config)

    risk_usd = equity * config.risk_per_trade

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
) -> str | None:
    """
    Check if position should be closed.

    Returns:
        "TP" — take profit hit
        "SL" — stop loss hit
        "TIME" — max hold time exceeded
        None — hold
    """
    if entry_price <= 0:
        return None

    upnl = (current_price / entry_price) - 1.0
    sl = stop_loss_pct(entry_price, atr, config)

    # --- Stop Loss ---
    if upnl <= -sl:
        return "SL"

    # --- Time Exit ---
    if bars_held >= config.max_hold_bars:
        return "TIME"

    # --- Break Even: move SL to entry after +1.2% ---
    if upnl >= config.break_even_trigger:
        if upnl <= -0.001:  # Price dropped back below entry
            return "SL"

    # --- Take Profit (with trailing) ---
    tp = config.tp_max  # Use the wider TP

    if trailing_active:
        # Lock in 60% of peak gains
        trail_floor = peak_pnl * 0.60
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
