"""
Trading Engine — The Main Loop.

Flow:
1. Check guards (max trades, drawdown, cooldown)
2. Fetch market data
3. If in position → manage (SL/TP/trail/time exit)
4. If not in position → compute signals + enrichments → buy if strong enough
5. Sleep and repeat

Enrichments (from old codebase, high-value features):
- Market Intelligence: Fear&Greed, Funding Rate, News Sentiment, Whale Alerts
- Multi-Timeframe: 5m/15m/1h alignment confirmation
"""
import logging
import time
import signal as sig
import threading
from datetime import datetime, timezone

from bot.config import TradingConfig
from bot.state import BotState
from bot.signals import add_indicators, compute_signals
from bot.risk import position_size, check_guards, should_close_position
from bot.executor import execute_buy, execute_sell, fetch_klines, get_current_price

logger = logging.getLogger("ethbot.engine")

# Graceful shutdown
_shutdown = threading.Event()


def _handle_signal(signum, frame):
    logger.info(f"Received signal {signum}, shutting down...")
    _shutdown.set()


def _notify(config: TradingConfig, msg: str):
    """Send Telegram notification (non-blocking)."""
    if not (config.telegram_token and config.telegram_chat_id):
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{config.telegram_token}/sendMessage",
            json={"chat_id": config.telegram_chat_id, "text": msg},
            timeout=5,
        )
    except Exception:
        pass


def _log_trade(action: str, qty: float, price: float, pnl: float = 0.0):
    """Log trade to CSV file."""
    import csv
    import os
    os.makedirs("logs", exist_ok=True)
    path = "logs/trades.csv"
    header_needed = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as f:
        if header_needed:
            f.write("timestamp,action,qty,price,pnl\n")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        csv.writer(f).writerow([ts, action, f"{qty:.6f}", f"{price:.2f}", f"{pnl:.2f}"])


