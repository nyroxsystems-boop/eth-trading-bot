#!/usr/bin/env python3
import os, re, time, subprocess, datetime
from pathlib import Path

LOG_PATH = Path("/root/ethbot/logs/console.out")
SERVICE = "ethbot.service"
LOG_ERR = "/root/ethbot/logs/watchdog_mini_jarvis.log"

# Telegram optional
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")

def notify(msg: str):
    print(msg)
    with open(LOG_ERR, "a") as f:
        f.write(f"{datetime.datetime.utcnow():%Y-%m-%d %H:%M:%S} {msg}\n")
    if TG_TOKEN and TG_CHAT:
        subprocess.run([
            "curl", "-s", "-X", "POST",
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            "-d", f"chat_id={TG_CHAT}",
            "-d", f"text=⚠️ Mini-Jarvis: {msg}"
        ])

def last_lines(path, n=200):
    try:
        return Path(path).read_text().splitlines()[-n:]
    except Exception:
        return []

def main():
    errors = last_lines(LOG_PATH, 150)
    text = "\n".join(errors)
    alerts = []

    # --- Fehlererkennung ---
    if re.search(r"cannot access local variable 'elapsed_bars'", text):
        alerts.append("elapsed_bars Fehler erkannt – wird zurückgesetzt")
        # Schnellreparatur: Zeile 739/740 kontrollieren
        try:
            subprocess.run([
                "sed","-i",
                r"s/elapsed_bars\s*=\s*int.*/elapsed_bars = 0  # auto-fixed by Mini-Jarvis/",
                "/root/ethbot/eth_master_bot.py"
            ])
        except Exception as e:
            alerts.append(f"Patch fehlgeschlagen: {e}")

    if re.search(r"ADX.*NaN|nan", text):
        alerts.append("NaN-Werte erkannt – Neustart empfohlen")

    if re.search(r"Traceback|Exception", text):
        alerts.append("Exception erkannt – Überprüfung läuft")

    # --- falls Fehler erkannt ---
    if alerts:
        for msg in alerts:
            notify(msg)
        subprocess.run(["systemctl", "restart", SERVICE])
        notify("Bot neugestartet ✅")
    else:
        notify("Alles stabil ✅")

if __name__ == "__main__":
    main()
