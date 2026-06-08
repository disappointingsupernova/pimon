"""CLI entry point for PiMon.

Provides commands for starting the monitoring daemon, checking sensor
status, viewing history, testing email configuration, displaying
current settings, and performing self-updates.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from src.config import config

_INSTALL_DIR = Path("/opt/pimon")
_APP_DIR = Path(__file__).resolve().parent

_PROG_DESCRIPTION = """\
PiMon - Raspberry Pi system health monitoring and alerting.

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

Documentation: https://github.com/disappointingsupernova/pimon
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
        from src.database.models import init_db
        from src.database.repository import get_recent_readings
        init_db()
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


def _cmd_logs(args: argparse.Namespace) -> None:
    """Display recent application log entries."""
    log_file = _APP_DIR / "logs" / "alerter.log"
    if not log_file.exists():
        print("No log file found. Start monitoring to generate logs.")
        sys.exit(1)

    # Read the last N lines efficiently
    lines = []
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
    except PermissionError:
        print(f"Permission denied reading {log_file}")
        print("Try: sudo pimon logs")
        sys.exit(1)

    count = args.lines
    tail = lines[-count:] if len(lines) > count else lines

    if not tail:
        print("Log file is empty.")
        sys.exit(1)

    for line in tail:
        print(line, end="")

    if args.follow:
        import time
        print(f"\n--- Following {log_file} (Ctrl+C to stop) ---\n")
        try:
            with open(log_file, "r") as f:
                # Seek to end
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopped.")


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
    """Pull latest changes from git, reinstall, and restart the service."""
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

    # Re-run install.sh to update dependencies, service file, and permissions
    install_script = app_dir / "install.sh"
    if install_script.exists():
        print("Running install.sh to update service file and dependencies...")
        result = subprocess.run(
            ["bash", str(install_script)],
            cwd=str(app_dir),
        )
        if result.returncode != 0:
            print("install.sh failed. Check output above.")
            sys.exit(1)
    else:
        # Fallback if install.sh is missing: just update pip deps
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
        ["systemctl", "is-active", "--quiet", "pimon"],
        capture_output=True,
    )
    if svc_check.returncode == 0:
        print("Restarting pimon service...")
        subprocess.run(["systemctl", "restart", "pimon"], check=True)
        print("Service restarted.")
    else:
        print("Service not running - skipping restart.")

    print("Update complete.")
    print()

    # Tail the logs so we can see the service starting up
    _cmd_logs(argparse.Namespace(lines=20, follow=True))


def _cmd_config(_args: argparse.Namespace) -> None:
    """Display the current configuration with secrets redacted."""
    print("PiMon - Current Configuration")
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
    from src.database.models import init_db
    from src.logger import setup_logging

    setup_logging()
    init_db()

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


