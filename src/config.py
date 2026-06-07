"""Configuration loader for Pi Temperature Alerter.

Reads all settings from the .env file and exposes them as typed attributes.
Supports reloading by creating a new Config instance.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def _bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in ("true", "1", "yes")


def _float(value: str | None, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: str | None, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list(value: str | None) -> list[str]:
    if not value:
        return []
    return [addr.strip() for addr in value.split(",") if addr.strip()]


class Config:
    """Application configuration sourced from environment variables."""

    def __init__(self) -> None:
        # SMTP
        self.smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port: int = _int(os.getenv("SMTP_PORT"), 587)
        self.smtp_use_tls: bool = _bool(os.getenv("SMTP_USE_TLS", "true"))
        self.smtp_username: str = os.getenv("SMTP_USERNAME", "")
        self.smtp_password: str = os.getenv("SMTP_PASSWORD", "")
        self.email_from: str = os.getenv("EMAIL_FROM", "")

        # Recipients per threshold
        self.recipients_warning: list[str] = _list(os.getenv("EMAIL_RECIPIENTS_WARNING", ""))
        self.recipients_critical: list[str] = _list(os.getenv("EMAIL_RECIPIENTS_CRITICAL", ""))
        self.recipients_emergency: list[str] = _list(os.getenv("EMAIL_RECIPIENTS_EMERGENCY", ""))

        # Thresholds
        self.temp_warning: float = _float(os.getenv("TEMP_WARNING"), 60.0)
        self.temp_critical: float = _float(os.getenv("TEMP_CRITICAL"), 70.0)
        self.temp_emergency: float = _float(os.getenv("TEMP_EMERGENCY"), 80.0)
        self.temp_hysteresis: float = _float(os.getenv("TEMP_HYSTERESIS"), 3.0)

        # Monitoring
        self.poll_interval: int = _int(os.getenv("POLL_INTERVAL"), 30)
        self.alert_cooldown: int = _int(os.getenv("ALERT_COOLDOWN"), 300)
        self.recovery_notifications: bool = _bool(os.getenv("RECOVERY_NOTIFICATIONS", "true"))

        # Sensors
        self.sensor_cpu_enabled: bool = _bool(os.getenv("SENSOR_CPU_ENABLED", "true"))
        self.sensor_gpu_enabled: bool = _bool(os.getenv("SENSOR_GPU_ENABLED", "true"))
        self.sensor_ds18b20_enabled: bool = _bool(os.getenv("SENSOR_DS18B20_ENABLED", "false"))
        self.ds18b20_base_dir: str = os.getenv("DS18B20_BASE_DIR", "/sys/bus/w1/devices")

        # Logging
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_max_size_mb: int = _int(os.getenv("LOG_MAX_SIZE_MB"), 10)
        self.log_backup_count: int = _int(os.getenv("LOG_BACKUP_COUNT"), 5)
        self.csv_logging_enabled: bool = _bool(os.getenv("CSV_LOGGING_ENABLED", "true"))
        self.csv_retention_days: int = _int(os.getenv("CSV_RETENTION_DAYS"), 30)

        # Dashboard
        self.dashboard_enabled: bool = _bool(os.getenv("DASHBOARD_ENABLED", "true"))
        self.dashboard_host: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
        self.dashboard_port: int = _int(os.getenv("DASHBOARD_PORT"), 5000)

        # Advanced
        self.dry_run: bool = _bool(os.getenv("DRY_RUN", "false"))

        # Per-sensor threshold overrides (populated dynamically)
        self.sensor_overrides: dict[str, dict[str, float]] = self._load_sensor_overrides()

    def _load_sensor_overrides(self) -> dict[str, dict[str, float]]:
        """Load per-sensor threshold overrides from environment variables.

        Looks for patterns like TEMP_WARNING_CPU=65, TEMP_CRITICAL_GPU=75,
        TEMP_EMERGENCY_DS18B20_28_XXXX=40. Sensor names are normalised to
        lowercase with hyphens replaced by underscores.
        """
        overrides: dict[str, dict[str, float]] = {}
        prefix_map = {
            "TEMP_WARNING_": "warning",
            "TEMP_CRITICAL_": "critical",
            "TEMP_EMERGENCY_": "emergency",
        }

        for key, value in os.environ.items():
            for prefix, level in prefix_map.items():
                if key.startswith(prefix) and key != prefix.rstrip("_"):
                    sensor_name = key[len(prefix):].lower().replace("-", "_")
                    threshold = _float(value, -1.0)
                    if threshold < 0:
                        continue
                    if sensor_name not in overrides:
                        overrides[sensor_name] = {}
                    overrides[sensor_name][level] = threshold

        return overrides

    def get_thresholds(self, sensor_name: str) -> dict[str, float]:
        """Return the effective thresholds for a given sensor.

        Falls back to global thresholds for any level not overridden.
        """
        overrides = self.sensor_overrides.get(sensor_name.lower().replace("-", "_"), {})
        return {
            "warning": overrides.get("warning", self.temp_warning),
            "critical": overrides.get("critical", self.temp_critical),
            "emergency": overrides.get("emergency", self.temp_emergency),
        }


config = Config()
