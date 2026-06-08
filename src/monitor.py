"""Core monitoring loop for Pi Temperature Alerter.

Periodically reads all sensors, evaluates thresholds, and dispatches
alerts with cooldown and hysteresis support.
"""

import logging
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

logger = logging.getLogger("pi_temp_alerter")


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

        # Prune old CSV files on startup
        removed = prune_old_csv_files()
        if removed:
            logger.info("Pruned %d old CSV file(s)", removed)

        sensors = self._sensor_manager.sensors
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
            from src.alerting.notifiers.mqtt import publish_online
            publish_online()

        while self._running:
            self._poll()
            time.sleep(config.poll_interval)

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

            # Fan control (needs per-reading evaluation)
            if self._fan_update:
                self._fan_update(reading.temperature_c)

            # Rate-of-change check
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

    def _publish_collector_stats(self) -> None:
        """Publish external service collector stats to MQTT.

        Services are auto-detected: if the service is running and responsive,
        stats are published. Set COLLECTOR_*_ENABLED=false in .env to explicitly
        disable a collector even if the service is present.
        """
        from src.alerting.notifiers.mqtt import _get_client, _topic, _now_iso
        import json

        client = _get_client()
        if client is None:
            return

        # Registry of all collectors: (config_attr, module_path, function_name, topic_suffix)
        collectors = [
            ("collector_fr24_enabled", "src.sensors.collectors.fr24feed", "collect_fr24_stats", "service/fr24feed/state"),
            ("collector_readsb_enabled", "src.sensors.collectors.readsb", "collect_readsb_stats", "service/readsb/state"),
            (None, "src.sensors.collectors.pihole", "collect_pihole_stats", "service/pihole/state"),
            (None, "src.sensors.collectors.adguard", "collect_adguard_stats", "service/adguard/state"),
            (None, "src.sensors.collectors.unbound", "collect_unbound_stats", "service/unbound/state"),
            (None, "src.sensors.collectors.wireguard", "collect_wireguard_stats", "service/wireguard/state"),
            (None, "src.sensors.collectors.tailscale", "collect_tailscale_stats", "service/tailscale/state"),
            (None, "src.sensors.collectors.nginx", "collect_nginx_stats", "service/nginx/state"),
            (None, "src.sensors.collectors.plex", "collect_plex_stats", "service/plex/state"),
            (None, "src.sensors.collectors.jellyfin", "collect_jellyfin_stats", "service/jellyfin/state"),
            (None, "src.sensors.collectors.zigbee2mqtt", "collect_zigbee2mqtt_stats", "service/zigbee2mqtt/state"),
            (None, "src.sensors.collectors.influxdb", "collect_influxdb_stats", "service/influxdb/state"),
            (None, "src.sensors.collectors.docker", "collect_docker_stats", "service/docker/state"),
            (None, "src.sensors.collectors.dump1090", "collect_dump1090_stats", "service/dump1090/state"),
            (None, "src.sensors.collectors.ups", "collect_ups_stats", "service/ups/state"),
            (None, "src.sensors.collectors.smart", "collect_smart_stats", "service/smart/state"),
            (None, "src.sensors.collectors.systemd", "collect_systemd_stats", "service/systemd/state"),
            (None, "src.sensors.collectors.ntp", "collect_ntp_stats", "service/ntp/state"),
            (None, "src.sensors.collectors.gps", "collect_gps_stats", "service/gps/state"),
        ]

        for config_attr, module_path, func_name, topic_suffix in collectors:
            # Check if explicitly disabled via config
            if config_attr:
                state = getattr(config, config_attr, None)
                if state is False:
                    continue

            try:
                import importlib
                mod = importlib.import_module(module_path)
                collect_fn = getattr(mod, func_name)
                stats = collect_fn()

                if stats:
                    # Log first detection
                    detection_key = f"_detected_{topic_suffix}"
                    if not hasattr(self, detection_key):
                        service_name = topic_suffix.split("/")[1]
                        logger.info("Auto-detected %s service, publishing stats", service_name)
                        setattr(self, detection_key, True)

                    # Send HA auto-discovery for all fields in this collector
                    from src.alerting.notifiers.mqtt import publish_ha_discovery_for_collector
                    service_name = topic_suffix.split("/")[1]
                    publish_ha_discovery_for_collector(service_name, stats)

                    stats["timestamp"] = _now_iso()
                    topic = _topic(topic_suffix)
                    client.publish(topic, json.dumps(stats), qos=1, retain=True)
            except Exception:
                # Silently skip collectors that fail - they're optional
                pass
