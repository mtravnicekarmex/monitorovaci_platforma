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


def test_prepare_rows_marks_extreme_delta_invalid_and_returns_review(monkeypatch):
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
    monkeypatch.setattr(
        kalorimetry_db_vse,
        "get_recent_delta_stats",
        lambda session, affected_idents, *, reference_time=None: {
            "K1": {
                "sample_size": 200,
                "median": 0.2,
                "p90": 0.5,
                "p99": 1.0,
                "std": 0.3,
            }
        },
    )

    rows, reviews = kalorimetry_db_vse.prepare_rows(
        session=None,
        new_rows=[
            {
                "recid": 1,
                "identifikace": "K1",
                "seriove_cislo": 1,
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "spotreba_energie": 120.0,
                "objem": 12.0,
                "platne": True,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
        source_name="AREAL",
        include_outlier_reviews=True,
    )

    assert len(rows) == 1
    assert rows[0]["platne"] is False
    assert rows[0]["delta"] is None
    assert len(reviews) == 1
    assert reviews[0]["identifikace"] == "K1"
    assert reviews[0]["detection_kind"] == "NORMAL_DELTA"
    assert reviews[0]["current_objem"] == pytest.approx(120.0)
    assert reviews[0]["baseline_objem"] == pytest.approx(100.0)
    assert reviews[0]["candidate_delta"] == pytest.approx(20.0)
    assert reviews[0]["threshold_delta"] == pytest.approx(10.0)


def test_prepare_rows_respects_confirmed_consumption_override(monkeypatch):
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
    monkeypatch.setattr(
        kalorimetry_db_vse,
        "get_recent_delta_stats",
        lambda session, affected_idents, *, reference_time=None: {
            "K1": {
                "sample_size": 200,
                "median": 0.2,
                "p90": 0.5,
                "p99": 1.0,
                "std": 0.3,
            }
        },
    )

    rows, reviews = kalorimetry_db_vse.prepare_rows(
        session=None,
        new_rows=[
            {
                "recid": 1,
                "identifikace": "K1",
                "seriove_cislo": 1,
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "spotreba_energie": 120.0,
                "objem": 12.0,
                "platne": True,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
        source_name="AREAL",
        include_outlier_reviews=True,
        review_overrides={
            ("K1", datetime.datetime(2026, 4, 10, 10, 15, 0), "AREAL"): "CONFIRMED_CONSUMPTION"
        },
    )

    assert len(rows) == 1
    assert rows[0]["platne"] is True
    assert rows[0]["delta"] == pytest.approx(20.0)
    assert reviews == []


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


def test_import_measurements_returns_new_outlier_review_ids(monkeypatch):
    prepared_rows = [
        {
            "source_recid": 1,
            "identifikace": "K1",
            "seriove_cislo": 1,
            "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
            "spotreba_energie": 120.0,
            "objem": 12.0,
            "delta": None,
            "interval_minutes": 15,
            "day_of_week": 4,
            "slot": 41,
            "nocni_odber": False,
            "platne": False,
            "gap_detected": False,
            "synthetic": False,
            "zdroj": "AREAL",
            "reset_detected": False,
        }
    ]
    outlier_reviews = [
        {
            "identifikace": "K1",
            "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
            "zdroj": "AREAL",
            "source_recid": 1,
            "seriove_cislo": "1",
            "interval_minutes": 15,
            "detection_kind": "NORMAL_DELTA",
            "current_objem": 120.0,
            "baseline_objem": 100.0,
            "baseline_date": datetime.datetime(2026, 4, 10, 10, 0, 0),
            "candidate_delta": 20.0,
            "threshold_delta": 10.0,
            "sample_size": 200,
            "median_delta": 0.2,
            "p90_delta": 0.5,
            "p99_delta": 1.0,
            "std_delta": 0.3,
        }
    ]
    call_counter = {"count": 0}
    captured_upsert_rows = []
    captured_state_rows = []

    class _Session:
        def execute(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        kalorimetry_db_vse,
        "filter_valid_rows",
        lambda session, rows, source_name: rows,
    )
    monkeypatch.setattr(
        kalorimetry_db_vse,
        "prepare_rows",
        lambda session, new_rows, source_name, **kwargs: (prepared_rows, outlier_reviews),
    )
    monkeypatch.setattr(
        kalorimetry_db_vse,
        "update_import_state",
        lambda session, source_name, ms_rows: captured_state_rows.extend(ms_rows),
    )

    def fake_load_review_ids(keys, *, session=None):
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            return {}
        return {keys[0]: 101}

    monkeypatch.setattr(
        kalorimetry_db_vse,
        "load_outlier_review_ids_by_keys",
        fake_load_review_ids,
    )
    monkeypatch.setattr(
        kalorimetry_db_vse,
        "upsert_outlier_review_candidates",
        lambda rows, *, session=None: captured_upsert_rows.extend(rows) or len(rows),
    )

    result = kalorimetry_db_vse.import_measurements(
        session=_Session(),
        source_name="AREAL",
        ms_rows=[
            {
                "recid": 1,
                "identifikace": "K1",
                "seriove_cislo": 1,
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "spotreba_energie": 120.0,
                "objem": 12.0,
                "platne": True,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
    )

    assert result["rows"] == prepared_rows
    assert result["new_outlier_review_ids"] == [101]
    assert captured_upsert_rows == outlier_reviews
    assert len(captured_state_rows) == 1
