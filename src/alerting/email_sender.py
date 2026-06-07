"""Email alert sender for Pi Temperature Alerter.

Handles SMTP connection, TLS, and message formatting.
Supports dry-run mode for testing without sending real emails.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.alerting.thresholds import AlertLevel
from src.config import config

logger = logging.getLogger("pi_temp_alerter")

_LEVEL_SUBJECTS = {
    AlertLevel.WARNING: "WARNING: Temperature elevated",
    AlertLevel.CRITICAL: "CRITICAL: Temperature high",
    AlertLevel.EMERGENCY: "EMERGENCY: Temperature dangerously high",
}


def send_alert_email(
    recipients: list[str],
    level: AlertLevel,
    sensor_name: str,
    temperature: float,
) -> bool:
    """Send a temperature alert email. Returns True on success."""
    subject = f"[Pi Alerter] {_LEVEL_SUBJECTS.get(level, 'Alert')} - {sensor_name}"
    body = (
        f"Temperature alert triggered on sensor: {sensor_name}\n"
        f"\n"
        f"  Level:       {level.name}\n"
        f"  Temperature: {temperature:.1f} C\n"
        f"  Thresholds:  Warning={config.temp_warning} C, "
        f"Critical={config.temp_critical} C, "
        f"Emergency={config.temp_emergency} C\n"
        f"\n"
        f"Please investigate the thermal condition of your Raspberry Pi.\n"
    )
    return _send(recipients, subject, body)


def send_recovery_email(
    recipients: list[str],
    sensor_name: str,
    temperature: float,
    previous_level: AlertLevel,
) -> bool:
    """Send a recovery notification email. Returns True on success."""
    subject = f"[Pi Alerter] RECOVERED: {sensor_name} back to normal"
    body = (
        f"Temperature has returned to normal on sensor: {sensor_name}\n"
        f"\n"
        f"  Current temperature: {temperature:.1f} C\n"
        f"  Previous level:      {previous_level.name}\n"
        f"\n"
        f"No further action required.\n"
    )
    # Send to all unique recipients from all levels
    all_recipients = list(set(
        config.recipients_warning
        + config.recipients_critical
        + config.recipients_emergency
    ))
    return _send(all_recipients, subject, body)


def send_test_email() -> bool:
    """Send a test email to verify SMTP configuration."""
    recipients = list(set(
        config.recipients_warning
        + config.recipients_critical
        + config.recipients_emergency
    ))
    if not recipients:
        logger.error("No recipients configured - cannot send test email")
        return False

    subject = "[Pi Alerter] Test Email - Configuration Verified"
    body = (
        "This is a test email from Pi Temperature Alerter.\n"
        "\n"
        "Your SMTP configuration is working correctly.\n"
        f"\n"
        f"  SMTP Host: {config.smtp_host}\n"
        f"  SMTP Port: {config.smtp_port}\n"
        f"  TLS:       {config.smtp_use_tls}\n"
    )
    return _send(recipients, subject, body)


def _send(recipients: list[str], subject: str, body: str) -> bool:
    """Internal: compose and send an email via SMTP."""
    if not recipients:
        logger.warning("No recipients specified, skipping email")
        return False

    if config.dry_run:
        logger.info("[DRY RUN] Would send email to %s: %s", recipients, subject)
        return True

    msg = MIMEMultipart()
    msg["From"] = config.email_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
            if config.smtp_use_tls:
                server.starttls()
            if config.smtp_username and config.smtp_password:
                server.login(config.smtp_username, config.smtp_password)
            server.sendmail(config.email_from, recipients, msg.as_string())

        logger.info("Email sent to %s: %s", recipients, subject)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("Failed to send email: %s", exc)
        return False
