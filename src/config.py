"""Configuration loader for PiMon.

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
        self.daily_digest_enabled: bool = _bool(os.getenv("DAILY_DIGEST_ENABLED", "false"))
        self.daily_digest_hour: int = _int(os.getenv("DAILY_DIGEST_HOUR"), 7)

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

        # Endpoint toggles (individually enable/disable dashboard routes)
        self.endpoint_api_enabled: bool = _bool(os.getenv("ENDPOINT_API_ENABLED", "true"))
        self.endpoint_health_enabled: bool = _bool(os.getenv("ENDPOINT_HEALTH_ENABLED", "true"))
        self.endpoint_metrics_enabled: bool = _bool(os.getenv("ENDPOINT_METRICS_ENABLED", "true"))

        # Database
        _default_db = "sqlite:///" + str(Path(__file__).resolve().parent.parent / "data" / "pimon.db")
        self.database_url: str = os.getenv("DATABASE_URL", _default_db)
        self.database_enabled: bool = _bool(os.getenv("DATABASE_ENABLED", "true"))
        self.database_retention_days: int = _int(os.getenv("DATABASE_RETENTION_DAYS"), 90)

        # Notifications
        self.webhook_enabled: bool = _bool(os.getenv("WEBHOOK_ENABLED", "false"))
        self.webhook_url: str = os.getenv("WEBHOOK_URL", "")
        self.webhook_verify_ssl: bool = _bool(os.getenv("WEBHOOK_VERIFY_SSL", "true"))
        self.telegram_enabled: bool = _bool(os.getenv("TELEGRAM_ENABLED", "false"))
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
        self.pushover_enabled: bool = _bool(os.getenv("PUSHOVER_ENABLED", "false"))
        self.pushover_app_token: str = os.getenv("PUSHOVER_APP_TOKEN", "")
        self.pushover_user_key: str = os.getenv("PUSHOVER_USER_KEY", "")
        self.mqtt_enabled: bool = _bool(os.getenv("MQTT_ENABLED", "false"))
        self.mqtt_host: str = os.getenv("MQTT_HOST", "localhost")
        self.mqtt_port: int = _int(os.getenv("MQTT_PORT"), 1883)
        self.mqtt_tls: bool = _bool(os.getenv("MQTT_TLS", "false"))
        self.mqtt_username: str = os.getenv("MQTT_USERNAME", "")
        self.mqtt_password: str = os.getenv("MQTT_PASSWORD", "")
        self.mqtt_client_id: str = os.getenv("MQTT_CLIENT_ID", "pimon")
        self.mqtt_topic_prefix: str = os.getenv("MQTT_TOPIC_PREFIX", "pimon")

        # Advanced
        self.dry_run: bool = _bool(os.getenv("DRY_RUN", "false"))
        self.low_write_mode: bool = _bool(os.getenv("LOW_WRITE_MODE", "false"))
        self.prometheus_prefix: str = os.getenv("PROMETHEUS_PREFIX", "pimon")
        self.scheduled_reboot_enabled: bool = _bool(os.getenv("SCHEDULED_REBOOT_ENABLED", "false"))
        self.scheduled_reboot_day: str = os.getenv("SCHEDULED_REBOOT_DAY", "sunday")
        self.scheduled_reboot_hour: int = _int(os.getenv("SCHEDULED_REBOOT_HOUR"), 4)

        # Apply low-write mode overrides to reduce SD card wear
        if self.low_write_mode:
            self.csv_logging_enabled = False
            self.poll_interval = max(self.poll_interval, 60)
            self.log_level = "WARNING" if self.log_level == "INFO" else self.log_level

        # Fan control
        self.fan_control_enabled: bool = _bool(os.getenv("FAN_CONTROL_ENABLED", "false"))
        self.fan_gpio_pin: int = _int(os.getenv("FAN_GPIO_PIN"), 14)
        self.fan_on_threshold: float = _float(os.getenv("FAN_ON_THRESHOLD"), 55.0)
        self.fan_off_threshold: float = _float(os.getenv("FAN_OFF_THRESHOLD"), 45.0)
        self.fan_sensor: str = os.getenv("FAN_SENSOR", "max")  # 'max' or specific sensor name

        # Sensor aliases (friendly names for display)
        self.sensor_aliases: dict[str, str] = self._load_sensor_aliases()

        # External service collectors (auto-detected unless explicitly disabled)
        # Set to 'false' to disable even if the service is detected
        self.collector_fr24_enabled: bool | None = self._collector_state("COLLECTOR_FR24_ENABLED")
        self.collector_readsb_enabled: bool | None = self._collector_state("COLLECTOR_READSB_ENABLED")
        self.collector_readsb_stats_dir: str = os.getenv("COLLECTOR_READSB_STATS_DIR", "/run/readsb")

        # Per-sensor threshold overrides (populated dynamically)
        self.sensor_overrides: dict[str, dict[str, float]] = self._load_sensor_overrides()

    def validate(self) -> list[str]:
        """Validate configuration and return a list of error messages.

        Returns an empty list if configuration is valid.
        Only validates SMTP if email recipients are configured.
        """
        errors: list[str] = []

        # SMTP validation - only require host and from address if recipients are set.
        # Username/password are optional (local relays like Postfix don't need auth).
        all_recipients = (
            self.recipients_warning
            + self.recipients_critical
            + self.recipients_emergency
        )
        if all_recipients:
            if not self.smtp_host:
                errors.append("SMTP_HOST is not set (required when recipients are configured)")
            if not self.email_from:
                errors.append("EMAIL_FROM is not set (required when recipients are configured)")

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

    def _collector_state(self, env_key: str) -> bool | None:
        """Determine collector state: True (forced on), False (forced off), None (auto-detect)."""
        value = os.getenv(env_key)
        if value is None:
            return None  # Not set - will auto-detect
        return _bool(value)

    def _load_sensor_aliases(self) -> dict[str, str]:
        """Load sensor aliases from environment variables.

        Looks for SENSOR_ALIAS_<NAME>=Friendly Name patterns.
        """
        aliases: dict[str, str] = {}
        prefix = "SENSOR_ALIAS_"
        for key, value in os.environ.items():
            if key.startswith(prefix) and value:
                sensor_name = key[len(prefix):].lower()
                aliases[sensor_name] = value.strip()
        return aliases

    def get_sensor_display_name(self, sensor_name: str) -> str:
        """Return the display name for a sensor (alias if set, otherwise raw name)."""
        return self.sensor_aliases.get(sensor_name.lower(), sensor_name)

    @staticmethod
    def get_pi_model() -> str:
        """Read the Raspberry Pi model from /proc/device-tree/model."""
        try:
            model = Path("/proc/device-tree/model").read_text().strip().rstrip("\x00")
            return model
        except (OSError, ValueError):
            return "Unknown"

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
