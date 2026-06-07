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
        self.rate_of_change_threshold: float = _float(os.getenv("RATE_OF_CHANGE_THRESHOLD"), 0.0)
        self.escalation_timeout: int = _int(os.getenv("ESCALATION_TIMEOUT"), 0)

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
        self.dashboard_auth_enabled: bool = _bool(os.getenv("DASHBOARD_AUTH_ENABLED", "false"))
        self.dashboard_username: str = os.getenv("DASHBOARD_USERNAME", "admin")
        self.dashboard_password: str = os.getenv("DASHBOARD_PASSWORD", "")

        # Notifications
        self.webhook_enabled: bool = _bool(os.getenv("WEBHOOK_ENABLED", "false"))
        self.webhook_url: str = os.getenv("WEBHOOK_URL", "")
        self.telegram_enabled: bool = _bool(os.getenv("TELEGRAM_ENABLED", "false"))
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
        self.pushover_enabled: bool = _bool(os.getenv("PUSHOVER_ENABLED", "false"))
        self.pushover_app_token: str = os.getenv("PUSHOVER_APP_TOKEN", "")
        self.pushover_user_key: str = os.getenv("PUSHOVER_USER_KEY", "")

        # Advanced
        self.dry_run: bool = _bool(os.getenv("DRY_RUN", "false"))

        # Per-sensor threshold overrides (populated dynamically)
        self.sensor_overrides: dict[str, dict[str, float]] = self._load_sensor_overrides()

    def validate(self) -> list[str]:
        """Validate configuration and return a list of error messages.

        Returns an empty list if configuration is valid.
        """
        errors: list[str] = []

        # SMTP validation
        if not self.smtp_host:
            errors.append("SMTP_HOST is not set")
        if not self.email_from:
            errors.append("EMAIL_FROM is not set")
        if not self.smtp_username:
            errors.append("SMTP_USERNAME is not set")
        if not self.smtp_password:
            errors.append("SMTP_PASSWORD is not set")

        # Recipient validation
        all_recipients = (
            self.recipients_warning
            + self.recipients_critical
            + self.recipients_emergency
        )
        if not all_recipients:
            errors.append("No email recipients configured at any level")

        # Threshold ordering
        if not (self.temp_warning < self.temp_critical < self.temp_emergency):
            errors.append(
                f"Thresholds must be in ascending order: "
                f"warning ({self.temp_warning}) < critical ({self.temp_critical}) "
                f"< emergency ({self.temp_emergency})"
            )

        # Hysteresis sanity
        if self.temp_hysteresis <= 0:
            errors.append("TEMP_HYSTERESIS must be positive")
        if self.temp_hysteresis >= self.temp_warning:
            errors.append("TEMP_HYSTERESIS must be less than TEMP_WARNING")

        # Monitoring intervals
        if self.poll_interval <= 0:
            errors.append("POLL_INTERVAL must be positive")
        if self.alert_cooldown < 0:
            errors.append("ALERT_COOLDOWN must be non-negative")

        # Sensor check
        if not (self.sensor_cpu_enabled or self.sensor_gpu_enabled or self.sensor_ds18b20_enabled):
            errors.append("At least one sensor must be enabled")

        # Per-sensor override ordering
        for sensor, overrides in self.sensor_overrides.items():
            w = overrides.get("warning", self.temp_warning)
            c = overrides.get("critical", self.temp_critical)
            e = overrides.get("emergency", self.temp_emergency)
            if not (w < c < e):
                errors.append(
                    f"Per-sensor thresholds for '{sensor}' must be in ascending order: "
                    f"warning ({w}) < critical ({c}) < emergency ({e})"
                )

        return errors

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
