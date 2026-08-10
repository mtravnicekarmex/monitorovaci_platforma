from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pandas as pd

from moduly.apps.dashboard import api_client
from moduly.apps.smartfuelpass import excel_import
from moduly.mereni.time_semantics import (
    SOURCE_TIMEZONE_EUROPE_PRAGUE,
    TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    TIMESTAMP_POSITION_INTERVAL,
)


def _xlsx_bytes(rows: list[dict[str, object]]) -> bytes:
    dataframe = pd.DataFrame(rows)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        dataframe.to_excel(
            writer,
            sheet_name="ChargingSessions",
            startrow=18,
            index=False,
        )
    return buffer.getvalue()


def _completed_row(
    *,
    purchase_id: str,
    start: str = "21.07.2026 12:00:30",
    end: str = "21.07.2026 13:00:30",
    energy: str = "12,345 kWh",
    amount: str = "185,18 Kč",
    connector_id: str = "CZ*ARM*E1",
    tariff: str = "ARMEX HOLDING 15Kč",
) -> dict[str, object]:
    return {
        "Veřejné ID": "public-id",
        "ID v externím CPO systému": "external-id",
        "Stav": "Dokončeno",
        "Energie": energy,
        "Nákup": purchase_id,
        "Čas spuštění": start,
        "Čas ukončení": end,
        "Název EV lokace": "Armex - Budova E - Děčín, dlouhá adresa",
        "Konektor EVSE ID": connector_id,
        "Název tarifu": tariff,
        "Suma": amount,
    }


def test_parse_smartfuelpass_excel_rows_maps_xlsx_to_db_shape():
    content = _xlsx_bytes(
        [
            _completed_row(purchase_id="new-session"),
            {
                **_completed_row(purchase_id="-"),
                "Stav": "Zrušeno",
                "Energie": "-",
                "Suma": "-",
            },
        ]
    )

    rows = excel_import.parse_smartfuelpass_excel_rows(content)

    assert len(rows) == 2
    completed = rows[0]
    assert completed.source_row_number == 20
    assert completed.id_relace == "new-session"
    assert completed.lokace == "Armex - Budova E"
    assert completed.validation_errors == ()
    assert completed.db_row == {
        "id_relace": "new-session",
        "kwh": 12.345,
        "tarif": "ARMEX HOLDING 15Kč",
        "battery_status": None,
        "suma": 185.18,
        "connector_id": "CZ*ARM*E1",
        "started_at": datetime(2026, 7, 21, 12, 0, 30),
        "ended_at": datetime(2026, 7, 21, 13, 0, 30),
        "source_started_at": datetime(2026, 7, 21, 12, 0, 30),
        "source_ended_at": datetime(2026, 7, 21, 13, 0, 30),
        "started_at_utc": datetime.fromisoformat("2026-07-21T10:00:30+00:00"),
        "ended_at_utc": datetime.fromisoformat("2026-07-21T11:00:30+00:00"),
        "time_basis": TIME_BASIS_EUROPE_PRAGUE_CIVIL,
        "source_timezone": SOURCE_TIMEZONE_EUROPE_PRAGUE,
        "started_utc_offset_minutes": 120,
        "ended_utc_offset_minutes": 120,
        "started_time_fold": None,
        "ended_time_fold": None,
        "timestamp_position": TIMESTAMP_POSITION_INTERVAL,
        "lokace": "Armex - Budova E",
        "rychlost_nabijeni": 12.345,
    }

    cancelled = rows[1]
    assert cancelled.db_row is None
    assert cancelled.validation_errors == ("Stav není Dokončeno.",)


