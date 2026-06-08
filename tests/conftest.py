"""Shared test fixtures for PiMon test suite."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Isolate each test from real environment and filesystem.

    Sets minimal safe defaults and points data/log paths to tmp_path.
    """
    env_defaults = {
        "SMTP_HOST": "localhost",
        "SMTP_PORT": "25",
        "SMTP_USE_TLS": "false",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
        "EMAIL_FROM": "test@example.com",
        "EMAIL_RECIPIENTS_WARNING": "warn@example.com",
        "EMAIL_RECIPIENTS_CRITICAL": "crit@example.com",
        "EMAIL_RECIPIENTS_EMERGENCY": "emerg@example.com",
        "TEMP_WARNING": "60",
        "TEMP_CRITICAL": "70",
        "TEMP_EMERGENCY": "80",
        "TEMP_HYSTERESIS": "3",
        "POLL_INTERVAL": "30",
        "ALERT_COOLDOWN": "300",
        "RECOVERY_NOTIFICATIONS": "true",
        "RATE_OF_CHANGE_THRESHOLD": "0",
        "ESCALATION_TIMEOUT": "0",
        "SENSOR_CPU_ENABLED": "true",
        "SENSOR_GPU_ENABLED": "false",
        "SENSOR_DS18B20_ENABLED": "false",
        "LOG_LEVEL": "DEBUG",
        "CSV_LOGGING_ENABLED": "false",
        "DASHBOARD_ENABLED": "false",
        "DATABASE_ENABLED": "false",
        "WEBHOOK_ENABLED": "false",
        "TELEGRAM_ENABLED": "false",
        "PUSHOVER_ENABLED": "false",
        "MQTT_ENABLED": "false",
        "DRY_RUN": "true",
        "LOW_WRITE_MODE": "false",
        "FAN_CONTROL_ENABLED": "false",
        "STARTUP_NOTIFICATION": "false",
        "ALERT_CPU_PERCENT": "0",
        "ALERT_MEMORY_PERCENT": "0",
        "ALERT_DISK_PERCENT": "0",
        "COOLDOWN_EMAIL": "0",
        "COOLDOWN_WEBHOOK": "0",
        "COOLDOWN_TELEGRAM": "0",
        "COOLDOWN_PUSHOVER": "0",
        "COOLDOWN_MQTT": "0",
        "SCHEDULED_REBOOT_ENABLED": "false",
        "DAILY_DIGEST_ENABLED": "false",
    }
    for key, val in env_defaults.items():
        monkeypatch.setenv(key, val)

    # Point database to tmp
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")


@pytest.fixture
def fresh_config():
    """Return a fresh Config instance with test environment applied."""
    from src.config import Config
    return Config()
