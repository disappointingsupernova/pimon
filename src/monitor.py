"""Core monitoring loop for Pi Temperature Alerter.

Periodically reads all sensors, evaluates thresholds, and dispatches
alerts with cooldown and hysteresis support.
"""

import logging
import signal
import time
from datetime import datetime, timezone

from src.alerting.email_sender import send_alert_email, send_recovery_email
from src.alerting.thresholds import AlertLevel, ThresholdEvaluator
from src.config import config
from src.logger import log_temperature_csv
from src.sensors.base import SensorReading
from src.sensors.manager import SensorManager

logger = logging.getLogger("pi_temp_alerter")


class Monitor:
    """Main monitoring loop with graceful shutdown support."""

    def __init__(self) -> None:
        self._running = False
        self._sensor_manager = SensorManager()
        self._evaluator = ThresholdEvaluator()
        self._start_time: datetime | None = None

    def start(self) -> None:
        """Begin the monitoring loop. Blocks until stopped."""
        self._running = True
        self._start_time = datetime.now(timezone.utc)
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

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
        """Perform a single polling cycle across all sensors."""
        readings = self._sensor_manager.read_all()

        for reading in readings:
            self._process_reading(reading)

    def _process_reading(self, reading: SensorReading) -> None:
        """Process a single sensor reading: log, evaluate, and alert."""
        if not reading.available:
            logger.warning(
                "Sensor %s unavailable: %s", reading.sensor_name, reading.error
            )
            return

        logger.debug(
            "Sensor %s: %.1f C", reading.sensor_name, reading.temperature_c
        )

        # Log to CSV
        log_temperature_csv(reading.sensor_name, reading.temperature_c)

        # Evaluate thresholds
        new_level, previous_level = self._evaluator.evaluate(
            reading.sensor_name, reading.temperature_c
        )

        # Handle escalation
        if new_level != AlertLevel.NORMAL and new_level != previous_level:
            self._handle_alert(reading, new_level)
        elif new_level != AlertLevel.NORMAL:
            # Same level - check cooldown for repeated alerts
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
        """Send an alert email and record the event."""
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

        send_alert_email(recipients, level, reading.sensor_name, reading.temperature_c)

        state = self._evaluator.get_state(reading.sensor_name)
        state.record_alert(level)

    def _handle_recovery(self, reading: SensorReading, previous_level: AlertLevel) -> None:
        """Send a recovery notification."""
        logger.info(
            "RECOVERY: Sensor %s back to normal at %.1f C (was %s)",
            reading.sensor_name,
            reading.temperature_c,
            previous_level.name,
        )
        send_recovery_email(
            [], reading.sensor_name, reading.temperature_c, previous_level
        )

    def get_latest_readings(self) -> list[SensorReading]:
        """Get a fresh set of readings from all sensors (for dashboard/CLI)."""
        return self._sensor_manager.read_all()
