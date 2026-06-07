"""CLI entry point for Pi Temperature Alerter.

Provides commands for monitoring, status checks, and configuration validation.
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

from src.config import config

_INSTALL_DIR = Path("/opt/pi-temp-alerter")
_APP_DIR = Path(__file__).resolve().parent


def _cmd_start(args: argparse.Namespace) -> None:
    """Start the monitoring daemon."""
    from src.dashboard.app import init_dashboard, start_dashboard
    from src.logger import setup_logging
    from src.monitor import Monitor
    from src.sensors.manager import SensorManager

    setup_logging()

    sensor_manager = SensorManager()
    init_dashboard(sensor_manager)

    if config.dashboard_enabled:
        start_dashboard()

    monitor = Monitor(sensor_manager)
    monitor.start()


def _cmd_status(_args: argparse.Namespace) -> None:
    """Show current temperature readings."""
    from src.sensors.manager import SensorManager

    manager = SensorManager()
    readings = manager.read_all()

    if not readings:
        print("No sensors available.")
        sys.exit(1)

    print(f"{'Sensor':<20} {'Temperature':<15} {'Status'}")
    print("-" * 50)
    for r in readings:
        if r.available:
            level = _get_level(r.temperature_c)
            print(f"{r.sensor_name:<20} {r.temperature_c:>6.1f} C       {level}")
        else:
            print(f"{r.sensor_name:<20} {'N/A':<15} {r.error or 'Unavailable'}")


def _cmd_history(args: argparse.Namespace) -> None:
    """Display recent temperature history from CSV log."""
    csv_path = _APP_DIR / "data" / "temperature_history.csv"
    if not csv_path.exists():
        print("No history data found. Start monitoring to begin logging.")
        sys.exit(1)

    count = args.lines
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("History file is empty.")
        sys.exit(1)

    print(f"{'Timestamp':<28} {'Sensor':<20} {'Temperature'}")
    print("-" * 60)
    for row in rows[-count:]:
        print(f"{row['timestamp']:<28} {row['sensor']:<20} {row['temperature_c']} C")


def _cmd_test_email(_args: argparse.Namespace) -> None:
    """Send a test email to verify SMTP configuration."""
    from src.alerting.email_sender import send_test_email
    from src.logger import setup_logging

    setup_logging()

    print(f"Sending test email via {config.smtp_host}:{config.smtp_port}...")
    success = send_test_email()

    if success:
        print("Test email sent successfully.")
    else:
        print("Failed to send test email. Check logs for details.")
        sys.exit(1)


def _cmd_update(_args: argparse.Namespace) -> None:
    """Pull latest changes from git and restart the service."""
    import os

    if os.geteuid() != 0:
        print("The update command must be run as root (sudo).")
        sys.exit(1)

    app_dir = _INSTALL_DIR if _INSTALL_DIR.exists() else _APP_DIR
    print(f"Updating from {app_dir}...")

    # Pull latest from remote
    result = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=str(app_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Git pull failed:\n{result.stderr}")
        sys.exit(1)

    print(result.stdout.strip())

    # Reinstall dependencies
    venv_pip = app_dir / "venv" / "bin" / "pip"
    if venv_pip.exists():
        print("Updating dependencies...")
        subprocess.run(
            [str(venv_pip), "install", "-r", "requirements.txt", "--quiet"],
            cwd=str(app_dir),
            check=True,
        )

    # Restart service if active
    svc_check = subprocess.run(
        ["systemctl", "is-active", "--quiet", "pi-temp-alerter"],
        capture_output=True,
    )
    if svc_check.returncode == 0:
        print("Restarting pi-temp-alerter service...")
        subprocess.run(["systemctl", "restart", "pi-temp-alerter"], check=True)
        print("Service restarted.")
    else:
        print("Service not running - skipping restart.")

    print("Update complete.")


def _cmd_config(_args: argparse.Namespace) -> None:
    """Display the current configuration (redacting secrets)."""
    print("Current Configuration")
    print("=" * 50)
    print(f"  SMTP Host:           {config.smtp_host}")
    print(f"  SMTP Port:           {config.smtp_port}")
    print(f"  SMTP TLS:            {config.smtp_use_tls}")
    print(f"  SMTP Username:       {config.smtp_username}")
    print(f"  SMTP Password:       {'***' if config.smtp_password else '(not set)'}")
    print(f"  Email From:          {config.email_from}")
    print()
    print(f"  Warning Recipients:  {', '.join(config.recipients_warning) or '(none)'}")
    print(f"  Critical Recipients: {', '.join(config.recipients_critical) or '(none)'}")
    print(f"  Emergency Recipients:{', '.join(config.recipients_emergency) or '(none)'}")
    print()
    print(f"  Temp Warning:        {config.temp_warning} C")
    print(f"  Temp Critical:       {config.temp_critical} C")
    print(f"  Temp Emergency:      {config.temp_emergency} C")
    print(f"  Hysteresis:          {config.temp_hysteresis} C")
    print()
    print(f"  Poll Interval:       {config.poll_interval}s")
    print(f"  Alert Cooldown:      {config.alert_cooldown}s")
    print(f"  Recovery Alerts:     {config.recovery_notifications}")
    print()
    print(f"  CPU Sensor:          {config.sensor_cpu_enabled}")
    print(f"  GPU Sensor:          {config.sensor_gpu_enabled}")
    print(f"  DS18B20 Sensors:     {config.sensor_ds18b20_enabled}")
    print()
    print(f"  Dashboard:           {config.dashboard_enabled}")
    print(f"  Dashboard Address:   {config.dashboard_host}:{config.dashboard_port}")
    print(f"  Dry Run:             {config.dry_run}")


def _get_level(temp: float) -> str:
    if temp >= config.temp_emergency:
        return "EMERGENCY"
    if temp >= config.temp_critical:
        return "CRITICAL"
    if temp >= config.temp_warning:
        return "WARNING"
    return "NORMAL"


def main() -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = argparse.ArgumentParser(
        prog="pi-temp-alerter",
        description="Raspberry Pi temperature monitoring and alerting system",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start
    subparsers.add_parser("start", help="Start the monitoring daemon")

    # status
    subparsers.add_parser("status", help="Show current sensor readings")

    # history
    history_parser = subparsers.add_parser("history", help="Show temperature history")
    history_parser.add_argument(
        "-n", "--lines", type=int, default=20, help="Number of recent entries to show"
    )

    # test-email
    subparsers.add_parser("test-email", help="Send a test email to verify SMTP config")

    # config
    subparsers.add_parser("config", help="Display current configuration")

    # update
    subparsers.add_parser("update", help="Pull latest changes and restart service (requires root)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "start": _cmd_start,
        "status": _cmd_status,
        "history": _cmd_history,
        "test-email": _cmd_test_email,
        "config": _cmd_config,
        "update": _cmd_update,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
