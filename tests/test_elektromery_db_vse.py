from __future__ import annotations

from datetime import datetime

from moduly.mereni.elektromery.database import elektromery_db_vse
from moduly.mereni.elektromery.database.models import Mereni_elektromery


def test_elektromery_vse_model_uses_monitoring_schema_and_nullable_objem():
    assert Mereni_elektromery.__tablename__ == "Mereni_elektromery_vse"
    assert Mereni_elektromery.__table__.schema == "monitoring"
    assert Mereni_elektromery.__table__.c.objem.nullable is True
    assert Mereni_elektromery.__table__.c.delta.nullable is True
    assert Mereni_elektromery.__table__.c.zdroj.nullable is False


def test_prepare_delta_rows_stores_ote_consumption_as_delta(monkeypatch):
    monkeypatch.setattr(elektromery_db_vse, "get_last_measurements", lambda *args, **kwargs: {})

    rows = [
        {
            "recid": 10,
            "identifikace": "TS2",
            "seriove_cislo": 859182400409180513,
            "date": datetime(2026, 2, 1, 0, 15),
            "objem": None,
            "delta": 1.2345678,
            "interval_minutes": 15,
            "platne": True,
            "delta_source": True,
        }
    ]

    prepared = elektromery_db_vse.prepare_delta_rows(object(), rows, "OTE")

    assert prepared == [
        {
            "source_recid": 10,
            "identifikace": "TS2",
            "seriove_cislo": 859182400409180513,
            "date": datetime(2026, 2, 1, 0, 15),
            "objem": None,
            "delta": 1.234568,
            "interval_minutes": 15,
            "day_of_week": 6,
            "slot": 1,
            "nocni_odber": True,
            "platne": True,
            "gap_detected": False,
            "synthetic": False,
            "zdroj": "OTE",
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
