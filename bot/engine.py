from __future__ import annotations
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
    except Exception as e:
        logger.debug(f"Non-critical: {e}")


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
        except Exception as e:
            logger.debug(f"Non-critical: {e}")

    # ── Step 0: Circuit Breaker check ──
    try:
        from bot.shield import get_circuit_breaker
        cb = get_circuit_breaker()
        if not cb.is_trading_allowed():
            return  # ALL trading halted
    except Exception as e:
        logger.debug(f"Non-critical: {e}")

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

            # ── Brain: Learn from this trade ──
            try:
                from bot.brain import get_brain
                brain = get_brain()
                brain.record_trade_result(
                    pair=pair,
                    entry_price=pos.entry_price,
                    exit_price=px,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    signals_used=getattr(pos, 'entry_signals', []),
                    regime=getattr(pos, 'entry_regime', 'unknown'),
                    hold_bars=pos.bars_held,
                )
                # Track strategy combo
                sig_combo = "+".join(sorted(getattr(pos, 'entry_signals', [])))
                if sig_combo:
                    brain.record_strategy_result(sig_combo, pnl_pct, getattr(pos, 'entry_regime', 'unknown'))
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

            # ── Experience Memory: record outcome ──
            try:
                from bot.experience import get_memory
                get_memory().record_outcome(pair, pnl_pct)
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

            # ── Shield: Circuit Breaker + Portfolio Guard ──
            try:
                from bot.shield import get_circuit_breaker, get_portfolio_guard
                get_circuit_breaker().record_trade(pnl, state.paper_balance)
                get_portfolio_guard().close_position(pair)
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

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
        except Exception as e:
            logger.debug(f"Non-critical: {e}")

        # ── Enrichment: Multi-Timeframe Alignment ──
        try:
            from bot.multi_tf import get_mtf_boost
            mtf_boost = get_mtf_boost(pair)
            if abs(mtf_boost) > 0.01:
                signal.score += mtf_boost
                signal.signals.append(f"MTF({mtf_boost:+.3f})")
        except Exception as e:
            logger.debug(f"Non-critical: {e}")

        # ── Brain: Record evaluation + get intelligence ──
        brain_confidence = 1.0
        try:
            from bot.brain import get_brain
            brain = get_brain()
            brain.record_evaluation(pair, signal, signal.regime, px,
                                    "BUY" if signal.should_buy else "SKIP",
                                    market=market)
            # Brain confidence adjustment
            brain_confidence = brain.get_pair_confidence(pair)
            regime_adj = brain.get_regime_adjustment(signal.regime)
            if abs(regime_adj) > 0.001:
                signal.score += regime_adj
                signal.signals.append(f"BRAIN({regime_adj:+.3f})")

            # Brain blocks underperforming pairs
            if not brain.should_trade_pair(pair):
                signal.should_buy = False
        except Exception as e:
            logger.debug(f"Non-critical: {e}")

        # ── Experience Memory: "Have I seen this before?" ──
        try:
            from bot.experience import get_memory
            exp_mem = get_memory()
            # Build feature dict for similarity search
            exp_features = {
                "rsi14": signal.rsi, "adx14": signal.adx,
                "atr_pct": float(row.get("atr", 0)) / max(px, 1) * 100,
                "macd_norm": float(row.get("macd", 0)),
                "volume_ratio": float(row.get("volume", 0)) / max(float(df["volume"].mean()), 1),
                "bb_position": float(row.get("bb_pct", 0.5)),
                "vwap_dev": float(row.get("vwap_dev", 0)),
                "trend_strength": signal.score,
                "fg_value": 0, "news_sentiment": 0,
                "funding_rate": 0, "oi_signal": 0,
                "mtf_boost": mtf_boost if 'mtf_boost' in dir() else 0,
                "score": signal.score,
            }
            # Record this experience
            exp_mem.record(pair, exp_features,
                          "BUY" if signal.should_buy else "SKIP",
                          signal.signals, signal.regime)
            # Get wisdom from similar past experiences
            wisdom = exp_mem.get_wisdom(exp_features, pair)
            if wisdom["similar_count"] >= 5:
                if wisdom["recommendation"] == "SKIP" and wisdom["confidence"] > 0.6:
                    signal.signals.append(f"MEMORY(SKIP:{wisdom['historical_winrate']:.0%})")
                    signal.should_buy = False
                elif wisdom["recommendation"] == "BUY" and wisdom["confidence"] > 0.5:
                    signal.signals.append(f"MEMORY(BUY:{wisdom['historical_winrate']:.0%})")
        except Exception as e:
            logger.debug(f"Non-critical: {e}")

        # Recheck buy after all enrichments
        # Brain is advisory, not a hard gate — let the Swarm decide
        signal.should_buy = signal.score >= config.entry_score_min
        if brain_confidence < 0.4 and brain_confidence > 0:
            # Brain actively says NO — apply score penalty
            signal.score -= 0.05
            signal.signals.append(f"BRAIN_WARN({brain_confidence:.2f})")

        # ── ML Feature Collection: record EVERY evaluation ──
        try:
            from bot.ml_collector import record_evaluation
            intel_data = None
            try:
                intel_data = mi.get_market_intelligence() if mi else None
            except Exception as e:
                logger.debug(f"Non-critical: {e}")
            record_evaluation(
                pair=pair,
                df=df,
                signal=signal,
                intel_data=intel_data,
                mtf_boost=mtf_boost if 'mtf_boost' in dir() else 0.0,
                action="BUY" if signal.should_buy else "SKIP",
            )
        except Exception as e:
            logger.debug(f"Non-critical: {e}")  # ML collection is optional

        # ── SWARM CONSENSUS: All agents vote ──
        swarm_approved = False
        try:
            from bot.swarm import get_swarm
            swarm = get_swarm()
            # Gather real intel data for the swarm
            fg_value = 0
            news_sentiment = 0
            funding_rate = 0
            oi_signal = 0
            intel_composite = 0
            try:
                if mi:
                    idata = mi.get_market_intelligence()
                    fg_value = idata.get("fear_greed", {}).get("value", 0)
                    news_sentiment = idata.get("news_sentiment", {}).get("signal", 0)
                    funding_rate = idata.get("funding_rate", {}).get("rate", 0)
                    oi_signal = idata.get("open_interest", {}).get("signal", 0)
                    intel_composite = mi.get_composite_score()
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

            swarm_data = {
                "pair": pair, "rsi": signal.rsi, "adx": signal.adx,
                "macd": float(row.get("macd", 0)),
                "macd_signal": float(row.get("macd_signal", 0)),
                "macd_hist": float(row.get("macd_hist", 0)),
                "bb_pct": float(row.get("bb_pct", 0.5)),
                "volume_ratio": float(row.get("volume", 0)) / max(float(df["volume"].mean()), 1),
                "vwap_dev": float(row.get("vwap_dev", 0)),
                "atr_pct": atr / max(px, 1) * 100,
                "regime": signal.regime, "score": signal.score,
                "mtf_boost": mtf_boost if 'mtf_boost' in dir() else 0,
                "fg_value": fg_value,
                "news_sentiment": news_sentiment,
                "funding_rate": funding_rate,
                "oi_signal": oi_signal,
                "intel_composite": intel_composite,
                "signal_count": len(signal.signals),
            }
            decision = swarm.decide(swarm_data)
            swarm_approved = decision.approved

            # Log swarm decision
            logger.info(
                f"[{pair}] 🐝 Swarm: {decision.buy_votes}/{decision.total_agents} BUY "
                f"({decision.consensus_pct:.0%}) | "
                f"Weight: {decision.weighted_score:+.3f} | "
                f"{'✅ APPROVED' if decision.approved else '· SKIP'} | "
                f"{decision.reasoning}"
            )
        except Exception as e:
            # Fallback to old score-based decision
            logger.debug(f"Swarm fallback: {e}")
            swarm_approved = signal.should_buy

        if swarm_approved:
            qty = position_size(px, atr, config, state)
            cost = qty * px

            if cost < 10:
                qty = max(qty, 50.0 / max(px, 1))

            # ── Portfolio Guard: check exposure ──
            can_trade = True
            try:
                from bot.shield import get_portfolio_guard
                pg = get_portfolio_guard()
                allowed, reason = pg.can_open_position(pair, qty * px)
                if not allowed:
                    logger.info(f"[{pair}] 🛡️ Portfolio Guard: {reason}")
                    can_trade = False
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

            if can_trade and execute_buy(px, qty, config, state):
                state.open_position(px, qty, atr)
                _log_trade("BUY", pair, qty, px)

                # Register position with portfolio guard
                try:
                    get_portfolio_guard().register_position(pair, qty * px)
                except Exception as e:
                    logger.debug(f"Non-critical: {e}")

                msg = (
                    f"[{pair}] ▶️ LONG {base} (SWARM {decision.buy_votes}/{decision.total_agents}) "
                    f"@ ${px:,.2f} | Size: ${qty*px:,.2f} | "
                    f"Consensus: {decision.consensus_pct:.0%} | "
                    f"Signals: {', '.join(signal.signals)}"
                )
                logger.info(msg)
                _notify(config, msg)
                state.save(f"logs/state_{pair}.json")


