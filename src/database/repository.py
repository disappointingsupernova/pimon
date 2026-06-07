"""Database repository - helper functions for common queries.

Provides a clean interface for the rest of the application to interact
with the database without needing to know SQLAlchemy details.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func

from src.database.models import (
    AlertEvent,
    SystemMetricRecord,
    TemperatureReading,
    get_session,
)

logger = logging.getLogger("pi_temp_alerter")


# ============================================================================
# Temperature readings
# ============================================================================

def store_reading(sensor_name: str, temperature_c: float) -> None:
    """Persist a temperature reading to the database."""
    store_readings_batch([(sensor_name, temperature_c)])


def store_readings_batch(readings: list[tuple[str, float]]) -> None:
    """Persist multiple temperature readings in a single transaction.

    Opens one session, adds all readings, and commits once. Reduces
    database I/O overhead and SQLite lock contention compared to
    one commit per reading.
    """
    if not readings:
        return

    session = get_session()
    try:
        now = datetime.now(timezone.utc)
        for sensor_name, temperature_c in readings:
            session.add(TemperatureReading(
                sensor_name=sensor_name,
                temperature_c=temperature_c,
                timestamp=now,
            ))
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Failed to store readings batch: %s", exc)
    finally:
        session.close()


def get_recent_readings(count: int = 20) -> list[dict]:
    """Retrieve the most recent temperature readings."""
    session = get_session()
    try:
        rows = (
            session.query(TemperatureReading)
            .order_by(desc(TemperatureReading.timestamp))
            .limit(count)
            .all()
        )
        # Return in chronological order
        return [
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                "sensor": r.sensor_name,
                "temperature_c": f"{r.temperature_c:.1f}",
            }
            for r in reversed(rows)
        ]
    finally:
        session.close()


def get_readings_for_sensor(sensor_name: str, hours: int = 24) -> list[dict]:
    """Retrieve readings for a specific sensor within the last N hours."""
    session = get_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = (
            session.query(TemperatureReading)
            .filter(
                TemperatureReading.sensor_name == sensor_name,
                TemperatureReading.timestamp >= cutoff,
            )
            .order_by(TemperatureReading.timestamp)
            .all()
        )
        return [
            {
                "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                "temperature_c": r.temperature_c,
            }
            for r in rows
        ]
    finally:
        session.close()


def get_daily_stats(sensor_name: str, day: datetime) -> dict | None:
    """Get min/max/avg statistics for a sensor on a given day."""
    session = get_session()
    try:
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        result = (
            session.query(
                func.min(TemperatureReading.temperature_c),
                func.max(TemperatureReading.temperature_c),
                func.avg(TemperatureReading.temperature_c),
                func.count(TemperatureReading.id),
            )
            .filter(
                TemperatureReading.sensor_name == sensor_name,
                TemperatureReading.timestamp >= start,
                TemperatureReading.timestamp < end,
            )
            .first()
        )
        if result and result[3] > 0:
            return {
                "min": round(result[0], 1),
                "max": round(result[1], 1),
                "avg": round(result[2], 1),
                "count": result[3],
            }
        return None
    finally:
        session.close()


# ============================================================================
# Alert events
# ============================================================================

def store_alert(sensor_name: str, level: str, temperature_c: float) -> None:
    """Record that an alert was dispatched."""
    session = get_session()
    try:
        event = AlertEvent(
            sensor_name=sensor_name,
            level=level,
            temperature_c=temperature_c,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(event)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Failed to store alert event: %s", exc)
    finally:
        session.close()


def mark_recovery(sensor_name: str) -> None:
    """Mark the most recent unrecovered alert for a sensor as recovered."""
    session = get_session()
    try:
        event = (
            session.query(AlertEvent)
            .filter(
                AlertEvent.sensor_name == sensor_name,
                AlertEvent.recovered == False,
            )
            .order_by(desc(AlertEvent.timestamp))
            .first()
        )
        if event:
            event.recovered = True
            event.recovered_at = datetime.now(timezone.utc)
            session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Failed to mark recovery: %s", exc)
    finally:
        session.close()


# ============================================================================
# System metrics
# ============================================================================

def store_system_metrics(
    cpu_percent: float,
    memory_percent: float,
    disk_percent: float,
    throttled: bool,
) -> None:
    """Persist a system metrics snapshot."""
    session = get_session()
    try:
        record = SystemMetricRecord(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_percent=disk_percent,
            throttled=throttled,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(record)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Failed to store system metrics: %s", exc)
    finally:
        session.close()


# ============================================================================
# Maintenance
# ============================================================================

def prune_old_records(retention_days: int) -> int:
    """Delete records older than the retention period. Returns count removed."""
    session = get_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        count = (
            session.query(TemperatureReading)
            .filter(TemperatureReading.timestamp < cutoff)
            .delete()
        )
        session.commit()
        return count
    except Exception as exc:
        session.rollback()
        logger.error("Failed to prune old records: %s", exc)
        return 0
    finally:
        session.close()
