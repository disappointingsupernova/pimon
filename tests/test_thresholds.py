"""Tests for src.alerting.thresholds module."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.alerting.thresholds import AlertLevel, AlertState, ThresholdEvaluator


class TestAlertLevel:
    """Test AlertLevel enum."""

    def test_levels_exist(self):
        assert AlertLevel.NORMAL
        assert AlertLevel.WARNING
        assert AlertLevel.CRITICAL
        assert AlertLevel.EMERGENCY

    def test_ordering(self):
        assert AlertLevel.NORMAL.value < AlertLevel.WARNING.value
        assert AlertLevel.WARNING.value < AlertLevel.CRITICAL.value
        assert AlertLevel.CRITICAL.value < AlertLevel.EMERGENCY.value


class TestAlertState:
    """Test AlertState dataclass."""

    def test_initial_state(self):
        state = AlertState(sensor_name="test")
        assert state.current_level == AlertLevel.NORMAL
        assert state.level_entered_at is None
        assert state.last_alert_times == {}

    def test_can_send_alert_first_time(self):
        state = AlertState(sensor_name="test")
        assert state.can_send_alert(AlertLevel.WARNING) is True

    def test_can_send_alert_respects_cooldown(self, fresh_config):
        state = AlertState(sensor_name="test")
        state.record_alert(AlertLevel.WARNING)
        # Immediately after recording, cooldown not elapsed
        assert state.can_send_alert(AlertLevel.WARNING) is False

    def test_record_alert_stores_timestamp(self):
        state = AlertState(sensor_name="test")
        state.record_alert(AlertLevel.CRITICAL)
        assert AlertLevel.CRITICAL in state.last_alert_times

    def test_seconds_at_current_level_zero_initially(self):
        state = AlertState(sensor_name="test")
        assert state.seconds_at_current_level() == 0.0

    def test_seconds_at_current_level_nonzero(self):
        state = AlertState(sensor_name="test")
        state.level_entered_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert state.seconds_at_current_level() > 0


class TestThresholdEvaluator:
    """Test ThresholdEvaluator logic including hysteresis."""

    @pytest.fixture
    def evaluator(self):
        with patch("src.alerting.thresholds.config") as mock_config:
            mock_config.database_enabled = False
            mock_config.temp_warning = 60.0
            mock_config.temp_critical = 70.0
            mock_config.temp_emergency = 80.0
            mock_config.temp_hysteresis = 3.0
            mock_config.alert_cooldown = 300
            mock_config.escalation_timeout = 0
            mock_config.get_thresholds.return_value = {
                "warning": 60.0,
                "critical": 70.0,
                "emergency": 80.0,
            }
            mock_config.recipients_warning = ["test@example.com"]
            mock_config.recipients_critical = ["test@example.com"]
            mock_config.recipients_emergency = ["test@example.com"]
            yield ThresholdEvaluator()

    def test_normal_reading(self, evaluator):
        new, prev = evaluator.evaluate("cpu", 50.0)
        assert new == AlertLevel.NORMAL
        assert prev == AlertLevel.NORMAL

    def test_warning_trigger(self, evaluator):
        new, prev = evaluator.evaluate("cpu", 62.0)
        assert new == AlertLevel.WARNING
        assert prev == AlertLevel.NORMAL

    def test_critical_trigger(self, evaluator):
        new, prev = evaluator.evaluate("cpu", 72.0)
        assert new == AlertLevel.CRITICAL
        assert prev == AlertLevel.NORMAL

    def test_emergency_trigger(self, evaluator):
        new, prev = evaluator.evaluate("cpu", 82.0)
        assert new == AlertLevel.EMERGENCY
        assert prev == AlertLevel.NORMAL

    def test_hysteresis_prevents_flapping(self, evaluator):
        # Go into warning
        evaluator.evaluate("cpu", 62.0)
        # Drop just below warning but within hysteresis
        new, prev = evaluator.evaluate("cpu", 58.0)
        assert new == AlertLevel.WARNING  # Still warning due to hysteresis

    def test_hysteresis_allows_recovery(self, evaluator):
        # Go into warning
        evaluator.evaluate("cpu", 62.0)
        # Drop below warning - hysteresis (60 - 3 = 57)
        new, prev = evaluator.evaluate("cpu", 56.0)
        assert new == AlertLevel.NORMAL

    def test_escalation_from_warning_to_critical(self, evaluator):
        evaluator.evaluate("cpu", 62.0)  # Warning
        new, prev = evaluator.evaluate("cpu", 72.0)  # Critical
        assert new == AlertLevel.CRITICAL
        assert prev == AlertLevel.WARNING

    def test_get_state_creates_new(self, evaluator):
        state = evaluator.get_state("new_sensor")
        assert state.sensor_name == "new_sensor"
        assert state.current_level == AlertLevel.NORMAL

    def test_get_state_returns_same_instance(self, evaluator):
        s1 = evaluator.get_state("cpu")
        s2 = evaluator.get_state("cpu")
        assert s1 is s2

    def test_get_recipients_warning(self, evaluator):
        recipients = evaluator.get_recipients(AlertLevel.WARNING)
        assert "test@example.com" in recipients

    def test_get_recipients_normal_empty(self, evaluator):
        recipients = evaluator.get_recipients(AlertLevel.NORMAL)
        assert recipients == []