def _cmd_doctor(args: argparse.Namespace) -> None:
    """Run comprehensive diagnostic checks on all PiMon subsystems."""
    import shutil
    import smtplib
    import platform

    from src.logger import setup_logging
    setup_logging()

    print("PiMon Doctor")
    print("=" * 60)
    passed = 0
    failed = 0
    warnings = 0

    def _check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        status = "PASS" if ok else "FAIL"
        suffix = f" ({detail})" if detail else ""
        print(f"  [{status}] {name}{suffix}")
        if ok:
            passed += 1
        else:
            failed += 1

    def _warn(name: str, detail: str = "") -> None:
        nonlocal warnings
        suffix = f" ({detail})" if detail else ""
        print(f"  [WARN] {name}{suffix}")
        warnings += 1

    # System info
    print("\nSystem")
    from src import __version__
    print(f"  PiMon version:  {__version__}")
    print(f"  Python version: {platform.python_version()}")
    print(f"  Platform:       {platform.platform()}")
    print(f"  Architecture:   {platform.machine()}")

    # Configuration validation
    print("\nConfiguration")
    errors = config.validate()
    _check("Configuration valid", len(errors) == 0, "; ".join(errors) if errors else "")

    # Sensors
    print("\nSensors")
    from src.sensors.manager import SensorManager
    manager = SensorManager()
    readings = manager.read_all()
    if readings:
        for r in readings:
            _check(f"Sensor: {r.sensor_name}", r.available, r.error or f"{r.temperature_c:.1f} C")
    else:
        _check("Any sensor available", False, "no sensors detected")

    # Database
    print("\nDatabase")
    if config.database_enabled:
        try:
            from src.database.models import init_db, get_session
            init_db()
            session = get_session()
            session.execute(__import__("sqlalchemy").text("SELECT 1"))
            session.close()
            _check("Database connection", True, config.database_url.split("://")[0])
        except Exception as exc:
            _check("Database connection", False, str(exc))

        # Check table counts
        try:
            from src.database.repository import get_recent_readings, get_recent_alerts
            readings_count = len(get_recent_readings(1))
            alerts_count = len(get_recent_alerts(1))
            _check("Database has data", readings_count > 0 or alerts_count > 0,
                   f"{readings_count} readings, {alerts_count} alerts")
        except Exception:
            _warn("Database data check", "could not query")
    else:
        _warn("Database", "DATABASE_ENABLED=false")

    # SMTP
    print("\nSMTP")
    if config.smtp_host and config.email_from:
        try:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as server:
                if config.smtp_use_tls:
                    server.starttls()
                if config.smtp_username and config.smtp_password:
                    server.login(config.smtp_username, config.smtp_password)
            _check("SMTP connection", True, f"{config.smtp_host}:{config.smtp_port}")
        except Exception as exc:
            _check("SMTP connection", False, str(exc))
        all_recip = config.recipients_warning + config.recipients_critical + config.recipients_emergency
        _check("Recipients configured", len(all_recip) > 0, f"{len(set(all_recip))} unique")
    else:
        _warn("SMTP", "SMTP_HOST or EMAIL_FROM not set")

    # MQTT
    print("\nMQTT")
    if config.mqtt_enabled:
        try:
            from src.alerting.notifiers.mqtt import _get_client
            client = _get_client()
            _check("MQTT connection", client is not None, f"{config.mqtt_host}:{config.mqtt_port}")
        except Exception as exc:
            _check("MQTT connection", False, str(exc))
    else:
        _warn("MQTT", "MQTT_ENABLED=false")

    # Notification channels
    print("\nNotification Channels")
    channels = [
        ("Webhook", config.webhook_enabled),
        ("Telegram", config.telegram_enabled),
        ("Pushover", config.pushover_enabled),
        ("MQTT alerts", config.mqtt_enabled),
    ]
    enabled_channels = [name for name, enabled in channels if enabled]
    if enabled_channels:
        print(f"  Enabled: {', '.join(enabled_channels)}")
    else:
        _warn("No notification channels enabled besides email")

    # Disk and filesystem
    print("\nFilesystem")
    try:
        usage = shutil.disk_usage("/")
        pct = (usage.used / usage.total) * 100
        free_gb = (usage.total - usage.used) / (1024**3)
        _check("Disk space", pct < 90, f"{pct:.1f}% used, {free_gb:.1f} GB free")
        if pct > 80:
            _warn("Disk usage above 80%", f"{pct:.1f}%")
    except OSError:
        _warn("Disk space", "unable to check")

    for d in ["logs", "data"]:
        dir_path = Path(__file__).resolve().parent / d
        if dir_path.exists():
            import os as _os
            _check(f"Directory writable: {d}/", _os.access(str(dir_path), _os.W_OK))
        else:
            _check(f"Directory exists: {d}/", False, "missing")

    # Service collectors
    print("\nService Collectors")
    from src.sensors.collectors.registry import collect_all
    collector_results = collect_all()
    if collector_results:
        for service_name, stats in collector_results.items():
            metric_count = len([v for v in stats.values() if isinstance(v, (int, float, bool))])
            _check(f"Collector: {service_name}", True, f"{metric_count} metrics")
    else:
        print("  No services auto-detected (this is normal if none are installed)")

    # Templates
    print("\nTemplates")
    template_dir = Path(__file__).resolve().parent / "templates"
    if template_dir.exists():
        templates = list(template_dir.glob("*.j2"))
        _check("Alert templates", len(templates) > 0, f"{len(templates)} template(s)")
    else:
        _warn("Templates directory", "missing")

    # Test suite
    print("\nTest Suite")
    test_dir = Path(__file__).resolve().parent / "tests"
    if test_dir.exists():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short", "--no-header"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(Path(__file__).resolve().parent),
            )
            # Parse output for pass/fail summary (last line)
            output_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
            summary_line = output_lines[-1] if output_lines else "no output"
            _check("Test suite", result.returncode == 0, summary_line)

            # If tests failed, print the failure details
            if result.returncode != 0 and output_lines:
                print("\n  Test failures:")
                in_failures = False
                for line in output_lines:
                    if "FAILURES" in line or "FAILED" in line or line.startswith("E "):
                        in_failures = True
                    if in_failures:
                        print(f"    {line}")
        except subprocess.TimeoutExpired:
            _check("Test suite", False, "timed out after 120s")
        except (OSError, FileNotFoundError):
            _warn("Test suite", "pytest not installed")
    else:
        _warn("Test suite", "tests/ directory not found")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {warnings} warnings")
    if failed:
        sys.exit(1)


