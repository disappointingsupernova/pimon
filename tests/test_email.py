"""Tests for src.alerting.email_sender module."""

from unittest.mock import patch, MagicMock

import pytest

from src.alerting.thresholds import AlertLevel


class TestSendAlertEmail:
    """Test alert email sending."""

    @patch("src.alerting.email_sender.config")
    @patch("src.alerting.email_sender._send")
    def test_calls_send_with_recipients(self, mock_send, mock_config):
        mock_config.temp_warning = 60.0
        mock_config.temp_critical = 70.0
        mock_config.temp_emergency = 80.0
        mock_config.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}
        mock_config.dashboard_host = "localhost"
        mock_config.dashboard_port = 5000
        mock_send.return_value = True

        from src.alerting.email_sender import send_alert_email
        result = send_alert_email(["test@example.com"], AlertLevel.WARNING, "cpu", 65.0)
        mock_send.assert_called_once()
        assert "[PiMon]" in mock_send.call_args[0][1]  # subject

    @patch("src.alerting.email_sender.config")
    @patch("src.alerting.email_sender._send")
    def test_subject_contains_level(self, mock_send, mock_config):
        mock_config.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}
        mock_config.dashboard_host = "localhost"
        mock_config.dashboard_port = 5000
        mock_send.return_value = True

        from src.alerting.email_sender import send_alert_email
        send_alert_email(["test@example.com"], AlertLevel.CRITICAL, "gpu", 72.0)
        subject = mock_send.call_args[0][1]
        assert "CRITICAL" in subject


class TestSendRecoveryEmail:
    """Test recovery email sending."""

    @patch("src.alerting.email_sender.config")
    @patch("src.alerting.email_sender._send")
    def test_sends_recovery(self, mock_send, mock_config):
        mock_config.recipients_warning = ["a@example.com"]
        mock_config.recipients_critical = ["b@example.com"]
        mock_config.recipients_emergency = []
        mock_config.get_thresholds.return_value = {"warning": 60, "critical": 70, "emergency": 80}
        mock_config.dashboard_host = "localhost"
        mock_config.dashboard_port = 5000
        mock_send.return_value = True

        from src.alerting.email_sender import send_recovery_email
        send_recovery_email("cpu", 55.0, AlertLevel.WARNING)
        mock_send.assert_called_once()
        subject = mock_send.call_args[0][1]
        assert "RECOVERED" in subject


class TestInternalSend:
    """Test the _send function."""

    @patch("src.alerting.email_sender.config")
    def test_dry_run_does_not_connect(self, mock_config):
        mock_config.dry_run = True
        mock_config.email_from = "from@example.com"

        from src.alerting.email_sender import _send
        result = _send(["test@example.com"], "Test Subject", "Test body")
        assert result is True  # Dry run returns True

    @patch("src.alerting.email_sender.config")
    def test_no_recipients_returns_false(self, mock_config):
        mock_config.dry_run = False

        from src.alerting.email_sender import _send
        result = _send([], "Subject", "Body")
        assert result is False

    @patch("src.alerting.email_sender.config")
    @patch("src.alerting.email_sender.smtplib.SMTP")
    def test_smtp_failure_returns_false(self, mock_smtp_class, mock_config):
        mock_config.dry_run = False
        mock_config.email_from = "from@example.com"
        mock_config.smtp_host = "localhost"
        mock_config.smtp_port = 25
        mock_config.smtp_use_tls = False
        mock_config.smtp_username = ""
        mock_config.smtp_password = ""
        mock_smtp_class.side_effect = OSError("connection refused")

        from src.alerting.email_sender import _send
        result = _send(["test@example.com"], "Subject", "Body")
        assert result is False