def run(config: TradingConfig | None = None):
    """
    Main trading loop.

    This is the ENTIRE bot. Read it top to bottom.
    """
    if config is None:
        config = TradingConfig.from_env()

    # Setup
    sig.signal(sig.SIGINT, _handle_signal)
    sig.signal(sig.SIGTERM, _handle_signal)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Load or create state
    state = BotState.load()
    state.paper_balance = max(state.paper_balance, config.paper_balance)
    state.check_new_day()

    mode = "PAPER" if config.paper_mode else "LIVE"
    logger.info(f"═══ Ethbot v3 Starting ═══")
    logger.info(f"Mode: {mode} | Pair: {config.pair} | Interval: {config.interval}")
    logger.info(f"Balance: ${state.paper_balance:,.2f} | Risk: {config.risk_per_trade*100:.1f}%/trade")
    logger.info(f"TP: {config.tp_min*100:.1f}-{config.tp_max*100:.1f}% | SL floor: {config.stop_floor*100:.1f}%")
    logger.info(f"Max trades/day: {config.max_trades_per_day} | Entry min: {config.entry_score_min}")

    _notify(config, f"🤖 Ethbot v3 gestartet [{mode}] | ${state.paper_balance:,.0f}")

    loop_count = 0

    # ═══════════════════════════════════════════════
    # MAIN LOOP
    # ═══════════════════════════════════════════════
    while not _shutdown.is_set():
        try:
            loop_count += 1
            state.check_new_day()

            # ── Step 1: Pre-trade guards ──
            if not state.is_in_position:
                guard = check_guards(config, state)
                if guard:
                    if loop_count % 10 == 1:  # Log every 10th loop to avoid spam
                        logger.info(f"Guard: {guard}")
                    _shutdown.wait(config.loop_sleep_seconds)
                    continue

            # ── Step 2: Fetch market data ──
            try:
                df = fetch_klines(config.pair, config.interval, lookback=300)
                df = add_indicators(df)
                if len(df) < 50:
                    logger.info("Waiting for data...")
                    _shutdown.wait(config.loop_sleep_seconds)
                    continue
            except Exception as e:
                logger.error(f"Data fetch failed: {e}")
                _shutdown.wait(30)  # Short retry
                continue

            row = df.iloc[-1]
            px = float(row["close"])
            atr = float(row["atr"])

            # ── Step 3: Manage open position ──
            if state.is_in_position:
                pos = state.position
                pos.bars_held += 1

                # Track peak PnL
                upnl = pos.unrealized_pnl(px)
                if upnl > pos.peak_pnl:
                    pos.peak_pnl = upnl

                # Activate trailing if TP reached
                if upnl >= config.tp_max and not pos.trailing_active:
                    pos.trailing_active = True
                    logger.info(f"📈 Trailing activated: +{upnl*100:.2f}%")

                # Check exit conditions
                decision = should_close_position(
                    pos.entry_price, px, pos.atr_at_entry,
                    pos.bars_held, pos.peak_pnl, pos.trailing_active,
                    config,
                )

                if decision:
                    pnl = state.close_position(px)
                    execute_sell(px, pos.quantity, config, state)
                    _log_trade("SELL", pos.quantity, px, pnl)

                    emoji = "✅" if pnl > 0 else "⚠️"
                    pnl_pct = (px / pos.entry_price - 1.0) * 100
                    msg = f"{emoji} {decision} | {pnl_pct:+.2f}% | PnL: ${pnl:+.2f} | Daily: ${state.daily_pnl:+.2f}"
                    logger.info(msg)
                    _notify(config, msg)

                    # Check loss streak cooldown
                    if state.loss_streak >= config.loss_streak_cooldown:
                        state.trigger_cooldown(config.cooldown_minutes)
                        logger.info(f"⏸️ Cooldown: {config.cooldown_minutes}min after {config.loss_streak_cooldown} losses")
                        _notify(config, f"⏸️ Cooldown — {config.loss_streak_cooldown}x Verlust")

                    state.save()

            # ── Step 4: Look for new entry ──
            elif not state.is_in_position:
                signal = compute_signals(
                    df,
                    entry_score_min=config.entry_score_min,
                    rsi_min=config.rsi_min,
                    rsi_max=config.rsi_max,
                    ml_confidence=0.5,  # TODO: integrate ML predictor
                    ml_threshold=config.ml_threshold,
                )

                # ── Enrichment: Market Intelligence ──
                intel_boost = 0.0
                try:
                    from bot.market_intel import MarketIntelligence
                    mi = MarketIntelligence()
                    mi.enabled = True
                    intel_boost = mi.get_entry_score_adjustment()
                    if abs(intel_boost) > 0.01:
                        signal.score += intel_boost
                        signal.signals.append(f"INTEL({intel_boost:+.3f})")
                except Exception:
                    pass  # Market intel is optional

                # ── Enrichment: Multi-Timeframe Alignment ──
                mtf_boost = 0.0
                try:
                    from bot.multi_tf import get_mtf_boost
                    mtf_boost = get_mtf_boost(config.pair)
                    if abs(mtf_boost) > 0.01:
                        signal.score += mtf_boost
                        signal.signals.append(f"MTF({mtf_boost:+.3f})")
                except Exception:
                    pass  # MTF is optional

                # Recheck buy after enrichments
                signal.should_buy = signal.score >= config.entry_score_min

                # Log status every loop
                logger.info(
                    f"{'→' if signal.should_buy else '·'} "
                    f"Score: {signal.score:.3f}/{config.entry_score_min:.2f} | "
                    f"Signals: {signal.signals} | "
                    f"RSI: {signal.rsi:.1f} | ADX: {signal.adx:.1f} | "
                    f"Regime: {signal.regime} | "
                    f"Price: ${signal.price:,.2f}"
                )

                if signal.should_buy:
                    qty = position_size(px, atr, config, state)
                    cost = qty * px

                    if cost < 10:
                        qty = max(qty, 50.0 / max(px, 1))  # Minimum $50 position

                    if execute_buy(px, qty, config, state):
                        state.open_position(px, qty, atr)
                        _log_trade("BUY", qty, px)

                        entry_type = signal.signals[0] if signal.signals else "SIGNAL"
                        msg = (
                            f"▶️ LONG {config.base_asset} ({entry_type}) "
                            f"@ ${px:,.2f} | Size: ${qty*px:,.2f} | "
                            f"Score: {signal.score:.3f} | "
                            f"Signals: {', '.join(signal.signals)}"
                        )
                        logger.info(msg)
                        _notify(config, msg)
                        state.save()

            # ── Step 5: Sleep ──
            _shutdown.wait(config.loop_sleep_seconds)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Loop error: {e}", exc_info=True)
            _shutdown.wait(30)

    # Shutdown
    logger.info("Ethbot shutting down...")
    state.save()
    _notify(config, "🛑 Ethbot gestoppt")


if __name__ == "__main__":
    run()
