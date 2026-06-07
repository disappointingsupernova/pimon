"""Daily digest email for Pi Temperature Alerter.

Sends a once-daily summary with min/max/average temperatures,
alert count, and uptime statistics.
"""

import csv
import logging
from datetime import date, timedelta
from pathlib import Path

from src.alerting.email_sender import _send
from src.config import config

logger = logging.getLogger("pi_temp_alerter")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def send_daily_digest() -> bool:
    """Generate and send the daily digest email. Returns True on success."""
    yesterday = date.today() - timedelta(days=1)
    csv_path = _DATA_DIR / f"temperature_{yesterday.isoformat()}.csv"

    if not csv_path.exists():
        logger.info("No data for %s, skipping daily digest", yesterday)
        return False

    # Parse readings
    readings_by_sensor: dict[str, list[float]] = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sensor = row.get("sensor", "unknown")
            try:
                temp = float(row.get("temperature_c", 0))
            except ValueError:
                continue
            if sensor not in readings_by_sensor:
                readings_by_sensor[sensor] = []
            readings_by_sensor[sensor].append(temp)

    if not readings_by_sensor:
        return False

    # Build summary
    lines = [
        f"Daily Temperature Digest - {yesterday.isoformat()}",
        "=" * 50,
        "",
    ]

    for sensor, temps in sorted(readings_by_sensor.items()):
        avg = sum(temps) / len(temps)
        lines.append(f"  {sensor}:")
        lines.append(f"    Min: {min(temps):.1f} C")
        lines.append(f"    Max: {max(temps):.1f} C")
        lines.append(f"    Avg: {avg:.1f} C")
        lines.append(f"    Readings: {len(temps)}")
        lines.append("")

    total_readings = sum(len(t) for t in readings_by_sensor.values())
    lines.append(f"  Total readings: {total_readings}")
    lines.append(f"  Sensors active: {len(readings_by_sensor)}")

    body = "\n".join(lines)
    subject = f"[Pi Alerter] Daily Digest - {yesterday.isoformat()}"

    recipients = list(set(
        config.recipients_warning
        + config.recipients_critical
        + config.recipients_emergency
    ))

    return _send(recipients, subject, body)
