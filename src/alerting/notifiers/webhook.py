"""Generic webhook notification backend.

Sends a JSON POST to a configurable URL on alert and recovery events.
Supports optional SSL verification bypass for internal self-signed endpoints.
"""

import json
import logging
import ssl
import urllib.request
import urllib.error

from src.config import config

logger = logging.getLogger("pi_temp_alerter")


def send_webhook(payload: dict) -> bool:
    """Send a JSON payload to the configured webhook URL. Returns True on success."""
    url = config.webhook_url
    if not url:
        return False

    if config.dry_run:
        logger.info("[DRY RUN] Would POST to webhook: %s", url)
        return True

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        # Allow disabling SSL verification for internal self-signed endpoints
        ssl_context = None
        if config.webhook_verify_ssl is False:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as resp:
            if resp.status < 300:
                logger.info("Webhook sent to %s (status %d)", url, resp.status)
                return True
            logger.warning("Webhook returned status %d", resp.status)
            return False
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Webhook failed: %s", exc)
        return False
