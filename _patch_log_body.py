def log(msg):
    from datetime import datetime, timezone
    import os, re, io

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"

    # Ringbuffer, falls vorhanden
    try:
        ring.append(line)  # noqa: F821
    except Exception:
        pass

    # Konsole
    try:
        print(line, flush=True)
    except Exception:
        pass

    # Persistentes File-Logging (optional getrennt vom console.out-Redirect)
    try:
        with open("/root/ethbot/logs/ethbot.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    # --- NEU: BUY/SELL in trades.csv ---
    try:
        os.makedirs("/root/ethbot/logs", exist_ok=True)
        csv_path = "/root/ethbot/logs/trades.csv"
        # Header sicherstellen
        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("timestamp,action,qty,price\n")

        # Muster:
        # [DRY] BUY 17.96018 ETH @ ~3897.51
        # [DRY] SELL 17.96018 ETH
        # [LIVE] BUY/SELL ...
        m_buy  = re.search(r"\[(?:DRY|LIVE)\]\s*BUY\s+([0-9.]+)\s+\w+(?:\s*@\s*~?([0-9.]+))?", msg)
        m_sell = re.search(r"\[(?:DRY|LIVE)\]\s*SELL\s+([0-9.]+)\s+\w+(?:\s*@\s*~?([0-9.]+))?", msg)

        row = None
        if m_buy:
            qty  = float(m_buy.group(1))
            px   = float(m_buy.group(2)) if m_buy.group(2) else 0.0
            row  = f"{ts},BUY,{qty:.6f},{px:.2f}\n"
        elif m_sell:
            qty  = float(m_sell.group(1))
            px   = float(m_sell.group(2)) if m_sell.group(2) else 0.0  # falls im Log vorhanden
            row  = f"{ts},SELL,{qty:.6f},{px:.2f}\n"

        if row:
            with open(csv_path, "a", encoding="utf-8") as f:
                f.write(row)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
    except Exception:
        # CSV-Fehler sollen nicht den Bot killen
        pass
