from __future__ import annotations

import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard import revize_shared
from moduly.apps.dashboard.revize_shared import (
    REVIZE_STATUS_DUE_SOON,
    REVIZE_STATUS_EXPIRED,
    REVIZE_STATUS_NO_DATE,
    REVIZE_STATUS_VALID,
    RevizeLinkedDeviceValidationError,
    build_revize_metrics,
    build_link_uri,
    calculate_revize_valid_until,
    classify_revize_status,
    filter_revize_dataframe,
    load_revize_record_values,
    normalize_revize_payload,
    parse_revize_linked_device_ids,
    prepare_revize_dataframe,
    validate_revize_linked_devices,
)
from services.api.services import revize_admin
from services.api.services.revize_admin import (
    create_revize_admin,
    update_revize_admin,
)


def test_classify_revize_status_distinguishes_expired_due_soon_valid_and_missing():
    reference_date = datetime.date(2026, 5, 7)

    assert classify_revize_status(datetime.date(2026, 5, 6), reference_date=reference_date) == REVIZE_STATUS_EXPIRED
    assert classify_revize_status(datetime.date(2026, 5, 21), reference_date=reference_date) == REVIZE_STATUS_DUE_SOON
    assert classify_revize_status(datetime.date(2026, 8, 1), reference_date=reference_date) == REVIZE_STATUS_VALID
    assert classify_revize_status(None, reference_date=reference_date) == REVIZE_STATUS_NO_DATE


def test_prepare_revize_dataframe_adds_status_labels_and_links():
    df = pd.DataFrame(
        [
            {
                "budova": "F",
                "datum": datetime.date(2025, 12, 18),
                "datum_platnosti": datetime.date(2026, 12, 18),
                "typ_zarizeni": "ROZVODY PLYNU",
                "nazev_revize": "F - revize - rozvody plynu",
                "dodavatel": "Roman Svoboda",
                "soubor": r"P:\Holding\Budovy\F\Revize\plyn.pdf",
                "servisni_smlouva": "https://example.test/smlouva.pdf",
                "poznamka": None,
                "linked_devices": 3,
            }
        ]
    )

    prepared = prepare_revize_dataframe(df, reference_date=datetime.date(2026, 5, 7))

    assert prepared.loc[0, "Stav"] == REVIZE_STATUS_VALID
    assert prepared.loc[0, "Soubor"] == "plyn.pdf"
    assert prepared.loc[0, "Otevřít soubor"] == "file:///P:/Holding/Budovy/F/Revize/plyn.pdf"
    assert prepared.loc[0, "Otevřít smlouvu"] == "https://example.test/smlouva.pdf"
    assert prepared.loc[0, "Navázaná zařízení"] == 3


def test_filter_revize_dataframe_applies_building_status_and_search():
    source_df = pd.DataFrame(
        [
            {
                "budova": "F",
                "typ_zarizeni": "ELEKTROREVIZE",
                "status": REVIZE_STATUS_EXPIRED,
                "nazev_revize": "Elektro F",
                "dodavatel": "Dodavatel A",
                "soubor": r"P:\f.pdf",
                "servisni_smlouva": "",
                "poznamka": "",
            },
            {
                "budova": "G",
                "typ_zarizeni": "HYDRANTY",
                "status": REVIZE_STATUS_VALID,
                "nazev_revize": "Hydranty G",
                "dodavatel": "Dodavatel B",
                "soubor": r"P:\g.pdf",
                "servisni_smlouva": "",
                "poznamka": "",
            },
        ]
    )

    filtered = filter_revize_dataframe(
        source_df,
        buildings=["F"],
        device_types=["ELEKTROREVIZE"],
        status=REVIZE_STATUS_EXPIRED,
        search_text="elektro",
    )

    assert len(filtered) == 1
    assert filtered.iloc[0]["budova"] == "F"


def test_build_revize_metrics_counts_statuses_and_missing_files():
    df = pd.DataFrame(
        [
            {"status": REVIZE_STATUS_EXPIRED, "soubor": r"P:\a.pdf"},
            {"status": REVIZE_STATUS_DUE_SOON, "soubor": ""},
            {"status": REVIZE_STATUS_VALID, "soubor": r"P:\c.pdf"},
        ]
    )

    metrics = build_revize_metrics(df)

    assert metrics == {
        "total": 3,
        "expired": 1,
        "due_soon": 1,
        "valid": 1,
        "missing_file": 1,
    }


