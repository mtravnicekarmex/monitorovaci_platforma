from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st
import streamlit.components.v1 as components


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    get_dashboard_browser_api_base_url,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access
from moduly.apps.dashboard.map_shared import (
    build_leaflet_map_html,
    build_map_features_request,
    load_map_filter_options_payload,
    load_map_features_payload,
    load_map_layer_catalog_payload,
    merge_selected_filter_options,
    normalize_catalog_layers,
    normalize_filter_options_payload,
)
from moduly.apps.dashboard.responsive import render_responsive_page_styles


st.set_page_config(
    page_title="Mapove podklady - Mapa",
    page_icon="map",
    layout="wide",
)


require_page_access("mapove_podklady_map")


def _layer_id(layer: dict[str, object]) -> str:
    return str(layer.get("layer_id") or "")


def _format_layer_label(layer_by_id: dict[str, dict[str, object]], layer_id: str) -> str:
    layer = layer_by_id.get(layer_id, {})
    title = str(layer.get("title") or layer_id)
    layer_kind = str(layer.get("layer_kind") or "context")
    return f"{title} ({layer_kind})"


def _session_filters_by_layer(
    selected_layer_ids: list[str],
    layer_by_id: dict[str, dict[str, object]],
) -> dict[str, dict[str, list[str]]]:
    filters_by_layer: dict[str, dict[str, list[str]]] = {}
    for layer_id in selected_layer_ids:
        layer = layer_by_id.get(layer_id, {})
        layer_filters: dict[str, list[str]] = {}
        filter_fields = [
            field
            for field in layer.get("filter_fields", [])
            if isinstance(field, dict) and field.get("key")
        ]
        for field in filter_fields:
            filter_key = str(field["key"])
            state_key = f"map_filter_{layer_id}_{filter_key}"
            raw_values = st.session_state.get(state_key, [])
            if not isinstance(raw_values, list):
                raw_values = []
            values = [str(value) for value in raw_values if str(value).strip()]
            if values:
                layer_filters[filter_key] = values
        filters_by_layer[layer_id] = layer_filters
    return filters_by_layer


def render_map_page_styles() -> None:
    st.markdown(
        """
        <style>
        .map-mobile-filter-note {
            display: none;
        }

        @media (max-width: 720px) {
            .map-mobile-filter-note {
                display: block;
                margin: 0.25rem 0 0.75rem;
                color: #64748b;
                font-size: 0.85rem;
            }

            .st-key-map_page_layout [data-testid="stHorizontalBlock"] {
                flex-direction: column !important;
            }

            .st-key-map_page_layout [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                flex: 1 1 100% !important;
                width: 100% !important;
                min-width: 100% !important;
            }

            .st-key-map_page_layout [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
                order: 2;
            }

            .st-key-map_page_layout [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {
                order: 1;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page() -> None:
    render_responsive_page_styles()
    render_map_page_styles()
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")

    catalog_payload = load_map_layer_catalog_payload(access_token)
    catalog_layers = normalize_catalog_layers(catalog_payload)
    if not catalog_layers:
        st.info("Pro aktualniho uzivatele nejsou dostupne zadne mapove vrstvy.")
        return

    layer_by_id = {_layer_id(layer): layer for layer in catalog_layers if _layer_id(layer)}
    layer_ids = list(layer_by_id)
    default_layer_ids = [
        layer_id
        for layer_id, layer in layer_by_id.items()
        if bool(layer.get("default_visible", True))
    ] or layer_ids[:1]

    with st.container(key="map_page_layout"):
        filter_col, map_col = st.columns([0.85, 4.15], gap="small")

    with filter_col:
        selected_layer_ids = st.multiselect(
            "Aktivni vrstvy",
            options=layer_ids,
            default=default_layer_ids,
            format_func=lambda layer_id: _format_layer_label(layer_by_id, layer_id),
            help="Vyber jednu nebo vice vrstev, ktere se maji nacist do mapy.",
        )

        if st.button("Obnovit katalog a data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if not selected_layer_ids:
        with map_col:
            st.info("Vyber alespon jednu mapovou vrstvu.")
        return

    session_filters_by_layer = _session_filters_by_layer(list(selected_layer_ids), layer_by_id)
    filter_options_request = build_map_features_request(list(selected_layer_ids), session_filters_by_layer)
    filter_options_payload = load_map_filter_options_payload(access_token, filter_options_request)
    options_by_layer = normalize_filter_options_payload(filter_options_payload)

    filters_by_layer: dict[str, dict[str, list[str]]] = {}
    with filter_col:
        st.markdown(
            '<div class="map-mobile-filter-note">Mapa je na telefonu zobrazena nad timto panelem.</div>',
            unsafe_allow_html=True,
        )
        st.subheader("Filtry")
        for layer_id in selected_layer_ids:
            layer = layer_by_id[layer_id]
            filter_fields = [
                field
                for field in layer.get("filter_fields", [])
                if isinstance(field, dict) and field.get("key")
            ]
            layer_options = options_by_layer.get(layer_id, {})
            current_layer_filters = session_filters_by_layer.get(layer_id, {})

            with st.expander(_format_layer_label(layer_by_id, layer_id), expanded=True):
                layer_filters: dict[str, list[str]] = {}
                if not filter_fields:
                    st.caption("Vrstva nema nastavene filtrovaci sloupce.")
                for field in filter_fields:
                    filter_key = str(field["key"])
                    label = str(field.get("label") or field.get("property_key") or filter_key)
                    current_values = current_layer_filters.get(filter_key, [])
                    options = merge_selected_filter_options(layer_options.get(filter_key, []), current_values)
                    selected_values = st.multiselect(
                        label,
                        options=options,
                        default=current_values,
                        key=f"map_filter_{layer_id}_{filter_key}",
                        help="Vice hodnot v jednom filtru se chova jako OR. Vice filtru ve vrstve se kombinuje jako AND.",
                    )
                    if selected_values:
                        layer_filters[filter_key] = selected_values
                filters_by_layer[layer_id] = layer_filters

    filtered_request = build_map_features_request(list(selected_layer_ids), filters_by_layer)
    filtered_payload = load_map_features_payload(access_token, filtered_request)

    with map_col:
        components.html(
            build_leaflet_map_html(
                filtered_payload,
                height_px=880,
                image_api_base_url=get_dashboard_browser_api_base_url(),
                access_token=access_token,
            ),
            height=900,
            scrolling=False,
        )


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist mapove podklady.")
    st.exception(exc)
