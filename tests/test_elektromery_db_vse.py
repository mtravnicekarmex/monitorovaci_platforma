from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from moduly.mereni.elektromery.database import elektromery_db_vse
from moduly.mereni.elektromery.database.models import Mereni_elektromery
from moduly.mereni.elektromery.database.time_semantics import (
    SOURCE_TIMEZONE_FIXED_CET,
    SOURCE_TIMEZONE_EUROPE_PRAGUE,
    TIME_BASIS_FIXED_OFFSET,
    TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    TIMESTAMP_POSITION_START,
)


def _prague_time_columns(source_date: datetime, *, offset_minutes: int = 60):
    return {
        "source_date": source_date,
        "time_utc": (source_date - timedelta(minutes=offset_minutes)).replace(tzinfo=timezone.utc),
        "time_basis": TIME_BASIS_EUROPE_PRAGUE_CIVIL,
        "source_timezone": SOURCE_TIMEZONE_EUROPE_PRAGUE,
        "source_utc_offset_minutes": offset_minutes,
        "time_fold": None,
        "timestamp_position": TIMESTAMP_POSITION_START,
    }


def _binary_time_columns(source_date: datetime):
    return {
        "source_date": source_date,
        "time_utc": (source_date - timedelta(minutes=60)).replace(tzinfo=timezone.utc),
        "time_basis": TIME_BASIS_FIXED_OFFSET,
        "source_timezone": SOURCE_TIMEZONE_FIXED_CET,
        "source_utc_offset_minutes": 60,
        "time_fold": None,
        "timestamp_position": TIMESTAMP_POSITION_START,
    }


def test_elektromery_vse_model_uses_monitoring_schema_and_nullable_objem():
    assert Mereni_elektromery.__tablename__ == "Mereni_elektromery_vse"
    assert Mereni_elektromery.__table__.schema == "monitoring"
    assert Mereni_elektromery.__table__.c.objem.nullable is True
    assert Mereni_elektromery.__table__.c.delta.nullable is True
    assert Mereni_elektromery.__table__.c.zdroj.nullable is False
    assert {"source_date", "time_utc", "time_basis", "source_timezone"}.issubset(
        Mereni_elektromery.__table__.c.keys()
    )


def test_prepare_delta_rows_stores_binary_consumption_as_delta(monkeypatch):
    monkeypatch.setattr(elektromery_db_vse, "get_last_measurements", lambda *args, **kwargs: {})

    rows = [
        {
            "recid": 10,
            "identifikace": "TS2",
            "seriove_cislo": 859182400409180513,
            "date": datetime(2026, 2, 1, 0, 15),
            **_binary_time_columns(datetime(2026, 2, 1, 0, 15)),
            "objem": None,
            "delta": 1.2345678,
            "interval_minutes": 15,
            "platne": True,
            "delta_source": True,
        }
    ]

    prepared = elektromery_db_vse.prepare_delta_rows(object(), rows, "BINARY_TEST")

    assert prepared == [
        {
            "source_recid": 10,
            "identifikace": "TS2",
            "seriove_cislo": 859182400409180513,
            "date": datetime(2026, 2, 1, 0, 15),
            **_binary_time_columns(datetime(2026, 2, 1, 0, 15)),
            "objem": None,
            "delta": 1.234568,
            "interval_minutes": 15,
            "day_of_week": 6,
            "slot": 1,
            "nocni_odber": True,
            "platne": True,
            "gap_detected": False,
            "synthetic": False,
            "zdroj": "BINARY_TEST",
            "reset_detected": False,
        }
    ]


def test_prepare_state_rows_computes_softlink_delta_from_meter_state(monkeypatch):
    monkeypatch.setattr(elektromery_db_vse, "get_last_measurements", lambda *args, **kwargs: {})

    rows = [
        {
            "recid": 1,
            "identifikace": "B-1.1",
            "seriove_cislo": 25722370615,
            "date": datetime(2026, 4, 29, 0, 15),
            "objem": 100.0,
            "interval_minutes": 1440,
            "platne": True,
        },
        {
            "recid": 2,
            "identifikace": "B-1.1",
            "seriove_cislo": 25722370615,
            "date": datetime(2026, 4, 30, 0, 15),
            "objem": 125.5,
            "interval_minutes": 1440,
            "platne": True,
        },
    ]

    prepared = elektromery_db_vse.prepare_state_rows(object(), rows, "SOFTLINK")

    assert [row["objem"] for row in prepared] == [100.0, 125.5]
    assert [row["delta"] for row in prepared] == [None, 25.5]
    assert all(row["zdroj"] == "SOFTLINK" for row in prepared)


def test_prepare_state_rows_distributes_gap_delta_without_double_count(monkeypatch):
    monkeypatch.setattr(
        elektromery_db_vse,
        "get_last_measurements",
        lambda *args, **kwargs: {
            "TS2": SimpleNamespace(
                objem=100.0,
                date=datetime(2026, 2, 1, 10, 0),
                seriove_cislo=859182400409180513,
            )
        },
    )

    rows = [
        {
            "recid": 10,
            "identifikace": "TS2",
            "seriove_cislo": 859182400409180513,
            "date": datetime(2026, 2, 1, 11, 0),
            "objem": 104.0,
            "interval_minutes": 15,
            "platne": True,
        }
    ]

    prepared = elektromery_db_vse.prepare_state_rows(object(), rows, "SOFTLINK")

    assert [row["date"] for row in prepared] == [
        datetime(2026, 2, 1, 10, 15),
        datetime(2026, 2, 1, 10, 30),
        datetime(2026, 2, 1, 10, 45),
        datetime(2026, 2, 1, 11, 0),
    ]
    assert [row["synthetic"] for row in prepared] == [True, True, True, False]
    assert [row["delta"] for row in prepared] == [1.0, 1.0, 1.0, 1.0]
    assert prepared[-1]["gap_detected"] is True
    assert sum(row["delta"] for row in prepared if row["delta"] is not None) == pytest.approx(4.0)


def test_filter_valid_rows_ignores_small_drop_even_when_serial_changes(monkeypatch):
    monkeypatch.setattr(
        elektromery_db_vse,
        "get_last_measurements",
        lambda *args, **kwargs: {
            "TS2": SimpleNamespace(
                objem=28.420,
                date=datetime(2026, 2, 1, 10, 0),
                seriove_cislo=1,
            )
        },
    )

    rows = elektromery_db_vse.filter_valid_rows(
        object(),
        [
            {
                "recid": 10,
                "identifikace": "TS2",
                "seriove_cislo": 2,
                "date": datetime(2026, 2, 1, 10, 15),
                "objem": 28.419,
                "interval_minutes": 15,
                "platne": True,
            },
            {
                "recid": 11,
                "identifikace": "TS2",
                "seriove_cislo": 2,
                "date": datetime(2026, 2, 1, 10, 30),
                "objem": 28.500,
                "interval_minutes": 15,
                "platne": True,
            },
        ],
        "SOFTLINK",
    )

    assert [row["reset_detected"] for row in rows] == [False, False]
