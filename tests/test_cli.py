"""Tests for main.py CLI entry point."""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestCLIParser:
    """Test CLI argument parsing."""

    def test_no_args_shows_help(self, capsys):
        with patch("sys.argv", ["pimon"]):
            from main import main
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_status_command_parsed(self):
        with patch("sys.argv", ["pimon", "status"]):
            from main import main
            with patch("main._cmd_status") as mock_status:
                main()
                mock_status.assert_called_once()

    def test_history_default_lines(self):
        with patch("sys.argv", ["pimon", "history"]):
            from main import main
            with patch("main._cmd_history") as mock_history:
                main()
                args = mock_history.call_args[0][0]
                assert args.lines == 20

    def test_history_custom_lines(self):
        with patch("sys.argv", ["pimon", "history", "-n", "50"]):
            from main import main
            with patch("main._cmd_history") as mock_history:
                main()
                args = mock_history.call_args[0][0]
                assert args.lines == 50

    def test_export_defaults(self):
        with patch("sys.argv", ["pimon", "export"]):
            from main import main
            with patch("main._cmd_export") as mock_export:
                main()
                args = mock_export.call_args[0][0]
                assert args.format == "csv"
                assert args.lines == 1000
                assert args.output is None

    def test_export_json_format(self):
        with patch("sys.argv", ["pimon", "export", "-f", "json", "-n", "100"]):
            from main import main
            with patch("main._cmd_export") as mock_export:
                main()
                args = mock_export.call_args[0][0]
                assert args.format == "json"
                assert args.lines == 100

    def test_backup_output_arg(self):
        with patch("sys.argv", ["pimon", "backup", "-o", "/tmp/backups"]):
            from main import main
            with patch("main._cmd_backup") as mock_backup:
                main()
                args = mock_backup.call_args[0][0]
                assert args.output == "/tmp/backups"

    def test_doctor_command(self):
        with patch("sys.argv", ["pimon", "doctor"]):
            from main import main
            with patch("main._cmd_doctor") as mock_doctor:
                main()
                mock_doctor.assert_called_once()


class TestCmdConfig:
    """Test the config display command."""

    def test_config_displays_output(self, capsys):
        with patch("sys.argv", ["pimon", "config"]):
            from main import main, _cmd_config
            _cmd_config(argparse.Namespace())
            captured = capsys.readouterr()
            assert "SMTP" in captured.out
            assert "Thresholds" in captured.out
            assert "Dashboard" in captured.out


class TestCmdExport:
    """Test the export command."""

    def test_export_csv_to_stdout(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_ENABLED", "true")
        db_path = tmp_path / "export_test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

        import src.database.models as models_mod
        models_mod._engine = None
        models_mod._SessionLocal = None

        from src.database.models import init_db
        from src.database.repository import store_reading
        init_db()
        store_reading("cpu", 55.0)

        from main import _cmd_export
        args = argparse.Namespace(format="csv", lines=100, output=None)

        from src.config import Config
        with patch("main.config", Config()):
            _cmd_export(args)

        captured = capsys.readouterr()
        assert "cpu" in captured.out
        assert "55.0" in captured.out

    def test_export_json_to_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_ENABLED", "true")
        db_path = tmp_path / "export_test2.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

        import src.database.models as models_mod
        models_mod._engine = None
        models_mod._SessionLocal = None

        from src.database.models import init_db
        from src.database.repository import store_reading
        init_db()
        store_reading("gpu", 48.0)

        output_file = tmp_path / "export.json"
        args = argparse.Namespace(format="json", lines=100, output=str(output_file))

        from main import _cmd_export
        from src.config import Config
        with patch("main.config", Config()):
            _cmd_export(args)

        import json
        data = json.loads(output_file.read_text())
        assert len(data) >= 1
        assert any(r["sensor"] == "gpu" for r in data)
