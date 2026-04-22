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
from bot.executor import execute_buy, execute_sell, fetch_klines

logger = logging.getLogger("ethbot.engine")

# Focused pair universe — top 8 by volatility + liquidity for maximum ROI
FALLBACK_PAIRS = [
    {"pair": "BTCUSDT", "base": "BTC"},
    {"pair": "ETHUSDT", "base": "ETH"},
    {"pair": "SOLUSDT", "base": "SOL"},
    {"pair": "BNBUSDT", "base": "BNB"},
    {"pair": "DOGEUSDT", "base": "DOGE"},
    {"pair": "AVAXUSDT", "base": "AVAX"},
    {"pair": "LINKUSDT", "base": "LINK"},
    {"pair": "SUIUSDT", "base": "SUI"},
]


def _get_pairs(n: int = 8) -> list:
    """
    Get trading pairs — dynamic from Binance or env override.
    Priority: PAIRS env var > Dynamic scanner > Fallback.
    Always returns at least 8 pairs by merging scanner + fallback.
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
    dynamic = []
    try:
        from bot.pair_scanner import get_top_pairs
        n_pairs = int(os.getenv("NUM_PAIRS", str(n)))
        dynamic = get_top_pairs(n_pairs)
        if dynamic:
            logger.info(f"Dynamic scanner: {len(dynamic)} pairs found")
    except Exception as e:
        logger.warning(f"Dynamic pair scan failed: {e}")

    # 3. Merge: scanner pairs + fallback to guarantee minimum 8
    seen = set()
    merged = []
    for p in dynamic:
        if p["pair"] not in seen:
            seen.add(p["pair"])
            merged.append(p)
    # Fill up with fallback pairs
    for p in FALLBACK_PAIRS:
        if p["pair"] not in seen:
            seen.add(p["pair"])
            merged.append(p)

    if len(merged) > len(dynamic):
        added = len(merged) - len(dynamic)
        logger.info(f"Merged {len(dynamic)} scanner + {added} fallback = {len(merged)} total pairs")

    return merged if merged else FALLBACK_PAIRS

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
    """Log trade to CSV file AND PostgreSQL (for deploy persistence)."""
    import csv
    import os
    os.makedirs("logs", exist_ok=True)
    path = "logs/trades.csv"
    header_needed = not os.path.exists(path) or os.path.getsize(path) == 0
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", newline="") as f:
        if header_needed:
            f.write("timestamp,action,pair,qty,price,pnl\n")
        csv.writer(f).writerow([ts, action, pair, f"{qty:.6f}", f"{price:.2f}", f"{pnl:.2f}"])
    
    # Persist to PostgreSQL (survives Railway deploys)
    try:
        from trade_store import save_trade
        save_trade(ts, action, pair, qty, price, pnl)
    except Exception:
        pass  # CSV is the backup


def _trade_pair(
    pair_info: dict,
    config: TradingConfig,
    state: BotState,
    pool_equity: float = 0.0,
) -> None:
    """Execute one trading cycle for a single pair (crypto or stock).
    
    pool_equity: Total available capital pool (total - locked in other positions).
                 Used for dynamic position sizing — strong signals get more capital.
    """
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

        # Detect MACD bearish crossover for momentum exit
        macd_val = float(row.get("macd", 0))
        macd_sig_val = float(row.get("macd_sig", 0))
        prev_row = df.iloc[-2] if len(df) >= 2 else row
        prev_macd = float(prev_row.get("macd", 0))
        prev_macd_sig = float(prev_row.get("macd_sig", 0))
        macd_bearish = (macd_val < macd_sig_val) and (prev_macd >= prev_macd_sig)

        # Check exit conditions (with partial profit + momentum)
        decision = should_close_position(
            pos.entry_price, px, pos.atr_at_entry,
            pos.bars_held, pos.peak_pnl, pos.trailing_active,
            config,
            partial_taken=pos.partial_taken,
            macd_bearish=macd_bearish,
        )

        if decision == "PARTIAL":
            # Close 50% of position, keep rest running
            half_qty = pos.quantity * 0.5
            partial_pnl = (px - pos.entry_price) * half_qty
            execute_sell(px, half_qty, config, state)
            _log_trade("PARTIAL_SELL", pair, half_qty, px, partial_pnl)
            pos.quantity -= half_qty
            pos.partial_taken = True
            state.paper_balance += partial_pnl
            state.daily_pnl += partial_pnl

            logger.info(
                f"[{pair}] 💰 PARTIAL +{upnl*100:.2f}% | "
                f"Sold 50% ({half_qty:.4f}) for ${partial_pnl:+.2f} | "
                f"Keeping {pos.quantity:.4f} with trailing"
            )
            pos.trailing_active = True  # Activate trailing on remainder
            state.save(f"logs/state_{pair}.json")

        elif decision:
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

            # ── Correlation Guard: remove closed position ──
            try:
                from bot.correlation import get_correlation_guard
                get_correlation_guard().close_position(pair)
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

            # ── Swarm: Learn from trade outcome ──
            try:
                from bot.swarm import get_swarm
                swarm = get_swarm()
                market_data = {
                    "close": px,
                    "rsi": float(row.get("rsi", 50)),
                    "macd": float(row.get("macd", 0)),
                    "adx": float(row.get("adx", 25)),
                    "bb_upper": float(row.get("bb_upper", px)),
                    "bb_lower": float(row.get("bb_lower", px)),
                    "volume": float(row.get("volume", 0)),
                    "atr": atr,
                    "vwap": float(row.get("vwap", px)),
                    "regime": getattr(pos, 'entry_regime', 'unknown'),
                }
                swarm.learn_from_outcome(market_data, was_profitable=(pnl > 0))
                logger.info(f"[{pair}] 🐝 Swarm learned from trade (profitable={pnl > 0})")
            except Exception as e:
                logger.debug(f"Non-critical swarm learning: {e}")

            # ── RL Optimizer: learn from trade outcome ──
            try:
                from bot.rl_optimizer import get_rl_optimizer
                rl = get_rl_optimizer()
                # Get the swarm votes that led to this trade
                from bot.swarm import get_swarm
                get_swarm()  # Ensure singleton is initialized
                trade_regime = getattr(pos, 'entry_regime', 'unknown')
                rl.learn_from_trade(
                    votes=decision.votes if 'decision' in dir() else [],
                    regime=trade_regime,
                    was_profitable=pnl > 0,
                )
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

            if state.loss_streak >= config.loss_streak_cooldown:
                state.trigger_cooldown(config.cooldown_minutes)
                logger.info(f"[{pair}] ⏸️ Cooldown: {config.cooldown_minutes}min")

            state.save(f"logs/state_{pair}.json")

    # ── Step 4: Look for new entry ──
    elif not state.is_in_position:
        # ── Brain Intelligence: Pre-filters ──
        brain_pair_confidence = 1.0
        adaptive_entry_score = config.entry_score_min

        try:
            from bot.brain import get_brain
            brain = get_brain()

            # M2: HOURLY FILTER — Skip hours with historically bad performance
            from datetime import datetime, timezone as tz
            current_hour = str(datetime.now(tz.utc).hour)
            hourly_data = brain.memory.get("hourly_performance", {}).get(current_hour, {})
            h_trades = hourly_data.get("trades", 0)
            h_wins = hourly_data.get("wins", 0)
            if h_trades >= 10:
                h_winrate = h_wins / h_trades
                if h_winrate < 0.30:
                    logger.info(f"[{pair}] 🕐 Brain: Hour {current_hour} UTC has {h_winrate:.0%} WR ({h_trades} trades) — skipping")
                    return

            # M3: ADAPTIVE ENTRY SCORE — Use brain's learned optimal threshold
            optimal = brain.get_optimal_threshold(pair)
            if optimal and optimal > 0:
                adaptive_entry_score = max(config.entry_score_min, optimal)

            # M1: PAIR CONFIDENCE — Scale conviction by historical performance
            brain_pair_confidence = brain.get_pair_confidence(pair)
        except Exception as e:
            logger.debug(f"Non-critical brain pre-filter: {e}")

        signal = compute_signals(
            df,
            entry_score_min=adaptive_entry_score,
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
                    idata = mi.get_market_intelligence(pair)
                    fg_value = idata.get("fear_greed", {}).get("value", 0)
                    news_sentiment = idata.get("news_sentiment", {}).get("signal", 0)
                    funding_rate = idata.get("funding_rate", {}).get("rate", 0)
                    oi_signal = idata.get("open_interest", {}).get("signal", 0)
                    intel_composite = mi.get_composite_score(pair)
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

            # ── On-Chain Intelligence: Whale + Exchange Flow ──
            onchain_signal = 0.0
            try:
                from bot.onchain import get_onchain
                oc = get_onchain()
                oc_data = oc.get_signal(pair)
                onchain_signal = oc_data.signal
                if abs(onchain_signal) > 0.3:
                    logger.info(f"[{pair}] 🔗 On-Chain: {onchain_signal:+.2f} | {oc_data.details}")
            except Exception as e:
                logger.debug(f"Non-critical: {e}")

            # ── Correlation Guard: Update price data ──
            try:
                from bot.correlation import get_correlation_guard
                get_correlation_guard().update_price(pair, px)
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
                "onchain_signal": onchain_signal,
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
            # EXPOSURE CHECK: Don't open if pool is nearly exhausted
            if pool_equity < config.paper_balance * 0.05:
                logger.info(f"[{pair}] 🛡️ Pool exhausted: ${pool_equity:,.0f} remaining — skipping")
            else:
              # M1: Scale confidence by brain's pair-specific knowledge
              adjusted_confidence = signal.score * brain_pair_confidence if 'brain_pair_confidence' in dir() else signal.score
              qty = position_size(
                px, atr, config, state,
                confidence=adjusted_confidence,
                swarm_pct=decision.consensus_pct,
                total_pool_equity=pool_equity,
              )
              # Apply leverage (3x default)
              qty *= min(config.leverage, config.max_leverage)
              cost = qty * px

              # Cap position at remaining pool equity (prevent over-allocation)
              max_cost = pool_equity * 0.60  # Never more than 60% of REMAINING pool
              if cost > max_cost and max_cost > 0:
                  qty = max_cost / max(px, 1)
                  cost = qty * px
                  logger.info(f"[{pair}] 🛡️ Position capped to ${cost:,.0f} (60% of remaining ${pool_equity:,.0f})")

              if cost < 10:
                qty = max(qty, 50.0 / max(px, 1))

              # ── Portfolio Guard + Correlation Guard ──
              can_trade = True

              # Check correlation with existing positions
              try:
                  from bot.correlation import get_correlation_guard
                  cg = get_correlation_guard()
                  corr_ok, corr_reason = cg.can_open_position(pair, "LONG")
                  if not corr_ok:
                      logger.info(f"[{pair}] 🔗 Correlation Guard: {corr_reason}")
                      can_trade = False
              except Exception as e:
                  logger.debug(f"Non-critical: {e}")

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
                  state.position.direction = "LONG"
                  _log_trade("BUY", pair, qty, px)

                  # Register position with portfolio guard + correlation guard
                  try:
                      get_portfolio_guard().register_position(pair, qty * px)
                  except Exception as e:
                      logger.debug(f"Non-critical: {e}")
                  try:
                      from bot.correlation import get_correlation_guard
                      get_correlation_guard().register_position(pair, "LONG")
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

        # ── SHORT SELLING: Bearish signals + swarm confirmation ──
        # LOOSENED CONDITIONS: Shorts should trigger in real bearish markets
        elif (not swarm_approved and not state.is_in_position
              and decision.weighted_score < -0.1          # Was -0.3 (too strict)
              and decision.skip_votes >= 2):              # Was 4 (too strict)

            # M4: DEDICATED SHORT SIGNALS
            short_signals = []
            short_score = 0.0

            # S1: MACD bearish crossover
            macd_val = float(row.get("macd", 0))
            macd_sig = float(row.get("macd_sig", 0))
            prev_row = df.iloc[-2] if len(df) >= 2 else row
            if macd_val < macd_sig and float(prev_row.get("macd", 0)) >= float(prev_row.get("macd_sig", 0)):
                short_signals.append("MACD_BEAR_CROSS")
                short_score += 0.20
            elif macd_val < macd_sig:
                # Already bearish (no fresh cross needed)
                short_signals.append("MACD_BEARISH")
                short_score += 0.10

            # S2: Price below EMAs (downtrend)
            ema20 = float(row.get("ema20", px))
            ema50 = float(row.get("ema50", px))
            if px < ema20 < ema50:
                short_signals.append("DOWNTREND")
                short_score += 0.15
            elif px < ema20:
                short_signals.append("BELOW_EMA20")
                short_score += 0.08

            # S3: RSI overbought / elevated
            rsi = signal.rsi
            if rsi > 60:
                short_signals.append("RSI_ELEVATED")
                short_score += 0.10
            if rsi > 70:
                short_score += 0.10  # Extra for overbought

            # S4: Bearish engulfing (big red candle after green)
            if len(df) >= 2:
                curr_open = float(row.get("open", px))
                curr_close = float(row.get("close", px))
                prev_open = float(prev_row.get("open", px))
                prev_close = float(prev_row.get("close", px))
                if (prev_close > prev_open and  # Previous was green
                    curr_close < curr_open and   # Current is red
                    curr_close < prev_open and   # Engulfs previous
                    curr_open > prev_close):
                    short_signals.append("BEARISH_ENGULF")
                    short_score += 0.15

            # S5: Breakdown below 20-period low
            ll20 = float(row.get("ll20", px))
            if px < ll20:
                short_signals.append("BREAKDOWN")
                short_score += 0.20

            # S6: Strong trend confirmation (ADX)
            if signal.adx > 20:
                short_signals.append("ADX_TREND")
                short_score += 0.08

            # S7: Volume confirmation
            vol_ratio = float(row.get("volume_ratio", 1.0))
            if vol_ratio >= 1.2:
                short_signals.append("VOL_CONFIRM")
                short_score += 0.08

            # S8: Price below VWAP (institutional selling pressure)
            vwap = float(row.get("vwap", px))
            if px < vwap * 0.998:  # Below VWAP with small buffer
                short_signals.append("BELOW_VWAP")
                short_score += 0.10

            # S9: Upper Bollinger reject (touched top and reversed)
            bb_upper = float(row.get("bb_upper", px * 1.1))
            bb_pct = float(row.get("bb_pct", 0.5))
            if bb_pct > 0.8 and curr_close < curr_open if len(df) >= 2 else False:
                short_signals.append("BB_UPPER_REJECT")
                short_score += 0.12

            # Require at least 2 bearish signals AND minimum score
            short_approved = len(short_signals) >= 2 and short_score >= 0.20

            if short_approved and signal.adx > 18 and signal.rsi > 45:

                qty = position_size(
                    px, atr, config, state,
                    confidence=abs(decision.weighted_score),
                    swarm_pct=1.0 - decision.consensus_pct,
                    total_pool_equity=pool_equity,
                )
                # Apply leverage (conservative for shorts: cap at 2x)
                short_leverage = min(config.leverage, config.max_leverage, 2.0)
                qty *= short_leverage
                cost = qty * px

                if cost >= 10:
                    # Paper mode: simulate short
                    if config.paper_mode:
                        state.open_position(px, qty, atr)
                        state.position.direction = "SHORT"
                        _log_trade("SHORT", pair, qty, px)

                        msg = (
                            f"[{pair}] 🔻 SHORT {base} (SWARM {decision.skip_votes}/{decision.total_agents} SKIP) "
                            f"@ ${px:,.2f} | Size: ${cost:,.2f} | "
                            f"Bearish: {', '.join(short_signals)} | Score: {short_score:.2f} | RSI: {signal.rsi:.0f}"
                        )
                        logger.info(msg)
                        _notify(config, msg)
                    else:
                        # Live mode: use margin executor
                        try:
                            from bot.margin_executor import get_margin_client
                            mc = get_margin_client()
                            result = mc.open_short(pair, qty)
                            if result:
                                state.open_position(px, qty, atr)
                                state.position.direction = "SHORT"
                                _log_trade("SHORT", pair, qty, px)
                                logger.info(f"[{pair}] 🔻 MARGIN SHORT {base} @ ${px:,.2f} | Qty: {qty:.5f}")
                        except Exception as e:
                            logger.warning(f"[{pair}] Margin short failed: {e}")

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
                # Execute paper trade for S5
                try:
                    s5_state = BotState.load(f"logs/state_S5_{cascade.symbol}.json")
                    s5_state.paper_balance = capital
                    s5_state.check_new_day()
                    if not s5_state.is_in_position:
                        qty = capital * 0.5 / max(cascade.entry_price, 0.01)  # 50% of allocation
                        if execute_buy(cascade.entry_price, qty, config, s5_state):
                            s5_state.open_position(cascade.entry_price, qty, cascade.entry_price * 0.02)
                            _log_trade("BUY", f"S5_{cascade.symbol}", qty, cascade.entry_price)
                            logger.info(f"🎯 S5 EXECUTED: LONG {cascade.symbol} | {qty:.4f} @ ${cascade.entry_price:,.2f}")
                            s5_state.save(f"logs/state_S5_{cascade.symbol}.json")
                except Exception as e:
                    logger.warning(f"S5 execution: {e}")
    except Exception as e:
        logger.debug(f"S5 check: {e}")

    # S1 FundingArb removed — requires perpetual futures (not available in DE)

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
                        # Execute paper trade for S2 (long leg only in margin mode)
                        try:
                            import requests as req
                            long_asset = pair.asset_a if action == "LONG_A_SHORT_B" else pair.asset_b
                            long_symbol = f"{long_asset}USDT"
                            # Fetch current price for the long asset
                            long_price = float(req.get(
                                "https://api.binance.com/api/v3/ticker/price",
                                params={"symbol": long_symbol}, timeout=3
                            ).json()["price"])
                            s2_state = BotState.load(f"logs/state_S2_{long_symbol}.json")
                            s2_state.paper_balance = capital
                            s2_state.check_new_day()
                            if not s2_state.is_in_position:
                                qty = capital * 0.3 / max(long_price, 0.01)  # 30% of allocation
                                if execute_buy(long_price, qty, config, s2_state):
                                    s2_state.open_position(long_price, qty, long_price * 0.015)
                                    _log_trade("BUY", f"S2_{long_symbol}", qty, long_price)
                                    logger.info(f"📊 S2 EXECUTED: LONG {long_symbol} | {qty:.4f} @ ${long_price:,.2f}")
                                    s2_state.save(f"logs/state_S2_{long_symbol}.json")
                        except Exception as e:
                            logger.warning(f"S2 execution: {e}")

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

    # Migrate CSV trades to Postgres (one-time, persists across deploys)
    try:
        from trade_store import migrate_csv_to_postgres
        migrate_csv_to_postgres()
    except Exception as e:
        logger.debug(f"Trade store init: {e}")

    try:
        from bot.swarm import get_swarm
        get_swarm()  # Initialize singleton
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

    # S1 FundingArb removed — requires perpetual futures (not available in DE)
    logger.info("💰 S1 Funding Arb: DISABLED (Futures not available in DE, using Margin)")

    try:
        from bot.strategies.stat_arb import get_stat_arb
        sa = get_stat_arb()
        logger.info(f"📊 S2 Stat Arb: {len(sa.UNIVERSE)} assets")
    except Exception as e:
        logger.warning(f"S2 init: {e}")

    try:
        from bot.strategies.momentum_v2 import get_momentum
        mom = get_momentum()
        logger.info("📈 S4 Momentum V2: Hurst regime filter active")
    except Exception as e:
        logger.warning(f"S4 init: {e}")

    try:
        from bot.strategies.liquidation_hunter import get_liq_hunter
        lh = get_liq_hunter()
        lh.start_monitoring()
        logger.info(f"🎯 S5 Liquidation Hunter: Monitoring {len(lh.MONITOR_SYMBOLS)} symbols")
    except Exception as e:
        logger.warning(f"S5 init: {e}")

    # SHARED CAPITAL POOL — all pairs share the total balance
    # The bot decides dynamically how much to allocate per trade based on confidence
    # Strong signals → more capital, weak signals → less capital
    
    # ── Restore balance from Postgres (survives Railway deploys) ──
    restored_balance = config.paper_balance
    try:
        from trade_store import get_all_trades
        all_trades = get_all_trades()
        sells = [t for t in all_trades if 'SELL' in t.get('action', '').upper()]
        total_realized = sum(t.get('pnl', 0) for t in sells)
        if total_realized != 0:
            restored_balance = config.paper_balance + total_realized
            logger.info(f"💰 Restored balance from Postgres: ${restored_balance:,.2f} ({len(sells)} closed trades, PnL: ${total_realized:+.2f})")
    except Exception as e:
        logger.debug(f"Balance restore: {e}")
    
    pairs = _get_pairs()
    states: dict[str, BotState] = {}
    for p in pairs:
        pair_key = p["pair"]
        state = BotState.load(f"logs/state_{pair_key}.json")
        # Each pair tracks its OWN P&L, but has access to the full pool
        # Don't overwrite balance if state was loaded (preserves P&L tracking)
        if state.paper_balance == 100_000.0:  # Fresh state, never traded
            state.paper_balance = restored_balance
        state.check_new_day()
        # Fix stale positions: recover bars_held from entry_time
        if state.position and state.position.entry_time:
            try:
                from datetime import datetime, timezone
                entry_dt = datetime.fromisoformat(state.position.entry_time)
                elapsed_minutes = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60
                # Convert to bars (5m interval)
                interval_minutes = int(config.interval.replace('m', '').replace('h', '')) 
                if 'h' in config.interval:
                    interval_minutes *= 60
                estimated_bars = int(elapsed_minutes / max(interval_minutes, 1))
                if estimated_bars > state.position.bars_held:
                    logger.info(f"[{pair_key}] 🔄 Recovered bars_held: {state.position.bars_held} → {estimated_bars} (stale position)")
                    state.position.bars_held = estimated_bars
            except Exception as e:
                logger.debug(f"Bars recovery: {e}")
        states[pair_key] = state

    # ── Stocks DISABLED — focused on 24/7 crypto for max throughput ──
    enable_stocks = False  # os.getenv("ENABLE_STOCKS", "false").lower() in ("true", "1", "yes")
    if enable_stocks:
        try:
            from bot.stocks import DEFAULT_STOCK_PAIRS
            stock_pairs = DEFAULT_STOCK_PAIRS[:int(os.getenv("NUM_STOCKS", "10"))]
            for sp in stock_pairs:
                if sp["pair"] not in states:
                    st = BotState.load(f"logs/state_{sp['pair']}.json")
                    # Recalculate per-pair balance with stocks included
                    st.paper_balance = config.paper_balance / (len(pairs) + len(stock_pairs))
                    st.check_new_day()
                    states[sp["pair"]] = st
            # Update per-pair balance for all pairs now that stocks are added
            total_pairs = len(pairs) + len(stock_pairs)
            new_per_pair = config.paper_balance / max(total_pairs, 1)
            for key in states:
                if not states[key].is_in_position:
                    states[key].paper_balance = new_per_pair
            pairs = pairs + stock_pairs
            logger.info(f"📈 Stocks enabled: {[s['pair'] for s in stock_pairs]}")
        except Exception as e:
            logger.warning(f"Stock init failed: {e}")

    mode = "PAPER" if config.paper_mode else "LIVE"
    crypto_count = sum(1 for p in pairs if p.get("market", "crypto") == "crypto")
    stock_count = sum(1 for p in pairs if p.get("market") == "stock")
    total_balance = config.paper_balance
    locked_in_positions = sum(s.paper_locked for s in states.values())
    logger.info("═══ Ethbot v3 Multi-Strategy Starting ═══")
    logger.info(f"Mode: {mode} | Crypto: {crypto_count} | Stocks: {stock_count} | Total: {len(pairs)}")
    logger.info("Strategies: S2(StatArb) + S4(Momentum) + S5(LiqHunter) | Mode: Margin Trading")
    logger.info(f"Interval: {config.interval} | Capital Pool: ${total_balance:,.2f} | Locked: ${locked_in_positions:,.2f}")
    logger.info(f"Dynamic sizing: Confidence-based (5%-55% of available pool per trade)")
    logger.info(f"Trade limit: adaptive (base 20) | Entry min: {config.entry_score_min}")

    _notify(config, f"🤖 Ethbot v3 [{mode}] | {crypto_count} crypto + {stock_count} stocks | S2+S4+S5 (Margin) | ${total_balance:,.0f}")

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
                                if st.paper_balance == 100_000.0:  # Fresh state
                                    st.paper_balance = config.paper_balance
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

                # Calculate available pool equity = total capital - locked in all open positions
                total_locked = sum(s.paper_locked for s in states.values())
                pool_equity = max(0, config.paper_balance - total_locked)

                # EXPOSURE LIMIT: Skip if >80% of pool is already locked in positions
                max_exposure = config.paper_balance * 0.80
                if total_locked >= max_exposure and not state.is_in_position:
                    logger.debug(f"[{pair_key}] Pool exposure limit: ${total_locked:,.0f} / ${config.paper_balance:,.0f} ({total_locked/config.paper_balance:.0%}) — skipping new entries")
                    # Still manage existing positions (exits)
                    if state.is_in_position:
                        try:
                            _trade_pair(pair_info, config, state, pool_equity=pool_equity)
                        except Exception as e:
                            logger.error(f"[{pair_key}] Error: {e}", exc_info=True)
                    continue

                try:
                    _trade_pair(pair_info, config, state, pool_equity=pool_equity)
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
                                    # Execute paper trade for S4 (only with volume confirmation)
                                    if signal.volume_confirmed and signal.side == "LONG":
                                        try:
                                            s4_state = BotState.load(f"logs/state_S4_{pair_key}.json")
                                            s4_state.paper_balance = capital
                                            s4_state.check_new_day()
                                            if not s4_state.is_in_position:
                                                qty = min(size, capital * 0.4 / max(signal.entry, 0.01))
                                                if execute_buy(signal.entry, qty, config, s4_state):
                                                    s4_state.open_position(signal.entry, qty, signal.atr)
                                                    _log_trade("BUY", f"S4_{pair_key}", qty, signal.entry)
                                                    logger.info(f"📈 S4 EXECUTED: LONG {pair_key} | {qty:.4f} @ ${signal.entry:,.2f}")
                                                    s4_state.save(f"logs/state_S4_{pair_key}.json")
                                        except Exception as e:
                                            logger.warning(f"S4 execution: {e}")
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

            # ── AUTO-COMPOUNDING: Reinvest profits for exponential growth ──
            if loop_count % 5 == 0:  # Check every 5 loops
                total_daily_pnl = sum(s.daily_pnl for s in states.values())
                if total_daily_pnl > 0:
                    old_balance = config.paper_balance
                    config.paper_balance += total_daily_pnl
                    new_per_pair = config.paper_balance / max(len(pairs), 1)
                    for key in states:
                        if not states[key].is_in_position:
                            states[key].paper_balance = new_per_pair
                    if loop_count % 20 == 0:
                        logger.info(
                            f"💰 COMPOUND: ${old_balance:,.0f} → ${config.paper_balance:,.0f} "
                            f"(+${total_daily_pnl:,.2f} today)"
                        )

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
