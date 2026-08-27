from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAP_PAGE_PATH = PROJECT_ROOT / "moduly" / "apps" / "dashboard" / "pages" / "36_mapove_podklady.py"
REVIZE_MAP_PAGE_PATH = PROJECT_ROOT / "moduly" / "apps" / "dashboard" / "pages" / "40_revize_mapa.py"
MAP_PAGE_SHARED_PATH = PROJECT_ROOT / "moduly" / "apps" / "dashboard" / "map_page_shared.py"


def test_map_page_uses_full_width_map_with_in_map_controls():
    source = MAP_PAGE_SHARED_PATH.read_text(encoding="utf-8")
    map_page_source = MAP_PAGE_PATH.read_text(encoding="utf-8")
    revize_map_page_source = REVIZE_MAP_PAGE_PATH.read_text(encoding="utf-8")

    assert "MAP_IFRAME_FALLBACK_HEIGHT_PX = 920" in source
    assert "def _leaflet_map_payload(" in source
    assert "def _dict_value(" in source
    assert '"property_labels": property_labels' in source
    assert '**_dict_value(catalog_layer.get("property_labels"))' in source
    assert '**_dict_value(layer_payload.get("property_labels"))' in source
    assert '"filter_fields": [' in source
    assert '"filter_options": filter_options_by_layer.get(layer_id, {})' in source
    assert "filter_options_request = build_map_features_request(layer_ids)" in source
    assert "features_request = build_map_features_request(layer_ids)" in source
    assert "leaflet_payload = _leaflet_map_payload(features_payload, catalog_layers, options_by_layer)" in source
    assert "map_context=map_context" in source
    assert "with st.container(key=\"map_page_layout\")" in source
    assert "filter_col, map_col = st.columns" not in source
    assert "with map_col" not in source
    assert "st.columns" not in source
    assert "st.expander" not in source
    assert "st.multiselect" not in source
    assert "--map-sidebar-toggle-gutter: 2.5rem" in source
    assert 'header[data-testid="stHeader"]' in source
    assert "position: fixed !important" in source
    assert "top: 0 !important" in source
    assert "right: 0 !important" in source
    assert "left: 0 !important" in source
    assert "background: transparent !important" in source
    assert "overflow: visible !important" in source
    assert "pointer-events: none !important" in source
    assert 'div[data-testid="stToolbar"]' in source
    assert ".stAppToolbar" in source
    assert 'div[data-testid="stSidebarCollapsedControl"]' in source
    assert 'div[data-testid="stExpandSidebarButton"]' in source
    assert 'button[data-testid="stExpandSidebarButton"]' in source
    assert "top: 0.5rem !important" in source
    assert "left: 0.25rem !important" in source
    assert "z-index: 999999 !important" in source
    assert 'button[data-testid="stSidebarCollapseButton"]' in source
    assert 'button[kind="header"]' in source
    assert "z-index: 1000000 !important" in source
    assert 'div[data-testid="stDecoration"]' in source
    assert 'div[data-testid="stStatusWidget"]' in source
    hidden_decoration_block = source[
        source.index('div[data-testid="stDecoration"]') : source.index(
            "div[data-testid=\"stAppViewContainer\"]"
        )
    ]
    assert "stToolbar" not in hidden_decoration_block
    assert 'div[data-testid="stMainBlockContainer"]' in source
    assert "max-width: none !important" in source
    assert "padding-top: 0 !important" in source
    assert "padding-right: 0 !important" in source
    assert "padding-bottom: 0 !important" in source
    assert "padding-left: 0 !important" in source
    assert 'body:has(div[data-testid="stExpandSidebarButton"])' in source
    assert "padding-left: var(--map-sidebar-toggle-gutter) !important" in source
    assert "gap: 0 !important" in source
    assert 'div[data-testid="stElementContainer"]:has(style)' in source
    assert "width: 100%;" in source
    assert "width: 100%%;" not in source
    assert "height: 100vh !important" in source
    assert "height: 100dvh !important" in source
    assert "height: 100svh !important" in source
    assert "height_px=MAP_IFRAME_FALLBACK_HEIGHT_PX" in source
    assert "height=MAP_IFRAME_FALLBACK_HEIGHT_PX" in source
    assert "fill_parent_height=True" in source
    assert "flex-direction: column !important" not in source
    assert "order: 2" not in source
    assert "order: 1" not in source
    assert "Mapa je na telefonu zobrazena nad timto panelem." not in source
    assert 'map_context="evidence"' in map_page_source
    assert 'page_key="mapove_podklady_map"' in map_page_source
    assert 'map_context="revize"' in revize_map_page_source
    assert 'page_key="revize_map"' in revize_map_page_source


def test_map_page_does_not_pass_main_token_to_iframe():
    source = "\n".join(
        [
            MAP_PAGE_SHARED_PATH.read_text(encoding="utf-8"),
            MAP_PAGE_PATH.read_text(encoding="utf-8"),
            REVIZE_MAP_PAGE_PATH.read_text(encoding="utf-8"),
        ]
    )

    assert "access_token=access_token" not in source
    assert "image_endpoint_url=_map_image_endpoint_url()" in source
    assert "document_endpoint_url=_map_document_endpoint_url()" in source
    assert "get_dashboard_browser_api_base_url" not in source
    assert "DASHBOARD_BROWSER_API_BASE_URL" not in source
