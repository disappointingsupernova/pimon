"""Email alert sender for Pi Temperature Alerter.

Handles SMTP connection, TLS, and message formatting.
Sends multipart emails with both plain text and HTML parts.
Supports dry-run mode for testing without sending real emails.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape as html_escape

from src.alerting.thresholds import AlertLevel
from src.config import config

logger = logging.getLogger("pi_temp_alerter")

_LEVEL_SUBJECTS = {
    AlertLevel.WARNING: "WARNING: Temperature elevated",
    AlertLevel.CRITICAL: "CRITICAL: Temperature high",
    AlertLevel.EMERGENCY: "EMERGENCY: Temperature dangerously high",
}

_LEVEL_COLOURS = {
    AlertLevel.WARNING: "#f39c12",
    AlertLevel.CRITICAL: "#e74c3c",
    AlertLevel.EMERGENCY: "#8e44ad",
}


def _html_alert(level: AlertLevel, sensor_name: str, temperature: float) -> str:
    """Generate HTML body for an alert email."""
    colour = _LEVEL_COLOURS.get(level, "#333")
    thresholds = config.get_thresholds(sensor_name)
    dashboard_url = f"http://{config.dashboard_host}:{config.dashboard_port}"

    # Escape all interpolated values to prevent HTML injection
    safe_sensor = html_escape(sensor_name)
    safe_level = html_escape(level.name)

    return f"""\
<html>
<body style="font-family: -apple-system, sans-serif; padding: 20px; background: #f5f5f5;">
  <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden;">
    <div style="background: {colour}; padding: 16px 20px; color: white;">
      <h2 style="margin: 0; font-size: 18px;">{safe_level}: {safe_sensor}</h2>
    </div>
    <div style="padding: 20px;">
      <p style="font-size: 36px; font-weight: bold; margin: 10px 0;">{temperature:.1f} C</p>
      <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; color: #666;">Sensor</td><td>{safe_sensor}</td></tr>
        <tr><td style="padding: 4px 0; color: #666;">Level</td><td style="color: {colour}; font-weight: bold;">{safe_level}</td></tr>
        <tr><td style="padding: 4px 0; color: #666;">Warning</td><td>{thresholds['warning']} C</td></tr>
        <tr><td style="padding: 4px 0; color: #666;">Critical</td><td>{thresholds['critical']} C</td></tr>
        <tr><td style="padding: 4px 0; color: #666;">Emergency</td><td>{thresholds['emergency']} C</td></tr>
      </table>
      <p style="margin-top: 16px; font-size: 13px; color: #666;">
        Please investigate the thermal condition of your Raspberry Pi.
      </p>
      <a href="{dashboard_url}" style="display: inline-block; margin-top: 12px; padding: 8px 16px; background: {colour}; color: white; text-decoration: none; border-radius: 4px; font-size: 13px;">View Dashboard</a>
    </div>
  </div>
</body>
</html>"""


def _html_recovery(sensor_name: str, temperature: float, previous_level: AlertLevel) -> str:
    """Generate HTML body for a recovery email."""
    dashboard_url = f"http://{config.dashboard_host}:{config.dashboard_port}"

    # Escape all interpolated values to prevent HTML injection
    safe_sensor = html_escape(sensor_name)
    safe_prev_level = html_escape(previous_level.name)

    return f"""\
<html>
<body style="font-family: -apple-system, sans-serif; padding: 20px; background: #f5f5f5;">
  <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden;">
    <div style="background: #27ae60; padding: 16px 20px; color: white;">
      <h2 style="margin: 0; font-size: 18px;">RECOVERED: {safe_sensor}</h2>
    </div>
    <div style="padding: 20px;">
      <p style="font-size: 36px; font-weight: bold; margin: 10px 0;">{temperature:.1f} C</p>
      <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; color: #666;">Sensor</td><td>{safe_sensor}</td></tr>
        <tr><td style="padding: 4px 0; color: #666;">Previous level</td><td>{safe_prev_level}</td></tr>
        <tr><td style="padding: 4px 0; color: #666;">Current</td><td style="color: #27ae60; font-weight: bold;">NORMAL</td></tr>
      </table>
      <p style="margin-top: 16px; font-size: 13px; color: #666;">
        No further action required.
      </p>
      <a href="{dashboard_url}" style="display: inline-block; margin-top: 12px; padding: 8px 16px; background: #27ae60; color: white; text-decoration: none; border-radius: 4px; font-size: 13px;">View Dashboard</a>
    </div>
  </div>
</body>
</html>"""


def send_alert_email(
    recipients: list[str],
    level: AlertLevel,
    sensor_name: str,
    temperature: float,
) -> bool:
    """Send a temperature alert email. Returns True on success."""
    subject = f"[Pi Alerter] {_LEVEL_SUBJECTS.get(level, 'Alert')} - {sensor_name}"
    plain = (
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
    html = _html_alert(level, sensor_name, temperature)
    return _send(recipients, subject, plain, html)


def send_recovery_email(
    sensor_name: str,
    temperature: float,
    previous_level: AlertLevel,
) -> bool:
    """Send a recovery notification email. Returns True on success."""
    subject = f"[Pi Alerter] RECOVERED: {sensor_name} back to normal"
    plain = (
        f"Temperature has returned to normal on sensor: {sensor_name}\n"
        f"\n"
        f"  Current temperature: {temperature:.1f} C\n"
        f"  Previous level:      {previous_level.name}\n"
        f"\n"
        f"No further action required.\n"
    )
    html = _html_recovery(sensor_name, temperature, previous_level)
    all_recipients = list(set(
        config.recipients_warning
        + config.recipients_critical
        + config.recipients_emergency
    ))
    return _send(all_recipients, subject, plain, html)


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
    plain = (
        "This is a test email from Pi Temperature Alerter.\n"
        "\n"
        "Your SMTP configuration is working correctly.\n"
        f"\n"
        f"  SMTP Host: {config.smtp_host}\n"
        f"  SMTP Port: {config.smtp_port}\n"
        f"  TLS:       {config.smtp_use_tls}\n"
    )
    return _send(recipients, subject, plain)


def _send(recipients: list[str], subject: str, body: str, html: str | None = None) -> bool:
    """Internal: compose and send an email via SMTP."""
    if not recipients:
        logger.warning("No recipients specified, skipping email")
        return False

    if config.dry_run:
        logger.info("[DRY RUN] Would send email to %s: %s", recipients, subject)
        return True

    msg = MIMEMultipart("alternative")
    msg["From"] = config.email_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    if html:
        msg.attach(MIMEText(html, "html"))

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