def test_build_link_uri_preserves_http_and_converts_file_paths():
    assert build_link_uri("https://example.test/file.pdf") == "https://example.test/file.pdf"
    assert build_link_uri(r"P:\Holding\Revize\file.pdf") == "file:///P:/Holding/Revize/file.pdf"


def test_calculate_revize_valid_until_adds_calendar_months():
    assert calculate_revize_valid_until(datetime.date(2025, 12, 18), 18) == datetime.date(2027, 6, 18)
    assert calculate_revize_valid_until(datetime.date(2025, 1, 31), 1) == datetime.date(2025, 2, 28)


def test_normalize_revize_payload_validates_required_fields_and_coerces_values():
    payload = normalize_revize_payload(
        budova=" F ",
        datum="18.12.2025",
        delka_platnosti="18",
        datum_platnosti=datetime.date(2099, 1, 1),
        typ_zarizeni=" Elektro ",
        nazev_revize="Revize F",
        dodavatel="Dodavatel",
        servisni_smlouva="",
        soubor=r"P:\revize.pdf",
        poznamka="",
    )

    assert payload["budova"] == "F"
    assert payload["datum"] == datetime.date(2025, 12, 18)
    assert str(payload["delka_platnosti"]) == "18"
    assert payload["datum_platnosti"] == datetime.date(2027, 6, 18)
    assert payload["typ_zarizeni"] == "Elektro"
    assert payload["servisni_smlouva"] is None
    assert payload["poznamka"] is None


def test_normalize_revize_payload_requires_device_type():
    with pytest.raises(ValueError, match="Zarizeni"):
        normalize_revize_payload(
            budova="F",
            datum="18.12.2025",
            delka_platnosti="18",
            typ_zarizeni="",
        )


def test_parse_revize_linked_device_ids_accepts_single_number_and_lists():
    assert parse_revize_linked_device_ids("123") == [123]
    assert parse_revize_linked_device_ids("123, 124\n125;123 126") == [123, 124, 125, 126]
    assert parse_revize_linked_device_ids("") == []


def test_parse_revize_linked_device_ids_rejects_non_numeric_values():
    with pytest.raises(RevizeLinkedDeviceValidationError) as exc_info:
        parse_revize_linked_device_ids("123, abc, -5, 0, 12.5")

    assert exc_info.value.messages == (
        "abc: neni cele cislo",
        "-5: musi byt vetsi nez nula",
        "0: musi byt vetsi nez nula",
        "12.5: neni cele cislo",
    )


class _FakeMappingResult:
    def __init__(self, *, one_row=None, rows=None):
        self._one_row = one_row
        self._rows = rows or []

    def mappings(self):
        return self

    def one(self):
        return self._one_row

    def all(self):
        return self._rows


class _FakeRevizeValidationSession:
    def __init__(self, *, table_info, device_rows):
        self.table_info = table_info
        self.device_rows = device_rows

    def execute(self, statement, params=None):
        statement_text = str(statement)
        if "information_schema.tables" in statement_text:
            return _FakeMappingResult(one_row=self.table_info)
        return _FakeMappingResult(rows=self.device_rows)


def test_validate_revize_linked_devices_checks_fid_and_building():
    session = _FakeRevizeValidationSession(
        table_info={"table_exists": True, "has_fid": True, "has_budova": True},
        device_rows=[
            {"fid": 10, "budova": "F"},
            {"fid": 11, "budova": "G"},
        ],
    )

    with pytest.raises(RevizeLinkedDeviceValidationError) as exc_info:
        validate_revize_linked_devices(
            session,
            budova="F",
            typ_zarizeni="HYDRANTY",
            linked_device_ids=[10, 11, 12],
        )

    assert exc_info.value.messages == (
        '11: patri do budovy G, ale ve formulari je budova F',
        '12: nenalezeno v "evidence"."HYDRANTY".fid',
    )


def test_validate_revize_linked_devices_rejects_unknown_evidence_table():
    session = _FakeRevizeValidationSession(
        table_info={"table_exists": False, "has_fid": False, "has_budova": False},
        device_rows=[],
    )

    with pytest.raises(RevizeLinkedDeviceValidationError) as exc_info:
        validate_revize_linked_devices(
            session,
            budova="F",
            typ_zarizeni="NEEXISTUJE",
            linked_device_ids=[10],
        )

    assert exc_info.value.messages == ('NEEXISTUJE: tabulka evidence."NEEXISTUJE" neexistuje.',)


