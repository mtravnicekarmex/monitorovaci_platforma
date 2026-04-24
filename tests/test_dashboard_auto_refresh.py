import datetime

from moduly.apps.dashboard.auto_refresh import (
    QUARTER_HOUR_PAGE_REFRESH_MINUTES,
    SENSOR_DB_WRITE_MINUTES,
    SENSOR_REFRESH_MINUTES,
    build_interval_refresh_minutes,
    build_post_write_refresh_minutes,
    get_scheduler_job_anchor_minute,
    get_next_scheduled_refresh,
    normalize_refresh_minutes,
)


def test_normalize_refresh_minutes_sorts_and_deduplicates():
    assert normalize_refresh_minutes((40, 5, 20, 5)) == (5, 20, 40)


def test_build_post_write_refresh_minutes_offsets_scheduler_write_slots():
    assert SENSOR_DB_WRITE_MINUTES == (5, 16, 35, 50)
    assert build_post_write_refresh_minutes(SENSOR_DB_WRITE_MINUTES, buffer_minutes=1) == (6, 17, 36, 51)
    assert SENSOR_REFRESH_MINUTES == (6, 17, 36, 51)


def test_get_scheduler_job_anchor_minute_reads_quarter_hour_job_from_scheduler_specs():
    assert get_scheduler_job_anchor_minute("quarter_hour_job") == 5


def test_build_interval_refresh_minutes_creates_regular_quarter_hour_slots_after_job_anchor():
    assert build_interval_refresh_minutes(5, interval_minutes=15, buffer_minutes=1) == (6, 21, 36, 51)
    assert QUARTER_HOUR_PAGE_REFRESH_MINUTES == (6, 21, 36, 51)


def test_normalize_refresh_minutes_rejects_invalid_values():
    try:
        normalize_refresh_minutes((5, 61))
    except ValueError as exc:
        assert "0-59" in str(exc)
    else:
        raise AssertionError("Expected invalid refresh minute to raise ValueError.")


def test_get_next_scheduled_refresh_returns_next_slot_in_same_hour():
    now = datetime.datetime(2026, 4, 8, 10, 19, 59)

    next_refresh = get_next_scheduled_refresh(now, SENSOR_REFRESH_MINUTES)

    assert next_refresh == datetime.datetime(2026, 4, 8, 10, 36)


def test_get_next_scheduled_refresh_skips_current_exact_slot():
    now = datetime.datetime(2026, 4, 8, 10, 36, 0)

    next_refresh = get_next_scheduled_refresh(now, SENSOR_REFRESH_MINUTES)

    assert next_refresh == datetime.datetime(2026, 4, 8, 10, 51)


def test_get_next_scheduled_refresh_wraps_to_next_hour():
    now = datetime.datetime(2026, 4, 8, 23, 59, 0)

    next_refresh = get_next_scheduled_refresh(now, SENSOR_REFRESH_MINUTES)

    assert next_refresh == datetime.datetime(2026, 4, 9, 0, 6)
