from __future__ import annotations

import datetime
from pathlib import Path
import sys

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard import elektromery_shared
from moduly.mereni.elektromery.database.models import Elektromer_areal_Zarizeni


def test_prepare_measurements_uses_pg_delta_when_available():
    measurements = pd.DataFrame(
        [
            {
                "date": datetime.datetime(2026, 4, 29, 0, 15),
                "identifikace": "B-1.1",
                "seriove_cislo": 25722370615,
                "total": 100.0,
                "delta": None,
                "reset_detected": False,
            },
            {
                "date": datetime.datetime(2026, 4, 30, 0, 15),
                "identifikace": "B-1.1",
                "seriove_cislo": 25722370615,
                "total": 125.5,
                "delta": 25.5,
                "reset_detected": False,
            },
        ]
    )

    prepared = elektromery_shared.prepare_measurements(measurements)

    assert prepared["stav_celkem"].tolist() == [100.0, 125.5]
    assert prepared["spotreba"].tolist() == [0.0, 25.5]
    assert prepared["kumulovana_spotreba"].tolist() == [0.0, 25.5]


def test_prepare_measurements_keeps_ote_delta_only_rows():
    measurements = pd.DataFrame(
        [
            {
                "date": datetime.datetime(2026, 2, 1, 0, 15),
                "identifikace": "TS2",
                "seriove_cislo": 859182400409180513,
                "total": None,
                "delta": 1.25,
                "zdroj": "OTE",
                "reset_detected": False,
            },
            {
                "date": datetime.datetime(2026, 2, 1, 0, 30),
                "identifikace": "TS2",
                "seriove_cislo": 859182400409180513,
                "total": None,
                "delta": 2.0,
                "zdroj": "OTE",
                "reset_detected": False,
            },
        ]
    )

    prepared = elektromery_shared.prepare_measurements(measurements)

    assert len(prepared) == 2
    assert prepared["stav_celkem"].isna().all()
    assert prepared["spotreba"].tolist() == [1.25, 2.0]
    assert prepared["kumulovana_spotreba"].tolist() == [1.25, 3.25]
    assert elektromery_shared.build_change_table(prepared).empty


def test_delta_consumption_summary_is_used_for_ote_source():
    measurements = pd.DataFrame(
        [
            {
                "date": datetime.datetime(2026, 2, 1, 0, 15),
                "zdroj": "OTE",
                "spotreba": 1.25,
            },
            {
                "date": datetime.datetime(2026, 2, 1, 0, 30),
                "zdroj": "OTE",
                "spotreba": 2.0,
            },
        ]
    )

    summary = elektromery_shared.build_delta_consumption_summary(measurements)

    assert elektromery_shared.uses_ote_delta_source(measurements) is True
    assert summary.to_dict(orient="records") == [
        {
            "Zdroj": "OTE",
            "První měření": pd.Timestamp("2026-02-01 00:15:00"),
            "Poslední měření": pd.Timestamp("2026-02-01 00:30:00"),
            "Počet měření": 2,
            "Spotřeba z delta": 3.25,
        }
    ]


def test_serialize_device_detail_includes_photo_path():
    device = Elektromer_areal_Zarizeni(identifikace="TS1")
    device.foto = r"C:\fotky\elektromery\ts1.jpg"

    serialized = elektromery_shared._serialize_device_detail(device)

    assert serialized["foto"] == r"C:\fotky\elektromery\ts1.jpg"


def test_resolve_device_photo_path_supports_absolute_and_project_relative_paths(tmp_path, monkeypatch):
    absolute_photo = tmp_path / "absolute.jpg"
    absolute_photo.write_bytes(b"fake image")

    relative_dir = tmp_path / "images"
    relative_dir.mkdir()
    relative_photo = relative_dir / "relative.jpg"
    relative_photo.write_bytes(b"fake image")
    monkeypatch.setattr(elektromery_shared, "PROJECT_ROOT", tmp_path)

    assert elektromery_shared.resolve_device_photo_path(str(absolute_photo)) == absolute_photo
    assert elektromery_shared.resolve_device_photo_path(str(Path("images") / "relative.jpg")) == relative_photo
    assert elektromery_shared.resolve_device_photo_path("") is None


def test_build_device_photo_data_uri_encodes_image_bytes(tmp_path):
    photo_path = tmp_path / "detail.png"
    photo_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    data_uri = elektromery_shared.build_device_photo_data_uri(photo_path)

    assert data_uri is not None
    assert data_uri.startswith("data:image/png;base64,")