def _run_strategy_cycle(config: TradingConfig, loop_count: int):
    """
    Execute one strategy evaluation cycle.
    Runs S1/S2/S4/S5 strategies + Master Allocator risk checks.
    """
    # ── Allocator Risk Check (EVERY loop — this is the kill switch) ──
    try:
        from bot.strategies.allocator import get_allocator
        allocator = get_allocator()
        risk = allocator.check_global_risk()
        if risk["kill_switch"]:
            logger.error("🚨 ALLOCATOR KILL SWITCH ACTIVE — Halting all strategy trades")
            return
    except Exception as e:
        logger.debug(f"Allocator check: {e}")

    # ── S5: Liquidation Hunter — Check EVERY loop (time-critical) ──
    try:
        from bot.strategies.liquidation_hunter import get_liq_hunter
        hunter = get_liq_hunter()

        # Start monitoring on first call
        if not hunter._running:
            hunter.start_monitoring()

        cascade = hunter.detect_cascade()
        if cascade:
            logger.info(
                f"🎯 LIQ CASCADE: {cascade.symbol} | ${cascade.cascade_usd/1e6:.1f}M | "
                f"Direction: {cascade.direction} | Confidence: {cascade.confidence:.0%}"
            )
            # Check allocator allows this trade
            capital = allocator.get_allocation("S5_LiqHunter") if allocator else 0
            if capital and capital > 0:
                logger.info(
                    f"🎯 S5 Signal: {cascade.direction} {cascade.symbol} | "
                    f"Entry: ${cascade.entry_price:,.2f} | "
                    f"TP: +{cascade.target_pct:.1%} | SL: -{cascade.stop_pct:.1%} | "
                    f"Capital: ${capital:,.0f}"
                )
                # TODO: Execute via executor when Futures API integrated
    except Exception as e:
        logger.debug(f"S5 check: {e}")

    # ── S1: Funding Rate Arb — Scan every 30 loops (~1 hour) ──
    if loop_count % 30 == 5:  # Offset from pair refresh at %30==1
        try:
            from bot.strategies.funding_arb import get_funding_arb
            arb = get_funding_arb()
            opps = arb.scan_opportunities()

            for opp in opps:
                if arb.should_enter(opp):
                    capital = allocator.get_allocation("S1_FundingArb") if allocator else 0
                    if capital and capital > 0:
                        logger.info(
                            f"💰 S1 Opportunity: {opp.symbol} | "
                            f"Funding: {opp.funding_rate:.4%}/8h ({opp.annualized:.1%} p.a.) | "
                            f"Net edge: {opp.net_edge_per_8h:.4%} | OI: ${opp.oi_usd/1e6:.0f}M | "
                            f"Capital: ${capital:,.0f}"
                        )
                        # TODO: Execute Long Spot + Short Perp when Futures API integrated

            # Check exits
            for sym in list(arb.positions.keys()):
                if arb.should_exit(sym):
                    logger.info(f"💰 S1 EXIT: {sym} — funding rate dropped")
                    # TODO: Execute unwind

        except Exception as e:
            logger.debug(f"S1 scan: {e}")

    # ── S2: Stat Arb — Rescan pairs daily, check signals every 10 loops ──
    if loop_count % 10 == 3:  # Offset from ML backfill at %10==0
        try:
            from bot.strategies.stat_arb import get_stat_arb
            stat = get_stat_arb()

            # Daily cointegration rescan
            if loop_count % 720 == 3:  # ~24 hours at 2-min loops
                stat.find_cointegrated_pairs()

            # Generate signals on existing pairs
            if stat.pairs:
                signals = stat.generate_signals()
                for sig_data in signals:
                    pair = sig_data["pair"]
                    action = sig_data["action"]
                    z = sig_data["zscore"]
                    capital = allocator.get_allocation("S2_StatArb") if allocator else 0

                    if action in ("LONG_A_SHORT_B", "SHORT_A_LONG_B") and capital and capital > 0:
                        logger.info(
                            f"📊 S2 Signal: {action} {pair.asset_a}/{pair.asset_b} | "
                            f"Z-Score: {z:.2f} | Hedge: {pair.hedge_ratio:.4f} | "
                            f"p-value: {pair.pvalue:.4f} | Capital: ${capital:,.0f}"
                        )
                        # TODO: Execute paired trade when margin available

                    elif action in ("EXIT", "STOP"):
                        logger.info(
                            f"📊 S2 {action}: {pair.asset_a}/{pair.asset_b} | "
                            f"Z-Score: {z:.2f} | Reason: {sig_data.get('reason', 'n/a')}"
                        )

        except Exception as e:
            logger.debug(f"S2 check: {e}")

    # ── Strategy status log (every 50 loops) ──
    if loop_count % 50 == 0:
        try:
            from bot.strategies.allocator import get_allocator
            alloc = get_allocator()
            status = alloc.get_status()
            logger.info(
                f"🎛️ Allocator: ${status['total_equity']:,.0f} equity | "
                f"DD: {status['drawdown_pct']:.1f}% | Kill: {status['kill_switch']} | "
                + " | ".join(
                    f"{sid}: {s['weight']:.0f}%({s['status'][0]})"
                    for sid, s in status['strategies'].items()
                    if s['weight'] > 0
                )
            )
        except Exception as e:
            logger.debug(f"Allocator status: {e}")


