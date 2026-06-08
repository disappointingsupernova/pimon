"""Tests for src.monitor module."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from src.alerting.thresholds import AlertLevel
from src.sensors.base import SensorReading


class TestMonitorInit:
    """Test Monitor initialisation."""

    @patch("src.monitor.config")
    def test_creates_evaluator(self, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False

        from src.monitor import Monitor
        manager = MagicMock()
        monitor = Monitor(manager)
        assert monitor._evaluator is not None

    @patch("src.monitor.config")
    def test_no_crash_without_optional_modules(self, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False

        from src.monitor import Monitor
        manager = MagicMock()
        monitor = Monitor(manager)
        assert monitor._store_readings_batch is None
        assert monitor._mqtt_publish is None
        assert monitor._fan_update is None


class TestMonitorProperties:
    """Test Monitor properties."""

    @patch("src.monitor.config")
    def test_uptime_zero_before_start(self, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())
        assert monitor.uptime_seconds == 0.0

    @patch("src.monitor.config")
    def test_is_running_false_initially(self, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())
        assert monitor.is_running is False


class TestEvaluateAndAlert:
    """Test the _evaluate_and_alert method."""

    @patch("src.alerting.thresholds.config")
    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_dispatches_alert_on_threshold_breach(self, mock_dispatch, mock_config, mock_thresh_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.recovery_notifications = False

        # Configure threshold config mock
        for cfg in (mock_config, mock_thresh_config):
            cfg.temp_warning = 60.0
            cfg.temp_critical = 70.0
            cfg.temp_emergency = 80.0
            cfg.temp_hysteresis = 3.0
            cfg.alert_cooldown = 300
            cfg.escalation_timeout = 0
            cfg.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}
            cfg.recipients_warning = ["test@example.com"]
            cfg.recipients_critical = ["crit@example.com"]
            cfg.recipients_emergency = ["emerg@example.com"]
            cfg.database_enabled = False

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())
        reading = SensorReading(sensor_name="cpu", temperature_c=65.0)
        monitor._evaluate_and_alert(reading)
        mock_dispatch.assert_called_once()

    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_recovery")
    @patch("src.monitor.dispatch_alert")
    def test_dispatches_recovery_on_return_to_normal(self, mock_alert, mock_recovery, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.recovery_notifications = True
        mock_config.temp_warning = 60.0
        mock_config.temp_critical = 70.0
        mock_config.temp_emergency = 80.0
        mock_config.temp_hysteresis = 3.0
        mock_config.alert_cooldown = 300
        mock_config.escalation_timeout = 0
        mock_config.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}
        mock_config.recipients_warning = ["test@example.com"]

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        # First trigger warning
        reading_high = SensorReading(sensor_name="cpu", temperature_c=65.0)
        monitor._evaluate_and_alert(reading_high)

        # Then recover (below warning - hysteresis)
        reading_low = SensorReading(sensor_name="cpu", temperature_c=50.0)
        monitor._evaluate_and_alert(reading_low)
        mock_recovery.assert_called_once()


class TestMetricAlerts:
    """Test system metric alert checking."""

    @patch("src.alerting.thresholds.config")
    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_cpu_alert_when_threshold_exceeded(self, mock_dispatch, mock_config, mock_thresh_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.alert_cpu_percent = 90.0
        mock_config.alert_memory_percent = 0.0
        mock_config.alert_disk_percent = 0.0
        mock_config.alert_cooldown = 300
        mock_config.recipients_warning = ["test@example.com"]
        mock_config.recipients_critical = []
        mock_config.recipients_emergency = []

        mock_thresh_config.recipients_warning = ["test@example.com"]
        mock_thresh_config.recipients_critical = []
        mock_thresh_config.recipients_emergency = []
        mock_thresh_config.database_enabled = False

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        metrics = MagicMock()
        metrics.cpu_percent = 95.0
        metrics.memory_percent = 50.0
        metrics.disk_percent = 30.0

        monitor._check_metric_alerts(metrics)
        mock_dispatch.assert_called_once()
        call_args = mock_dispatch.call_args
        assert call_args[0][1] == "system/cpu_percent"

    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_no_alert_when_below_threshold(self, mock_dispatch, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.alert_cpu_percent = 90.0
        mock_config.alert_memory_percent = 0.0
        mock_config.alert_disk_percent = 0.0
        mock_config.alert_cooldown = 300

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        metrics = MagicMock()
        metrics.cpu_percent = 50.0
        metrics.memory_percent = 50.0
        metrics.disk_percent = 30.0

        monitor._check_metric_alerts(metrics)
        mock_dispatch.assert_not_called()

    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_no_alert_when_disabled(self, mock_dispatch, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.alert_cpu_percent = 0.0
        mock_config.alert_memory_percent = 0.0
        mock_config.alert_disk_percent = 0.0
        mock_config.alert_cooldown = 300

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        metrics = MagicMock()
        metrics.cpu_percent = 99.0
        metrics.memory_percent = 99.0
        metrics.disk_percent = 99.0

        monitor._check_metric_alerts(metrics)
        mock_dispatch.assert_not_called()

    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_metric_alert_respects_cooldown(self, mock_dispatch, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.alert_cpu_percent = 90.0
        mock_config.alert_memory_percent = 0.0
        mock_config.alert_disk_percent = 0.0
        mock_config.alert_cooldown = 300
        mock_config.recipients_warning = ["test@example.com"]
        mock_config.recipients_critical = []
        mock_config.recipients_emergency = []

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        metrics = MagicMock()
        metrics.cpu_percent = 95.0
        metrics.memory_percent = 50.0
        metrics.disk_percent = 30.0

        monitor._check_metric_alerts(metrics)
        mock_dispatch.reset_mock()

        # Second call should be throttled
        monitor._check_metric_alerts(metrics)
        mock_dispatch.assert_not_called()


class TestRateOfChange:
    """Test rate-of-change alerting."""

    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_no_alert_when_disabled(self, mock_dispatch, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.rate_of_change_threshold = 0.0

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())
        reading = SensorReading(sensor_name="cpu", temperature_c=65.0)
        monitor._check_rate_of_change(reading)
        mock_dispatch.assert_not_called()