def _cmd_backup(args: argparse.Namespace) -> None:
    """Create a tarball backup of the SQLite database and .env file."""
    import tarfile
    from datetime import datetime as _dt

    app_dir = _INSTALL_DIR if _INSTALL_DIR.exists() else _APP_DIR
    timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output) if args.output else app_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    tarball_path = output_dir / f"pimon_backup_{timestamp}.tar.gz"

    files_to_backup: list[tuple[Path, str]] = []

    # .env file
    env_path = app_dir / ".env"
    if env_path.exists():
        files_to_backup.append((env_path, ".env"))

    # SQLite database
    if config.database_url.startswith("sqlite"):
        db_path = Path(config.database_url.replace("sqlite:///", ""))
        if not db_path.is_absolute():
            db_path = app_dir / db_path
        if db_path.exists():
            files_to_backup.append((db_path, f"data/{db_path.name}"))

    if not files_to_backup:
        print("Nothing to back up.")
        sys.exit(1)

    with tarfile.open(tarball_path, "w:gz") as tar:
        for file_path, arcname in files_to_backup:
            tar.add(str(file_path), arcname=arcname)
            print(f"  Added: {arcname}")

    print(f"\nBackup saved to: {tarball_path}")
    print(f"Size: {tarball_path.stat().st_size / 1024:.1f} KB")


def _cmd_export(args: argparse.Namespace) -> None:
    """Export temperature history to CSV or JSON format."""
    import csv as csv_mod
    import json

    if not config.database_enabled:
        print("Database is not enabled. Cannot export history.")
        sys.exit(1)

    from src.database.models import init_db
    from src.database.repository import get_recent_readings
    init_db()

    rows = get_recent_readings(args.lines)
    if not rows:
        print("No history data found.")
        sys.exit(1)

    output_path = Path(args.output) if args.output else None

    if args.format == "json":
        content = json.dumps(rows, indent=2)
    else:
        import io
        buf = io.StringIO()
        writer = csv_mod.DictWriter(buf, fieldnames=["timestamp", "sensor", "temperature_c"])
        writer.writeheader()
        writer.writerows(rows)
        content = buf.getvalue()

    if output_path:
        output_path.write_text(content)
        print(f"Exported {len(rows)} records to {output_path}")
    else:
        print(content)


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

    logger = logging.getLogger("pimon")

    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", "--quiet", "pimon"],
            capture_output=True,
        )
        if result.returncode != 0:
            msg = (
                "The pimon systemd service is not enabled for auto-start. "
                "Run 'sudo systemctl enable pimon' to start on boot."
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
                "[PiMon] Service not enabled for auto-start",
                "The pimon service is not enabled for automatic startup.\n"
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
        prog="pimon",
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

    # logs
    logs_parser = subparsers.add_parser(
        "logs",
        help="View application log output",
        description=(
            "Display recent entries from the application log file.\n"
            "Use -f/--follow to tail the log in real time (like tail -f).\n"
            "\n"
            "Useful for checking startup messages, alert dispatches,\n"
            "sensor errors, and other runtime events."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    logs_parser.add_argument(
        "-n", "--lines",
        type=int,
        default=50,
        metavar="COUNT",
        help="Number of recent log lines to display (default: 50)",
    )
    logs_parser.add_argument(
        "-f", "--follow",
        action="store_true",
        help="Follow the log in real time (like tail -f)",
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
            "If running from /opt/pimon, updates that directory.\n"
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

    # doctor
    subparsers.add_parser(
        "doctor",
        help="Run diagnostic checks on all subsystems",
        description=(
            "Run a comprehensive health check of all PiMon subsystems:\n"
            "sensors, SMTP, MQTT, database, disk space, and directories.\n"
            "\n"
            "Exits with code 1 if any check fails."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # backup
    backup_parser = subparsers.add_parser(
        "backup",
        help="Create a tarball backup of database and configuration",
        description=(
            "Create a compressed tarball (.tar.gz) containing the SQLite\n"
            "database file and .env configuration for safe off-device storage."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    backup_parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        metavar="DIR",
        help="Output directory for the tarball (default: application root)",
    )

    # export
    export_parser = subparsers.add_parser(
        "export",
        help="Export temperature history to CSV or JSON",
        description=(
            "Export temperature readings from the database to CSV or JSON format.\n"
            "Output is written to stdout unless -o/--output is specified."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_parser.add_argument(
        "-f", "--format",
        choices=["csv", "json"],
        default="csv",
        help="Output format (default: csv)",
    )
    export_parser.add_argument(
        "-n", "--lines",
        type=int,
        default=1000,
        metavar="COUNT",
        help="Number of records to export (default: 1000)",
    )
    export_parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "start": _cmd_start,
        "status": _cmd_status,
        "history": _cmd_history,
        "logs": _cmd_logs,
        "test-email": _cmd_test_email,
        "config": _cmd_config,
        "update": _cmd_update,
        "migrate-db": _cmd_migrate_db,
        "doctor": _cmd_doctor,
        "backup": _cmd_backup,
        "export": _cmd_export,
    }
    commands[args.command](args)


def _run() -> None:
    """Top-level entry point with user-friendly error handling."""
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as exc:
        # Show a clean one-line error to the user
        print(f"Error: {exc}")
        print("\nRun with LOG_LEVEL=DEBUG in .env for full details, or check logs/alerter.log")
        sys.exit(1)


if __name__ == "__main__":
    _run()