def test_validate_revize_linked_devices_allows_empty_links_for_existing_table():
    session = _FakeRevizeValidationSession(
        table_info={"table_exists": True, "has_fid": True, "has_budova": True},
        device_rows=[],
    )

    assert (
        validate_revize_linked_devices(
            session,
            budova="F",
            typ_zarizeni="HYDRANTY",
            linked_device_ids=[],
        )
        == []
    )


def test_validate_revize_linked_devices_rejects_empty_links_for_unknown_table():
    session = _FakeRevizeValidationSession(
        table_info={"table_exists": False, "has_fid": False, "has_budova": False},
        device_rows=[],
    )

    with pytest.raises(RevizeLinkedDeviceValidationError) as exc_info:
        validate_revize_linked_devices(
            session,
            budova="F",
            typ_zarizeni="NEEXISTUJE",
            linked_device_ids=[],
        )

    assert exc_info.value.messages == ('NEEXISTUJE: tabulka evidence."NEEXISTUJE" neexistuje.',)


class _FakeQuery:
    def __init__(self, duplicate_id=None, session=None, rows=None):
        self.duplicate_id = duplicate_id
        self.session = session
        self.rows = rows or []

    def filter(self, *conditions):
        return self

    def order_by(self, *clauses):
        return self

    def all(self):
        return self.rows

    def first(self):
        if self.duplicate_id is None:
            return None
        return (self.duplicate_id,)

    def delete(self, synchronize_session=False):
        if self.session is not None:
            self.session.delete_count += 1
        return 0


class _FakeCreateSession(_FakeRevizeValidationSession):
    def __init__(self, *, table_info, device_rows, duplicate_id=None, records=None, linked_rows=None):
        super().__init__(table_info=table_info, device_rows=device_rows)
        self.duplicate_id = duplicate_id
        self.records = records or {}
        self.linked_rows = linked_rows or []
        self.added_records = []
        self.added_links = []
        self.delete_count = 0
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def query(self, *entities):
        return _FakeQuery(self.duplicate_id, self, rows=self.linked_rows)

    def get(self, model, key):
        return self.records.get(int(key))

    def add(self, record):
        self.added_records.append(record)

    def add_all(self, records):
        self.added_links.extend(list(records))

    def flush(self):
        self.flush_count += 1
        for index, record in enumerate(self.added_records, start=1):
            if getattr(record, "id", None) is None:
                record.id = index

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


def _minimal_revize_payload(**overrides):
    payload = {
        "budova": "F",
        "datum": datetime.date(2026, 5, 28),
        "delka_platnosti": 12,
        "datum_platnosti": datetime.date(2027, 5, 28),
        "typ_zarizeni": "HYDRANTY",
        "nazev_revize": "Hydranty",
        "dodavatel": None,
        "servisni_smlouva": None,
        "soubor": r"P:\revize\hydranty.pdf",
        "poznamka": None,
    }
    payload.update(overrides)
    return payload


def _minimal_revize_record(**overrides):
    record = {
        "id": 1,
        "budova": "F",
        "datum": datetime.date(2026, 5, 28),
        "delka_platnosti": 12,
        "datum_platnosti": datetime.date(2027, 5, 28),
        "typ_zarizeni": "ROZVODY PLYNU",
        "nazev_revize": "Rozvody plynu",
        "dodavatel": None,
        "servisni_smlouva": None,
        "soubor": r"P:\revize\plyn.pdf",
        "poznamka": None,
    }
    record.update(overrides)
    return SimpleNamespace(**record)


def _admin_user():
    return SimpleNamespace(is_admin=True)


def test_load_revize_record_values_includes_linked_device_types(monkeypatch):
    record = _minimal_revize_record()
    linked_rows = [
        SimpleNamespace(zarizeni_id=1, typ_zarizeni="PLYNOVÁ ZAŘÍZENÍ"),
        SimpleNamespace(zarizeni_id=2, typ_zarizeni="PLYNOVÁ ZAŘÍZENÍ"),
    ]
    session = _FakeCreateSession(
        table_info={"table_exists": True, "has_fid": True, "has_budova": True},
        device_rows=[],
        records={1: record},
        linked_rows=linked_rows,
    )
    monkeypatch.setattr(revize_shared, "get_session_pg", lambda: session)

    values = load_revize_record_values(1)

    assert values["typ_zarizeni"] == "ROZVODY PLYNU"
    assert values["linked_device_ids"] == [1, 2]
    assert values["linked_device_types"] == ["PLYNOVÁ ZAŘÍZENÍ"]
    assert values["linked_device_type"] == "PLYNOVÁ ZAŘÍZENÍ"
    assert session.close_count == 1


