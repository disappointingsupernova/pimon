"""Tests for src.database.repository and models modules."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_db_engine(tmp_path, monkeypatch):
    """Reset the database engine for each test to ensure isolation."""
    import uuid
    monkeypatch.setenv("DATABASE_ENABLED", "true")
    db_path = tmp_path / f"test_{uuid.uuid4().hex[:8]}.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    import src.database.models as models_mod
    import src.config as config_mod

    # Dispose existing engine
    if models_mod._engine is not None:
        models_mod._engine.dispose()
    models_mod._engine = None
    models_mod._SessionLocal = None

    # Ensure config picks up new DATABASE_URL
    config_mod.config = config_mod.Config()

    from src.database.models import init_db
    init_db()
    yield

    if models_mod._engine is not None:
        models_mod._engine.dispose()
    models_mod._engine = None
    models_mod._SessionLocal = None


class TestStoreReadings:
    """Test temperature reading persistence."""

    def test_store_and_retrieve_reading(self):
        from src.database.repository import store_reading, get_recent_readings
        store_reading("test_sensor_1", 55.5)
        rows = get_recent_readings(100)
        matching = [r for r in rows if r["sensor"] == "test_sensor_1"]
        assert len(matching) == 1
        assert matching[0]["temperature_c"] == "55.5"

    def test_store_batch(self):
        from src.database.repository import store_readings_batch, get_recent_readings
        store_readings_batch([("batch_a", 50.0), ("batch_b", 45.0)])
        rows = get_recent_readings(100)
        batch_rows = [r for r in rows if r["sensor"] in ("batch_a", "batch_b")]
        assert len(batch_rows) == 2

    def test_get_recent_readings_respects_limit(self):
        from src.database.repository import store_readings_batch, get_recent_readings
        store_readings_batch([(f"sensor_{i}", float(i)) for i in range(50)])
        rows = get_recent_readings(10)
        assert len(rows) == 10


class TestAlertEvents:
    """Test alert event persistence."""

    def test_store_alert(self):
        from src.database.repository import store_alert, get_recent_alerts
        store_alert("alert_test_sensor", "WARNING", 65.0)
        alerts = get_recent_alerts(100)
        matching = [a for a in alerts if a["sensor"] == "alert_test_sensor"]
        assert len(matching) == 1
        assert matching[0]["level"] == "WARNING"
        assert matching[0]["recovered"] is False

    def test_mark_recovery(self):
        from src.database.repository import store_alert, mark_recovery
        from src.database.models import get_session, AlertEvent
        from sqlalchemy import desc
        store_alert("recovery_test", "CRITICAL", 72.0)
        mark_recovery("recovery_test")

        session = get_session()
        event = (
            session.query(AlertEvent)
            .filter(AlertEvent.sensor_name == "recovery_test")
            .order_by(desc(AlertEvent.timestamp))
            .first()
        )
        assert event.recovered is True
        assert event.recovered_at is not None
        session.close()


class TestAlertStatePersistence:
    """Test alert state deduplication across restarts."""

    def test_save_and_load_alert_state(self):
        from src.database.repository import save_alert_state, load_alert_states
        now = datetime.now(timezone.utc)
        save_alert_state("cpu", "WARNING", now, {"WARNING": now, "CRITICAL": None, "EMERGENCY": None})

        states = load_alert_states()
        assert len(states) == 1
        assert states[0]["sensor_name"] == "cpu"
        assert states[0]["current_level"] == "WARNING"
        assert states[0]["last_alert_times"]["WARNING"] is not None

    def test_save_updates_existing(self):
        from src.database.repository import save_alert_state, load_alert_states
        now = datetime.now(timezone.utc)
        save_alert_state("cpu", "WARNING", now, {"WARNING": now, "CRITICAL": None, "EMERGENCY": None})
        save_alert_state("cpu", "CRITICAL", now, {"WARNING": now, "CRITICAL": now, "EMERGENCY": None})

        states = load_alert_states()
        assert len(states) == 1
        assert states[0]["current_level"] == "CRITICAL"


class TestSystemMetrics:
    """Test system metrics persistence."""

    def test_store_system_metrics(self):
        from src.database.repository import store_system_metrics
        from src.database.models import get_session, SystemMetricRecord
        store_system_metrics(45.0, 60.0, 30.0, False)

        session = get_session()
        record = session.query(SystemMetricRecord).first()
        assert record.cpu_percent == 45.0
        assert record.memory_percent == 60.0
        assert record.throttled is False
        session.close()


class TestPruning:
    """Test database record pruning."""

    def test_prune_old_records(self):
        from src.database.repository import store_reading, prune_old_records, get_recent_readings
        from src.database.models import get_session, TemperatureReading

        # Insert an old record directly
        session = get_session()
        old_record = TemperatureReading(
            sensor_name="prune_old",
            temperature_c=50.0,
            timestamp=datetime.now(timezone.utc) - timedelta(days=100),
        )
        session.add(old_record)
        session.commit()
        session.close()

        # Insert a recent record
        store_reading("prune_new", 55.0)

        removed = prune_old_records(90)
        assert removed >= 1

        rows = get_recent_readings(100)
        # The old record should be gone, the new one remains
        assert not any(r["sensor"] == "prune_old" for r in rows)
        assert any(r["sensor"] == "prune_new" for r in rows)
