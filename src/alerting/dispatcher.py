"""Notification dispatcher for PiMon.

Sends alerts and recovery notifications via all enabled channels:
email, webhook, Telegram, Pushover, and MQTT.
Respects per-channel notification cooldowns.
"""

import logging
import time

from src.alerting.thresholds import AlertLevel
from src.config import config

logger = logging.getLogger("pimon")

# Per-channel last-send timestamps for throttling
_last_sent: dict[str, float] = {}


def _channel_allowed(channel: str) -> bool:
    """Check whether a channel's cooldown has elapsed."""
    cooldown_map = {
        "email": config.cooldown_email,
        "webhook": config.cooldown_webhook,
        "telegram": config.cooldown_telegram,
        "pushover": config.cooldown_pushover,
        "mqtt": config.cooldown_mqtt,
    }
    cooldown = cooldown_map.get(channel, 0) or config.alert_cooldown
    now = time.monotonic()
    last = _last_sent.get(channel, 0.0)
    if (now - last) < cooldown:
        return False
    _last_sent[channel] = now
    return True


def dispatch_alert(
    level: AlertLevel,
    sensor_name: str,
    temperature: float,
    recipients: list[str],
) -> None:
    """Send an alert notification via all enabled channels."""
    from src.alerting.email_sender import send_alert_email
    from src.alerting.notifiers.mqtt import publish_alert
    from src.alerting.notifiers.pushover import send_pushover
    from src.alerting.notifiers.telegram import send_telegram
    from src.alerting.notifiers.webhook import send_webhook

    # Email
    if _channel_allowed("email"):
        send_alert_email(recipients, level, sensor_name, temperature)

    # Webhook
    if config.webhook_enabled and config.webhook_url and _channel_allowed("webhook"):
        send_webhook({
            "event": "alert",
            "level": level.name,
            "sensor": sensor_name,
            "temperature_c": temperature,
            "thresholds": config.get_thresholds(sensor_name),
        })

    # Telegram
    if config.telegram_enabled and _channel_allowed("telegram"):
        msg = (
            f"<b>{level.name}</b>: {sensor_name}\n"
            f"Temperature: {temperature:.1f} C"
        )
        send_telegram(msg)

    # Pushover
    if config.pushover_enabled and _channel_allowed("pushover"):
        send_pushover(
            title=f"{level.name}: {sensor_name}",
            message=f"Temperature: {temperature:.1f} C",
            level=level.name,
        )

    # MQTT
    if config.mqtt_enabled and _channel_allowed("mqtt"):
        publish_alert(sensor_name, level.name, temperature)

    # Persist alert event to database
    if config.database_enabled:
        from src.database.repository import store_alert
        store_alert(sensor_name, level.name, temperature)


def dispatch_recovery(
    sensor_name: str,
    temperature: float,
    previous_level: AlertLevel,
) -> None:
    """Send a recovery notification via all enabled channels."""
    from src.alerting.email_sender import send_recovery_email
    from src.alerting.notifiers.pushover import send_pushover
    from src.alerting.notifiers.telegram import send_telegram
    from src.alerting.notifiers.webhook import send_webhook

    # Email
    send_recovery_email(sensor_name, temperature, previous_level)

    # Webhook
    if config.webhook_enabled and config.webhook_url:
        send_webhook({
            "event": "recovery",
            "sensor": sensor_name,
            "temperature_c": temperature,
            "previous_level": previous_level.name,
        })

    # Telegram
    if config.telegram_enabled:
        msg = (
            f"RECOVERED: {sensor_name}\n"
            f"Temperature: {temperature:.1f} C (was {previous_level.name})"
        )
        send_telegram(msg)

    # Pushover
    if config.pushover_enabled:
        send_pushover(
            title=f"RECOVERED: {sensor_name}",
            message=f"Temperature: {temperature:.1f} C (was {previous_level.name})",
            level="WARNING",
        )

    # MQTT
    if config.mqtt_enabled:
        from src.alerting.notifiers.mqtt import publish_recovery
        publish_recovery(sensor_name, temperature, previous_level.name)
