from dataclasses import replace
from types import SimpleNamespace

import pytest

from services.api.services.device_map import (
    BUDOVY_MAP_LAYER,
    MISTNOSTI_MAP_LAYER,
    MapFeatureImageError,
    MapFeatureImageNotFound,
    VODOMERY_MAP_LAYER,
    _empty_layer_response,
    _load_detail_properties,
    _row_to_feature,
    resolve_map_feature_image_file,
)


def test_row_to_feature_serializes_vodomery_geometry_and_properties():
    room_column = "m\u00edstnost"
    row = {
        "fid": 100,
        "identifikace": "V-1",
        "budova": "F",
        "patro": "1",
        room_column: "101",
        "mistnost_id": "M-101",
        "geometry": '{"type":"Point","coordinates":[14.1,50.7]}',
    }

    feature = _row_to_feature(row, VODOMERY_MAP_LAYER)

    assert feature == {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [14.1, 50.7]},
        "properties": {
            "fid": 100,
            "identifikace": "V-1",
            "evidence_budova": "F",
            "evidence_patro": "1",
            "evidence_mistnost": "101",
            "mistnost_id": "M-101",
            "detail_source_found": False,
            "has_photo": False,
            "layer_id": "vodomery",
            "layer_title": "Vodomery",
        },
    }


def test_row_to_feature_merges_ms_device_details_by_identifikace():
    room_column = "m\u00edstnost"
    row = {
        "fid": 100,
        "identifikace": "V-1",
        "budova": "F",
        "patro": "1",
        room_column: "101",
        "mistnost_id": "M-101",
        "geometry": '{"type":"Point","coordinates":[14.1,50.7]}',
    }
    detail_properties = {
        "V-1": {
            "identifikace": "V-1",
            "seriove_cislo": "S-1",
            "MBUS": "MB-1",
            "objekt": "Objekt MS",
            "patro": "2",
            "mistnost": "202",
            "foto": r"P:\photos\v1.jpg",
        }
    }

    feature = _row_to_feature(row, VODOMERY_MAP_LAYER, detail_properties)

    assert feature is not None
    properties = feature["properties"]
    assert properties["detail_source_found"] is True
    assert properties["identifikace"] == "V-1"
    assert properties["evidence_budova"] == "F"
    assert properties["evidence_patro"] == "1"
    assert properties["evidence_mistnost"] == "101"
    assert properties["mistnost_id"] == "M-101"
    assert properties["seriove_cislo"] == "S-1"
    assert properties["MBUS"] == "MB-1"
    assert properties["objekt"] == "Objekt MS"
    assert properties["patro"] == "2"
    assert properties["mistnost"] == "202"
    assert properties["has_photo"] is True
    assert "foto" not in properties


def test_empty_layer_response_keeps_geojson_shape():
    response = _empty_layer_response(VODOMERY_MAP_LAYER)

    assert response["layer_id"] == "vodomery"
    assert response["source_srid"] == 3857
    assert response["target_srid"] == 4326
    assert response["total"] == 0
    assert response["feature_collection"] == {
        "type": "FeatureCollection",
        "features": [],
    }


def test_row_to_feature_serializes_budovy_polygon_and_properties():
    floor_count_column = "po\u010det_podla\u017e\u00ed"
    row = {
        "fid": 10,
        "budova": "A",
        floor_count_column: 3,
        "geometry": '{"type":"Polygon","coordinates":[[[14.1,50.7],[14.2,50.7],[14.2,50.8],[14.1,50.7]]]}',
    }

    feature = _row_to_feature(row, BUDOVY_MAP_LAYER)

    assert feature is not None
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["properties"] == {
        "fid": 10,
        "budova": "A",
        "pocet_podlazi": 3,
        "detail_source_found": False,
        "layer_id": "budovy",
        "layer_title": "Budovy",
    }


def test_row_to_feature_serializes_mistnosti_polygon_and_properties():
    room_column = "m\u00edstnost"
    tenant_column = "n\u00e1jemce"
    row = {
        "fid": 20,
        "mistnost_id": "F-1NP-101",
        room_column: "101",
        "patro": "1.NP",
        "budova": "F",
        tenant_column: "Vyroba",
        "popis": "Dilna",
        "plocha": 25.5,
        "geometry": '{"type":"Polygon","coordinates":[[[14.1,50.7],[14.2,50.7],[14.2,50.8],[14.1,50.7]]]}',
    }

    feature = _row_to_feature(row, MISTNOSTI_MAP_LAYER)

    assert feature is not None
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["properties"] == {
        "fid": 20,
        "mistnost_id": "F-1NP-101",
        "mistnost": "101",
        "patro": "1.NP",
        "budova": "F",
        "najemce": "Vyroba",
        "popis": "Dilna",
        "plocha": 25.5,
        "detail_source_found": False,
        "layer_id": "mistnosti",
        "layer_title": "M\u00edstnosti",
    }


def test_vodomery_layer_config_uses_existing_device_permission_identifier():
    user_context = SimpleNamespace(is_admin=False, allowed_devices=("V-1",))

    assert VODOMERY_MAP_LAYER.table == "vodom\u011bry"
    assert VODOMERY_MAP_LAYER.identifier_column == "identifikace"
    assert "m\u00edstnost" in VODOMERY_MAP_LAYER.property_columns
    assert VODOMERY_MAP_LAYER.show_photo is True
    assert user_context.allowed_devices == ("V-1",)


