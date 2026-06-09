from types import SimpleNamespace

import pytest

from services.api.services.dashboard_auth import AuthorizationError
from services.api.services.map_layers import (
    DEFAULT_MAP_LAYER_SEEDS,
    _load_layer_filter_options,
    _normalize_requested_filters,
    load_map_feature_image_file,
    load_requested_map_filter_options,
    list_map_layers_admin,
    list_map_layer_catalog,
    map_layer_record_to_config,
    user_can_access_map_layer,
)
from services.api.services.device_map import BUDOVY_MAP_LAYER, MISTNOSTI_MAP_LAYER, VODOMERY_MAP_LAYER


def test_default_map_layer_seeds_cover_initial_map_layers():
    seed_ids = [seed["layer_id"] for seed in DEFAULT_MAP_LAYER_SEEDS]

    assert seed_ids == ["budovy", "mistnosti", "vodomery"]
    vodomery_seed = next(seed for seed in DEFAULT_MAP_LAYER_SEEDS if seed["layer_id"] == "vodomery")
    assert vodomery_seed["layer_kind"] == "device"
    assert vodomery_seed["device_section_key"] == "vodomery"
    assert vodomery_seed["restrict_to_allowed_devices"] is True
    assert vodomery_seed["map_enabled"] is True
    assert vodomery_seed["show_photo"] is True


def test_map_layer_record_to_config_preserves_runtime_metadata():
    record = {
        "layer_id": "test",
        "title": "Test",
        "layer_kind": "device",
        "source_schema": "evidence",
        "source_table": "TEST",
        "geometry_column": "geom",
        "identifier_column": "identifikace",
        "source_srid": 3857,
        "target_srid": 4326,
        "property_columns": ["identifikace", "budova"],
        "property_aliases": {"budova": "evidence_budova"},
        "filter_columns": ["budova"],
        "popup_columns": ["identifikace"],
        "style": {"color": "#111111", "fillOpacity": 0.4},
        "device_section_key": "vodomery",
        "restrict_to_allowed_devices": True,
        "map_enabled": True,
        "default_visible": False,
        "show_photo": True,
        "draw_order": 50,
    }

    config = map_layer_record_to_config(record)

    assert config.layer_id == "test"
    assert config.layer_kind == "device"
    assert config.device_section_key == "vodomery"
    assert config.property_aliases["budova"] == "evidence_budova"
    assert config.filter_columns == ("budova",)
    assert config.popup_columns == ("identifikace",)
    assert config.style["color"] == "#111111"
    assert config.default_visible is False
    assert config.show_photo is True
    assert config.draw_order == 50


def test_list_map_layers_admin_requires_admin():
    current_user = SimpleNamespace(is_admin=False)

    with pytest.raises(AuthorizationError):
        list_map_layers_admin(current_user)


def test_user_can_access_device_layer_only_with_section_and_devices():
    allowed_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("vodomery",),
        allowed_devices=("V-1",),
    )
    no_devices_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("vodomery",),
        allowed_devices=(),
    )
    wrong_section_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("plynomery",),
        allowed_devices=("V-1",),
    )

    assert user_can_access_map_layer(allowed_user, VODOMERY_MAP_LAYER) is True
    assert user_can_access_map_layer(no_devices_user, VODOMERY_MAP_LAYER) is False
    assert user_can_access_map_layer(wrong_section_user, VODOMERY_MAP_LAYER) is False
    assert user_can_access_map_layer(wrong_section_user, BUDOVY_MAP_LAYER) is True


def test_map_layer_catalog_filters_unavailable_device_layers(monkeypatch):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(),
        allowed_devices=(),
    )
    monkeypatch.setattr(
        "services.api.services.map_layers.list_enabled_map_layer_configs",
        lambda _layer_ids=None: [BUDOVY_MAP_LAYER, VODOMERY_MAP_LAYER],
    )

    catalog = list_map_layer_catalog(current_user)

    assert [layer["layer_id"] for layer in catalog] == ["budovy"]


def test_normalize_requested_filters_accepts_source_column_and_property_alias():
    normalized = _normalize_requested_filters(
        MISTNOSTI_MAP_LAYER,
        {
            "budova": ["F", "F", ""],
            "najemce": ["Vyroba"],
        },
    )

    assert normalized == {
        "budova": ("F",),
        "n\u00e1jemce": ("Vyroba",),
    }


