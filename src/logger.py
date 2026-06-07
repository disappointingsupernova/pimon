"""Logging configuration for Pi Temperature Alerter.

Sets up rotating file handler and console output. Implements daily CSV
rotation with configurable retention for temperature history.
"""

import csv
import logging
from datetime import date, datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import config

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def setup_logging() -> logging.Logger:
    """Initialise and return the application logger."""
    _LOG_DIR.mkdir(exist_ok=True)

    logger = logging.getLogger("pi_temp_alerter")
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    # Prevent duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler
    file_handler = RotatingFileHandler(
        _LOG_DIR / "alerter.log",
        maxBytes=config.log_max_size_mb * 1024 * 1024,
        backupCount=config.log_backup_count,
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def _get_csv_path(day: date | None = None) -> Path:
    """Return the CSV path for a given day (defaults to today)."""
    if day is None:
        day = date.today()
    return _DATA_DIR / f"temperature_{day.isoformat()}.csv"


def log_temperature_csv(sensor: str, temperature: float) -> None:
    """Append a temperature reading to today's CSV file."""
    if not config.csv_logging_enabled:
        return
    log_temperatures_csv_batch([(sensor, temperature)])


def log_temperatures_csv_batch(readings: list[tuple[str, float]]) -> None:
    """Append multiple temperature readings to today's CSV file in one I/O operation.

    Opens the file once, writes all readings, then closes. Reduces SD card
    wear and I/O overhead compared to opening per individual reading.
    """
    if not config.csv_logging_enabled or not readings:
        return

    _DATA_DIR.mkdir(exist_ok=True)
    csv_path = _get_csv_path()
    file_exists = csv_path.exists()
    now = datetime.now(timezone.utc).isoformat()

    with open(csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "sensor", "temperature_c"])
        for sensor, temperature in readings:
            writer.writerow([now, sensor, f"{temperature:.1f}"])


def prune_old_csv_files() -> int:
    """Remove CSV files older than the configured retention period.

    Returns the number of files removed.
    """
    if not _DATA_DIR.exists():
        return 0

    cutoff = date.today() - timedelta(days=config.csv_retention_days)
    removed = 0

    for csv_file in _DATA_DIR.glob("temperature_*.csv"):
        try:
            # Extract date from filename: temperature_YYYY-MM-DD.csv
            date_str = csv_file.stem.replace("temperature_", "")
            file_date = date.fromisoformat(date_str)
            if file_date < cutoff:
                csv_file.unlink()
                removed += 1
        except ValueError:
            continue

    return removed


def get_recent_csv_rows(count: int = 20) -> list[dict]:
    """Read the most recent CSV entries across today and yesterday's files."""
    rows: list[dict] = []

    # Check today and yesterday (covers the case where we just rolled over)
    for days_ago in range(2):
        day = date.today() - timedelta(days=days_ago)
        csv_path = _get_csv_path(day)
        if csv_path.exists():
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                rows.extend(reader)

    # Sort by timestamp descending and return the requested count
    rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return list(reversed(rows[:count]))
