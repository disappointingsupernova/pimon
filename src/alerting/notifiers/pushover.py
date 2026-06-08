"""Pushover notification backend.

Sends push notifications via the Pushover API.
"""

import logging
import urllib.request
import urllib.error
import urllib.parse

from src.config import config

logger = logging.getLogger("pimon")

_API_URL = "https://api.pushover.net/1/messages.json"

_PRIORITY_MAP = {
    "WARNING": 0,
    "CRITICAL": 1,
    "EMERGENCY": 2,
}


def send_pushover(title: str, message: str, level: str = "WARNING") -> bool:
    """Send a push notification via Pushover. Returns True on success."""
    token = config.pushover_app_token
    user_key = config.pushover_user_key

    if not token or not user_key:
        return False

    if config.dry_run:
        logger.info("[DRY RUN] Would send Pushover notification: %s", title)
        return True

    priority = _PRIORITY_MAP.get(level, 0)
    params = {
        "token": token,
        "user": user_key,
        "title": title,
        "message": message,
        "priority": str(priority),
    }

    # Emergency priority requires retry and expire parameters
    if priority == 2:
        params["retry"] = "60"
        params["expire"] = "3600"

    try:
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(_API_URL, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status < 300:
                logger.info("Pushover notification sent: %s", title)
                return True
            logger.warning("Pushover API returned status %d", resp.status)
            return False
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Pushover notification failed: %s", exc)
        return False
