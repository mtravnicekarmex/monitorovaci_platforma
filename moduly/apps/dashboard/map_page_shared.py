from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

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


MAP_IMAGE_ENDPOINT_PATH = "/api/v1/map/images"
MAP_IFRAME_FALLBACK_HEIGHT_PX = 920


def _layer_id(layer: dict[str, object]) -> str:
    return str(layer.get("layer_id") or "")


def _dict_value(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


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
        property_labels = {
            **_dict_value(catalog_layer.get("property_labels")),
            **_dict_value(layer_payload.get("property_labels")),
        }
        merged_layer = {
            **catalog_layer,
            **layer_payload,
            "property_labels": property_labels,
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
        :root {
            --map-sidebar-toggle-gutter: 2.5rem;
        }
        header[data-testid="stHeader"],
        .stApp > header {
            position: fixed !important;
            top: 0 !important;
            right: 0 !important;
            left: 0 !important;
            display: block !important;
            background: transparent !important;
            height: 0 !important;
            min-height: 0 !important;
            overflow: visible !important;
            pointer-events: none !important;
            z-index: 999999 !important;
        }
        header[data-testid="stHeader"] *,
        .stApp > header * {
            pointer-events: auto !important;
        }
        div[data-testid="stToolbar"],
        .stAppToolbar {
            display: flex !important;
            background: transparent !important;
            height: 0 !important;
            min-height: 0 !important;
            overflow: visible !important;
            pointer-events: none !important;
        }
        div[data-testid="stToolbar"] *,
        .stAppToolbar * {
            pointer-events: auto !important;
        }
        div[data-testid="stSidebarCollapsedControl"],
        button[data-testid="stSidebarCollapsedControl"],
        div[data-testid="collapsedControl"],
        button[data-testid="collapsedControl"],
        div[data-testid="stExpandSidebarButton"],
        button[data-testid="stExpandSidebarButton"] {
            position: fixed !important;
            top: 0.5rem !important;
            left: 0.25rem !important;
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            z-index: 1000000 !important;
        }
        button[data-testid="stSidebarCollapseButton"],
        button[kind="header"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            z-index: 1000000 !important;
        }
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"] {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
        }
        div[data-testid="stAppViewContainer"],
        section.main {
            padding-top: 0 !important;
        }
        section.main > div.block-container,
        div[data-testid="stMainBlockContainer"] {
            box-sizing: border-box;
            max-width: none !important;
            padding-top: 0 !important;
            padding-right: 0 !important;
            padding-bottom: 0 !important;
            padding-left: 0 !important;
        }
        body:has(div[data-testid="stExpandSidebarButton"]) section.main > div.block-container,
        body:has(div[data-testid="stExpandSidebarButton"]) div[data-testid="stMainBlockContainer"],
        body:has(button[data-testid="stExpandSidebarButton"]) section.main > div.block-container,
        body:has(button[data-testid="stExpandSidebarButton"]) div[data-testid="stMainBlockContainer"] {
            padding-left: var(--map-sidebar-toggle-gutter) !important;
        }
        section.main > div.block-container > div[data-testid="stVerticalBlock"],
        div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] {
            gap: 0 !important;
        }
        div[data-testid="stElementContainer"]:has(style),
        div[data-testid="stElementContainer"]:has(div[data-testid="stMarkdownContainer"] style) {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .st-key-map_page_layout {
            width: 100%;
            margin: 0 !important;
            padding: 0 !important;
        }
        .st-key-map_page_layout iframe {
            display: block;
            width: 100%;
            height: 100vh !important;
            height: 100dvh !important;
            margin: 0 !important;
        }
        @media (max-width: 720px) {
            .st-key-map_page_layout iframe {
                height: 100svh !important;
                height: 100dvh !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_map_page(
    *,
    page_key: str,
    map_context: str,
    empty_message: str,
    load_error_message: str,
) -> None:
    require_page_access(page_key)
    try:
        render_map_page_styles()
        access_token = get_auth_token()
        if not access_token:
            raise DashboardApiError("Chybi bearer token pro dashboard API.")

        catalog_payload = load_map_layer_catalog_payload(access_token, map_context=map_context)
        catalog_layers = normalize_catalog_layers(catalog_payload)
        if not catalog_layers:
            st.info(empty_message)
            return

        layer_ids = [_layer_id(layer) for layer in catalog_layers if _layer_id(layer)]

        with st.container(key="map_page_layout"):
            if not layer_ids:
                st.info("Vyber alespon jednu mapovou vrstvu.")
                return

            filter_options_request = build_map_features_request(layer_ids)
            filter_options_payload = load_map_filter_options_payload(
                access_token,
                filter_options_request,
                map_context=map_context,
            )
            options_by_layer = normalize_filter_options_payload(filter_options_payload)

            features_request = build_map_features_request(layer_ids)
            features_payload = load_map_features_payload(
                access_token,
                features_request,
                map_context=map_context,
            )
            leaflet_payload = _leaflet_map_payload(features_payload, catalog_layers, options_by_layer)

            components.html(
                build_leaflet_map_html(
                    leaflet_payload,
                    height_px=MAP_IFRAME_FALLBACK_HEIGHT_PX,
                    image_endpoint_url=_map_image_endpoint_url(),
                    fill_parent_height=True,
                ),
                height=MAP_IFRAME_FALLBACK_HEIGHT_PX,
                scrolling=False,
            )
    except DashboardApiError as exc:
        st.error(load_error_message)
        st.exception(exc)
