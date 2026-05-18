import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.kalorimetry.database import kalorimetry_db_vse
from moduly.mereni.kalorimetry.database.models import Mereni_kalorimetry
from moduly.mereni.time_semantics import (
    SOURCE_TIMEZONE_EUROPE_PRAGUE,
    TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    TIMESTAMP_POSITION_INSTANT,
)


def test_kalorimetry_vse_model_has_time_semantics_columns():
    assert Mereni_kalorimetry.__tablename__ == "Mereni_kalorimetry_vse"
    assert Mereni_kalorimetry.__table__.schema == "monitoring"
    assert {
        "source_date",
        "time_utc",
        "time_basis",
        "source_timezone",
        "spotreba_energie",
        "delta",
        "gap_detected",
        "synthetic",
    }.issubset(Mereni_kalorimetry.__table__.c.keys())


def test_prepare_rows_distributes_gap_delta_without_losing_terminal_delta(monkeypatch):
    last_valid = SimpleNamespace(
        spotreba_energie=100.0,
        objem=10.0,
        date=datetime.datetime(2026, 4, 10, 10, 0, 0),
        seriove_cislo=1,
    )

    monkeypatch.setattr(
        kalorimetry_db_vse,
        "get_last_measurements",
        lambda session, affected_idents, *, only_valid=False: {"K1": last_valid},
    )

    rows = kalorimetry_db_vse.prepare_rows(
        session=None,
        new_rows=[
            {
                "recid": 1,
                "identifikace": "K1",
                "seriove_cislo": 1,
                "date": datetime.datetime(2026, 4, 10, 11, 0, 0),
                "spotreba_energie": 104.0,
                "objem": 14.0,
                "platne": True,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
        source_name="AREAL",
    )

    assert [row["date"] for row in rows] == [
        datetime.datetime(2026, 4, 10, 10, 15, 0),
        datetime.datetime(2026, 4, 10, 10, 30, 0),
        datetime.datetime(2026, 4, 10, 10, 45, 0),
        datetime.datetime(2026, 4, 10, 11, 0, 0),
    ]
    assert [row["synthetic"] for row in rows] == [True, True, True, False]
    assert [row["spotreba_energie"] for row in rows] == [101.0, 102.0, 103.0, 104.0]
    assert [row["delta"] for row in rows] == [1.0, 1.0, 1.0, 1.0]
    assert rows[-1]["gap_detected"] is True
    assert sum(row["delta"] for row in rows if row["delta"] is not None) == pytest.approx(4.0)
    assert rows[-1]["time_basis"] == TIME_BASIS_EUROPE_PRAGUE_CIVIL
    assert rows[-1]["source_timezone"] == SOURCE_TIMEZONE_EUROPE_PRAGUE
    assert rows[-1]["source_utc_offset_minutes"] == 120
    assert rows[-1]["timestamp_position"] == TIMESTAMP_POSITION_INSTANT


def test_prepare_rows_uses_terminal_residual_when_existing_rows_block_synthetic(monkeypatch):
    last_valid = SimpleNamespace(
        spotreba_energie=100.0,
        objem=10.0,
        date=datetime.datetime(2026, 4, 10, 10, 0, 0),
        seriove_cislo=1,
    )
    occupied_dates = {
        datetime.datetime(2026, 4, 10, 10, 15, 0),
        datetime.datetime(2026, 4, 10, 10, 30, 0),
        datetime.datetime(2026, 4, 10, 10, 45, 0),
    }

    monkeypatch.setattr(
        kalorimetry_db_vse,
        "get_last_measurements",
        lambda session, affected_idents, *, only_valid=False: {"K1": last_valid},
    )
    monkeypatch.setattr(
        kalorimetry_db_vse,
        "get_existing_measurement_dates",
        lambda session, affected_idents, source_name, *, min_date, max_date: {"K1": occupied_dates},
    )

    rows = kalorimetry_db_vse.prepare_rows(
        session=object(),
        new_rows=[
            {
                "recid": 1,
                "identifikace": "K1",
                "seriove_cislo": 1,
                "date": datetime.datetime(2026, 4, 10, 11, 0, 0),
                "spotreba_energie": 104.0,
                "objem": 14.0,
                "platne": True,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
        source_name="AREAL",
    )

    assert len(rows) == 1
    assert rows[0]["synthetic"] is False
    assert rows[0]["gap_detected"] is True
    assert rows[0]["delta"] == pytest.approx(4.0)


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeSession:
    def __init__(self, valid_idents):
        self._valid_idents = valid_idents

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        return _FakeScalarResult(self._valid_idents)


def test_filter_valid_rows_marks_only_first_row_after_reset(monkeypatch):
    last_valid = SimpleNamespace(
        spotreba_energie=100.0,
        date=datetime.datetime(2026, 4, 10, 10, 0, 0),
        seriove_cislo=1,
    )

    monkeypatch.setattr(
        kalorimetry_db_vse,
        "get_last_measurements",
        lambda session, affected_idents, *, only_valid=False: {"K1": last_valid},
    )
    monkeypatch.setattr(
        kalorimetry_db_vse,
        "Session",
        lambda *_args, **_kwargs: _FakeSession(["K1"]),
    )

    rows = kalorimetry_db_vse.filter_valid_rows(
        session=_FakeSession(["K1"]),
        rows=[
            {
                "recid": 1,
                "identifikace": "K1",
                "seriove_cislo": 1,
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "spotreba_energie": 5.0,
                "objem": 1.0,
                "interval_minutes": 15,
            },
            {
                "recid": 2,
                "identifikace": "K1",
                "seriove_cislo": 1,
                "date": datetime.datetime(2026, 4, 10, 10, 30, 0),
                "spotreba_energie": 5.4,
                "objem": 1.4,
                "interval_minutes": 15,
            },
            {
                "recid": 3,
                "identifikace": "K1",
                "seriove_cislo": 1,
                "date": datetime.datetime(2026, 4, 10, 10, 45, 0),
                "spotreba_energie": 5.8,
                "objem": 1.8,
                "interval_minutes": 15,
            },
        ],
        source_name="AREAL",
    )

    assert [row["reset_detected"] for row in rows] == [True, False, False]
