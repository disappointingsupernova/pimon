"""Configuration loader for Pi Temperature Alerter.

Reads all settings from the .env file and exposes them as typed attributes.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def _bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes")


def _float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list(value: str) -> list[str]:
    if not value:
        return []
    return [addr.strip() for addr in value.split(",") if addr.strip()]


class Config:
    """Application configuration sourced from environment variables."""

    # SMTP
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = _int(os.getenv("SMTP_PORT"), 587)
    smtp_use_tls: bool = _bool(os.getenv("SMTP_USE_TLS", "true"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_from: str = os.getenv("EMAIL_FROM", "")

    # Recipients per threshold
    recipients_warning: list[str] = _list(os.getenv("EMAIL_RECIPIENTS_WARNING", ""))
    recipients_critical: list[str] = _list(os.getenv("EMAIL_RECIPIENTS_CRITICAL", ""))
    recipients_emergency: list[str] = _list(os.getenv("EMAIL_RECIPIENTS_EMERGENCY", ""))

    # Thresholds
    temp_warning: float = _float(os.getenv("TEMP_WARNING"), 60.0)
    temp_critical: float = _float(os.getenv("TEMP_CRITICAL"), 70.0)
    temp_emergency: float = _float(os.getenv("TEMP_EMERGENCY"), 80.0)
    temp_hysteresis: float = _float(os.getenv("TEMP_HYSTERESIS"), 3.0)

    # Monitoring
    poll_interval: int = _int(os.getenv("POLL_INTERVAL"), 30)
    alert_cooldown: int = _int(os.getenv("ALERT_COOLDOWN"), 300)
    recovery_notifications: bool = _bool(os.getenv("RECOVERY_NOTIFICATIONS", "true"))

    # Sensors
    sensor_cpu_enabled: bool = _bool(os.getenv("SENSOR_CPU_ENABLED", "true"))
    sensor_gpu_enabled: bool = _bool(os.getenv("SENSOR_GPU_ENABLED", "true"))
    sensor_ds18b20_enabled: bool = _bool(os.getenv("SENSOR_DS18B20_ENABLED", "false"))
    ds18b20_base_dir: str = os.getenv("DS18B20_BASE_DIR", "/sys/bus/w1/devices")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_max_size_mb: int = _int(os.getenv("LOG_MAX_SIZE_MB"), 10)
    log_backup_count: int = _int(os.getenv("LOG_BACKUP_COUNT"), 5)
    csv_logging_enabled: bool = _bool(os.getenv("CSV_LOGGING_ENABLED", "true"))

    # Dashboard
    dashboard_enabled: bool = _bool(os.getenv("DASHBOARD_ENABLED", "true"))
    dashboard_host: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    dashboard_port: int = _int(os.getenv("DASHBOARD_PORT"), 5000)

    # Advanced
    dry_run: bool = _bool(os.getenv("DRY_RUN", "false"))


config = Config()
