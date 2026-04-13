import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.database import vodomery_db_vse


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

    def execute(self, *_args, **_kwargs):
        return _FakeScalarResult(self._valid_idents)


def test_prepare_rows_marks_extreme_delta_invalid_and_keeps_valid_baseline(monkeypatch):
    last_valid = SimpleNamespace(
        objem=100.0,
        date=datetime.datetime(2026, 4, 10, 10, 0, 0),
        seriove_cislo="S1",
    )

    monkeypatch.setattr(
        vodomery_db_vse,
        "get_last_measurements",
        lambda session, affected_idents, *, only_valid=False: {"A": last_valid},
    )
    monkeypatch.setattr(
        vodomery_db_vse,
        "get_recent_delta_stats",
        lambda session, affected_idents, *, reference_time=None: {
            "A": {
                "sample_size": 200,
                "median": 0.2,
                "p90": 0.5,
                "p99": 1.0,
                "std": 0.3,
            }
        },
    )

    rows = vodomery_db_vse.prepare_rows(
        session=None,
        new_rows=[
            {
                "recid": 1,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "objem": 120.0,
                "interval_minutes": 15,
                "reset_detected": False,
            },
            {
                "recid": 2,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 10, 30, 0),
                "objem": 100.6,
                "interval_minutes": 15,
                "reset_detected": False,
            },
        ],
        source_name="AREAL",
    )

    assert rows[0]["platne"] is False
    assert rows[0]["delta"] is None
    assert rows[1]["platne"] is True
    assert rows[1]["delta"] == pytest.approx(0.6)


