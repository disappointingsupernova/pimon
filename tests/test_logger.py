"""Tests for src.logger module."""

import csv
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


class TestCSVLogging:
    """Test CSV temperature logging."""

    def test_log_batch_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CSV_LOGGING_ENABLED", "true")

        import src.logger as logger_mod
        logger_mod._DATA_DIR = tmp_path

        from src.config import Config
        with patch("src.logger.config", Config()):
            from src.logger import log_temperatures_csv_batch
            log_temperatures_csv_batch([("cpu", 55.0), ("gpu", 50.0)])

        csv_files = list(tmp_path.glob("temperature_*.csv"))
        assert len(csv_files) == 1

        with open(csv_files[0]) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["sensor"] == "cpu"
        assert rows[1]["sensor"] == "gpu"

    def test_log_batch_noop_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CSV_LOGGING_ENABLED", "false")

        import src.logger as logger_mod
        logger_mod._DATA_DIR = tmp_path

        from src.config import Config
        with patch("src.logger.config", Config()):
            from src.logger import log_temperatures_csv_batch
            log_temperatures_csv_batch([("cpu", 55.0)])

        csv_files = list(tmp_path.glob("temperature_*.csv"))
        assert len(csv_files) == 0


class TestCSVPruning:
    """Test CSV file pruning."""

    def test_prune_removes_old_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CSV_RETENTION_DAYS", "7")

        import src.logger as logger_mod
        logger_mod._DATA_DIR = tmp_path

        # Create an old file
        old_date = date.today() - timedelta(days=10)
        old_file = tmp_path / f"temperature_{old_date.isoformat()}.csv"
        old_file.write_text("timestamp,sensor,temperature_c\n")

        # Create a recent file
        recent_file = tmp_path / f"temperature_{date.today().isoformat()}.csv"
        recent_file.write_text("timestamp,sensor,temperature_c\n")

        from src.config import Config
        with patch("src.logger.config", Config()):
            from src.logger import prune_old_csv_files
            removed = prune_old_csv_files()

        assert removed == 1
        assert not old_file.exists()
        assert recent_file.exists()


class TestGetRecentCSV:
    """Test reading recent CSV rows."""

    def test_returns_empty_when_no_files(self, tmp_path, monkeypatch):
        import src.logger as logger_mod
        logger_mod._DATA_DIR = tmp_path

        from src.logger import get_recent_csv_rows
        rows = get_recent_csv_rows(10)
        assert rows == []

    def test_returns_rows_from_today(self, tmp_path, monkeypatch):
        import src.logger as logger_mod
        logger_mod._DATA_DIR = tmp_path

        today_file = tmp_path / f"temperature_{date.today().isoformat()}.csv"
        today_file.write_text(
            "timestamp,sensor,temperature_c\n"
            "2024-01-01T00:00:00,cpu,55.0\n"
            "2024-01-01T00:01:00,cpu,56.0\n"
        )

        from src.logger import get_recent_csv_rows
        rows = get_recent_csv_rows(10)
        assert len(rows) == 2
