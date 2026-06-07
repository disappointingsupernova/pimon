"""SQLAlchemy models and session management.

Defines the database schema for temperature readings, alerts, and
system metrics. Supports SQLite (default), MySQL, and PostgreSQL
via the DATABASE_URL connection string.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import config

logger = logging.getLogger("pi_temp_alerter")


# ============================================================================
# Base and engine setup
# ============================================================================

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def _get_engine():
    """Create the SQLAlchemy engine from the configured DATABASE_URL.

    Defaults to a local SQLite file if no URL is specified.
    For SQLite, enables WAL journal mode which significantly reduces
    SD card wear by using sequential writes instead of rewrites.
    """
    url = config.database_url

    # SQLite-specific settings for Pi SD card optimisation
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    engine = create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        echo=(config.log_level.upper() == "DEBUG"),
    )

    # Enable WAL mode for SQLite to reduce SD card write amplification.
    # WAL uses sequential appends instead of rewriting the journal file.
    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


# Lazy-initialised engine and session factory
_engine = None
_SessionLocal = None


def get_session() -> Session:
    """Return a new database session.

    Callers are responsible for closing the session after use,
    ideally via a context manager or try/finally block.
    """
    global _engine, _SessionLocal
    if _engine is None:
        _engine = _get_engine()
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_engine)
    return _SessionLocal()


def _redact_url(url: str) -> str:
    """Redact credentials from a database URL for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            # Replace password with *** in the netloc
            redacted_netloc = f"{parsed.username}:***@{parsed.hostname}"
            if parsed.port:
                redacted_netloc += f":{parsed.port}"
            return urlunparse(parsed._replace(netloc=redacted_netloc))
        return url
    except Exception:
        # If parsing fails, return the backend type only
        return url.split("://")[0] + "://***" if "://" in url else url


def init_db() -> None:
    """Create all tables if they do not exist.

    Safe to call multiple times - will not drop or alter existing tables.
    Ensures the data directory exists for SQLite databases.
    """
    global _engine

    # Ensure the data directory exists for SQLite
    if config.database_url.startswith("sqlite"):
        from pathlib import Path
        # Extract file path from sqlite:///path/to/file.db
        db_path = config.database_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    if _engine is None:
        _engine = _get_engine()
    Base.metadata.create_all(_engine)
    logger.info("Database initialised: %s", _redact_url(config.database_url))


# ============================================================================
# Models
# ============================================================================

class TemperatureReading(Base):
    """A single temperature reading from a sensor."""

    __tablename__ = "temperature_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    sensor_name = Column(String(100), nullable=False, index=True)
    temperature_c = Column(Float, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<TemperatureReading(sensor={self.sensor_name}, "
            f"temp={self.temperature_c}, time={self.timestamp})>"
        )


class AlertEvent(Base):
    """A record of an alert that was dispatched."""

    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    sensor_name = Column(String(100), nullable=False)
    level = Column(String(20), nullable=False)  # WARNING, CRITICAL, EMERGENCY
    temperature_c = Column(Float, nullable=False)
    recovered = Column(Boolean, default=False)
    recovered_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AlertEvent(sensor={self.sensor_name}, level={self.level}, "
            f"temp={self.temperature_c})>"
        )


class SystemMetricRecord(Base):
    """A snapshot of system resource usage at a point in time."""

    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    cpu_percent = Column(Float)
    memory_percent = Column(Float)
    disk_percent = Column(Float)
    throttled = Column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<SystemMetricRecord(cpu={self.cpu_percent}, mem={self.memory_percent})>"