def test_budovy_layer_config_is_context_layer_without_device_filter():
    assert BUDOVY_MAP_LAYER.table == "BUDOVY"
    assert BUDOVY_MAP_LAYER.identifier_column == "fid"
    assert "po\u010det_podla\u017e\u00ed" in BUDOVY_MAP_LAYER.property_columns
    assert BUDOVY_MAP_LAYER.property_aliases["po\u010det_podla\u017e\u00ed"] == "pocet_podlazi"
    assert BUDOVY_MAP_LAYER.restrict_to_allowed_devices is False


def test_mistnosti_layer_config_is_context_layer_with_filterable_location_fields():
    assert MISTNOSTI_MAP_LAYER.table == "M\u00cdSTNOSTI"
    assert MISTNOSTI_MAP_LAYER.identifier_column == "mistnost_id"
    assert "budova" in MISTNOSTI_MAP_LAYER.property_columns
    assert "patro" in MISTNOSTI_MAP_LAYER.property_columns
    assert "mistnost_id" in MISTNOSTI_MAP_LAYER.property_columns
    assert MISTNOSTI_MAP_LAYER.property_aliases["m\u00edstnost"] == "mistnost"
    assert MISTNOSTI_MAP_LAYER.property_aliases["n\u00e1jemce"] == "najemce"
    assert MISTNOSTI_MAP_LAYER.restrict_to_allowed_devices is False


def test_resolve_map_feature_image_file_returns_existing_vodomery_photo(monkeypatch, tmp_path):
    image_path = tmp_path / "device.jpg"
    image_path.write_bytes(b"image-bytes")
    monkeypatch.setattr(
        "services.api.services.device_map._load_vodomery_device_details",
        lambda _identifiers, *, include_photo: {"V-1": {"foto": str(image_path)}},
    )

    image_file = resolve_map_feature_image_file(VODOMERY_MAP_LAYER, "V-1")

    assert image_file.path == image_path
    assert image_file.media_type == "image/jpeg"


def test_resolve_map_feature_image_file_uses_configured_drive_fallback(monkeypatch, tmp_path):
    image_dir = tmp_path / "photos"
    image_dir.mkdir()
    image_path = image_dir / "device.jpg"
    image_path.write_bytes(b"image-bytes")
    monkeypatch.setattr(
        "services.api.services.device_map.PHOTO_PATH_PREFIX_FALLBACKS",
        (("P:\\", f"{tmp_path}\\"),),
    )
    monkeypatch.setattr(
        "services.api.services.device_map._load_vodomery_device_details",
        lambda _identifiers, *, include_photo: {"V-1": {"foto": r"P:\photos\device.jpg"}},
    )

    image_file = resolve_map_feature_image_file(VODOMERY_MAP_LAYER, "V-1")

    assert image_file.path == image_path
    assert image_file.media_type == "image/jpeg"


def test_resolve_map_feature_image_file_returns_not_found_for_empty_photo(monkeypatch):
    monkeypatch.setattr(
        "services.api.services.device_map._load_vodomery_device_details",
        lambda _identifiers, *, include_photo: {"V-1": {"foto": ""}},
    )

    with pytest.raises(MapFeatureImageNotFound):
        resolve_map_feature_image_file(VODOMERY_MAP_LAYER, "V-1")


def test_resolve_map_feature_image_file_rejects_non_image_suffix(monkeypatch, tmp_path):
    document_path = tmp_path / "device.txt"
    document_path.write_text("not an image", encoding="utf-8")
    monkeypatch.setattr(
        "services.api.services.device_map._load_vodomery_device_details",
        lambda _identifiers, *, include_photo: {"V-1": {"foto": str(document_path)}},
    )

    with pytest.raises(MapFeatureImageError):
        resolve_map_feature_image_file(VODOMERY_MAP_LAYER, "V-1")


def test_resolve_map_feature_image_file_rejects_layer_with_photos_disabled(monkeypatch):
    config = replace(VODOMERY_MAP_LAYER, show_photo=False)
    load_called = False

    def fake_load(_identifiers, *, include_photo):
        nonlocal load_called
        load_called = True
        return {}

    monkeypatch.setattr(
        "services.api.services.device_map._load_vodomery_device_details",
        fake_load,
    )

    with pytest.raises(MapFeatureImageError, match="neni pro vrstvu povoleno"):
        resolve_map_feature_image_file(config, "V-1")

    assert load_called is False


def test_row_to_feature_omits_photo_metadata_when_photos_disabled():
    config = replace(VODOMERY_MAP_LAYER, show_photo=False)
    row = {
        "identifikace": "V-1",
        "geometry": '{"type":"Point","coordinates":[14.1,50.7]}',
    }

    feature = _row_to_feature(
        row,
        config,
        {"V-1": {"identifikace": "V-1", "foto": r"P:\photos\v1.jpg"}},
    )

    assert feature is not None
    assert "foto" not in feature["properties"]
    assert "has_photo" not in feature["properties"]


def test_load_detail_properties_does_not_select_photo_when_disabled(monkeypatch):
    config = replace(VODOMERY_MAP_LAYER, show_photo=False)
    captured: dict[str, object] = {}

    def fake_load(identifiers, *, include_photo):
        captured["identifiers"] = identifiers
        captured["include_photo"] = include_photo
        return {"V-1": {"identifikace": "V-1"}}

    monkeypatch.setattr(
        "services.api.services.device_map._load_vodomery_device_details",
        fake_load,
    )

    details = _load_detail_properties(config, ("V-1",))

    assert captured == {
        "identifiers": ("V-1",),
        "include_photo": False,
    }
    assert details == {"V-1": {"identifikace": "V-1"}}
