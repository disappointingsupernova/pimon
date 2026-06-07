"""CLI entry point for Pi Temperature Alerter.

Provides commands for starting the monitoring daemon, checking sensor
status, viewing history, testing email configuration, displaying
current settings, and performing self-updates.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from src.config import config

_INSTALL_DIR = Path("/opt/pi-temp-alerter")
_APP_DIR = Path(__file__).resolve().parent

_PROG_DESCRIPTION = """\
Pi Temperature Alerter - Raspberry Pi system health monitoring and alerting.

Monitors CPU, GPU, and DS18B20 temperature sensors with configurable
multi-channel alerting (email, webhook, Telegram, Pushover, MQTT),
hysteresis-based threshold evaluation, real-time web dashboard, and
persistent data storage via SQLAlchemy (SQLite/MySQL/PostgreSQL).

Configuration is managed via .env file. Run 'config' to view current
settings or see .env.example for all available options.
"""

_PROG_EPILOG = """\
Examples:
  python main.py start          Start monitoring with all configured sensors
  python main.py status         Quick check of current temperatures
  python main.py history -n 50  Show last 50 temperature readings
  python main.py test-email     Verify SMTP is working
  python main.py config         Display all settings (secrets redacted)
  sudo python main.py update    Pull latest code and restart service

Documentation: https://github.com/your-user/Pi-Temperature-Alerter
"""


# =============================================================================
# Command implementations
# =============================================================================

def _cmd_start(_args: argparse.Namespace) -> None:
    """Start the monitoring daemon with all configured sensors and alerting."""
    from src.dashboard.app import init_dashboard, start_dashboard
    from src.logger import setup_logging
    from src.monitor import Monitor
    from src.sensors.manager import SensorManager

    setup_logging()

    # Validate configuration before starting
    errors = config.validate()
    if errors:
        print("Configuration errors detected:")
        for err in errors:
            print(f"  - {err}")
        print("\nFix these issues in your .env file before starting.")
        sys.exit(1)

    # Initialise database tables
    if config.database_enabled:
        from src.database.models import init_db
        init_db()

    # Warn if systemd service is not enabled for auto-start
    _check_service_enabled()

    sensor_manager = SensorManager()
    init_dashboard(sensor_manager)

    if config.dashboard_enabled:
        start_dashboard()

    monitor = Monitor(sensor_manager)
    monitor.start()


def _cmd_status(_args: argparse.Namespace) -> None:
    """Show current temperature readings from all enabled sensors."""
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
    """Display recent temperature history from the data store."""
    # Prefer database if enabled, fall back to CSV
    if config.database_enabled:
        from src.database.repository import get_recent_readings
        rows = get_recent_readings(args.lines)
    else:
        from src.logger import get_recent_csv_rows
        rows = get_recent_csv_rows(args.lines)

    if not rows:
        print("No history data found. Start monitoring to begin logging.")
        sys.exit(1)

    print(f"{'Timestamp':<28} {'Sensor':<20} {'Temperature'}")
    print("-" * 60)
    for row in rows:
        print(f"{row['timestamp']:<28} {row['sensor']:<20} {row['temperature_c']} C")


def _cmd_test_email(_args: argparse.Namespace) -> None:
    """Send a test email to verify SMTP configuration is working."""
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
    """Pull latest changes from git and restart the systemd service."""
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
    """Display the current configuration with secrets redacted."""
    print("Pi Temperature Alerter - Current Configuration")
    print("=" * 60)
    print()
    print("SMTP")
    print(f"  Host:              {config.smtp_host}")
    print(f"  Port:              {config.smtp_port}")
    print(f"  TLS:               {config.smtp_use_tls}")
    print(f"  Username:          {config.smtp_username}")
    print(f"  Password:          {'***' if config.smtp_password else '(not set)'}")
    print(f"  From:              {config.email_from}")
    print()
    print("Recipients")
    print(f"  Warning:           {', '.join(config.recipients_warning) or '(none)'}")
    print(f"  Critical:          {', '.join(config.recipients_critical) or '(none)'}")
    print(f"  Emergency:         {', '.join(config.recipients_emergency) or '(none)'}")
    print()
    print("Thresholds")
    print(f"  Warning:           {config.temp_warning} C")
    print(f"  Critical:          {config.temp_critical} C")
    print(f"  Emergency:         {config.temp_emergency} C")
    print(f"  Hysteresis:        {config.temp_hysteresis} C")
    print()
    print("Monitoring")
    print(f"  Poll interval:     {config.poll_interval}s")
    print(f"  Alert cooldown:    {config.alert_cooldown}s")
    print(f"  Recovery alerts:   {config.recovery_notifications}")
    print(f"  Rate of change:    {config.rate_of_change_threshold} C/min")
    print(f"  Escalation timeout:{config.escalation_timeout}s")
    print(f"  Daily digest:      {config.daily_digest_enabled} (hour: {config.daily_digest_hour})")
    print()
    print("Sensors")
    print(f"  CPU:               {config.sensor_cpu_enabled}")
    print(f"  GPU:               {config.sensor_gpu_enabled}")
    print(f"  DS18B20:           {config.sensor_ds18b20_enabled}")
    print()
    print("Dashboard")
    print(f"  Enabled:           {config.dashboard_enabled}")
    print(f"  Address:           {config.dashboard_host}:{config.dashboard_port}")
    print(f"  Auth:              {config.dashboard_auth_enabled}")
    print(f"  API endpoints:     {config.endpoint_api_enabled}")
    print(f"  Health endpoint:   {config.endpoint_health_enabled}")
    print(f"  Metrics endpoint:  {config.endpoint_metrics_enabled}")
    print()
    print("Database")
    print(f"  Enabled:           {config.database_enabled}")
    # Redact credentials from database URL
    db_display = config.database_url
    if "@" in db_display:
        parts = db_display.split("@")
        db_display = parts[0].split("://")[0] + "://***@" + parts[1]
    print(f"  URL:               {db_display}")
    print()
    print("Notifications")
    print(f"  Webhook:           {config.webhook_enabled}")
    print(f"  Telegram:          {config.telegram_enabled}")
    print(f"  Pushover:          {config.pushover_enabled}")
    print(f"  MQTT:              {config.mqtt_enabled}")
    print()
    print("Fan Control")
    print(f"  Enabled:           {config.fan_control_enabled}")
    print(f"  GPIO pin:          {config.fan_gpio_pin}")
    print(f"  On threshold:      {config.fan_on_threshold} C")
    print(f"  Off threshold:     {config.fan_off_threshold} C")
    print()
    print(f"Dry Run:             {config.dry_run}")
    print(f"Low-Write Mode:      {config.low_write_mode}")


def _cmd_migrate_db(args: argparse.Namespace) -> None:
    """Migrate all data from one database backend to another."""
    from src.database.migrate import migrate_database
    from src.logger import setup_logging

    setup_logging()

    source_url = args.source or config.database_url
    target_url = args.target

    print("Database Migration")
    print("=" * 50)
    print(f"  Source: {_redact_db_url(source_url)}")
    print(f"  Target: {_redact_db_url(target_url)}")
    print()

    # Safety confirmation
    confirm = input("Proceed with migration? [y/N] ").strip().lower()
    if confirm != "y":
        print("Migration cancelled.")
        sys.exit(0)

    print()
    success = migrate_database(source_url, target_url)

    if success:
        print("\nMigration complete.")
        print(f"\nTo switch to the new database, update DATABASE_URL in your .env:")
        print(f"  DATABASE_URL={target_url}")
    else:
        print("\nMigration failed. Check logs for details.")
        sys.exit(1)


# =============================================================================
# Helpers
# =============================================================================

def _get_level(temp: float) -> str:
    """Determine the alert level string for a given temperature."""
    if temp >= config.temp_emergency:
        return "EMERGENCY"
    if temp >= config.temp_critical:
        return "CRITICAL"
    if temp >= config.temp_warning:
        return "WARNING"
    return "NORMAL"


def _redact_db_url(url: str) -> str:
    """Redact credentials from a database URL for safe display."""
    if "@" in url:
        parts = url.split("@")
        return parts[0].split("://")[0] + "://***@" + parts[1]
    return url


def _check_service_enabled() -> None:
    """Warn if the systemd service is not enabled for auto-start."""
    import logging

    logger = logging.getLogger("pi_temp_alerter")

    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", "--quiet", "pi-temp-alerter"],
            capture_output=True,
        )
        if result.returncode != 0:
            msg = (
                "The pi-temp-alerter systemd service is not enabled for auto-start. "
                "Run 'sudo systemctl enable pi-temp-alerter' to start on boot."
            )
            logger.warning(msg)
            print(f"WARNING: {msg}")

            # Send a one-off advisory email if SMTP is configured
            from src.alerting.email_sender import _send
            _send(
                list(set(
                    config.recipients_warning
                    + config.recipients_critical
                    + config.recipients_emergency
                )),
                "[Pi Alerter] Service not enabled for auto-start",
                "The pi-temp-alerter service is not enabled for automatic startup.\n"
                "\n"
                "If the device reboots, monitoring will not resume automatically.\n"
                "Please enable the service for auto-start on the device.\n",
            )
    except (OSError, FileNotFoundError):
        # systemctl not available (development environment) - skip check
        pass


# =============================================================================
# Argument parser
# =============================================================================

def main() -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = argparse.ArgumentParser(
        prog="pi-temp-alerter",
        description=_PROG_DESCRIPTION,
        epilog=_PROG_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        description="Use 'python main.py <command> --help' for detailed help on each command.",
    )

    # start
    subparsers.add_parser(
        "start",
        help="Start the monitoring daemon",
        description=(
            "Start the temperature monitoring daemon. Validates configuration,\n"
            "initialises the database, checks systemd auto-start status, starts\n"
            "the web dashboard (if enabled), and begins the polling loop.\n"
            "\n"
            "The daemon will run until stopped via SIGINT (Ctrl+C) or SIGTERM.\n"
            "All enabled sensors are polled every POLL_INTERVAL seconds.\n"
            "Alerts are dispatched via all enabled notification channels."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # status
    subparsers.add_parser(
        "status",
        help="Show current sensor readings",
        description=(
            "Read all enabled sensors once and display their current temperature\n"
            "along with the corresponding alert level (NORMAL, WARNING, CRITICAL,\n"
            "or EMERGENCY). Useful for quick health checks without starting the\n"
            "full daemon."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # history
    history_parser = subparsers.add_parser(
        "history",
        help="Display recent temperature history",
        description=(
            "Show the most recent temperature readings from the data store.\n"
            "Uses the database (if enabled) or falls back to CSV files.\n"
            "\n"
            "Output includes timestamp, sensor name, and temperature in Celsius."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    history_parser.add_argument(
        "-n", "--lines",
        type=int,
        default=20,
        metavar="COUNT",
        help="Number of recent entries to display (default: 20)",
    )

    # test-email
    subparsers.add_parser(
        "test-email",
        help="Send a test email to verify SMTP configuration",
        description=(
            "Send a test email to all configured recipients to verify that\n"
            "SMTP settings (host, port, TLS, credentials) are correct.\n"
            "\n"
            "The test email will be sent to all unique addresses across\n"
            "WARNING, CRITICAL, and EMERGENCY recipient lists."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # config
    subparsers.add_parser(
        "config",
        help="Display current configuration (secrets redacted)",
        description=(
            "Print all current configuration values sourced from the .env file.\n"
            "Passwords, tokens, and credentials are redacted in the output.\n"
            "\n"
            "Useful for verifying that changes to .env have taken effect and\n"
            "for debugging configuration issues."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # update
    subparsers.add_parser(
        "update",
        help="Pull latest changes and restart service (requires root)",
        description=(
            "Perform a self-update by pulling the latest code from git,\n"
            "reinstalling Python dependencies, and restarting the systemd\n"
            "service if it is currently running.\n"
            "\n"
            "Requires root privileges (use sudo). Uses git pull --ff-only\n"
            "to ensure a clean fast-forward merge without conflicts.\n"
            "\n"
            "If running from /opt/pi-temp-alerter, updates that directory.\n"
            "Otherwise updates the current working directory."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # migrate-db
    migrate_parser = subparsers.add_parser(
        "migrate-db",
        help="Migrate data between database backends",
        description=(
            "Copy all data from one database to another. Useful for migrating\n"
            "from the default SQLite to a hosted MySQL or PostgreSQL instance,\n"
            "or between any two supported database backends.\n"
            "\n"
            "The source defaults to the currently configured DATABASE_URL.\n"
            "The destination must be provided via --target.\n"
            "\n"
            "Tables are created automatically on the target if they do not exist.\n"
            "Existing data in the target is preserved (records are appended).\n"
            "\n"
            "Examples:\n"
            "  # SQLite to PostgreSQL:\n"
            "  python main.py migrate-db --target postgresql+psycopg2://user:pass@host/db\n"
            "\n"
            "  # SQLite to MySQL:\n"
            "  python main.py migrate-db --target mysql+pymysql://user:pass@host/db\n"
            "\n"
            "  # Custom source (e.g. old SQLite file):\n"
            "  python main.py migrate-db --source sqlite:///data/old.db --target postgresql://..."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    migrate_parser.add_argument(
        "--source",
        type=str,
        default=None,
        metavar="URL",
        help="Source database URL (default: current DATABASE_URL from .env)",
    )
    migrate_parser.add_argument(
        "--target",
        type=str,
        required=True,
        metavar="URL",
        help="Target database URL to migrate data into",
    )

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
        "migrate-db": _cmd_migrate_db,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
