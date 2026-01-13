def log(msg):
    from datetime import datetime, timezone
    import re as _re
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    ring.append(line)
    print(line, flush=True)
    # persistentes File-Logging
    try:
        with open("/root/ethbot/logs/ethbot.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    # --- NEU: DRY BUY/SELL erkennen und in trades.csv loggen ---
    try:
        buy_m = _re.search(r"\[DRY\]\s*BUY\s+([0-9.]+)\s+\w+\s*@\s*~?([0-9.]+)", msg)
        sell_m = _re.search(r"\[DRY\]\s*SELL\s+([0-9.]+)\s+\w+", msg)
        if buy_m:
            qty = float(buy_m.group(1)); px = float(buy_m.group(2))
            log_trade("BUY", qty, px)
        elif sell_m:
            qty = float(sell_m.group(1))
            px = last_price() or 0.0
            log_trade("SELL", qty, float(px))
    except Exception:
        pass
