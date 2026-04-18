"""
Trading Engine — The Main Loop (Multi-Pair).

Flow per pair:
1. Check guards (max trades, drawdown, cooldown)
2. Fetch market data
3. If in position → manage (SL/TP/trail/time exit)
4. If not in position → compute signals + enrichments → buy if strong enough
5. Rotate to next pair

Enrichments (from old codebase, high-value features):
- Market Intelligence: Fear&Greed, Funding Rate, News Sentiment, Whale Alerts, OI
- Multi-Timeframe: 5m/15m/1h alignment confirmation
- VWAP: Mean reversion signal
"""
import os
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

# Fallback pairs if Binance API is down
FALLBACK_PAIRS = [
    {"pair": "BTCUSDT", "base": "BTC"},
    {"pair": "ETHUSDT", "base": "ETH"},
    {"pair": "SOLUSDT", "base": "SOL"},
    {"pair": "BNBUSDT", "base": "BNB"},
    {"pair": "XRPUSDT", "base": "XRP"},
]


def _get_pairs(n: int = 20) -> list:
    """
    Get trading pairs — dynamic from Binance or env override.
    Priority: PAIRS env var > Dynamic scanner > Fallback.
    """
    # 1. Check env var override
    pairs_env = os.getenv("PAIRS", "").strip()
    if pairs_env:
        result = []
        for item in pairs_env.split(","):
            item = item.strip()
            if ":" in item:
                pair, base = item.split(":", 1)
                result.append({"pair": pair.strip(), "base": base.strip()})
            else:
                base = item.replace("USDT", "").replace("BUSD", "")
                result.append({"pair": item, "base": base})
        if result:
            return result

    # 2. Dynamic scanner — top N by volume
    try:
        from bot.pair_scanner import get_top_pairs
        n_pairs = int(os.getenv("NUM_PAIRS", str(n)))
        dynamic = get_top_pairs(n_pairs)
        if dynamic:
            return dynamic
    except Exception as e:
        logger.warning(f"Dynamic pair scan failed: {e}")

    # 3. Fallback
    return FALLBACK_PAIRS

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


def _log_trade(action: str, pair: str, qty: float, price: float, pnl: float = 0.0):
    """Log trade to CSV file."""
    import csv
    import os
    os.makedirs("logs", exist_ok=True)
    path = "logs/trades.csv"
    header_needed = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as f:
        if header_needed:
            f.write("timestamp,action,pair,qty,price,pnl\n")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        csv.writer(f).writerow([ts, action, pair, f"{qty:.6f}", f"{price:.2f}", f"{pnl:.2f}"])


