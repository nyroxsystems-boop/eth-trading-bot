#!/usr/bin/env python3
"""
Auto-Optimization Module for ETH Trading Bot
Automatically adjusts trading parameters to achieve 1% daily target
"""

def auto_optimize_parameters():
    """
    Automatically adjust trading parameters based on performance
    Target: 1% daily return
    """
    # Import from main module
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Access global variables from main bot
    global current_params, performance_history, last_optimization, RISK_PCT_PER_TRADE
    global current_equity, day_start_equity, today_trades, DAILY_TARGET_PCT, log
    
    import time
    from datetime import datetime, timezone
    
    # Only optimize once per day
    now = time.time()
    if now - last_optimization < 86400:  # 24 hours
        return
    
    last_optimization = now
    
    try:
        # Calculate daily P&L percentage
        eq_now = current_equity()
        if day_start_equity is None or day_start_equity <= 0:
            return
        
        daily_pnl_pct = ((eq_now / day_start_equity) - 1.0) * 100
        
        # Track performance
        performance_history.append({
            'date': datetime.now(timezone.utc).isoformat(),
            'pnl_pct': daily_pnl_pct,
            'trades': today_trades,
            'params': current_params.copy()
        })
        
        # Keep only last 30 days
        if len(performance_history) > 30:
            performance_history = performance_history[-30:]
        
        # Calculate average performance
        if len(performance_history) < 3:
            return  # Need at least 3 days of data
        
        avg_pnl = sum(p['pnl_pct'] for p in performance_history[-7:]) / min(7, len(performance_history))
        
        log(f"[AUTO-OPT] Daily P&L: {daily_pnl_pct:.2f}% | 7-day avg: {avg_pnl:.2f}% | Target: {DAILY_TARGET_PCT}%")
        log(f"[AUTO-OPT] Trades today: {today_trades}")
        
        # CRITICAL: Check if no trades are happening (parameters too strict)
        if today_trades == 0:
            log("[AUTO-OPT] ⚠️ ZERO TRADES TODAY - Parameters too strict! Relaxing entry criteria...")
            
            # Aggressively relax entry criteria
            current_params['ml_threshold'] = max(current_params.get('ml_threshold', 0.52) * 0.85, 0.35)
            log(f"[AUTO-OPT] Lowered ML threshold to {current_params['ml_threshold']:.2f}")
            
            # Also check recent history for consistent zero trades
            recent_trades = [p.get('trades', 0) for p in performance_history[-3:]]
            if all(t == 0 for t in recent_trades):
                log("[AUTO-OPT] ⚠️ NO TRADES FOR 3 DAYS! Emergency parameter relaxation...")
                
                # Emergency relaxation
                current_params['ml_threshold'] = 0.30  # Very low threshold
                current_params['position_size_mult'] = min(current_params.get('position_size_mult', 1.0) * 1.2, 2.0)
                current_params['risk_pct'] = min(current_params.get('risk_pct', 0.006) * 1.1, 0.012)
                
                log(f"[AUTO-OPT] Emergency params: ml_thresh=0.30, pos_mult={current_params['position_size_mult']:.2f}, risk={current_params['risk_pct']:.4f}")
        
        # Adjust parameters based on performance
        elif avg_pnl < DAILY_TARGET_PCT * 0.5:
            # Underperforming - increase aggression
            log("[AUTO-OPT] Underperforming - increasing aggression")
            
            # Increase position size
            current_params['position_size_mult'] = min(current_params['position_size_mult'] * 1.1, 2.0)
            
            # Lower ML threshold (take more trades)
            current_params['ml_threshold'] = max(current_params['ml_threshold'] * 0.95, 0.45)
            
            # Increase risk per trade
            current_params['risk_pct'] = min(current_params['risk_pct'] * 1.05, 0.01)  # Max 1%
            
            # Increase TP targets
            current_params['tp_min'] = min(current_params['tp_min'] * 1.05, 0.025)
            current_params['tp_max'] = min(current_params['tp_max'] * 1.05, 0.03)
            
        elif avg_pnl > DAILY_TARGET_PCT * 1.5:
            # Overperforming - reduce risk to protect gains
            log("[AUTO-OPT] Overperforming - reducing risk")
            
            # Decrease position size
            current_params['position_size_mult'] = max(current_params['position_size_mult'] * 0.95, 0.5)
            
            # Raise ML threshold (be more selective)
            current_params['ml_threshold'] = min(current_params['ml_threshold'] * 1.05, 0.65)
            
            # Decrease risk per trade
            current_params['risk_pct'] = max(current_params['risk_pct'] * 0.95, 0.003)
            
        elif DAILY_TARGET_PCT * 0.8 <= avg_pnl <= DAILY_TARGET_PCT * 1.2:
            # On target - minor adjustments
            log("[AUTO-OPT] On target - maintaining current parameters")
        
        # Apply optimized parameters
        RISK_PCT_PER_TRADE = current_params['risk_pct']
        
        log(f"[AUTO-OPT] Updated params: risk={current_params['risk_pct']:.4f} ml_thresh={current_params['ml_threshold']:.2f} pos_mult={current_params['position_size_mult']:.2f}")
        
        # Save parameters to file
        try:
            import json
            import os
            _log_dir = os.path.join(os.getenv("ETHBOT_ROOT", os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(_log_dir, exist_ok=True)
            with open(os.path.join(_log_dir, "optimized_params.json"), "w") as f:
                json.dump({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'params': current_params,
                    'performance': {
                        'daily_pnl_pct': daily_pnl_pct,
                        'avg_7day_pnl': avg_pnl,
                        'target': DAILY_TARGET_PCT
                    }
                }, f, indent=2)
        except Exception as e:
            log(f"WARN failed to save params: {e}")
        
        # Send daily Telegram report
        send_daily_telegram_report(daily_pnl_pct, avg_pnl, today_trades)
        
    except Exception as e:
        log(f"WARN auto-optimization failed: {e}")


def send_daily_telegram_report(daily_pnl_pct, avg_7day_pnl, trades_today):
    """
    Send daily performance report to Telegram
    Called once per day at midnight
    """
    try:
        from datetime import datetime, timezone
        import os
        
        # Get Telegram credentials
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not bot_token or not chat_id:
            log("WARN: Telegram credentials not configured, skipping daily report")
            return
        
        # Calculate win rate from recent trades
        win_rate = calculate_win_rate()
        
        # Determine optimization action
        if daily_pnl_pct < DAILY_TARGET_PCT * 0.5:
            opt_status = "⬆️ Increased aggression (underperforming)"
        elif daily_pnl_pct > DAILY_TARGET_PCT * 1.5:
            opt_status = "⬇️ Reduced risk (overperforming)"
        elif DAILY_TARGET_PCT * 0.8 <= daily_pnl_pct <= DAILY_TARGET_PCT * 1.2:
            opt_status = "✅ Maintaining parameters (on target)"
        else:
            opt_status = "🔄 Minor adjustments"
        
        # Build report message
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Emoji based on performance
        if daily_pnl_pct >= DAILY_TARGET_PCT:
            perf_emoji = "🎯"
        elif daily_pnl_pct >= 0:
            perf_emoji = "📈"
        else:
            perf_emoji = "📉"
        
        message = f"""📊 **Daily Performance Report**
━━━━━━━━━━━━━━━━━━━━
📅 Date: {date_str}
💰 P&L: {daily_pnl_pct:+.2f}% {perf_emoji}
📊 Trades: {trades_today}
🎲 Win Rate: {win_rate:.1f}%
📈 7-Day Avg: {avg_7day_pnl:+.2f}%
🎯 Target: {DAILY_TARGET_PCT:.1f}%

🤖 **Auto-Optimization:**
{opt_status}
New params saved.

━━━━━━━━━━━━━━━━━━━━
💡 Bot is running 24/7
Next report: Tomorrow 00:00 UTC"""
        
        # Send via Telegram
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            log(f"[TELEGRAM] Daily report sent successfully")
        else:
            log(f"WARN: Telegram daily report failed: {response.status_code}")
            
    except Exception as e:
        log(f"WARN: Failed to send daily Telegram report: {e}")


def calculate_win_rate():
    """Calculate win rate from recent trades"""
    try:
        import csv
        import os
        
        trades_file = os.path.join(os.getenv("ETHBOT_ROOT", os.path.dirname(os.path.abspath(__file__))), "logs", "trades.csv")
        
        if not os.path.exists(trades_file):
            return 0.0
        
        wins = 0
        total = 0
        
        with open(trades_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('side') == 'SELL':
                    total += 1
                    pnl = float(row.get('pnl_pct', 0))
                    if pnl > 0:
                        wins += 1
        
        if total == 0:
            return 0.0
        
        return (wins / total) * 100
        
    except Exception as e:
        log(f"WARN: Failed to calculate win rate: {e}")
        return 0.0



def generate_demo_market_data(num_candles=1000):
    """
    Generate realistic demo market data for training
    Returns DataFrame with OHLCV data
    """
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta, timezone
    
    data = []
    base_price = 3200.0
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=5 * num_candles)
    
    for i in range(num_candles):
        # Trend component (sine wave)
        trend = np.sin(i / 50) * 50
        
        # Volatility component
        volatility = np.random.normal(0, 20)
        
        # Support/Resistance levels
        if base_price < 3000:
            base_price += abs(volatility)  # Bounce up from support
        elif base_price > 3400:
            base_price -= abs(volatility)  # Bounce down from resistance
        else:
            base_price += trend + volatility
        
        # Generate OHLC
        open_price = base_price + np.random.normal(0, 5)
        close_price = open_price + np.random.normal(0, 15)
        high_price = max(open_price, close_price) + abs(np.random.normal(0, 10))
        low_price = min(open_price, close_price) - abs(np.random.normal(0, 10))
        volume = abs(np.random.normal(1000, 300))
        
        data.append({
            'time': timestamp,
            'open': max(open_price, 1.0),
            'high': max(high_price, 1.0),
            'low': max(low_price, 1.0),
            'close': max(close_price, 1.0),
            'volume': max(volume, 0.1)
        })
        
        timestamp += timedelta(minutes=5)
        base_price = close_price
    
    df = pd.DataFrame(data)
    return df