def run(config: TradingConfig | None = None):
    """
    Main trading loop — Multi-Pair + Multi-Strategy.

    Rotates through all configured pairs, each with independent state.
    Additionally runs S1/S2/S4/S5 strategies as periodic tasks.
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

    # Initialize Brain + Experience Memory + Genetic Evolver
    try:
        from bot.brain import get_brain
        brain = get_brain()
        status = brain.get_status()
        logger.info(f"🧠 Brain Stage: {status['stage']}")
        logger.info(f"🧠 Known pairs: {status['pairs_known']} | Lessons: {status['lessons_learned']} | Patterns: {status['patterns_discovered']}")
    except Exception as e:
        logger.warning(f"Brain init: {e}")
        brain = None

    try:
        from bot.experience import get_memory, get_evolver
        exp_mem = get_memory()
        evolver = get_evolver()
        logger.info(f"💾 Experience Memory: {exp_mem.get_stats()['total_experiences']} experiences")
        logger.info(f"🧬 Genetic Evolver: Gen #{evolver.generation} | {len(evolver.population)} strategies")
    except Exception as e:
        logger.warning(f"Experience init: {e}")

    try:
        from bot.swarm import get_swarm
        swarm = get_swarm()
    except Exception as e:
        logger.warning(f"Swarm init: {e}")

    try:
        from bot.shield import get_circuit_breaker, get_portfolio_guard
        cb = get_circuit_breaker()
        pg = get_portfolio_guard()
        logger.info(f"🛡️ Shield: Circuit Breaker (max -{cb.max_daily_loss_pct}% daily) | Portfolio Guard (max {pg.max_positions} positions)")
    except Exception as e:
        logger.warning(f"Shield init: {e}")

    # ── Initialize Strategy Framework ──
    allocator = None
    try:
        from bot.strategies.allocator import get_allocator
        allocator = get_allocator()
        logger.info(f"🎛️ Master Allocator: ${allocator.state.total_equity:,.0f} | 5 strategies registered")
    except Exception as e:
        logger.warning(f"Allocator init: {e}")

    try:
        from bot.strategies.funding_arb import get_funding_arb
        fa = get_funding_arb()
        logger.info(f"💰 S1 Funding Arb: {len(fa.UNIVERSE)} pairs monitored")
    except Exception as e:
        logger.warning(f"S1 init: {e}")

    try:
        from bot.strategies.stat_arb import get_stat_arb
        sa = get_stat_arb()
        logger.info(f"📊 S2 Stat Arb: {len(sa.UNIVERSE)} assets")
    except Exception as e:
        logger.warning(f"S2 init: {e}")

    try:
        from bot.strategies.momentum_v2 import get_momentum
        mom = get_momentum()
        logger.info(f"📈 S4 Momentum V2: Hurst regime filter active")
    except Exception as e:
        logger.warning(f"S4 init: {e}")

    try:
        from bot.strategies.liquidation_hunter import get_liq_hunter
        lh = get_liq_hunter()
        lh.start_monitoring()
        logger.info(f"🎯 S5 Liquidation Hunter: Monitoring {len(lh.MONITOR_SYMBOLS)} symbols")
    except Exception as e:
        logger.warning(f"S5 init: {e}")

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
    logger.info(f"═══ Ethbot v3 Multi-Strategy Starting ═══")
    logger.info(f"Mode: {mode} | Crypto: {crypto_count} | Stocks: {stock_count} | Total: {len(pairs)}")
    logger.info(f"Strategies: S1(FundingArb) + S2(StatArb) + S4(Momentum) + S5(LiqHunter)")
    logger.info(f"Interval: {config.interval} | Total Balance: ${total_balance:,.2f}")
    logger.info(f"Per-Pair Balance: ${config.paper_balance / max(len(pairs), 1):,.2f}")
    logger.info(f"Max trades/day: {config.max_trades_per_day} | Entry min: {config.entry_score_min}")

    _notify(config, f"🤖 Ethbot v3 [{mode}] | {crypto_count} crypto + {stock_count} stocks | S1+S2+S4+S5 | ${total_balance:,.0f}")

    loop_count = 0

    # ═══════════════════════════════════════════════
    # MAIN LOOP — rotate through all pairs + run strategies
    # ═══════════════════════════════════════════════
    while not _shutdown.is_set():
        try:
            loop_count += 1

            # ── Run strategy framework (S1/S2/S4/S5 + Allocator) ──
            try:
                _run_strategy_cycle(config, loop_count)
            except Exception as e:
                logger.error(f"Strategy cycle error: {e}", exc_info=True)

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
                except Exception as e:
                    logger.debug(f"Non-critical: {e}")  # Keep using current pairs

            # ── S4: Momentum V2 — Evaluate during per-pair loop ──
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

                # S4: Run Momentum V2 on same data (if crypto)
                if pair_info.get("market", "crypto") == "crypto":
                    try:
                        from bot.strategies.momentum_v2 import get_momentum
                        mom = get_momentum()
                        df = fetch_klines(pair_key, config.interval, lookback=300)
                        if df is not None and len(df) >= 200:
                            df = add_indicators(df)
                            signal = mom.analyze(pair_key, df)
                            if signal and signal.rr_ratio >= 1.5:
                                from bot.strategies.allocator import get_allocator
                                capital = get_allocator().get_allocation("S4_MomentumV2")
                                if capital and capital > 0:
                                    size = mom.volatility_target_size(
                                        capital, signal.atr, signal.entry
                                    )
                                    logger.info(
                                        f"📈 S4 Signal: {signal.side} {pair_key} | "
                                        f"Regime: {signal.regime} (H={signal.hurst:.2f}) | "
                                        f"Entry: ${signal.entry:,.2f} → "
                                        f"TP: ${signal.target:,.2f} / SL: ${signal.stop:,.2f} | "
                                        f"R:R {signal.rr_ratio:.1f} | "
                                        f"Vol-sized: {size:.4f} units | "
                                        f"{'✅ VOL' if signal.volume_confirmed else '⚠️ no vol'}"
                                    )
                    except Exception as e:
                        logger.debug(f"S4 {pair_key}: {e}")

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
                            f"{stats['total_labeled']} labeled (Triple-Barrier) | "
                            f"{stats['total_buys']} buys | "
                            f"Ready: {stats['ready_for_training']}"
                        )
                except Exception as e:
                    logger.debug(f"Non-critical: {e}")

            # ── Brain: Periodic evolution tasks ──
            if loop_count % 20 == 0:
                try:
                    from bot.brain import get_brain
                    b = get_brain()
                    # Auto-train ML model when enough data
                    b.maybe_train_model()
                    # Discover patterns every 50 loops
                    if loop_count % 50 == 0:
                        b.discover_patterns()
                    # Log brain status
                    bs = b.get_status()
                    logger.info(
                        f"🧠 Brain: {bs['stage']} | "
                        f"{bs['total_trades']} trades | "
                        f"{bs['winrate']:.0%} WR | "
                        f"${bs['lifetime_pnl']:+,.2f} | "
                        f"{bs['pairs_known']} pairs known"
                    )
                except Exception as e:
                    logger.debug(f"Non-critical: {e}")

            # ── Allocator: Weekly rebalance ──
            if loop_count % 5040 == 0:  # ~weekly at 2-min loops
                try:
                    from bot.strategies.allocator import get_allocator
                    get_allocator().rebalance()
                except Exception as e:
                    logger.debug(f"Rebalance: {e}")

            # ── Sleep between full rotations ──
            _shutdown.wait(config.loop_sleep_seconds)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Loop error: {e}", exc_info=True)
            _shutdown.wait(30)

    # Shutdown — save all states + brain + strategies
    logger.info("Ethbot shutting down...")
    for pair_key, state in states.items():
        state.save(f"logs/state_{pair_key}.json")
    try:
        from bot.brain import get_brain
        get_brain().save_memory()
        get_brain().save_strategies()
        logger.info("🧠 Brain memory saved")
    except Exception as e:
        logger.debug(f"Non-critical: {e}")
    try:
        from bot.strategies.liquidation_hunter import get_liq_hunter
        get_liq_hunter().stop_monitoring()
        logger.info("🎯 Liquidation Hunter stopped")
    except Exception as e:
        logger.debug(f"Non-critical: {e}")
    try:
        from bot.strategies.allocator import get_allocator
        get_allocator()._save_state()
        logger.info("🎛️ Allocator state saved")
    except Exception as e:
        logger.debug(f"Non-critical: {e}")
    _notify(config, "🛑 Ethbot v3 gestoppt — alle Strategien beendet")


if __name__ == "__main__":
    run()
