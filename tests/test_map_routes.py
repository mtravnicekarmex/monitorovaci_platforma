import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dashboard_session import DASHBOARD_SESSION_COOKIE_NAME
from services.api.core import dependencies
from services.api.routes import map as map_routes
from services.api.schemas.device_map import MapLayerFeaturesRequest
from services.api.services.dashboard_auth import AuthorizationError
from services.api.services.device_map import MapFeatureImageFile, MapFeatureImageNotFound


def test_browser_session_user_uses_httponly_cookie_token(monkeypatch):
    token_payload = SimpleNamespace(subject="tester", token_version=3)
    user_context = SimpleNamespace(username="tester", token_version=3)
    monkeypatch.setattr(
        dependencies,
        "decode_access_token",
        lambda token: token_payload if token == "cookie-token" else None,
    )
    monkeypatch.setattr(
        dependencies,
        "get_dashboard_user_context",
        lambda subject: user_context if subject == "tester" else None,
    )

    current_user = dependencies.get_current_browser_session_user("cookie-token")

    assert current_user is user_context


def test_browser_session_user_rejects_bearer_without_cookie():
    with pytest.raises(HTTPException) as exc_info:
        dependencies.get_current_browser_session_user(None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Chybi dashboard session cookie."


def test_map_image_route_uses_browser_session_cookie_dependency():
    dependency = inspect.signature(map_routes.get_map_image).parameters["current_user"].default.dependency
    cookie_scheme = (
        inspect.signature(dependencies.get_current_browser_session_user)
        .parameters["access_token"]
        .default.dependency
    )

    assert dependency is dependencies.get_current_browser_session_user
    assert cookie_scheme is dependencies.browser_session_scheme
    assert dependencies.browser_session_scheme.model.name == DASHBOARD_SESSION_COOKIE_NAME


def test_map_layer_features_request_accepts_single_filter_value():
    request = MapLayerFeaturesRequest(
        layer_id="mistnosti",
        filters={"budova": "F"},
    )

    assert request.filters == {"budova": ["F"]}


def test_get_map_layer_catalog_returns_available_layers(monkeypatch):
    current_user = SimpleNamespace(is_admin=False, allowed_sections=(), allowed_devices=())
    monkeypatch.setattr(
        map_routes,
        "list_map_layer_catalog",
        lambda _user: [
            {
                "layer_id": "budovy",
                "title": "Budovy",
                "layer_kind": "context",
                "device_section_key": None,
                "default_visible": True,
                "draw_order": 10,
                "filter_fields": [
                    {
                        "key": "budova",
                        "source_column": "budova",
                        "property_key": "budova",
                        "label": "budova",
                        "multiple": True,
                    }
                ],
                "popup_columns": ["budova"],
                "style": {"color": "#d97706"},
            }
        ],
    )

    response = map_routes.get_map_layer_catalog(current_user)

    assert response.total == 1
    assert response.layers[0].layer_id == "budovy"
    assert response.layers[0].filter_fields[0].key == "budova"


def test_post_map_features_returns_feature_layers(monkeypatch):
    current_user = SimpleNamespace(is_admin=False, allowed_sections=("vodomery",), allowed_devices=("V-1",))

    def fake_load_requested_map_features(_user, requested_layers):
        assert requested_layers == [{"layer_id": "vodomery", "filters": {"budova": ["F"]}}]
        return {
            "primary_layer_id": "vodomery",
            "layers": [
                {
                    "layer_id": "vodomery",
                    "title": "Vodomery",
                    "layer_kind": "device",
                    "device_section_key": "vodomery",
                    "source_srid": 3857,
                    "target_srid": 4326,
                    "map_enabled": True,
                    "default_visible": True,
                    "draw_order": 100,
                    "filter_columns": ["budova"],
                    "popup_columns": ["identifikace"],
                    "style": {"color": "#0f5e9c"},
                    "total": 0,
                    "feature_collection": {"type": "FeatureCollection", "features": []},
                }
            ],
        }

    monkeypatch.setattr(map_routes, "load_requested_map_features", fake_load_requested_map_features)

    response = map_routes.post_map_features(
        map_routes.MapFeaturesRequest(layers=[{"layer_id": "vodomery", "filters": {"budova": ["F"]}}]),
        current_user,
    )

    assert response.primary_layer_id == "vodomery"
    assert response.layers[0].layer_id == "vodomery"


def test_post_map_features_maps_authorization_error_to_403(monkeypatch):
    current_user = SimpleNamespace(is_admin=False, allowed_sections=(), allowed_devices=())
    monkeypatch.setattr(
        map_routes,
        "load_requested_map_features",
        lambda *_: (_ for _ in ()).throw(AuthorizationError("forbidden")),
    )

    with pytest.raises(HTTPException) as exc_info:
        map_routes.post_map_features(map_routes.MapFeaturesRequest(layers=[]), current_user)

    assert exc_info.value.status_code == 403


def test_post_map_filter_options_returns_distinct_options(monkeypatch):
    current_user = SimpleNamespace(is_admin=False, allowed_sections=("vodomery",), allowed_devices=("V-1",))

    def fake_load_requested_map_filter_options(_user, requested_layers):
        assert requested_layers == [{"layer_id": "vodomery", "filters": {"budova": ["F"], "patro": ["1.NP"]}}]
        return {
            "layers": [
                {
                    "layer_id": "vodomery",
                    "options": {
                        "budova": ["A", "F"],
                        "patro": ["1.NP", "2.NP"],
                    },
                }
            ],
        }

    monkeypatch.setattr(map_routes, "load_requested_map_filter_options", fake_load_requested_map_filter_options)

    response = map_routes.post_map_filter_options(
        map_routes.MapFilterOptionsRequest(
            layers=[{"layer_id": "vodomery", "filters": {"budova": ["F"], "patro": ["1.NP"]}}]
        ),
        current_user,
    )

    assert response.layers[0].layer_id == "vodomery"
    assert response.layers[0].options == {
        "budova": ["A", "F"],
        "patro": ["1.NP", "2.NP"],
    }


def test_post_map_filter_options_maps_authorization_error_to_403(monkeypatch):
    current_user = SimpleNamespace(is_admin=False, allowed_sections=(), allowed_devices=())
    monkeypatch.setattr(
        map_routes,
        "load_requested_map_filter_options",
        lambda *_: (_ for _ in ()).throw(AuthorizationError("forbidden")),
    )

    with pytest.raises(HTTPException) as exc_info:
        map_routes.post_map_filter_options(map_routes.MapFilterOptionsRequest(layers=[]), current_user)

    assert exc_info.value.status_code == 403


def test_get_map_image_returns_file_response(monkeypatch, tmp_path):
    current_user = SimpleNamespace(is_admin=False, allowed_sections=("vodomery",), allowed_devices=("V-1",))
    image_path = tmp_path / "device.jpg"
    image_path.write_bytes(b"image-bytes")

    def fake_load_map_feature_image_file(_user, *, layer_id, identifier):
        assert layer_id == "vodomery"
        assert identifier == "V-1"
        return MapFeatureImageFile(path=image_path, media_type="image/jpeg")

    monkeypatch.setattr(map_routes, "load_map_feature_image_file", fake_load_map_feature_image_file)

    response = map_routes.get_map_image("vodomery", "V-1", current_user)

    assert Path(response.path) == image_path
    assert response.media_type == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=300"
    assert response.headers["vary"] == "Cookie"


def test_get_map_image_maps_missing_photo_to_404(monkeypatch):
    current_user = SimpleNamespace(is_admin=False, allowed_sections=("vodomery",), allowed_devices=("V-1",))
    monkeypatch.setattr(
        map_routes,
        "load_map_feature_image_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(MapFeatureImageNotFound("missing")),
    )

    with pytest.raises(HTTPException) as exc_info:
        map_routes.get_map_image("vodomery", "V-1", current_user)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Fotka neni dostupna."


def test_get_map_image_maps_authorization_error_to_403(monkeypatch):
    current_user = SimpleNamespace(is_admin=False, allowed_sections=("vodomery",), allowed_devices=("V-1",))
    monkeypatch.setattr(
        map_routes,
        "load_map_feature_image_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AuthorizationError("forbidden")),
    )

    with pytest.raises(HTTPException) as exc_info:
        map_routes.get_map_image("vodomery", "V-1", current_user)

    assert exc_info.value.status_code == 403
