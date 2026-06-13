import datetime
import sqlite3

from core.scheduler.database_availability_state import (
    DatabaseAvailabilityObservation,
    DatabaseAvailabilityStore,
)


UTC = datetime.UTC


def _observation(*, available: bool, reason: str | None = None):
    return DatabaseAvailabilityObservation(
        service_key="postgres",
        service_label="PostgreSQL",
        is_available=available,
        reason=reason,
    )


def test_store_creates_one_outage_event_and_suppresses_repeated_failures(tmp_path):
    path = tmp_path / "database-availability.sqlite3"
    store = DatabaseAvailabilityStore(path)
    first_failure_at = datetime.datetime(2026, 6, 13, 10, 5, tzinfo=UTC)
    second_failure_at = datetime.datetime(2026, 6, 13, 10, 16, tzinfo=UTC)

    store.record_observations(
        (_observation(available=False, reason="connection refused"),),
        checked_at=first_failure_at,
    )
    store.record_observations(
        (_observation(available=False, reason="timeout"),),
        checked_at=second_failure_at,
    )

    pending = DatabaseAvailabilityStore(path).load_pending_events()

    assert len(pending) == 1
    assert pending[0].event_type == "unavailable"
    assert pending[0].outage_started_at == first_failure_at
    assert pending[0].reason == "connection refused"

    with sqlite3.connect(path) as connection:
        state = connection.execute(
            """
            SELECT
                is_available,
                outage_started_at,
                last_reason,
                failed_check_count
            FROM database_availability_state
            WHERE service_key = 'postgres'
            """
        ).fetchone()

    assert state == (
        0,
        first_failure_at.isoformat(),
        "timeout",
        2,
    )


def test_store_records_recovery_interval_and_delivery_state(tmp_path):
    path = tmp_path / "database-availability.sqlite3"
    store = DatabaseAvailabilityStore(path)
    outage_started_at = datetime.datetime(2026, 6, 13, 10, 5, tzinfo=UTC)
    repeated_failure_at = datetime.datetime(2026, 6, 13, 10, 16, tzinfo=UTC)
    recovered_at = datetime.datetime(2026, 6, 13, 10, 35, tzinfo=UTC)

    store.record_observations(
        (_observation(available=False, reason="connection refused"),),
        checked_at=outage_started_at,
    )
    outage_event = store.load_pending_events()[0]
    store.mark_events_delivered((outage_event.id,))
    store.record_observations(
        (_observation(available=False, reason="timeout"),),
        checked_at=repeated_failure_at,
    )
    DatabaseAvailabilityStore(path).record_observations(
        (_observation(available=True),),
        checked_at=recovered_at,
    )

    pending = store.load_pending_events()

    assert len(pending) == 1
    recovery = pending[0]
    assert recovery.event_type == "recovered"
    assert recovery.outage_started_at == outage_started_at
    assert recovery.outage_ended_at == recovered_at
    assert recovery.reason == "timeout"
    assert recovery.failed_check_count == 2

    store.mark_events_delivered((recovery.id,), delivered_at=recovered_at)
    assert store.load_pending_events() == ()


def test_initial_available_observation_does_not_create_recovery_event(tmp_path):
    store = DatabaseAvailabilityStore(
        tmp_path / "database-availability.sqlite3"
    )

    store.record_observations(
        (_observation(available=True),),
        checked_at=datetime.datetime(2026, 6, 13, 10, 5, tzinfo=UTC),
    )

    assert store.load_pending_events() == ()
