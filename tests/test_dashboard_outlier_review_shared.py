import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.outlier_review_shared import (
    build_outlier_review_device_options,
    get_outlier_review_source_options,
    get_selected_outlier_review_module_keys,
    merge_outlier_review_rows,
    normalize_outlier_review_row,
)


def test_get_selected_outlier_review_module_keys_prefers_device_module():
    module_keys = get_selected_outlier_review_module_keys("plynomery", "vodomery")

    assert module_keys == ("vodomery",)


def test_get_outlier_review_source_options_returns_union_for_supported_modules():
    source_options = get_outlier_review_source_options(("vodomery", "plynomery"))

    assert source_options == ("VSE", "AREAL", "SCVK")


def test_merge_outlier_review_rows_sorts_pending_first_and_then_by_date_desc():
    rows = [
        normalize_outlier_review_row(
            "plynomery",
            {
                "id": 11,
                "identifikace": "PLY-02",
                "date": "2026-04-24T07:00:00",
                "review_status": "CONFIRMED_OUTLIER",
            },
        ),
        normalize_outlier_review_row(
            "vodomery",
            {
                "id": 12,
                "identifikace": "VDM-01",
                "date": "2026-04-24T06:00:00",
                "review_status": "PENDING",
            },
        ),
        normalize_outlier_review_row(
            "plynomery",
            {
                "id": 13,
                "identifikace": "PLY-01",
                "date": "2026-04-24T08:00:00",
                "review_status": "PENDING",
            },
        ),
    ]

    merged_rows = merge_outlier_review_rows(rows, limit=10)

    assert [row["id"] for row in merged_rows] == [13, 12, 11]


def test_build_outlier_review_device_options_prefixes_devices_by_module():
    options = build_outlier_review_device_options(
        {
            "vodomery": ["VDM-02", "VDM-01"],
            "plynomery": ["PLY-01"],
        }
    )

    assert options == [
        ("", ""),
        ("vodomery", "VDM-01"),
        ("vodomery", "VDM-02"),
        ("plynomery", "PLY-01"),
    ]
