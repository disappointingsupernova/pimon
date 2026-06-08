"""Tests for src.config module."""

import os

import pytest


class TestConfigDefaults:
    """Test that Config loads sensible defaults."""

    def test_threshold_ordering(self, fresh_config):
        assert fresh_config.temp_warning < fresh_config.temp_critical
        assert fresh_config.temp_critical < fresh_config.temp_emergency

    def test_poll_interval_positive(self, fresh_config):
        assert fresh_config.poll_interval > 0

    def test_alert_cooldown_non_negative(self, fresh_config):
        assert fresh_config.alert_cooldown >= 0

    def test_hysteresis_positive(self, fresh_config):
        assert fresh_config.temp_hysteresis > 0

    def test_metric_alerts_disabled_by_default(self, fresh_config):
        assert fresh_config.alert_cpu_percent == 0.0
        assert fresh_config.alert_memory_percent == 0.0
        assert fresh_config.alert_disk_percent == 0.0

    def test_startup_notification_disabled_by_default(self, fresh_config):
        assert fresh_config.startup_notification is False

    def test_per_channel_cooldowns_default_zero(self, fresh_config):
        assert fresh_config.cooldown_email == 0
        assert fresh_config.cooldown_webhook == 0
        assert fresh_config.cooldown_telegram == 0
        assert fresh_config.cooldown_pushover == 0
        assert fresh_config.cooldown_mqtt == 0


class TestConfigValidation:
    """Test the Config.validate() method."""

    def test_valid_config_returns_empty_list(self, fresh_config):
        errors = fresh_config.validate()
        assert errors == []

    def test_invalid_threshold_ordering(self, monkeypatch, fresh_config):
        monkeypatch.setenv("TEMP_WARNING", "80")
        monkeypatch.setenv("TEMP_CRITICAL", "70")
        monkeypatch.setenv("TEMP_EMERGENCY", "60")
        from src.config import Config
        cfg = Config()
        errors = cfg.validate()
        assert any("ascending order" in e for e in errors)

    def test_negative_hysteresis(self, monkeypatch):
        monkeypatch.setenv("TEMP_HYSTERESIS", "-1")
        from src.config import Config
        cfg = Config()
        errors = cfg.validate()
        assert any("TEMP_HYSTERESIS" in e for e in errors)

    def test_zero_poll_interval(self, monkeypatch):
        monkeypatch.setenv("POLL_INTERVAL", "0")
        from src.config import Config
        cfg = Config()
        errors = cfg.validate()
        assert any("POLL_INTERVAL" in e for e in errors)

    def test_no_sensors_enabled(self, monkeypatch):
        monkeypatch.setenv("SENSOR_CPU_ENABLED", "false")
        monkeypatch.setenv("SENSOR_GPU_ENABLED", "false")
        monkeypatch.setenv("SENSOR_DS18B20_ENABLED", "false")
        from src.config import Config
        cfg = Config()
        errors = cfg.validate()
        assert any("sensor" in e.lower() for e in errors)

    def test_smtp_required_when_recipients_set(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "")
        monkeypatch.setenv("EMAIL_FROM", "")
        from src.config import Config
        cfg = Config()
        errors = cfg.validate()
        assert any("SMTP_HOST" in e for e in errors)


class TestConfigHelpers:
    """Test config helper methods."""

    def test_get_thresholds_returns_globals(self, fresh_config):
        thresholds = fresh_config.get_thresholds("cpu")
        assert thresholds["warning"] == 60.0
        assert thresholds["critical"] == 70.0
        assert thresholds["emergency"] == 80.0

    def test_get_thresholds_with_override(self, monkeypatch):
        monkeypatch.setenv("TEMP_WARNING_CPU", "55")
        from src.config import Config
        cfg = Config()
        thresholds = cfg.get_thresholds("cpu")
        assert thresholds["warning"] == 55.0
        assert thresholds["critical"] == 70.0  # Falls back to global

    def test_sensor_display_name_default(self, fresh_config):
        assert fresh_config.get_sensor_display_name("cpu") == "cpu"

    def test_sensor_display_name_alias(self, monkeypatch):
        monkeypatch.setenv("SENSOR_ALIAS_CPU", "Main CPU")
        from src.config import Config
        cfg = Config()
        assert cfg.get_sensor_display_name("cpu") == "Main CPU"

    def test_low_write_mode_overrides(self, monkeypatch):
        monkeypatch.setenv("LOW_WRITE_MODE", "true")
        monkeypatch.setenv("POLL_INTERVAL", "10")
        monkeypatch.setenv("CSV_LOGGING_ENABLED", "true")
        from src.config import Config
        cfg = Config()
        assert cfg.csv_logging_enabled is False
        assert cfg.poll_interval >= 60


class TestConfigReload:
    """Test config hot-reload functionality."""

    def test_reload_env_reloads_values(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("TEMP_WARNING=65\n")

        import src.config as config_module
        config_module._ENV_PATH = env_file
        config_module.reload_env()

        assert os.getenv("TEMP_WARNING") == "65"
