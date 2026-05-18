from datetime import datetime, timezone

from moduly.mereni.elektromery.database.time_semantics import (
    build_time_columns,
)


def test_binary_fixed_offset_and_prague_civil_time_can_align_in_summer():
    binary_columns = build_time_columns(datetime(2024, 7, 1, 0, 0), "BINARY_19891")
    ote_columns = build_time_columns(datetime(2024, 7, 1, 1, 0), "OTE")

    assert binary_columns["time_utc"] == datetime(2024, 6, 30, 23, 0, tzinfo=timezone.utc)
    assert binary_columns["source_utc_offset_minutes"] == 60
    assert ote_columns["time_utc"] == binary_columns["time_utc"]
    assert ote_columns["source_utc_offset_minutes"] == 120


def test_prague_civil_time_uses_winter_offset():
    columns = build_time_columns(datetime(2026, 2, 1, 0, 15), "OTE")

    assert columns["time_utc"] == datetime(2026, 1, 31, 23, 15, tzinfo=timezone.utc)
    assert columns["source_utc_offset_minutes"] == 60
