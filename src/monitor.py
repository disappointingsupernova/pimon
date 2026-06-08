"""Core monitoring loop for PiMon.

Periodically reads all sensors, evaluates thresholds, and dispatches
alerts with cooldown and hysteresis support.
"""

import logging
import os
import signal
import time
from datetime import date, datetime, timezone

from src.alerting.dispatcher import dispatch_alert, dispatch_recovery
from src.alerting.thresholds import AlertLevel, ThresholdEvaluator
from src.config import config
from src.dashboard.app import record_reading, update_latest_readings
from src.logger import log_temperatures_csv_batch, prune_old_csv_files
from src.sensors.base import SensorReading
from src.sensors.manager import SensorManager
from src.watchdog import init_watchdog, notify_ready, notify_stopping, notify_watchdog

logger = logging.getLogger("pimon")


class Monitor:
    """Main monitoring loop with graceful shutdown support."""

    def __init__(self, sensor_manager: SensorManager) -> None:
        self._running = False
        self._sensor_manager = sensor_manager
        self._evaluator = ThresholdEvaluator()
        self._start_time: datetime | None = None
        self._last_readings: dict[str, tuple[float, datetime]] = {}
        self._roc_alerted: dict[str, datetime] = {}
        self._last_digest_date: date | None = None

        # Pre-resolve optional module references to avoid repeated imports in hot loop
        self._store_readings_batch = None
        self._mqtt_publish = None
        self._fan_update = None

        if config.database_enabled:
            from src.database.repository import store_readings_batch
            self._store_readings_batch = store_readings_batch

        if config.mqtt_enabled:
            from src.alerting.notifiers.mqtt import publish_reading
            self._mqtt_publish = publish_reading

        if config.fan_control_enabled:
            from src.sensors.fan_control import update_fan
            self._fan_update = update_fan

    def start(self) -> None:
        """Begin the monitoring loop. Blocks until stopped."""
        self._running = True
        self._start_time = datetime.now(timezone.utc)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # SIGHUP triggers config hot-reload (Unix only)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, self._handle_sighup)

        # Initialise systemd watchdog
        init_watchdog()

        # Startup health check
        self._startup_health_check()

        # Prune old CSV files on startup
        removed = prune_old_csv_files()
        if removed:
            logger.info("Pruned %d old CSV file(s)", removed)

        # Prune old database records on startup
        if config.database_enabled and config.database_retention_days > 0:
            from src.database.repository import prune_old_records
            db_removed = prune_old_records(config.database_retention_days)
            if db_removed:
                logger.info("Pruned %d old database record(s)", db_removed)

        sensors = self._sensor_manager.sensors
        # Notify systemd that startup is complete
        notify_ready()

        # Send one-off startup notification if configured
        self._send_startup_notification()

        logger.info(
            "Monitoring started with %d sensor(s): %s",
            len(sensors),
            ", ".join(s.name for s in sensors),
        )
        logger.info(
            "Thresholds: warning=%.1f C, critical=%.1f C, emergency=%.1f C",
            config.temp_warning,
            config.temp_critical,
            config.temp_emergency,
        )
        if config.low_write_mode:
            logger.info(
                "Low-write mode active: CSV disabled, poll interval %ds, log level %s",
                config.poll_interval,
                config.log_level,
            )

        # Publish MQTT online status for Home Assistant availability tracking
        if config.mqtt_enabled:
            from src.alerting.notifiers.mqtt import publish_birth_message, publish_online
            publish_online()
            publish_birth_message()

        while self._running:
            self._poll()
            notify_watchdog()
            time.sleep(config.poll_interval)

        notify_stopping()
        logger.info("Monitoring stopped")

    def stop(self) -> None:
        """Signal the monitoring loop to stop."""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uptime_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return (datetime.now(timezone.utc) - self._start_time).total_seconds()

    def _handle_signal(self, signum: int, _frame) -> None:
        logger.info("Received signal %d, shutting down gracefully", signum)
        self.stop()

    def _handle_sighup(self, _signum: int, _frame) -> None:
        """Reload configuration from .env without restarting the service."""
        logger.info("Received SIGHUP, reloading configuration...")
        from src.config import Config, reload_env
        import src.config as config_module

        reload_env()
        config_module.config = Config()

        errors = config_module.config.validate()
        if errors:
            for err in errors:
                logger.error("Config reload error: %s", err)
            logger.error("Configuration invalid after reload, some values may be stale")
        else:
            logger.info("Configuration reloaded successfully")

    def _poll(self) -> None:
        """Perform a single polling cycle across all sensors.

        Reads all sensors first, then batches I/O operations (CSV, database,
        MQTT) to minimise file handles and network round-trips per cycle.
        """
        readings = self._sensor_manager.read_all()

        # Collect successful readings for batched I/O
        successful: list[tuple[str, float]] = []

        for reading in readings:
            if not reading.available:
                logger.warning(
                    "Sensor %s unavailable: %s", reading.sensor_name, reading.error
                )
                continue

            logger.debug(
                "Sensor %s: %.1f C", reading.sensor_name, reading.temperature_c
            )
            successful.append((reading.sensor_name, reading.temperature_c))

            # Update dashboard in-memory buffer
            record_reading(reading.sensor_name, reading.temperature_c)

        # Fan control using max temperature (or configured sensor)
        if self._fan_update and successful:
            if config.fan_sensor == "max":
                fan_temp = max(t for _, t in successful)
            else:
                fan_temp = next(
                    (t for s, t in successful if s == config.fan_sensor),
                    max(t for _, t in successful) if successful else 0.0,
                )
            self._fan_update(fan_temp)

        for reading in readings:
            if not reading.available:
                continue

            # Rate-of-change check
            self._check_rate_of_change(reading)

            # Threshold evaluation and alerting
            self._evaluate_and_alert(reading)
            self._check_rate_of_change(reading)

            # Threshold evaluation and alerting
            self._evaluate_and_alert(reading)

        # Batch I/O: CSV (one file open), database (one commit), MQTT
        if successful:
            log_temperatures_csv_batch(successful)

            if self._store_readings_batch:
                self._store_readings_batch(successful)

            # Store system metrics alongside temperature data
            if self._store_readings_batch:
                from src.sensors.system_metrics import collect_metrics
                from src.database.repository import store_system_metrics
                metrics = collect_metrics()
                store_system_metrics(
                    metrics.cpu_percent,
                    metrics.memory_percent,
                    metrics.disk_percent,
                    metrics.throttled,
                )
                # Check system metric thresholds
                self._check_metric_alerts(metrics)

            if self._mqtt_publish:
                for sensor_name, temp in successful:
                    self._mqtt_publish(sensor_name, temp)

            # Publish system metrics to MQTT
            if config.mqtt_enabled:
                from src.alerting.notifiers.mqtt import publish_system_metrics
                from src.sensors.system_metrics import collect_full_metrics
                publish_system_metrics(collect_full_metrics())

                # Publish external service collector stats
                self._publish_collector_stats()

        # Update cached data for dashboard API endpoints
        update_latest_readings([
            {
                "sensor": r.sensor_name,
                "temperature_c": r.temperature_c,
                "available": r.available,
                "error": r.error,
            }
            for r in readings
        ])

        # Send daily digest once per day
        self._check_daily_digest()

        # Check scheduled reboot
        self._check_scheduled_reboot()

    def _evaluate_and_alert(self, reading: SensorReading) -> None:
        """Evaluate thresholds and dispatch alerts/recovery for a reading."""
        new_level, previous_level = self._evaluator.evaluate(
            reading.sensor_name, reading.temperature_c
        )

        # Handle escalation
        if new_level != AlertLevel.NORMAL and new_level != previous_level:
            self._handle_alert(reading, new_level)
        elif new_level != AlertLevel.NORMAL:
            state = self._evaluator.get_state(reading.sensor_name)
            if state.can_send_alert(new_level):
                self._handle_alert(reading, new_level)

        # Handle recovery
        if (
            new_level == AlertLevel.NORMAL
            and previous_level != AlertLevel.NORMAL
            and config.recovery_notifications
        ):
            self._handle_recovery(reading, previous_level)

    def _handle_alert(self, reading: SensorReading, level: AlertLevel) -> None:
        """Dispatch alert via all enabled notification channels."""
        recipients = self._evaluator.get_recipients(level)
        if not recipients:
            logger.warning("No recipients configured for level %s", level.name)
            return

        logger.warning(
            "ALERT [%s] Sensor %s at %.1f C",
            level.name,
            reading.sensor_name,
            reading.temperature_c,
        )

        dispatch_alert(level, reading.sensor_name, reading.temperature_c, recipients)

        state = self._evaluator.get_state(reading.sensor_name)
        state.record_alert(level)
        self._persist_alert_state(reading.sensor_name)

    def _handle_recovery(self, reading: SensorReading, previous_level: AlertLevel) -> None:
        """Dispatch recovery notification via all enabled channels."""
        logger.info(
            "RECOVERY: Sensor %s back to normal at %.1f C (was %s)",
            reading.sensor_name,
            reading.temperature_c,
            previous_level.name,
        )
        dispatch_recovery(
            reading.sensor_name, reading.temperature_c, previous_level
        )
        self._persist_alert_state(reading.sensor_name)

    def _persist_alert_state(self, sensor_name: str) -> None:
        """Save the current alert state for a sensor to the database."""
        if not config.database_enabled:
            return
        state = self._evaluator.get_state(sensor_name)
        last_times = {
            lvl.name: ts
            for lvl, ts in state.last_alert_times.items()
        }
        from src.database.repository import save_alert_state
        save_alert_state(
            sensor_name,
            state.current_level.name,
            state.level_entered_at,
            last_times,
        )

    def get_latest_readings(self) -> list[SensorReading]:
        """Get a fresh set of readings from all sensors (for dashboard/CLI)."""
        return self._sensor_manager.read_all()

    def _check_rate_of_change(self, reading: SensorReading) -> None:
        """Alert if temperature is rising faster than the configured threshold."""
        if config.rate_of_change_threshold <= 0:
            return

        now = datetime.now(timezone.utc)
        sensor = reading.sensor_name

        if sensor in self._last_readings:
            prev_temp, prev_time = self._last_readings[sensor]
            elapsed_minutes = (now - prev_time).total_seconds() / 60.0

            if elapsed_minutes > 0:
                rate = (reading.temperature_c - prev_temp) / elapsed_minutes

                if rate >= config.rate_of_change_threshold:
                    # Respect cooldown
                    last_roc = self._roc_alerted.get(sensor)
                    if last_roc is None or (now - last_roc).total_seconds() >= config.alert_cooldown:
                        logger.warning(
                            "RATE-OF-CHANGE: %s rising at %.1f C/min (threshold: %.1f C/min)",
                            sensor, rate, config.rate_of_change_threshold,
                        )
                        recipients = self._evaluator.get_recipients(AlertLevel.WARNING)
                        if recipients:
                            dispatch_alert(
                                AlertLevel.WARNING, sensor, reading.temperature_c, recipients
                            )
                        self._roc_alerted[sensor] = now

        self._last_readings[sensor] = (reading.temperature_c, now)

    def _check_daily_digest(self) -> None:
        """Send the daily digest email if the day has rolled over."""
        if not config.daily_digest_enabled:
            return

        today = date.today()
        if self._last_digest_date == today:
            return

        # Only send after the configured hour
        now = datetime.now()
        if now.hour < config.daily_digest_hour:
            return

        self._last_digest_date = today

        from src.alerting.digest import send_daily_digest
        logger.info("Sending daily digest")
        send_daily_digest()

    def _check_scheduled_reboot(self) -> None:
        """Reboot the Pi on a scheduled day/hour if configured."""
        if not config.scheduled_reboot_enabled:
            return

        import subprocess
        now = datetime.now()
        day_name = now.strftime("%A").lower()

        if day_name != config.scheduled_reboot_day.lower():
            return
        if now.hour != config.scheduled_reboot_hour:
            return

        # Only reboot once (check we haven't already rebooted this hour)
        reboot_key = f"_rebooted_{now.date()}_{now.hour}"
        if hasattr(self, reboot_key):
            return
        setattr(self, reboot_key, True)

        logger.warning("Scheduled reboot triggered (day=%s, hour=%d)", day_name, now.hour)
        subprocess.run(["sudo", "reboot"], capture_output=True)

    def _startup_health_check(self) -> None:
        """Run a system health check on startup and log the results.

        Verifies that critical subsystems are operational before entering
        the main poll loop. Logs warnings for any issues detected.
        """
        logger.info("Running startup health check...")
        issues = []

        # Check sensors are available
        sensors = self._sensor_manager.sensors
        if not sensors:
            issues.append("No sensors available - nothing to monitor")

        # Check database connectivity
        if config.database_enabled:
            try:
                from src.database.models import get_session
                session = get_session()
                session.close()
            except Exception as exc:
                issues.append(f"Database connection failed: {exc}")

        # Check MQTT connectivity
        if config.mqtt_enabled:
            from src.alerting.notifiers.mqtt import _get_client
            client = _get_client()
            if client is None:
                issues.append("MQTT connection failed")

        # Check disk space (warn if > 90% full)
        try:
            import shutil
            usage = shutil.disk_usage("/")
            disk_percent = (usage.used / usage.total) * 100
            if disk_percent > 90:
                issues.append(f"Disk usage critically high: {disk_percent:.1f}%")
        except OSError:
            pass

        # Check writable directories
        from pathlib import Path
        for dir_name in ["logs", "data"]:
            dir_path = Path(__file__).resolve().parent.parent / dir_name
            if dir_path.exists() and not os.access(str(dir_path), os.W_OK):
                issues.append(f"Directory not writable: {dir_path}")

        # Report results
        if issues:
            for issue in issues:
                logger.warning("Health check: %s", issue)
            logger.warning("Startup health check completed with %d issue(s)", len(issues))
        else:
            logger.info("Startup health check passed")

    def _publish_collector_stats(self) -> None:
        """Run all service collectors, publish to MQTT, and check alert thresholds.

        Services are auto-detected: if the service is running and responsive,
        stats are published. Set COLLECTOR_*_ENABLED=false in .env to explicitly
        disable a collector even if the service is present.
        """
        from src.sensors.collectors.registry import collect_all, get_numeric_metrics
        from src.alerting.notifiers.mqtt import _get_client, _topic, _now_iso
        import json

        results = collect_all()

        client = _get_client()

        for service_name, stats in results.items():
            # Log first detection
            detection_key = f"_detected_{service_name}"
            if not hasattr(self, detection_key):
                logger.info("Auto-detected %s service, publishing stats", service_name)
                setattr(self, detection_key, True)

            # Publish to MQTT
            if client is not None:
                from src.alerting.notifiers.mqtt import publish_ha_discovery_for_collector
                publish_ha_discovery_for_collector(service_name, stats)
                payload = dict(stats)
                payload["timestamp"] = _now_iso()
                topic = _topic(f"service/{service_name}/state")
                client.publish(topic, json.dumps(payload), qos=1, retain=True)

            # Check collector alert thresholds
            self._check_collector_alerts(service_name, stats)

    def _send_startup_notification(self) -> None:
        """Send a one-off notification that PiMon has started successfully."""
        if not config.startup_notification:
            return

        import socket

        hostname = socket.gethostname()
        sensors = self._sensor_manager.sensors
        sensor_names = ", ".join(s.name for s in sensors) if sensors else "none"
        message = (
            f"PiMon is running on {hostname}\n"
            f"Sensors: {sensor_names}\n"
            f"Poll interval: {config.poll_interval}s\n"
            f"Dashboard: http://{config.dashboard_host}:{config.dashboard_port}"
        )

        logger.info("Sending startup notification")

        # Telegram
        if config.telegram_enabled:
            from src.alerting.notifiers.telegram import send_telegram
            send_telegram(message)

        # Pushover
        if config.pushover_enabled:
            from src.alerting.notifiers.pushover import send_pushover
            send_pushover(title="PiMon Started", message=message, level="INFO")

        # MQTT
        if config.mqtt_enabled:
            from src.alerting.notifiers.mqtt import publish_alert
            publish_alert("system", "INFO", 0.0)

    def _check_metric_alerts(self, metrics) -> None:
        """Check system metrics against configured thresholds and alert if exceeded.

        Each metric (CPU, memory, disk) is independently configurable.
        A value of 0 means the alert is disabled for that metric.
        Respects the global alert cooldown to avoid spamming.
        """
        now = datetime.now(timezone.utc)
        checks = [
            ("cpu_percent", metrics.cpu_percent, config.alert_cpu_percent),
            ("memory_percent", metrics.memory_percent, config.alert_memory_percent),
            ("disk_percent", metrics.disk_percent, config.alert_disk_percent),
        ]

        for metric_name, current_value, threshold in checks:
            if threshold <= 0:
                continue
            if current_value < threshold:
                continue

            # Respect cooldown per metric
            cooldown_key = f"_metric_alert_{metric_name}"
            last_alerted = getattr(self, cooldown_key, None)
            if last_alerted and (now - last_alerted).total_seconds() < config.alert_cooldown:
                continue

            setattr(self, cooldown_key, now)
            logger.warning(
                "METRIC ALERT: %s at %.1f%% (threshold: %.1f%%)",
                metric_name, current_value, threshold,
            )

            recipients = self._evaluator.get_recipients(AlertLevel.WARNING)
            if recipients:
                dispatch_alert(
                    AlertLevel.WARNING,
                    f"system/{metric_name}",
                    current_value,
                    recipients,
                )

    def _check_collector_alerts(self, service_name: str, stats: dict) -> None:
        """Check collector metrics against configured thresholds.

        Thresholds are defined in .env as ALERT_<SERVICE>_<METRIC>=<value>.
        For example: ALERT_DOCKER_CONTAINERS_STOPPED=1, ALERT_UPS_BATTERY_CHARGE=20.
        A value of 0 means disabled. Alerts fire when the metric exceeds the
        threshold (or drops below for 'min' prefixed thresholds).
        """
        import os

        now = datetime.now(timezone.utc)
        prefix = f"ALERT_{service_name.upper()}_"

        for key, value in stats.items():
            if not isinstance(value, (int, float)):
                continue

            # Check for threshold env var
            env_key = f"{prefix}{key.upper()}"
            threshold_str = os.getenv(env_key, "")
            if not threshold_str:
                continue

            try:
                threshold = float(threshold_str)
            except ValueError:
                continue

            if threshold <= 0:
                continue

            # Alert if value exceeds threshold
            if value < threshold:
                continue

            # Respect cooldown
            cooldown_key = f"_collector_alert_{service_name}_{key}"
            last_alerted = getattr(self, cooldown_key, None)
            if last_alerted and (now - last_alerted).total_seconds() < config.alert_cooldown:
                continue

            setattr(self, cooldown_key, now)
            logger.warning(
                "COLLECTOR ALERT: %s/%s at %s (threshold: %s)",
                service_name, key, value, threshold,
            )

            recipients = self._evaluator.get_recipients(AlertLevel.WARNING)
            if recipients:
                dispatch_alert(
                    AlertLevel.WARNING,
                    f"service/{service_name}/{key}",
                    float(value),
                    recipients,
                )
