"""Notification dispatcher for Pi Temperature Alerter.

Sends alerts and recovery notifications via all enabled channels:
email, webhook, Telegram, and Pushover.
"""

import logging

from src.alerting.thresholds import AlertLevel
from src.config import config

logger = logging.getLogger("pi_temp_alerter")


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
    send_alert_email(recipients, level, sensor_name, temperature)

    # Webhook
    if config.webhook_enabled and config.webhook_url:
        send_webhook({
            "event": "alert",
            "level": level.name,
            "sensor": sensor_name,
            "temperature_c": temperature,
            "thresholds": config.get_thresholds(sensor_name),
        })

    # Telegram
    if config.telegram_enabled:
        msg = (
            f"<b>{level.name}</b>: {sensor_name}\n"
            f"Temperature: {temperature:.1f} C"
        )
        send_telegram(msg)

    # Pushover
    if config.pushover_enabled:
        send_pushover(
            title=f"{level.name}: {sensor_name}",
            message=f"Temperature: {temperature:.1f} C",
            level=level.name,
        )

    # MQTT
    if config.mqtt_enabled:
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
