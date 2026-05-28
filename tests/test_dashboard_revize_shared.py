from __future__ import annotations

import datetime
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.revize_shared import (
    REVIZE_STATUS_DUE_SOON,
    REVIZE_STATUS_EXPIRED,
    REVIZE_STATUS_NO_DATE,
    REVIZE_STATUS_VALID,
    build_revize_metrics,
    build_link_uri,
    calculate_revize_valid_until,
    classify_revize_status,
    filter_revize_dataframe,
    normalize_revize_payload,
    parse_revize_linked_device_ids,
    prepare_revize_dataframe,
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


def test_parse_revize_linked_device_ids_accepts_single_number_and_lists():
    assert parse_revize_linked_device_ids("123") == [123]
    assert parse_revize_linked_device_ids("123, 124\n125;123 126") == [123, 124, 125, 126]
    assert parse_revize_linked_device_ids("") == []


def test_parse_revize_linked_device_ids_rejects_non_numeric_values():
    with pytest.raises(ValueError, match="Navazane zarizeni"):
        parse_revize_linked_device_ids("123, abc")
