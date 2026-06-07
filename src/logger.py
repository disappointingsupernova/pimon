"""Logging configuration for Pi Temperature Alerter.

Sets up rotating file handler and console output. Optionally logs
temperature readings to a CSV file for historical analysis.
"""

import csv
import logging
from datetime import datetime, timezone
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


def log_temperature_csv(sensor: str, temperature: float) -> None:
    """Append a temperature reading to the CSV history file."""
    if not config.csv_logging_enabled:
        return

    _DATA_DIR.mkdir(exist_ok=True)
    csv_path = _DATA_DIR / "temperature_history.csv"
    file_exists = csv_path.exists()

    with open(csv_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "sensor", "temperature_c"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            sensor,
            f"{temperature:.1f}",
        ])
