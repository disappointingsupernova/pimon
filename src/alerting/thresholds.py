"""Threshold evaluation with hysteresis for alert state management."""

from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.config import config


class AlertLevel(Enum):
    """Alert severity levels in ascending order."""

    NORMAL = auto()
    WARNING = auto()
    CRITICAL = auto()
    EMERGENCY = auto()


@dataclass
class AlertState:
    """Tracks the current alert state for a single sensor."""

    sensor_name: str
    current_level: AlertLevel = AlertLevel.NORMAL
    level_entered_at: datetime | None = None
    last_alert_times: dict[AlertLevel, datetime] = field(default_factory=dict)

    def can_send_alert(self, level: AlertLevel) -> bool:
        """Check whether cooldown has elapsed for a given alert level."""
        last_time = self.last_alert_times.get(level)
        if last_time is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
        return elapsed >= config.alert_cooldown

    def record_alert(self, level: AlertLevel) -> None:
        """Record that an alert was sent at the current time."""
        self.last_alert_times[level] = datetime.now(timezone.utc)

    def seconds_at_current_level(self) -> float:
        """Return how long the sensor has been at the current level."""
        if self.level_entered_at is None:
            return 0.0
        return (datetime.now(timezone.utc) - self.level_entered_at).total_seconds()


class ThresholdEvaluator:
    """Evaluates temperature readings against configured thresholds.

    Implements hysteresis to prevent alert flapping when temperature
    hovers around a threshold boundary.
    """

    def __init__(self) -> None:
        self._states: dict[str, AlertState] = {}

    def _get_state(self, sensor_name: str) -> AlertState:
        if sensor_name not in self._states:
            self._states[sensor_name] = AlertState(sensor_name=sensor_name)
        return self._states[sensor_name]

    def evaluate(self, sensor_name: str, temperature: float) -> tuple[AlertLevel, AlertLevel]:
        """Evaluate a temperature reading and return (new_level, previous_level).

        The new level accounts for hysteresis: a sensor must drop below
        (threshold - hysteresis) before the level is cleared downwards.
        Uses per-sensor threshold overrides when configured.
        """
        state = self._get_state(sensor_name)
        previous_level = state.current_level
        thresholds = config.get_thresholds(sensor_name)
        new_level = self._compute_level(temperature, previous_level, thresholds)

        # Escalation timeout: if stuck at a non-normal level for too long, escalate
        if (
            config.escalation_timeout > 0
            and new_level == previous_level
            and new_level not in (AlertLevel.NORMAL, AlertLevel.EMERGENCY)
            and state.seconds_at_current_level() >= config.escalation_timeout
        ):
            escalation_map = {
                AlertLevel.WARNING: AlertLevel.CRITICAL,
                AlertLevel.CRITICAL: AlertLevel.EMERGENCY,
            }
            new_level = escalation_map.get(new_level, new_level)

        # Track when we enter a new level
        if new_level != previous_level:
            state.level_entered_at = datetime.now(timezone.utc)

        state.current_level = new_level
        return new_level, previous_level

    def _compute_level(
        self, temp: float, current: AlertLevel, thresholds: dict[str, float]
    ) -> AlertLevel:
        """Determine the alert level with hysteresis applied."""
        hysteresis = config.temp_hysteresis
        warning = thresholds["warning"]
        critical = thresholds["critical"]
        emergency = thresholds["emergency"]

        # Escalation (no hysteresis needed going up)
        if temp >= emergency:
            return AlertLevel.EMERGENCY
        if temp >= critical:
            return AlertLevel.CRITICAL
        if temp >= warning:
            return AlertLevel.WARNING

        # De-escalation with hysteresis
        if current == AlertLevel.EMERGENCY:
            if temp < emergency - hysteresis:
                return self._compute_level(temp, AlertLevel.CRITICAL, thresholds)
            return AlertLevel.EMERGENCY

        if current == AlertLevel.CRITICAL:
            if temp < critical - hysteresis:
                return self._compute_level(temp, AlertLevel.WARNING, thresholds)
            return AlertLevel.CRITICAL

        if current == AlertLevel.WARNING:
            if temp < warning - hysteresis:
                return AlertLevel.NORMAL
            return AlertLevel.WARNING

        return AlertLevel.NORMAL

    def get_state(self, sensor_name: str) -> AlertState:
        """Retrieve the current alert state for a sensor."""
        return self._get_state(sensor_name)

    def get_recipients(self, level: AlertLevel) -> list[str]:
        """Return the configured recipient list for a given alert level."""
        match level:
            case AlertLevel.WARNING:
                return config.recipients_warning
            case AlertLevel.CRITICAL:
                return config.recipients_critical
            case AlertLevel.EMERGENCY:
                return config.recipients_emergency
            case _:
                return []