def test_build_smartfuelpass_excel_preview_marks_new_existing_and_ignored_rows():
    content = _xlsx_bytes(
        [
            _completed_row(purchase_id="new-session"),
            _completed_row(
                purchase_id="existing-session",
                start="21.07.2026 11:00:00",
                end="21.07.2026 11:30:00",
                energy="10,000",
                amount="150,00",
                connector_id="CZ*ARM*E2",
            ),
            {
                **_completed_row(purchase_id="-"),
                "Stav": "Zrušeno",
                "Energie": "-",
                "Suma": "-",
            },
        ]
    )

    existing_row = SimpleNamespace(
        id_relace="existing-session",
        kwh=Decimal("10.000"),
        suma=Decimal("150.00"),
        rychlost_nabijeni=Decimal("20.000"),
        started_at=datetime(2026, 7, 21, 11, 0),
        ended_at=datetime(2026, 7, 21, 11, 30),
        lokace="Armex - Budova E",
        connector_id="OLD-CONNECTOR",
        tarif="ARMEX HOLDING 15Kč",
    )

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        @staticmethod
        def all():
            return [existing_row]

    class FakeSession:
        @staticmethod
        def query(*args, **kwargs):
            return FakeQuery()

        @staticmethod
        def close():
            raise AssertionError("external test session must not be closed")

    preview = excel_import.build_smartfuelpass_excel_preview(
        content=content,
        filename="ChargingSessions.xlsx",
        db_session=FakeSession(),
    )

    assert preview["filename"] == "ChargingSessions.xlsx"
    assert preview["raw_row_count"] == 3
    assert preview["completed_row_count"] == 2
    assert preview["new_row_count"] == 1
    assert preview["existing_row_count"] == 1
    assert preview["existing_with_differences_count"] == 1
    assert preview["ignored_row_count"] == 1
    assert preview["importable_row_count"] == 1

    rows_by_id = {row["id_relace"]: row for row in preview["rows"]}
    assert rows_by_id["new-session"]["row_status"] == "new"
    assert rows_by_id["new-session"]["can_import"] is True
    assert rows_by_id["existing-session"]["row_status"] == "existing_with_differences"
    assert rows_by_id["existing-session"]["can_import"] is False
    assert rows_by_id["existing-session"]["difference_fields"] == ("connector_id",)


def test_insert_new_smartfuelpass_excel_rows_uses_insert_only_conflict_handling():
    class FakeResult:
        rowcount = 1

    class FakeSession:
        def __init__(self):
            self.statements = []

        def execute(self, stmt):
            self.statements.append(stmt)
            return FakeResult()

    fake_session = FakeSession()

    inserted = excel_import.insert_new_smartfuelpass_excel_rows(
        fake_session,
        [{"id_relace": "new-session", "suma": 1.0, "started_at": datetime.now(), "ended_at": datetime.now()}],
    )

    assert inserted == 1
    assert len(fake_session.statements) == 1
    assert fake_session.statements[0].table.name == "smartfuelpass_relace"
    assert "DO NOTHING" in str(fake_session.statements[0])


def test_dashboard_api_client_uses_smartfuelpass_excel_import_endpoints(monkeypatch):
    calls = []

    class FakeResponse:
        @staticmethod
        def json():
            return {"rows": []}

    monkeypatch.setattr(
        api_client,
        "_request",
        lambda method, path, **kwargs: calls.append((method, path, kwargs))
        or FakeResponse(),
    )

    api_client.preview_smartfuelpass_excel_import(
        "token",
        filename="ChargingSessions (3).xlsx",
        content=b"xlsx",
    )
    api_client.import_smartfuelpass_excel_records(
        "token",
        filename="ChargingSessions (3).xlsx",
        content=b"xlsx",
    )

    assert calls == [
        (
            "POST",
            "/api/v1/admin/smartfuelpass/excel-import/preview",
            {
                "access_token": "token",
                "raw_payload": b"xlsx",
                "extra_headers": {
                    "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "X-Filename": "ChargingSessions (3).xlsx",
                },
            },
        ),
        (
            "POST",
            "/api/v1/admin/smartfuelpass/excel-import/import",
            {
                "access_token": "token",
                "raw_payload": b"xlsx",
                "extra_headers": {
                    "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "X-Filename": "ChargingSessions (3).xlsx",
                },
            },
        ),
    ]
