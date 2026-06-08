"""Tests for src.__init__ (version), src.watchdog, src.alerting.templates, and sensors."""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestVersion:
    """Test version derivation from git."""

    def test_version_is_string(self):
        from src import __version__
        assert isinstance(__version__, str)

    def test_version_has_base(self):
        from src import __version__
        assert __version__.startswith("1.0.0")

    def test_version_contains_hash_when_in_repo(self):
        from src import __version__
        # We are in a git repo during tests
        assert "+" in __version__

    def test_fallback_when_git_unavailable(self):
        from src import _get_version, _FALLBACK_VERSION
        with patch("subprocess.run", side_effect=OSError("no git")):
            version = _get_version()
            assert version == _FALLBACK_VERSION

    def test_fallback_when_not_a_repo(self):
        from src import _get_version, _FALLBACK_VERSION
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            version = _get_version()
            assert version == _FALLBACK_VERSION


class TestWatchdog:
    """Test systemd watchdog module."""

    def test_init_noop_without_notify_socket(self, monkeypatch):
        monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
        from src.watchdog import init_watchdog, _enabled
        init_watchdog()
        # Should not crash

    def test_notify_ready_noop_when_disabled(self):
        from src import watchdog
        watchdog._enabled = False
        watchdog.notify_ready()  # Should not crash

    def test_notify_watchdog_noop_when_disabled(self):
        from src import watchdog
        watchdog._enabled = False
        watchdog.notify_watchdog()  # Should not crash

    def test_notify_stopping_noop_when_disabled(self):
        from src import watchdog
        watchdog._enabled = False
        watchdog.notify_stopping()  # Should not crash


class TestAlertTemplates:
    """Test Jinja2 alert template rendering."""

    def test_render_alert_returns_plain_text(self):
        with patch("src.alerting.templates.config") as mock_config:
            mock_config.dashboard_host = "localhost"
            mock_config.dashboard_port = 5000
            mock_config.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}

            from src.alerting.templates import render_alert
            plain, html = render_alert("WARNING", "cpu", 65.0)
            assert plain is not None
            assert "WARNING" in plain
            assert "cpu" in plain
            assert "65.0" in plain

    def test_render_alert_returns_html(self):
        with patch("src.alerting.templates.config") as mock_config:
            mock_config.dashboard_host = "localhost"
            mock_config.dashboard_port = 5000
            mock_config.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}

            from src.alerting.templates import render_alert
            plain, html = render_alert("CRITICAL", "gpu", 72.0)
            assert html is not None
            assert "<html>" in html

    def test_render_recovery(self):
        with patch("src.alerting.templates.config") as mock_config:
            mock_config.dashboard_host = "localhost"
            mock_config.dashboard_port = 5000
            mock_config.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}

            from src.alerting.templates import render_recovery
            plain, html = render_recovery("cpu", 55.0, "WARNING")
            assert plain is not None
            assert "RECOVERED" in plain
            assert html is not None

    def test_render_missing_template_returns_none(self):
        with patch("src.alerting.templates.config") as mock_config:
            mock_config.dashboard_host = "localhost"
            mock_config.dashboard_port = 5000
            mock_config.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}

            from src.alerting.templates import _render
            result = _render("nonexistent_template.txt.j2", {})
            assert result is None


class TestSensorBase:
    """Test sensor base classes."""

    def test_sensor_reading_dataclass(self):
        from src.sensors.base import SensorReading
        r = SensorReading(sensor_name="cpu", temperature_c=55.0)
        assert r.available is True
        assert r.error is None

    def test_sensor_reading_unavailable(self):
        from src.sensors.base import SensorReading
        r = SensorReading(sensor_name="gpu", temperature_c=0.0, available=False, error="not found")
        assert r.available is False
        assert r.error == "not found"

    def test_base_sensor_is_abstract(self):
        from src.sensors.base import BaseSensor
        with pytest.raises(TypeError):
            BaseSensor()
