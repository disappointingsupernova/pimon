"""Telegram notification backend.

Sends messages via the Telegram Bot API.
"""

import json
import logging
import urllib.request
import urllib.error

from src.config import config

logger = logging.getLogger("pimon")

_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(message: str) -> bool:
    """Send a message to the configured Telegram chat. Returns True on success."""
    token = config.telegram_bot_token
    chat_id = config.telegram_chat_id

    if not token or not chat_id:
        return False

    if config.dry_run:
        logger.info("[DRY RUN] Would send Telegram message to chat %s", chat_id)
        return True

    url = _API_BASE.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status < 300:
                logger.info("Telegram message sent to chat %s", chat_id)
                return True
            logger.warning("Telegram API returned status %d", resp.status)
            return False
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Telegram notification failed: %s", exc)
        return False