def test_prepare_rows_skips_gap_fill_for_extreme_gap_delta(monkeypatch):
    last_valid = SimpleNamespace(
        objem=100.0,
        date=datetime.datetime(2026, 4, 10, 10, 0, 0),
        seriove_cislo="S1",
    )

    monkeypatch.setattr(
        vodomery_db_vse,
        "get_last_measurements",
        lambda session, affected_idents, *, only_valid=False: {"A": last_valid},
    )
    monkeypatch.setattr(
        vodomery_db_vse,
        "get_recent_delta_stats",
        lambda session, affected_idents, *, reference_time=None: {
            "A": {
                "sample_size": 200,
                "median": 0.1,
                "p90": 0.2,
                "p99": 0.5,
                "std": 0.1,
            }
        },
    )

    rows = vodomery_db_vse.prepare_rows(
        session=None,
        new_rows=[
            {
                "recid": 1,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 11, 0, 0),
                "objem": 160.0,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
        source_name="AREAL",
    )

    assert len(rows) == 1
    assert rows[0]["platne"] is False
    assert rows[0]["gap_detected"] is False
    assert rows[0]["synthetic"] is False
    assert rows[0]["delta"] is None


def test_prepare_rows_returns_outlier_review_payload_when_requested(monkeypatch):
    last_valid = SimpleNamespace(
        objem=100.0,
        date=datetime.datetime(2026, 4, 10, 10, 0, 0),
        seriove_cislo="S1",
    )

    monkeypatch.setattr(
        vodomery_db_vse,
        "get_last_measurements",
        lambda session, affected_idents, *, only_valid=False: {"A": last_valid},
    )
    monkeypatch.setattr(
        vodomery_db_vse,
        "get_recent_delta_stats",
        lambda session, affected_idents, *, reference_time=None: {
            "A": {
                "sample_size": 200,
                "median": 0.2,
                "p90": 0.5,
                "p99": 1.0,
                "std": 0.3,
            }
        },
    )

    rows, reviews = vodomery_db_vse.prepare_rows(
        session=None,
        new_rows=[
            {
                "recid": 1,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "objem": 120.0,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
        source_name="AREAL",
        include_outlier_reviews=True,
    )

    assert len(rows) == 1
    assert rows[0]["platne"] is False
    assert len(reviews) == 1
    assert reviews[0]["identifikace"] == "A"
    assert reviews[0]["detection_kind"] == "NORMAL_DELTA"
    assert reviews[0]["candidate_delta"] == pytest.approx(20.0)
    assert reviews[0]["baseline_objem"] == pytest.approx(100.0)
    assert reviews[0]["threshold_delta"] == pytest.approx(10.0)


def test_prepare_rows_respects_confirmed_consumption_override(monkeypatch):
    last_valid = SimpleNamespace(
        objem=100.0,
        date=datetime.datetime(2026, 4, 10, 10, 0, 0),
        seriove_cislo="S1",
    )

    monkeypatch.setattr(
        vodomery_db_vse,
        "get_last_measurements",
        lambda session, affected_idents, *, only_valid=False: {"A": last_valid},
    )
    monkeypatch.setattr(
        vodomery_db_vse,
        "get_recent_delta_stats",
        lambda session, affected_idents, *, reference_time=None: {
            "A": {
                "sample_size": 200,
                "median": 0.2,
                "p90": 0.5,
                "p99": 1.0,
                "std": 0.3,
            }
        },
    )

    rows, reviews = vodomery_db_vse.prepare_rows(
        session=None,
        new_rows=[
            {
                "recid": 1,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "objem": 120.0,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
        source_name="AREAL",
        include_outlier_reviews=True,
        review_overrides={
            ("A", datetime.datetime(2026, 4, 10, 10, 15, 0), "AREAL"): "CONFIRMED_CONSUMPTION"
        },
    )

    assert len(rows) == 1
    assert rows[0]["platne"] is True
    assert rows[0]["delta"] == pytest.approx(20.0)
    assert reviews == []


def test_filter_valid_rows_marks_only_first_row_after_reset(monkeypatch):
    last_valid = SimpleNamespace(
        objem=100.0,
        date=datetime.datetime(2026, 4, 10, 10, 0, 0),
        seriove_cislo="S1",
    )

    monkeypatch.setattr(
        vodomery_db_vse,
        "get_last_measurements",
        lambda session, affected_idents, *, only_valid=False: {"A": last_valid},
    )

    rows = vodomery_db_vse.filter_valid_rows(
        session=_FakeSession(["A"]),
        rows=[
            {
                "recid": 1,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "objem": 5.0,
                "interval_minutes": 15,
            },
            {
                "recid": 2,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 10, 30, 0),
                "objem": 5.4,
                "interval_minutes": 15,
            },
            {
                "recid": 3,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 10, 45, 0),
                "objem": 5.8,
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
            "identifikace": "A",
            "seriove_cislo": "S1",
            "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
            "objem": 120.0,
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
            "identifikace": "A",
            "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
            "zdroj": "AREAL",
            "source_recid": 1,
            "seriove_cislo": "S1",
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

    class _Session:
        def execute(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        vodomery_db_vse,
        "filter_valid_rows",
        lambda session, rows, source_name: rows,
    )
    monkeypatch.setattr(
        vodomery_db_vse,
        "prepare_rows",
        lambda session, new_rows, source_name, **kwargs: (prepared_rows, outlier_reviews),
    )

    def fake_load_review_ids(keys, *, session=None):
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            return {}
        return {keys[0]: 101}

    monkeypatch.setattr(
        vodomery_db_vse,
        "load_outlier_review_ids_by_keys",
        fake_load_review_ids,
    )
    monkeypatch.setattr(
        vodomery_db_vse,
        "upsert_outlier_review_candidates",
        lambda rows, *, session=None: captured_upsert_rows.extend(rows) or len(rows),
    )

    result = vodomery_db_vse.import_measurements(
        session=_Session(),
        source_name="AREAL",
        ms_rows=[
            {
                "recid": 1,
                "identifikace": "A",
                "seriove_cislo": "S1",
                "date": datetime.datetime(2026, 4, 10, 10, 15, 0),
                "objem": 120.0,
                "interval_minutes": 15,
                "reset_detected": False,
            }
        ],
    )

    assert result["rows"] == prepared_rows
    assert result["new_outlier_review_ids"] == [101]
    assert captured_upsert_rows == outlier_reviews
