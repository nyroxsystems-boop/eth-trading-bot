"""
Notification Service — Telegram alerts.
"""
import logging
import requests

logger = logging.getLogger("ethbot.notify")


def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    if not (token and chat_id):
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=6,
        )
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")
        return False