def test_normalize_requested_filters_rejects_unknown_filter():
    with pytest.raises(ValueError):
        _normalize_requested_filters(MISTNOSTI_MAP_LAYER, {"unknown": ["x"]})


def test_load_requested_map_filter_options_passes_filters_to_layer_loader(monkeypatch):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(),
        allowed_devices=(),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "services.api.services.map_layers.list_enabled_map_layer_configs",
        lambda _layer_ids=None: [MISTNOSTI_MAP_LAYER],
    )

    def fake_load_layer_filter_options(user_context, config, filters):
        captured["user_context"] = user_context
        captured["config"] = config
        captured["filters"] = filters
        return {
            "layer_id": config.layer_id,
            "options": {"budova": ["F"], "patro": ["1.NP"]},
        }

    monkeypatch.setattr(
        "services.api.services.map_layers._load_layer_filter_options",
        fake_load_layer_filter_options,
    )

    response = load_requested_map_filter_options(
        current_user,
        [{"layer_id": "mistnosti", "filters": {"budova": ["F"], "patro": ["1.NP"]}}],
    )

    assert captured["user_context"] is current_user
    assert captured["config"] is MISTNOSTI_MAP_LAYER
    assert captured["filters"] == {"budova": ["F"], "patro": ["1.NP"]}
    assert response == {
        "layers": [
            {
                "layer_id": "mistnosti",
                "options": {"budova": ["F"], "patro": ["1.NP"]},
            }
        ]
    }


def test_load_requested_map_filter_options_rejects_unavailable_device_layer(monkeypatch):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(),
        allowed_devices=(),
    )
    monkeypatch.setattr(
        "services.api.services.map_layers.list_enabled_map_layer_configs",
        lambda _layer_ids=None: [VODOMERY_MAP_LAYER],
    )

    with pytest.raises(AuthorizationError):
        load_requested_map_filter_options(current_user, [{"layer_id": "vodomery", "filters": {}}])


def test_load_layer_filter_options_returns_source_filter_keys_when_no_allowed_devices(monkeypatch):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("vodomery",),
        allowed_devices=(),
    )
    required_columns = {
        VODOMERY_MAP_LAYER.geometry_column,
        VODOMERY_MAP_LAYER.identifier_column,
        *VODOMERY_MAP_LAYER.filter_columns,
    }
    monkeypatch.setattr(
        "services.api.services.map_layers._table_columns",
        lambda _schema, _table: required_columns,
    )

    response = _load_layer_filter_options(current_user, VODOMERY_MAP_LAYER, {})

    assert response == {
        "layer_id": "vodomery",
        "options": {
            "budova": [],
            "patro": [],
            "mistnost_id": [],
            "identifikace": [],
        },
    }


def test_load_map_feature_image_file_rejects_device_outside_allowed_identifiers(monkeypatch):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("vodomery",),
        allowed_devices=("V-1",),
    )
    monkeypatch.setattr(
        "services.api.services.map_layers.get_enabled_map_layer_config",
        lambda _layer_id: VODOMERY_MAP_LAYER,
    )

    with pytest.raises(AuthorizationError):
        load_map_feature_image_file(current_user, layer_id="vodomery", identifier="V-2")


def test_load_map_feature_image_file_resolves_allowed_device(monkeypatch, tmp_path):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("vodomery",),
        allowed_devices=("V-1",),
    )
    image_path = tmp_path / "device.jpg"
    image_path.write_bytes(b"image-bytes")
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "services.api.services.map_layers.get_enabled_map_layer_config",
        lambda _layer_id: VODOMERY_MAP_LAYER,
    )

    def fake_resolve_map_feature_image_file(config, identifier):
        captured["config"] = config
        captured["identifier"] = identifier
        return SimpleNamespace(path=image_path, media_type="image/jpeg")

    monkeypatch.setattr(
        "services.api.services.map_layers.resolve_map_feature_image_file",
        fake_resolve_map_feature_image_file,
    )

    response = load_map_feature_image_file(current_user, layer_id="vodomery", identifier="V-1")

    assert captured == {"config": VODOMERY_MAP_LAYER, "identifier": "V-1"}
    assert response.path == image_path
    assert response.media_type == "image/jpeg"
