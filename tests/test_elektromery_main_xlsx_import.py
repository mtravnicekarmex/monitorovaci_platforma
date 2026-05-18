import datetime
import io
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.elektromery.database import hlavni_xlsx_import
from moduly.mereni.elektromery.database.hlavni_xlsx_import import archive_main_meter_xlsx, parse_main_meter_xlsx
from moduly.mereni.elektromery.database.models import Elektromer_OTE_Mereni, Elektromer_areal_Mereni


def _build_workbook_bytes(rows):
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "List1"
    for row in rows:
        worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_main_meter_xlsx_reads_main_meter_columns():
    payload = _build_workbook_bytes(
        [
            [
                None,
                "seriove_cislo: 859182400407782429, identifikace: TS1 + TS3",
                "seriove_cislo: 859182400409180513, identifikace: TS2",
            ],
            [datetime.datetime(2026, 2, 1, 0, 0), 19.41, 4.75],
            [datetime.datetime(2026, 2, 1, 0, 15), "20,41", "4,5"],
        ]
    )

    parsed = parse_main_meter_xlsx(payload)

    assert parsed.sheet_name == "List1"
    assert parsed.errors == ()
    assert parsed.warnings == ()
    assert [device.identifikace for device in parsed.devices] == ["TS1 + TS3", "TS2"]
    assert [device.seriove_cislo for device in parsed.devices] == [
        859182400407782429,
        859182400409180513,
    ]
    assert len(parsed.measurements) == 4
    assert parsed.measurements[0].identifikace == "TS1 + TS3"
    assert parsed.measurements[0].date == datetime.datetime(2026, 2, 1, 0, 0)
    assert parsed.measurements[0].objem == 19.41
    assert parsed.measurements[-1].identifikace == "TS2"
    assert parsed.measurements[-1].objem == 4.5


def test_parse_main_meter_xlsx_detects_duplicate_measurements():
    payload = _build_workbook_bytes(
        [
            [None, "seriove_cislo: 1, identifikace: TS2"],
            [datetime.datetime(2026, 2, 1, 0, 0), 4.75],
            [datetime.datetime(2026, 2, 1, 0, 0), 4.80],
        ]
    )

    parsed = parse_main_meter_xlsx(payload)

    assert len(parsed.measurements) == 1
    assert len(parsed.errors) == 1
    assert parsed.errors[0].message == "Duplicitni mereni v importovanem souboru."
    assert parsed.errors[0].identifikace == "TS2"


def test_parse_real_lds_fixture_shape():
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "moduly"
        / "mereni"
        / "elektromery"
        / "data"
        / "LDS 2026-02.xlsx"
    )

    if not fixture_path.exists():
        pytest.skip("Real LDS fixture is not available in this checkout.")

    parsed = parse_main_meter_xlsx(fixture_path.read_bytes())

    assert parsed.errors == ()
    assert parsed.warnings == ()
    assert [device.identifikace for device in parsed.devices] == ["TS1 + TS3", "TS2"]
    assert len(parsed.measurements) == 5376
    assert min(measurement.date for measurement in parsed.measurements) == datetime.datetime(2026, 2, 1, 0, 0)
    assert max(measurement.date for measurement in parsed.measurements) == datetime.datetime(2026, 2, 28, 23, 45)


def test_softlink_id_is_nullable_for_xlsx_imports():
    assert Elektromer_areal_Mereni.__table__.c.softlink_id.nullable is True


def test_ote_raw_table_schema_targets_postgres_dbo():
    assert Elektromer_OTE_Mereni.__table__.schema == "dbo"
    assert Elektromer_OTE_Mereni.__tablename__ == "Mereni_elektromery_OTE"
    assert {"identifikace", "seriove_cislo", "objem", "date"}.issubset(
        Elektromer_OTE_Mereni.__table__.c.keys()
    )
    assert {"source_date", "time_utc", "time_basis", "source_timezone"}.issubset(
        Elektromer_OTE_Mereni.__table__.c.keys()
    )


def test_unknown_identification_issues_are_built_from_ms_lookup(monkeypatch):
    payload = _build_workbook_bytes(
        [
            [None, "seriove_cislo: 1, identifikace: UNKNOWN_TS"],
            [datetime.datetime(2026, 2, 1, 0, 0), 4.75],
        ]
    )
    parsed = parse_main_meter_xlsx(payload)

    monkeypatch.setattr(
        hlavni_xlsx_import,
        "find_unknown_elektromery_identifikace",
        lambda values: tuple(values),
    )

    issues = hlavni_xlsx_import.build_unknown_identification_issues(parsed)

    assert len(issues) == 1
    assert issues[0].identifikace == "UNKNOWN_TS"
    assert issues[0].row_number == 1
    assert issues[0].message == "Identifikace neni zalozena v MS tabulce dbo.Zarizeni_elektromery."


def test_archive_main_meter_xlsx_copies_file_without_overwrite(tmp_path):
    payload = b"xlsx-bytes"
    archived_path = archive_main_meter_xlsx(
        payload,
        source_file=r"..\LDS 2026-02.xlsx",
        archive_dir=tmp_path,
    )

    assert archived_path == tmp_path / "LDS 2026-02.xlsx"
    assert archived_path.read_bytes() == payload

    duplicate_path = archive_main_meter_xlsx(
        payload,
        source_file="LDS 2026-02.xlsx",
        archive_dir=tmp_path,
    )

    assert duplicate_path == archived_path
    assert len(list(tmp_path.glob("*.xlsx"))) == 1

    versioned_path = archive_main_meter_xlsx(
        b"different-content",
        source_file="LDS 2026-02.xlsx",
        archive_dir=tmp_path,
    )

    assert versioned_path != archived_path
    assert versioned_path.name.startswith("LDS 2026-02_")
    assert versioned_path.read_bytes() == b"different-content"
    assert len(list(tmp_path.glob("*.xlsx"))) == 2
