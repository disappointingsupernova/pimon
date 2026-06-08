"""Tests for src.sensors.collectors.registry and collector alerting."""

from unittest.mock import patch, MagicMock

import pytest


class TestCollectorRegistry:
    """Test the centralised collector registry."""

    def test_collect_all_returns_dict(self):
        from src.sensors.collectors.registry import collect_all
        # On a dev machine most collectors will return None
        results = collect_all()
        assert isinstance(results, dict)

    def test_get_cached_results_empty_initially(self):
        from src.sensors.collectors.registry import _last_results
        # After collect_all has been called at least once in test above
        assert isinstance(_last_results, dict)

    def test_get_numeric_metrics_filters_strings(self):
        from src.sensors.collectors.registry import get_numeric_metrics
        stats = {
            "cpu_percent": 45.0,
            "status": "healthy",
            "version": "1.2.3",
            "containers_running": 3,
            "throttled": True,
            "timestamp": "2024-01-01T00:00:00",
        }
        result = get_numeric_metrics(stats)
        assert "cpu_percent" in result
        assert "containers_running" in result
        assert "throttled" in result
        assert "status" not in result
        assert "version" not in result
        assert "timestamp" not in result

    def test_get_numeric_metrics_empty_dict(self):
        from src.sensors.collectors.registry import get_numeric_metrics
        assert get_numeric_metrics({}) == {}

    @patch("src.sensors.collectors.registry.config")
    def test_disabled_collector_skipped(self, mock_config):
        mock_config.collector_fr24_enabled = False
        mock_config.collector_readsb_enabled = False

        from src.sensors.collectors.registry import collect_all
        results = collect_all()
        assert "fr24feed" not in results
        assert "readsb" not in results


class TestCollectorAlerts:
    """Test collector-based alerting in the monitor."""

    @patch("src.alerting.thresholds.config")
    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_collector_alert_fires_when_threshold_exceeded(self, mock_dispatch, mock_config, mock_thresh_config, monkeypatch):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.alert_cooldown = 300
        mock_config.recipients_warning = ["test@example.com"]
        mock_config.recipients_critical = []
        mock_config.recipients_emergency = []

        mock_thresh_config.recipients_warning = ["test@example.com"]
        mock_thresh_config.recipients_critical = []
        mock_thresh_config.recipients_emergency = []
        mock_thresh_config.database_enabled = False
        mock_thresh_config.alert_cooldown = 300

        monkeypatch.setenv("ALERT_DOCKER_CONTAINERS_STOPPED", "2")

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        stats = {"containers_stopped": 5, "containers_running": 2, "images": 10}
        monitor._check_collector_alerts("docker", stats)
        mock_dispatch.assert_called_once()
        assert "service/docker/containers_stopped" in mock_dispatch.call_args[0][1]

    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_collector_alert_does_not_fire_below_threshold(self, mock_dispatch, mock_config, monkeypatch):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.alert_cooldown = 300

        monkeypatch.setenv("ALERT_UPS_BATTERY_CHARGE", "20")

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        stats = {"battery_charge": 15.0, "load_percent": 30.0}
        monitor._check_collector_alerts("ups", stats)
        mock_dispatch.assert_not_called()

    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_collector_alert_respects_cooldown(self, mock_dispatch, mock_config, monkeypatch):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.alert_cooldown = 300
        mock_config.recipients_warning = ["test@example.com"]
        mock_config.recipients_critical = []
        mock_config.recipients_emergency = []

        monkeypatch.setenv("ALERT_NGINX_ACTIVE_CONNECTIONS", "100")

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        stats = {"active_connections": 150}
        monitor._check_collector_alerts("nginx", stats)
        mock_dispatch.reset_mock()

        # Second call within cooldown
        monitor._check_collector_alerts("nginx", stats)
        mock_dispatch.assert_not_called()

    @patch("src.monitor.config")
    @patch("src.monitor.dispatch_alert")
    def test_collector_alert_skipped_when_no_env_var(self, mock_dispatch, mock_config):
        mock_config.database_enabled = False
        mock_config.mqtt_enabled = False
        mock_config.fan_control_enabled = False
        mock_config.alert_cooldown = 300

        from src.monitor import Monitor
        monitor = Monitor(MagicMock())

        stats = {"peers_total": 10, "peers_active": 5}
        monitor._check_collector_alerts("wireguard", stats)
        mock_dispatch.assert_not_called()


class TestPrometheusCollectorMetrics:
    """Test that Prometheus endpoint includes collector metrics."""

    def test_metrics_endpoint_includes_service_prefix(self):
        with patch("src.dashboard.app.config") as mock_config:
            mock_config.endpoint_metrics_enabled = True
            mock_config.dashboard_auth_enabled = False
            mock_config.prometheus_prefix = "pimon"
            mock_config.temp_warning = 60.0
            mock_config.temp_critical = 70.0
            mock_config.temp_emergency = 80.0

            from src.dashboard.app import app, _rate_buckets, _rate_lock
            app.config["TESTING"] = True
            with _rate_lock:
                _rate_buckets.clear()

            # Seed cached collector results
            from src.sensors.collectors import registry
            registry._last_results = {
                "docker": {"containers_running": 3, "images": 10},
            }

            with app.test_client() as client:
                resp = client.get("/metrics")
                assert resp.status_code == 200
                body = resp.data.decode()
                assert "pimon_service_docker_containers_running 3" in body
                assert "pimon_service_docker_images 10" in body

            # Clean up
            registry._last_results = {}
