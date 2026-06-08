"""Database migration tool for PiMon.

Copies all records from one database backend to another, enabling
migration between SQLite, MySQL, and PostgreSQL without data loss.
"""

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import (
    AlertEvent,
    Base,
    SystemMetricRecord,
    TemperatureReading,
)

logger = logging.getLogger("pimon")

# Batch size for bulk inserts to manage memory on large datasets
_BATCH_SIZE = 1000


def migrate_database(source_url: str, target_url: str) -> bool:
    """Migrate all data from source to target database.

    Creates tables on the target if they do not exist. Copies all rows
    from temperature_readings, alert_events, and system_metrics in
    batches to avoid excessive memory usage.

    Returns True on success, False on failure.
    """
    try:
        # Create engines for both databases
        source_engine = _create_engine(source_url)
        target_engine = _create_engine(target_url)

        # Create tables on target
        logger.info("Creating tables on target database...")
        print("  Creating tables on target...")
        Base.metadata.create_all(target_engine)

        SourceSession = sessionmaker(bind=source_engine)
        TargetSession = sessionmaker(bind=target_engine)

        # Migrate each table
        tables = [
            ("temperature_readings", TemperatureReading),
            ("alert_events", AlertEvent),
            ("system_metrics", SystemMetricRecord),
        ]

        for table_name, model in tables:
            count = _migrate_table(SourceSession, TargetSession, model, table_name)
            logger.info("Migrated %d rows from %s", count, table_name)

        return True

    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        print(f"  ERROR: {exc}")
        return False


def _create_engine(url: str):
    """Create an engine with appropriate settings for the backend."""
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    return create_engine(url, connect_args=connect_args)


def _migrate_table(SourceSession, TargetSession, model, table_name: str) -> int:
    """Copy all rows from a single table in batches.

    Returns the total number of rows migrated.
    """
    source = SourceSession()
    total = 0

    try:
        # Count total rows for progress reporting
        row_count = source.query(model).count()
        print(f"  Migrating {table_name}: {row_count} rows...")

        if row_count == 0:
            return 0

        # Process in batches to avoid loading everything into memory
        offset = 0
        while offset < row_count:
            rows = (
                source.query(model)
                .order_by(model.id)
                .offset(offset)
                .limit(_BATCH_SIZE)
                .all()
            )

            if not rows:
                break

            # Detach from source session and insert into target
            target = TargetSession()
            try:
                for row in rows:
                    # Create a new instance with the same column values
                    # (excluding the primary key so the target assigns its own)
                    data = {
                        col.name: getattr(row, col.name)
                        for col in model.__table__.columns
                        if col.name != "id"
                    }
                    target.add(model(**data))

                target.commit()
                total += len(rows)
            except Exception:
                target.rollback()
                raise
            finally:
                target.close()

            offset += _BATCH_SIZE

        print(f"    Done: {total} rows migrated.")
        return total

    finally:
        source.close()