def _trade_pair(
    pair_info: dict,
    config: TradingConfig,
    state: BotState,
) -> None:
    """Execute one trading cycle for a single pair (crypto or stock)."""
    pair = pair_info["pair"]
    base = pair_info["base"]
    market = pair_info.get("market", "crypto")

    # ── Stock market hours check ──
    if market == "stock":
        try:
            from bot.stocks import is_market_open
            if not is_market_open():
                return  # Skip stocks outside trading hours
        except Exception:
            pass

    # ── Step 1: Pre-trade guards ──
    if not state.is_in_position:
        guard = check_guards(config, state)
        if guard:
            return  # Skip this pair

    # ── Step 2: Fetch market data (route by market type) ──
    try:
        if market == "stock":
            from bot.stocks import fetch_stock_klines
            df = fetch_stock_klines(pair, config.interval, lookback=300)
        else:
            df = fetch_klines(pair, config.interval, lookback=300)

        if df is None or len(df) < 20:
            return
        df = add_indicators(df)
        if len(df) < 50:
            return
    except Exception as e:
        logger.warning(f"[{pair}] Data fetch failed: {e}")
        return

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
            logger.info(f"[{pair}] 📈 Trailing activated: +{upnl*100:.2f}%")

        # Check exit conditions
        decision = should_close_position(
            pos.entry_price, px, pos.atr_at_entry,
            pos.bars_held, pos.peak_pnl, pos.trailing_active,
            config,
        )

        if decision:
            pnl = state.close_position(px)
            execute_sell(px, pos.quantity, config, state)
            _log_trade("SELL", pair, pos.quantity, px, pnl)

            emoji = "✅" if pnl > 0 else "⚠️"
            pnl_pct = (px / pos.entry_price - 1.0) * 100
            msg = f"[{pair}] {emoji} {decision} | {pnl_pct:+.2f}% | PnL: ${pnl:+.2f} | Daily: ${state.daily_pnl:+.2f}"
            logger.info(msg)
            _notify(config, msg)

            if state.loss_streak >= config.loss_streak_cooldown:
                state.trigger_cooldown(config.cooldown_minutes)
                logger.info(f"[{pair}] ⏸️ Cooldown: {config.cooldown_minutes}min")

            state.save(f"logs/state_{pair}.json")

    # ── Step 4: Look for new entry ──
    elif not state.is_in_position:
        signal = compute_signals(
            df,
            entry_score_min=config.entry_score_min,
            rsi_min=config.rsi_min,
            rsi_max=config.rsi_max,
            ml_confidence=0.5,
            ml_threshold=config.ml_threshold,
        )

        # ── Enrichment: Market Intelligence ──
        try:
            from bot.market_intel import MarketIntelligence
            mi = MarketIntelligence()
            mi.enabled = True
            intel_boost = mi.get_entry_score_adjustment()
            if abs(intel_boost) > 0.01:
                signal.score += intel_boost
                signal.signals.append(f"INTEL({intel_boost:+.3f})")
        except Exception:
            pass

        # ── Enrichment: Multi-Timeframe Alignment ──
        try:
            from bot.multi_tf import get_mtf_boost
            mtf_boost = get_mtf_boost(pair)
            if abs(mtf_boost) > 0.01:
                signal.score += mtf_boost
                signal.signals.append(f"MTF({mtf_boost:+.3f})")
        except Exception:
            pass

        # Recheck buy after enrichments
        signal.should_buy = signal.score >= config.entry_score_min

        # ── ML Feature Collection: record EVERY evaluation ──
        try:
            from bot.ml_collector import record_evaluation
            intel_data = None
            try:
                intel_data = mi.get_market_intelligence() if mi else None
            except Exception:
                pass
            record_evaluation(
                pair=pair,
                df=df,
                signal=signal,
                intel_data=intel_data,
                mtf_boost=mtf_boost if 'mtf_boost' in dir() else 0.0,
                action="BUY" if signal.should_buy else "SKIP",
            )
        except Exception:
            pass  # ML collection is optional

        # Log status
        logger.info(
            f"[{pair}] {'→' if signal.should_buy else '·'} "
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
                qty = max(qty, 50.0 / max(px, 1))

            if execute_buy(px, qty, config, state):
                state.open_position(px, qty, atr)
                _log_trade("BUY", pair, qty, px)

                entry_type = signal.signals[0] if signal.signals else "SIGNAL"
                msg = (
                    f"[{pair}] ▶️ LONG {base} ({entry_type}) "
                    f"@ ${px:,.2f} | Size: ${qty*px:,.2f} | "
                    f"Score: {signal.score:.3f} | "
                    f"Signals: {', '.join(signal.signals)}"
                )
                logger.info(msg)
                _notify(config, msg)
                state.save(f"logs/state_{pair}.json")


def run(config: TradingConfig | None = None):
    """
    Main trading loop — Multi-Pair.

    Rotates through all configured pairs, each with independent state.
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

    # Get pairs and create per-pair states
    pairs = _get_pairs()
    states: dict[str, BotState] = {}
    for p in pairs:
        pair_key = p["pair"]
        state = BotState.load(f"logs/state_{pair_key}.json")
        state.paper_balance = max(state.paper_balance, config.paper_balance / len(pairs))
        state.check_new_day()
        states[pair_key] = state

    # ── Add stock pairs if enabled ──
    enable_stocks = os.getenv("ENABLE_STOCKS", "true").lower() in ("true", "1", "yes")
    if enable_stocks:
        try:
            from bot.stocks import DEFAULT_STOCK_PAIRS
            stock_pairs = DEFAULT_STOCK_PAIRS[:int(os.getenv("NUM_STOCKS", "10"))]
            for sp in stock_pairs:
                if sp["pair"] not in states:
                    st = BotState.load(f"logs/state_{sp['pair']}.json")
                    st.paper_balance = config.paper_balance / (len(pairs) + len(stock_pairs))
                    st.check_new_day()
                    states[sp["pair"]] = st
            pairs = pairs + stock_pairs
            logger.info(f"📈 Stocks enabled: {[s['pair'] for s in stock_pairs]}")
        except Exception as e:
            logger.warning(f"Stock init failed: {e}")

    mode = "PAPER" if config.paper_mode else "LIVE"
    crypto_count = sum(1 for p in pairs if p.get("market", "crypto") == "crypto")
    stock_count = sum(1 for p in pairs if p.get("market") == "stock")
    total_balance = sum(s.paper_balance for s in states.values())
    logger.info(f"═══ Ethbot v3 Multi-Asset Starting ═══")
    logger.info(f"Mode: {mode} | Crypto: {crypto_count} | Stocks: {stock_count} | Total: {len(pairs)}")
    logger.info(f"Interval: {config.interval} | Total Balance: ${total_balance:,.2f}")
    logger.info(f"Per-Pair Balance: ${config.paper_balance / max(len(pairs), 1):,.2f}")
    logger.info(f"Max trades/day: {config.max_trades_per_day} | Entry min: {config.entry_score_min}")

    _notify(config, f"🤖 Ethbot v3 [{mode}] | {crypto_count} crypto + {stock_count} stocks | ${total_balance:,.0f}")

    loop_count = 0

    # ═══════════════════════════════════════════════
    # MAIN LOOP — rotate through all pairs
    # ═══════════════════════════════════════════════
    while not _shutdown.is_set():
        try:
            loop_count += 1

            # ── Refresh pairs every 30 loops (~1 hour) ──
            if loop_count % 30 == 1 and loop_count > 1:
                try:
                    new_pairs = _get_pairs()
                    if new_pairs and new_pairs != pairs:
                        # Add states for new pairs
                        for p in new_pairs:
                            pk = p["pair"]
                            if pk not in states:
                                st = BotState.load(f"logs/state_{pk}.json")
                                st.paper_balance = config.paper_balance / len(new_pairs)
                                st.check_new_day()
                                states[pk] = st
                        pairs = new_pairs
                        logger.info(f"Pairs refreshed: {[p['pair'] for p in pairs]}")
                except Exception:
                    pass  # Keep using current pairs

            for pair_info in pairs:
                if _shutdown.is_set():
                    break

                pair_key = pair_info["pair"]
                state = states[pair_key]
                state.check_new_day()

                try:
                    _trade_pair(pair_info, config, state)
                except Exception as e:
                    logger.error(f"[{pair_key}] Error: {e}", exc_info=True)

                # Small delay between pairs to avoid rate limits
                time.sleep(2)

            # ── Periodic ML backfill: label past evaluations with outcomes ──
            if loop_count % 10 == 0:
                try:
                    from bot.ml_collector import backfill_outcomes, get_stats
                    for p in pairs:
                        backfill_outcomes(p["pair"])
                    stats = get_stats()
                    if stats["total_evaluations"] > 0:
                        logger.info(
                            f"ML Data: {stats['total_evaluations']} evals | "
                            f"{stats['total_labeled']} labeled | "
                            f"{stats['total_buys']} buys | "
                            f"Ready: {stats['ready_for_training']}"
                        )
                except Exception:
                    pass

            # ── Sleep between full rotations ──
            _shutdown.wait(config.loop_sleep_seconds)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Loop error: {e}", exc_info=True)
            _shutdown.wait(30)

    # Shutdown — save all states
    logger.info("Ethbot shutting down...")
    for pair_key, state in states.items():
        state.save(f"logs/state_{pair_key}.json")
    _notify(config, "🛑 Ethbot gestoppt")


if __name__ == "__main__":
    run()
