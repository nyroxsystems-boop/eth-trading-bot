#!/usr/bin/env python3
import os, re, time, subprocess, pathlib, sys

LOG = pathlib.Path("/root/ethbot/logs/console.out")
ENV = os.environ
TELEGRAM = os.environ.get("TELEGRAM_WATCHDOG_ALERTS", "1")  # 1=on, 0=quiet
ERROR_RX = os.environ.get("WATCHDOG_ERROR_REGEX", r"(ERROR|CRITICAL|Traceback)")
MIN_GAP  = int(os.environ.get("WATCHDOG_MIN_RESTART_SEC", "600"))
STAMP    = pathlib.Path("/root/ethbot/.watchdog_last_restart")

def tg_send(msg: str):
    # versuche zentralen Notifier (mit _tg_should_send Filter)
    try:
        import telegram_notify as tn
        return tn.tg_send(msg)
    except Exception:
        # Fallback: nur senden, wenn explizit Alerts erlaubt
        if TELEGRAM == "1":
            tok = os.getenv("TELEGRAM_BOT_TOKEN")
            cid = os.getenv("TELEGRAM_CHAT_ID")
            if tok and cid:
                import requests
                try:
                    requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                                  json={"chat_id": cid, "text": msg, "disable_web_page_preview": True, "parse_mode": "Markdown"})
                except Exception:
                    pass

def too_soon() -> bool:
    if STAMP.exists():
        try:
            last = float(STAMP.read_text().strip() or "0")
            return (time.time() - last) < MIN_GAP
        except Exception:
            return False
    return False

def mark_now():
    STAMP.write_text(str(time.time()))

def main():
    # quiet mode? nichts senden, nur ggf. leise restarten
    quiet = (TELEGRAM != "1")
    rx = re.compile(ERROR_RX, re.IGNORECASE)

    if not LOG.exists():
        if not quiet: tg_send("⚠️ Watchdog: console.out fehlt – starte ethbot neu.")
        if not too_soon():
            mark_now()
            subprocess.run(["systemctl","restart","ethbot.service"])
        return 0

    # Nur die letzten 400 Zeilen prüfen
    try:
        lines = LOG.read_text(errors="ignore").splitlines()[-400:]
    except Exception:
        lines = []

    # Fehler suchen – aber harmloses Rauschen herausfiltern
    noisy = (r"INFO px=" , r"[DRY] BUY", r"[DRY] SELL", r"[EDGE]", r"[SAFEGUARD]")
    bad = []
    for ln in lines:
        if any(no in ln for no in noisy):
            continue
        if rx.search(ln):
            bad.append(ln)

    if bad:
        if too_soon():
            # Schon kürzlich reagiert → keine Endlosschleife
            return 0
        mark_now()
        subprocess.run(["systemctl","restart","ethbot.service"])
        if not quiet:
            tg_send("♻️ Restarting ethbot (watchdog): error pattern")
    else:
        # optional: nichts tun
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
