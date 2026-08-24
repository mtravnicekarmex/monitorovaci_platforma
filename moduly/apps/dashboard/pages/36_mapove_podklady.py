from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st
import streamlit.components.v1 as components


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import get_auth_token, require_page_access
from moduly.apps.dashboard.map_shared import (
    build_leaflet_map_html,
    build_map_features_request,
    load_map_filter_options_payload,
    load_map_features_payload,
    load_map_layer_catalog_payload,
    normalize_catalog_layers,
    normalize_filter_options_payload,
)


st.set_page_config(
    page_title="Mapove podklady - Mapa",
    page_icon="map",
    layout="wide",
)


require_page_access("mapove_podklady_map")
MAP_IMAGE_ENDPOINT_PATH = "/api/v1/map/images"
MAP_HTML_HEIGHT_PX = 920
MAP_IFRAME_HEIGHT_PX = MAP_HTML_HEIGHT_PX + 20


def _layer_id(layer: dict[str, object]) -> str:
    return str(layer.get("layer_id") or "")


def _request_header(name: str) -> str:
    headers = getattr(st.context, "headers", {}) or {}
    value = ""
    try:
        value = str(headers.get(name, "") or "")
    except AttributeError:
        value = ""
    if not value:
        try:
            value = str(headers.get(name.lower(), "") or "")
        except AttributeError:
            value = ""
    return value.split(",", 1)[0].strip()


def _dashboard_request_origin() -> str | None:
    host = _request_header("X-Forwarded-Host") or _request_header("Host")
    if not host or any(char in host for char in "/\\\r\n"):
        return None

    proto = _request_header("X-Forwarded-Proto") or "http"
    proto = proto.casefold()
    if proto not in {"http", "https"}:
        return None

    return f"{proto}://{host}"


def _map_image_endpoint_url() -> str:
    origin = _dashboard_request_origin()
    if not origin:
        return MAP_IMAGE_ENDPOINT_PATH
    return f"{origin}{MAP_IMAGE_ENDPOINT_PATH}"


def _leaflet_map_payload(
    features_payload: dict[str, object],
    catalog_layers: list[dict[str, object]],
    filter_options_by_layer: dict[str, dict[str, list[str]]],
) -> dict[str, object]:
    catalog_by_id = {_layer_id(layer): layer for layer in catalog_layers if _layer_id(layer)}
    raw_layers = features_payload.get("layers")
    if not isinstance(raw_layers, list):
        raw_layers = []

    layers: list[dict[str, object]] = []
    for layer_payload in raw_layers:
        if not isinstance(layer_payload, dict):
            continue
        layer_id = _layer_id(layer_payload)
        if not layer_id:
            continue
        catalog_layer = catalog_by_id.get(layer_id, {})
        merged_layer = {
            **catalog_layer,
            **layer_payload,
            "filter_fields": [
                field
                for field in catalog_layer.get("filter_fields", [])
                if isinstance(field, dict) and field.get("key")
            ],
            "filter_options": filter_options_by_layer.get(layer_id, {}),
        }
        layers.append(merged_layer)

    primary_layer_id = next(
        (
            _layer_id(layer)
            for layer in catalog_layers
            if _layer_id(layer) and bool(layer.get("default_visible", True))
        ),
        layers[0].get("layer_id") if layers else None,
    )
    return {
        **features_payload,
        "primary_layer_id": primary_layer_id,
        "layers": layers,
    }


def render_map_page_styles() -> None:
    st.markdown(
        """
        <style>
        .st-key-map_page_layout iframe {
            display: block;
            width: 100%;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page() -> None:
    render_map_page_styles()
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")

    catalog_payload = load_map_layer_catalog_payload(access_token)
    catalog_layers = normalize_catalog_layers(catalog_payload)
    if not catalog_layers:
        st.info("Pro aktualniho uzivatele nejsou dostupne zadne mapove vrstvy.")
        return

    layer_ids = [_layer_id(layer) for layer in catalog_layers if _layer_id(layer)]

    with st.container(key="map_page_layout"):
        if not layer_ids:
            st.info("Vyber alespon jednu mapovou vrstvu.")
            return

        filter_options_request = build_map_features_request(layer_ids)
        filter_options_payload = load_map_filter_options_payload(access_token, filter_options_request)
        options_by_layer = normalize_filter_options_payload(filter_options_payload)

        features_request = build_map_features_request(layer_ids)
        features_payload = load_map_features_payload(access_token, features_request)
        leaflet_payload = _leaflet_map_payload(features_payload, catalog_layers, options_by_layer)

        components.html(
            build_leaflet_map_html(
                leaflet_payload,
                height_px=MAP_HTML_HEIGHT_PX,
                image_endpoint_url=_map_image_endpoint_url(),
            ),
            height=MAP_IFRAME_HEIGHT_PX,
            scrolling=False,
        )


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist mapove podklady.")
    st.exception(exc)
