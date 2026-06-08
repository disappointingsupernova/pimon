"""Flask web dashboard for real-time temperature monitoring."""

import csv
import hmac
import logging
import os
import re
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Thread

from flask import Flask, jsonify, render_template, request, Response

from src.config import config
from src.sensors.manager import SensorManager

logger = logging.getLogger("pimon")

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

app = Flask(__name__, template_folder=str(_TEMPLATE_DIR))
app.config["SECRET_KEY"] = os.urandom(32)

# In-memory buffer for recent readings (last 100 per sensor)
_recent_readings: dict[str, deque] = {}
_sensor_manager: SensorManager | None = None
_start_time: datetime = datetime.now(timezone.utc)
_last_poll_time: datetime | None = None
# Cached latest readings from the monitor loop (updated every poll cycle)
_latest_sensor_data: list[dict] = []


def init_dashboard(sensor_manager: SensorManager) -> None:
    """Initialise the dashboard with a reference to the sensor manager."""
    global _sensor_manager
    _sensor_manager = sensor_manager


def _check_auth() -> Response | None:
    """Verify basic auth credentials if authentication is enabled.

    Uses hmac.compare_digest for constant-time comparison to prevent
    timing attacks against the username and password.
    """
    if not config.dashboard_auth_enabled:
        return None

    auth = request.authorization
    if auth is None:
        return Response(
            "Authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="PiMon"'},
        )

    # Constant-time comparison prevents timing-based credential guessing
    username_valid = hmac.compare_digest(auth.username, config.dashboard_username)
    password_valid = hmac.compare_digest(auth.password, config.dashboard_password)

    if not (username_valid and password_valid):
        return Response(
            "Authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="PiMon"'},
        )
    return None


@app.before_request
def before_request():
    """Enforce authentication on all routes if enabled."""
    return _check_auth()


def record_reading(sensor_name: str, temperature: float) -> None:
    """Store a reading in the in-memory buffer for the dashboard."""
    global _last_poll_time
    _last_poll_time = datetime.now(timezone.utc)
    if sensor_name not in _recent_readings:
        _recent_readings[sensor_name] = deque(maxlen=100)
    _recent_readings[sensor_name].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": temperature,
    })


def update_latest_readings(readings: list[dict]) -> None:
    """Update the cached sensor data served by API endpoints.

    Called by the monitor after each poll cycle so dashboard endpoints
    serve cached data rather than triggering fresh subprocess reads.
    """
    global _latest_sensor_data
    _latest_sensor_data = readings


@app.route("/")
def index():
    """Render the main dashboard page."""
    return render_template("index.html", config=config)


@app.route("/api/current")
def api_current():
    """Return current readings from cached monitor data."""
    if not config.endpoint_api_enabled:
        return Response("Endpoint disabled.", 404)

    return jsonify({
        "readings": _latest_sensor_data,
        "thresholds": {
            "warning": config.temp_warning,
            "critical": config.temp_critical,
            "emergency": config.temp_emergency,
        },
    })


@app.route("/api/history")
def api_history():
    """Return recent in-memory readings for charting."""
    if not config.endpoint_api_enabled:
        return Response("Endpoint disabled.", 404)
    return jsonify(_recent_readings)


@app.route("/api/history/db")
def api_history_db():
    """Return historical readings from the database with configurable lookback.

    Query parameters:
        hours: Number of hours to look back (default: 24, max: 168)
        sensor: Optional sensor name filter
    """
    if not config.endpoint_api_enabled:
        return Response("Endpoint disabled.", 404)
    if not config.database_enabled:
        return jsonify({"error": "Database not enabled"}), 400

    from src.database.repository import get_readings_for_sensor, get_recent_readings

    hours = request.args.get("hours", 24, type=int)
    hours = min(max(hours, 1), 168)  # Clamp between 1 and 168 (7 days)
    sensor = request.args.get("sensor", None)

    if sensor:
        readings = get_readings_for_sensor(sensor, hours=hours)
        return jsonify({"sensor": sensor, "hours": hours, "readings": readings})

    # Return all sensors grouped
    from src.database.models import get_session, TemperatureReading
    from sqlalchemy import distinct
    session = get_session()
    try:
        sensors = [
            r[0] for r in session.query(distinct(TemperatureReading.sensor_name)).all()
        ]
    finally:
        session.close()

    result = {}
    for s in sensors:
        result[s] = get_readings_for_sensor(s, hours=hours)

    return jsonify({"hours": hours, "sensors": result})


