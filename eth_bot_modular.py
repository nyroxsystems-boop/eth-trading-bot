#!/usr/bin/env python3
"""
ETH Trading Bot - Modular Version
Main orchestration file using modular components
"""
import signal
import time
import threading
from datetime import datetime, timezone
from typing import Optional

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.core.market_data import MarketDataProvider
from src.core.ml_engine import MLEngine
from src.core.strategy import TradingStrategy
from src.core.risk_manager import RiskManager, Position
from src.core.order_executor import OrderExecutor

# Setup logger
logger = setup_logger('ethbot_modular', level='INFO')

# Global state
STOP = threading.Event()
open_position: Optional[Position] = None
today_trades = 0
last_trade_day = datetime.now(timezone.utc).date().isoformat()
bars_in_position = 0


def now_date() -> str:
    """Get current UTC date as ISO string"""
    return datetime.now(timezone.utc).date().isoformat()


def reset_daily_state(risk_manager: RiskManager, order_executor: OrderExecutor):
    """Reset daily trading state"""
    global today_trades, last_trade_day, open_position, bars_in_position
    
    last_trade_day = now_date()
    today_trades = 0
    bars_in_position = 0
    
    current_equity = order_executor.estimate_equity()
    risk_manager.reset_daily_state(current_equity)
    
    logger.info(f"New UTC day - reset trade counter | equity={current_equity:.2f}")


def decide_and_trade(
    market_data: MarketDataProvider,
    ml_engine: MLEngine,
    strategy: TradingStrategy,
    risk_manager: RiskManager,
    order_executor: OrderExecutor
):
    """Main trading decision logic"""
    global open_position, today_trades, last_trade_day, bars_in_position
    
    config = get_config()
    
    # Check for new day
    if now_date() != last_trade_day:
        reset_daily_state(risk_manager, order_executor)
    
    # Check cooldown
    if risk_manager.check_cooldown():
        logger.debug("In cooldown period, skipping")
        return
    
    # Check daily drawdown
    current_equity = order_executor.estimate_equity()
    if risk_manager.check_daily_drawdown(current_equity):
        return
    
    # Check max trades
    if today_trades >= config.trading.max_trades_per_day and not open_position:
        logger.debug("Max trades reached for today")
        return
    
    # Fetch market data
    try:
        df = market_data.fetch_klines()
        df_with_indicators = market_data.add_indicators(df)
        
        if len(df_with_indicators) < 60:
            logger.warning("Insufficient data for analysis")
            return
        
    except Exception as e:
        logger.error(f"Failed to fetch market data: {e}")
        return
    
    # Update ML model
    ml_engine.update_online(df_with_indicators)
    
    # Get current market state
    current_row = df_with_indicators.iloc[-1]
    previous_row = df_with_indicators.iloc[-2]
    current_price = float(current_row["close"])
    current_atr = float(current_row["atr"])
    current_rsi = float(current_row["rsi14"])
    
    # Compute regime
    regime = strategy.compute_regime(df_with_indicators)
    
    # Log price and regime
    logger.debug(
        f"Price: {current_price:.2f} | "
        f"ADX: {regime.adx:.1f} | "
        f"RSI: {current_rsi:.1f} | "
        f"Trend: {regime.trend_ok} | "
        f"Vol: {regime.vol_ok}"
    )
    
    # Manage open position
    if open_position:
        bars_in_position += 1
        
        should_exit, exit_reason = risk_manager.should_exit_position(
            position=open_position,
            current_price=current_price,
            current_atr=current_atr,
            bars_in_position=bars_in_position,
            rsi=current_rsi,
            adx=regime.adx
        )
        
        if should_exit:
            # Calculate PnL
            entry = open_position.entry
            upnl = (current_price / entry) - 1.0
            
            # Execute sell
            if order_executor.place_sell(open_position.qty):
                # Log and notify
                message = (
                    f"{'✅' if upnl > 0 else '⚠️'} {exit_reason} | "
                    f"{upnl*100:+.2f}% | "
                    f"close @{current_price:.2f}"
                )
                logger.info(message)
                order_executor.send_telegram_notification(message)
                
                # Update risk state
                risk_manager.update_loss_streak(upnl < 0)
                
                # Clear position
                open_position = None
                bars_in_position = 0
            
            return
    
    # Check for new entry
    if open_position:
        return  # Already in position
    
    if today_trades >= config.trading.max_trades_per_day:
        return  # Max trades reached
    
    # Calculate entry signal
    signal = strategy.calculate_entry_signal(current_row, previous_row, regime)
    
    should_enter, entry_reason = strategy.should_enter_long(signal, regime)
    
    if not should_enter:
        logger.debug(f"No entry: {entry_reason}")
        return
    
    # Calculate position size
    stop_loss_pct = risk_manager.calculate_stop_loss(current_price, current_atr)
    qty = risk_manager.position_size_for_risk(current_price, stop_loss_pct, current_equity)
    
    # Check minimum position size
    if qty * current_price < 10:
        logger.warning(f"Position too small (<$10): ${qty * current_price:.2f}")
        return
    
    # Execute buy
    if order_executor.place_buy(qty, current_price):
        # Create position
        open_position = Position(
            entry=current_price,
            qty=qty,
            atr=current_atr,
            open_bar_time=str(current_row["time"])
        )
        
        today_trades += 1
        bars_in_position = 0
        
        # Calculate TP range
        tp_pct = risk_manager.calculate_take_profit(current_rsi, regime.adx)
        
        # Log and notify
        signal_desc = strategy.get_signal_description(signal)
        message = (
            f"▶️ LONG {config.trading.base_asset} @ {current_price:.2f} | "
            f"size≈${qty*current_price:.2f} | "
            f"TP {tp_pct*100:.1f}% | "
            f"{signal_desc}"
        )
        logger.info(message)
        order_executor.send_telegram_notification(message)


def main_loop():
    """Main trading loop"""
    config = get_config()
    
    # Initialize components
    logger.info("Initializing trading components...")
    market_data = MarketDataProvider()
    ml_engine = MLEngine()
    strategy = TradingStrategy(market_data, ml_engine)
    risk_manager = RiskManager()
    order_executor = OrderExecutor()
    
    # Startup message
    startup_msg = (
        f"✅ Bot started | "
        f"DRY_RUN={config.system.dry_run} | "
        f"MaxTrades={config.trading.max_trades_per_day}"
    )
    logger.info(startup_msg)
    order_executor.send_telegram_notification(startup_msg)
    
    if config.system.dry_run:
        logger.info(f"Paper trading with ${config.system.paper_base_usdt:.2f}")
    
    # Main loop
    while not STOP.is_set():
        cycle_start = time.time()
        
        try:
            decide_and_trade(market_data, ml_engine, strategy, risk_manager, order_executor)
        except Exception as e:
            logger.error(f"Trading cycle error: {e}", exc_info=True)
        
        # Sleep until next cycle
        elapsed = time.time() - cycle_start
        remaining = max(0.0, config.system.sleep_seconds - elapsed)
        
        if remaining > 0:
            STOP.wait(remaining)


def handle_signal(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutdown signal received, stopping...")
    STOP.set()


def main():
    """Main entry point"""
    # Setup signal handlers
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    # Run main loop
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
