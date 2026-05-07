import datetime
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.smartfuelpass import sync


def _sample_sync_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Veřejné ID": (
                    "95b9e46b-6b47-402e Domácí nabíjení Dokončeno 0 kW 35,498 kWh 79 % null "
                    "AdHoc nabíjení - Web (Google pay) ARMEX HOLDING 15Kč + 20,00 % "
                    "(ARMEX HOLDING 15Kč) 0,00 Kč (532,47 Kč)"
                ),
                "Nákup": "80ed662a-a75f-4feb",
                "Suma": "532,47 Kč",
                "Čas spuštění": "01.05.2026 16:43 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "01.05.2026 17:05 Ukončeno nabíječkou",
                "Hodnoty měřidel": "01.05.2026 17:05",
                "Název EV lokace": "Armex - Budova E null",
            },
            {
                "Veřejné ID": (
                    "cb959684-8892-439e Domácí nabíjení Dokončeno 0 kW 15,955 kWh 86 % "
                    "null null ARMEX HOLDING 15Kč 229,35 Kč (239,32 Kč)"
                ),
                "Nákup": "d04c027c-5164-45aa",
                "Suma": "217,78 Kč",
                "Čas spuštění": "29.04.2026 12:17 Vzdálené zahájení přes mobilní aplikaci",
                "Čas ukončení": "29.04.2026 12:32 Ukončeno z důvodu dosažení limitu",
                "Hodnoty měřidel": "29.04.2026 12:32",
                "Název EV lokace": "Armex - Budova E null",
            },
            {
                "Veřejné ID": (
                    "9cc09caa-df76-4a87 Domácí nabíjení Zrušeno 0 kW 0 kWh null null "
                    "AdHoc nabíjení ARMEX HOLDING 15Kč ()"
                ),
                "Nákup": "-",
                "Suma": "-",
                "Čas spuštění": "27.04.2026 15:14 Vzdálené zahájení přes backend systém",
                "Čas ukončení": "- Zrušeno systémem",
                "Hodnoty měřidel": "-",
                "Název EV lokace": "Armex - Budova E null",
            },
        ]
    )


def test_build_charge_sessions_sync_rows_extracts_requested_fields():
    rows, stats = sync.build_charge_sessions_sync_rows(_sample_sync_dataframe())

    assert stats == {
        "raw_row_count": 3,
        "prepared_row_count": 2,
        "completed_row_count": 2,
        "invalid_row_count": 0,
        "skipped_missing_id_count": 0,
    }
    assert len(rows) == 2

    rows_by_id = {row["id_relace"]: row for row in rows}

    assert rows_by_id["80ed662a-a75f-4feb"] == {
        "id_relace": "80ed662a-a75f-4feb",
        "kwh": 35.498,
        "tarif": "ARMEX HOLDING 15Kč + 20,00%",
        "battery_status": 79,
        "suma": 532.47,
        "started_at": datetime.datetime(2026, 5, 1, 16, 43),
        "ended_at": datetime.datetime(2026, 5, 1, 17, 5),
        "lokace": "Armex - Budova E",
        "rychlost_nabijeni": 96.813,
    }
    assert rows_by_id["d04c027c-5164-45aa"] == {
        "id_relace": "d04c027c-5164-45aa",
        "kwh": 15.955,
        "tarif": "ARMEX HOLDING 15Kč",
        "battery_status": 86,
        "suma": 217.78,
        "started_at": datetime.datetime(2026, 4, 29, 12, 17),
        "ended_at": datetime.datetime(2026, 4, 29, 12, 32),
        "lokace": "Armex - Budova E",
        "rychlost_nabijeni": 63.82,
    }


def test_upsert_charge_sessions_sync_rows_executes_single_statement_and_commits():
    class FakeResult:
        def __init__(self, rowcount):
            self.rowcount = rowcount

    class FakeSession:
        def __init__(self):
            self.statements = []
            self.commit_calls = 0

        def execute(self, stmt):
            self.statements.append(stmt)
            return FakeResult(1)

        def commit(self):
            self.commit_calls += 1

    fake_session = FakeSession()
    rows = [
        {
            "id_relace": "80ed662a-a75f-4feb",
            "kwh": 35.498,
            "tarif": "ARMEX HOLDING 15Kč + 20,00%",
            "battery_status": 79,
            "suma": 532.47,
            "started_at": datetime.datetime(2026, 5, 1, 16, 43),
            "ended_at": datetime.datetime(2026, 5, 1, 17, 5),
            "lokace": "Armex - Budova E",
            "rychlost_nabijeni": 96.813,
        }
    ]

    result = sync.upsert_charge_sessions_sync_rows(fake_session, rows)

    assert result == 1
    assert fake_session.commit_calls == 1
    assert len(fake_session.statements) == 1
    assert fake_session.statements[0].table.name == "smartfuelpass_relace"
    assert fake_session.statements[0].table.schema == "monitoring"
    assert "DO NOTHING" in str(fake_session.statements[0])


def test_sync_charge_sessions_to_db_fetches_rows_through_retry_helper_and_closes_owned_session(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    fake_session = FakeSession()
    captured = {}

    monkeypatch.setattr(sync, "ensure_smartfuelpass_tables", lambda: captured.update({"ensure_called": True}))
    monkeypatch.setattr(sync, "get_session_pg", lambda: fake_session)
    monkeypatch.setattr(
        sync,
        "fetch_charge_sessions_dataframe_with_retries",
        lambda **kwargs: captured.update({"fetch_kwargs": kwargs}) or _sample_sync_dataframe(),
    )
    monkeypatch.setattr(
        sync,
        "upsert_charge_sessions_sync_rows",
        lambda db_session, rows: captured.update({"rows": rows, "db_session": db_session}) or len(rows),
    )

    result = sync.sync_charge_sessions_to_db(headless=True, timeout_seconds=17)

    assert captured["ensure_called"] is True
    assert captured["db_session"] is fake_session
    assert captured["fetch_kwargs"] == {
        "cookie_path": None,
        "headless": True,
        "timeout_seconds": 17,
    }
    assert len(captured["rows"]) == 2
    assert result["upserted_count"] == 2
    assert result["raw_row_count"] == 3
    assert fake_session.closed is True