@app.route("/api/health")
def api_health():
    """Return system health status from cached data."""
    if not config.endpoint_health_enabled:
        return Response("Endpoint disabled.", 404)
    from src.sensors.system_metrics import collect_metrics

    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    metrics = collect_metrics()

    return jsonify({
        "status": "healthy",
        "uptime_seconds": round(uptime, 1),
        "last_poll": _last_poll_time.isoformat() if _last_poll_time else None,
        "sensors": _latest_sensor_data,
        "system": {
            "cpu_percent": metrics.cpu_percent,
            "memory_percent": metrics.memory_percent,
            "memory_used_mb": metrics.memory_used_mb,
            "memory_total_mb": metrics.memory_total_mb,
            "disk_percent": metrics.disk_percent,
            "disk_used_gb": metrics.disk_used_gb,
            "disk_total_gb": metrics.disk_total_gb,
            "throttled": metrics.throttled,
            "throttle_flags": metrics.throttle_flags,
        },
        "config": {
            "poll_interval": config.poll_interval,
            "alert_cooldown": config.alert_cooldown,
            "dry_run": config.dry_run,
        },
    })


@app.route("/api/history/csv")
def api_history_csv():
    """Return the last 500 entries from recent CSV logs.

    Uses a bounded deque to avoid loading the entire file into memory.
    CSV data is already in chronological order so no sorting is needed.
    """
    if not config.endpoint_api_enabled:
        return Response("Endpoint disabled.", 404)

    # Use a deque to retain only the last 500 rows in memory
    tail = deque(maxlen=500)
    for days_ago in range(2):
        day = date.today() - timedelta(days=days_ago)
        csv_path = _DATA_DIR / f"temperature_{day.isoformat()}.csv"
        if csv_path.exists():
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tail.append(row)

    return jsonify({"entries": list(tail)})


@app.route("/metrics")
def prometheus_metrics():
    """Expose metrics in Prometheus text format."""
    if not config.endpoint_metrics_enabled:
        return Response("Endpoint disabled.", 404)
    from src.sensors.system_metrics import collect_metrics

    lines = []
    lines.append("# HELP pimon_uptime_seconds Uptime in seconds")
    lines.append("# TYPE pimon_uptime_seconds gauge")
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    lines.append(f"pimon_uptime_seconds {uptime:.1f}")

    if _latest_sensor_data:
        lines.append("# HELP pimon_temperature_celsius Current temperature")
        lines.append("# TYPE pimon_temperature_celsius gauge")
        for sensor_data in _latest_sensor_data:
            if sensor_data.get("available", False):
                safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', sensor_data["sensor"])
                lines.append(
                    f'pimon_temperature_celsius{{sensor="{safe_name}"}} '
                    f"{sensor_data['temperature_c']:.1f}"
                )

    metrics = collect_metrics()
    lines.append("# HELP pimon_cpu_usage_percent CPU usage percentage")
    lines.append("# TYPE pimon_cpu_usage_percent gauge")
    lines.append(f"pimon_cpu_usage_percent {metrics.cpu_percent}")

    lines.append("# HELP pimon_memory_usage_percent Memory usage percentage")
    lines.append("# TYPE pimon_memory_usage_percent gauge")
    lines.append(f"pimon_memory_usage_percent {metrics.memory_percent}")

    lines.append("# HELP pimon_disk_usage_percent Disk usage percentage")
    lines.append("# TYPE pimon_disk_usage_percent gauge")
    lines.append(f"pimon_disk_usage_percent {metrics.disk_percent}")

    lines.append("# HELP pimon_throttled Whether the Pi is throttled")
    lines.append("# TYPE pimon_throttled gauge")
    lines.append(f"pimon_throttled {1 if metrics.throttled else 0}")

    return Response("\n".join(lines) + "\n", mimetype="text/plain; charset=utf-8")


def start_dashboard() -> Thread | None:
    """Start the Flask dashboard in a background thread."""
    if not config.dashboard_enabled:
        return None

    # Security warning if exposed to the network without authentication
    if config.dashboard_host in ("0.0.0.0", "") and not config.dashboard_auth_enabled:
        logger.warning(
            "Dashboard is binding to all interfaces (0.0.0.0) with authentication "
            "disabled. Anyone on the network can access sensor data and system "
            "metrics. Set DASHBOARD_AUTH_ENABLED=true or bind to 127.0.0.1."
        )

    # Suppress Flask's development server warning banner in logs
    # Set the werkzeug logger to ERROR level to hide the startup warning
    # while still allowing the server to bind and run normally
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    thread = Thread(
        target=lambda: app.run(
            host=config.dashboard_host,
            port=config.dashboard_port,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )
    thread.start()
    logger.info(
        "Dashboard running at http://%s:%d",
        config.dashboard_host,
        config.dashboard_port,
    )
    return thread