def test_create_revize_admin_validates_links_before_flush(monkeypatch):
    session = _FakeCreateSession(
        table_info={"table_exists": False, "has_fid": False, "has_budova": False},
        device_rows=[],
    )
    monkeypatch.setattr(revize_admin, "get_session_pg", lambda: session)

    with pytest.raises(RevizeLinkedDeviceValidationError):
        create_revize_admin(
            _admin_user(),
            payload=_minimal_revize_payload(typ_zarizeni="NEEXISTUJE"),
            linked_device_ids=[10],
        )

    assert session.added_records == []
    assert session.flush_count == 0
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.close_count == 1


def test_create_revize_admin_rejects_duplicate_before_flush(monkeypatch):
    session = _FakeCreateSession(
        table_info={"table_exists": True, "has_fid": True, "has_budova": True},
        device_rows=[],
        duplicate_id=42,
    )
    monkeypatch.setattr(revize_admin, "get_session_pg", lambda: session)

    with pytest.raises(ValueError, match="uz existuje"):
        create_revize_admin(
            _admin_user(),
            payload=_minimal_revize_payload(),
            linked_device_ids=[],
        )

    assert session.added_records == []
    assert session.flush_count == 0
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.close_count == 1


def test_update_revize_admin_validates_links_before_mutating_record(monkeypatch):
    record = SimpleNamespace(
        id=1,
        budova="F",
        typ_zarizeni="HYDRANTY",
        soubor=r"P:\revize\puvodni.pdf",
    )
    session = _FakeCreateSession(
        table_info={"table_exists": False, "has_fid": False, "has_budova": False},
        device_rows=[],
        records={1: record},
    )
    monkeypatch.setattr(revize_admin, "get_session_pg", lambda: session)

    with pytest.raises(RevizeLinkedDeviceValidationError):
        update_revize_admin(
            _admin_user(),
            revize_id=1,
            payload=_minimal_revize_payload(typ_zarizeni="NEEXISTUJE"),
            linked_device_ids=[10],
        )

    assert record.typ_zarizeni == "HYDRANTY"
    assert record.soubor == r"P:\revize\puvodni.pdf"
    assert session.delete_count == 0
    assert session.added_links == []
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.close_count == 1


def test_update_revize_admin_rejects_duplicate_before_mutating_record(monkeypatch):
    record = SimpleNamespace(
        id=1,
        budova="F",
        typ_zarizeni="HYDRANTY",
        soubor=r"P:\revize\puvodni.pdf",
    )
    session = _FakeCreateSession(
        table_info={"table_exists": True, "has_fid": True, "has_budova": True},
        device_rows=[],
        duplicate_id=42,
        records={1: record},
    )
    monkeypatch.setattr(revize_admin, "get_session_pg", lambda: session)

    with pytest.raises(ValueError, match="uz existuje"):
        update_revize_admin(
            _admin_user(),
            revize_id=1,
            payload=_minimal_revize_payload(),
            linked_device_ids=[],
        )

    assert record.soubor == r"P:\revize\puvodni.pdf"
    assert session.delete_count == 0
    assert session.added_links == []
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.close_count == 1


def test_update_revize_admin_replaces_links_after_successful_validation(monkeypatch):
    record = SimpleNamespace(
        id=1,
        budova="F",
        datum=datetime.date(2026, 1, 1),
        soubor=r"P:\revize\puvodni.pdf",
        typ_zarizeni="HYDRANTY",
    )
    session = _FakeCreateSession(
        table_info={"table_exists": True, "has_fid": True, "has_budova": True},
        device_rows=[
            {"fid": 10, "budova": "F"},
            {"fid": 11, "budova": "F"},
        ],
        records={1: record},
    )
    monkeypatch.setattr(revize_admin, "get_session_pg", lambda: session)

    update_revize_admin(
        _admin_user(),
        revize_id=1,
        payload=_minimal_revize_payload(),
        linked_device_ids=[10, 11],
    )

    assert record.soubor == r"P:\revize\hydranty.pdf"
    assert record.typ_zarizeni == "HYDRANTY"
    assert session.delete_count == 1
    assert [link.zarizeni_id for link in session.added_links] == [10, 11]
    assert session.commit_count == 1
    assert session.rollback_count == 0
    assert session.close_count == 1
