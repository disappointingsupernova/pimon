"""Tests for src.dashboard.app module."""

import time
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def client():
    """Create a Flask test client with dashboard config mocked."""
    with patch("src.dashboard.app.config") as mock_config:
        mock_config.dashboard_auth_enabled = False
        mock_config.endpoint_api_enabled = True
        mock_config.endpoint_health_enabled = True
        mock_config.endpoint_metrics_enabled = True
        mock_config.database_enabled = False
        mock_config.temp_warning = 60.0
        mock_config.temp_critical = 70.0
        mock_config.temp_emergency = 80.0
        mock_config.prometheus_prefix = "pimon"

        from src.dashboard.app import app, _rate_buckets, _rate_lock
        app.config["TESTING"] = True

        # Reset rate limit state
        with _rate_lock:
            _rate_buckets.clear()

        with app.test_client() as client:
            yield client


class TestDashboardRoutes:
    """Test basic dashboard route responses."""

    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_api_current_returns_json(self, client):
        resp = client.get("/api/current")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "readings" in data
        assert "thresholds" in data

    def test_api_history_returns_json(self, client):
        resp = client.get("/api/history")
        assert resp.status_code == 200

    def test_alerts_page_returns_200(self, client):
        resp = client.get("/alerts")
        assert resp.status_code == 200


class TestRateLimiting:
    """Test token-bucket rate limiting."""

    def test_requests_within_limit_succeed(self, client):
        for _ in range(10):
            resp = client.get("/api/current")
            assert resp.status_code == 200

    def test_exceeding_limit_returns_429(self, client):
        # Exhaust the bucket (60 tokens)
        for _ in range(61):
            resp = client.get("/api/current")
        assert resp.status_code == 429

    def test_bucket_refills_over_time(self, client):
        # Exhaust
        for _ in range(61):
            client.get("/api/current")

        # Simulate time passing by manually adjusting bucket
        from src.dashboard.app import _rate_buckets, _rate_lock
        with _rate_lock:
            for ip in _rate_buckets:
                _rate_buckets[ip] = (5.0, time.monotonic())

        resp = client.get("/api/current")
        assert resp.status_code == 200


class TestDashboardAuth:
    """Test basic authentication on dashboard."""

    def test_auth_required_when_enabled(self):
        with patch("src.dashboard.app.config") as mock_config:
            mock_config.dashboard_auth_enabled = True
            mock_config.dashboard_username = "admin"
            mock_config.dashboard_password = "secret"
            mock_config.endpoint_api_enabled = True

            from src.dashboard.app import app, _rate_buckets, _rate_lock
            app.config["TESTING"] = True
            with _rate_lock:
                _rate_buckets.clear()

            with app.test_client() as client:
                resp = client.get("/api/current")
                assert resp.status_code == 401

    def test_auth_succeeds_with_credentials(self):
        with patch("src.dashboard.app.config") as mock_config:
            mock_config.dashboard_auth_enabled = True
            mock_config.dashboard_username = "admin"
            mock_config.dashboard_password = "secret"
            mock_config.endpoint_api_enabled = True
            mock_config.temp_warning = 60.0
            mock_config.temp_critical = 70.0
            mock_config.temp_emergency = 80.0

            from src.dashboard.app import app, _rate_buckets, _rate_lock
            app.config["TESTING"] = True
            with _rate_lock:
                _rate_buckets.clear()

            with app.test_client() as client:
                from base64 import b64encode
                creds = b64encode(b"admin:secret").decode()
                resp = client.get("/api/current", headers={"Authorization": f"Basic {creds}"})
                assert resp.status_code == 200
