from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard import kalorimetry_shared, plynomery_shared
from moduly.apps.dashboard.device_photo import build_photo_data_uri, resolve_photo_path
from moduly.mereni.kalorimetry.database.models import Kalorimetr_areal_Zarizeni
from moduly.mereni.plynomery.database.models import Plynomer_areal_Zarizeni


def test_resolve_photo_path_supports_absolute_and_project_relative_paths(tmp_path):
    absolute_photo = tmp_path / "absolute.jpg"
    absolute_photo.write_bytes(b"fake image")

    relative_dir = tmp_path / "images"
    relative_dir.mkdir()
    relative_photo = relative_dir / "relative.jpg"
    relative_photo.write_bytes(b"fake image")

    assert resolve_photo_path(str(absolute_photo), project_root=tmp_path) == absolute_photo
    assert resolve_photo_path(str(Path("images") / "relative.jpg"), project_root=tmp_path) == relative_photo
    assert resolve_photo_path("", project_root=tmp_path) is None


def test_build_photo_data_uri_encodes_image_bytes(tmp_path):
    photo_path = tmp_path / "detail.png"
    photo_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    data_uri = build_photo_data_uri(photo_path)

    assert data_uri is not None
    assert data_uri.startswith("data:image/png;base64,")


def test_plynomery_serialize_device_detail_includes_photo_path():
    device = Plynomer_areal_Zarizeni(identifikace="P-1")
    device.foto = r"C:\fotky\plynomery\p1.jpg"

    serialized = plynomery_shared._serialize_device_detail(device)

    assert serialized["foto"] == r"C:\fotky\plynomery\p1.jpg"


def test_kalorimetry_serialize_device_detail_includes_photo_path():
    device = Kalorimetr_areal_Zarizeni(identifikace="K-1")
    device.foto = r"C:\fotky\kalorimetry\k1.jpg"

    serialized = kalorimetry_shared._serialize_device_detail(device)

    assert serialized["foto"] == r"C:\fotky\kalorimetry\k1.jpg"
