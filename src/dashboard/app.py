"""Flask web dashboard for real-time temperature monitoring."""

import csv
import logging
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Thread

from flask import Flask, jsonify, render_template

from src.config import config
from src.sensors.manager import SensorManager

logger = logging.getLogger("pi_temp_alerter")

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

app = Flask(__name__, template_folder=str(_TEMPLATE_DIR))

# In-memory buffer for recent readings (last 100 per sensor)
_recent_readings: dict[str, deque] = {}
_sensor_manager: SensorManager | None = None


def init_dashboard(sensor_manager: SensorManager) -> None:
    """Initialise the dashboard with a reference to the sensor manager."""
    global _sensor_manager
    _sensor_manager = sensor_manager


def record_reading(sensor_name: str, temperature: float) -> None:
    """Store a reading in the in-memory buffer for the dashboard."""
    if sensor_name not in _recent_readings:
        _recent_readings[sensor_name] = deque(maxlen=100)
    _recent_readings[sensor_name].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": temperature,
    })


@app.route("/")
def index():
    """Render the main dashboard page."""
    return render_template("index.html", config=config)


@app.route("/api/current")
def api_current():
    """Return current readings from all sensors."""
    if _sensor_manager is None:
        return jsonify({"error": "Sensor manager not initialised"}), 500

    readings = _sensor_manager.read_all()
    return jsonify({
        "readings": [
            {
                "sensor": r.sensor_name,
                "temperature_c": r.temperature_c,
                "available": r.available,
                "error": r.error,
            }
            for r in readings
        ],
        "thresholds": {
            "warning": config.temp_warning,
            "critical": config.temp_critical,
            "emergency": config.temp_emergency,
        },
    })


@app.route("/api/history")
def api_history():
    """Return recent in-memory readings for charting."""
    return jsonify(_recent_readings)


@app.route("/api/history/csv")
def api_history_csv():
    """Return the last 500 entries from recent CSV logs."""
    entries = []
    for days_ago in range(2):
        day = date.today() - timedelta(days=days_ago)
        csv_path = _DATA_DIR / f"temperature_{day.isoformat()}.csv"
        if csv_path.exists():
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                entries.extend(reader)

    entries.sort(key=lambda r: r.get("timestamp", ""))
    return jsonify({"entries": entries[-500:]})


def start_dashboard() -> Thread | None:
    """Start the Flask dashboard in a background thread."""
    if not config.dashboard_enabled:
        return None

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
