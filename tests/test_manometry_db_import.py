import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.manometry.database import manometry_db_vse
from moduly.mereni.manometry.database.models import Mereni_manometry_vse
from moduly.mereni.time_semantics import (
    SOURCE_TIMEZONE_EUROPE_PRAGUE,
    TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    TIMESTAMP_POSITION_INSTANT,
    get_default_time_semantics,
)


def test_manometry_default_time_semantics_is_prague_civil_instant():
    semantics = get_default_time_semantics("MANOMETRY")

    assert semantics.time_basis == TIME_BASIS_EUROPE_PRAGUE_CIVIL
    assert semantics.source_timezone == SOURCE_TIMEZONE_EUROPE_PRAGUE
    assert semantics.timestamp_position == TIMESTAMP_POSITION_INSTANT


def test_manometry_vse_model_has_time_semantics_columns_without_consumption_columns():
    assert Mereni_manometry_vse.__tablename__ == "Mereni_manometry_vse"
    assert Mereni_manometry_vse.__table__.schema == "monitoring"
    assert {
        "source_date",
        "time_utc",
        "time_basis",
        "source_timezone",
        "source_utc_offset_minutes",
        "time_fold",
        "timestamp_position",
        "hodnota",
        "platne",
    }.issubset(Mereni_manometry_vse.__table__.c.keys())
    assert "delta" not in Mereni_manometry_vse.__table__.c.keys()
    assert "synthetic" not in Mereni_manometry_vse.__table__.c.keys()
    assert "gap_detected" not in Mereni_manometry_vse.__table__.c.keys()


def test_prepare_rows_keeps_pressure_value_and_adds_time_semantics():
    rows = manometry_db_vse.prepare_rows(
        [
            {
                "recid": 1,
                "identifikace": "M1",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 5, 14, 11, 17),
                "hodnota": 250.5,
                "platne": True,
            }
        ],
        source_name="AREAL",
    )

    assert len(rows) == 1
    assert rows[0]["source_recid"] == 1
    assert rows[0]["identifikace"] == "M1"
    assert rows[0]["hodnota"] == 250.5
    assert rows[0]["platne"] is True
    assert rows[0]["zdroj"] == "AREAL"
    assert rows[0]["source_date"] == datetime.datetime(2026, 5, 14, 11, 17)
    assert rows[0]["time_utc"] == datetime.datetime(2026, 5, 14, 9, 17, tzinfo=datetime.timezone.utc)
    assert rows[0]["time_basis"] == TIME_BASIS_EUROPE_PRAGUE_CIVIL
    assert rows[0]["source_timezone"] == SOURCE_TIMEZONE_EUROPE_PRAGUE
    assert rows[0]["source_utc_offset_minutes"] == 120
    assert rows[0]["timestamp_position"] == TIMESTAMP_POSITION_INSTANT


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


def test_filter_valid_rows_sanitizes_pressure_rows_and_drops_unknown_devices(monkeypatch):
    monkeypatch.setattr(
        manometry_db_vse,
        "Session",
        lambda *_args, **_kwargs: _FakeSession(["M1"]),
    )

    rows = manometry_db_vse.filter_valid_rows(
        [
            {
                "recid": 1,
                "identifikace": " M1 ",
                "seriove_cislo": 123,
                "date": datetime.datetime(2026, 5, 14, 11, 17),
                "hodnota": "250.5",
                "platne": None,
            },
            {
                "recid": 2,
                "identifikace": "UNKNOWN",
                "seriove_cislo": "S2",
                "date": datetime.datetime(2026, 5, 14, 11, 18),
                "hodnota": 251.0,
                "platne": True,
            },
        ],
        source_name="AREAL",
    )

    assert len(rows) == 1
    assert rows[0]["identifikace"] == "M1"
    assert rows[0]["seriove_cislo"] == "123"
    assert rows[0]["hodnota"] == 250.5
    assert rows[0]["platne"] is True
