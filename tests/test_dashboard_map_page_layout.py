from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAP_PAGE_PATH = PROJECT_ROOT / "moduly" / "apps" / "dashboard" / "pages" / "36_mapove_podklady.py"


def test_map_page_uses_full_width_map_with_in_map_controls():
    source = MAP_PAGE_PATH.read_text(encoding="utf-8")

    assert "MAP_HTML_HEIGHT_PX = 920" in source
    assert "MAP_IFRAME_HEIGHT_PX = MAP_HTML_HEIGHT_PX + 20" in source
    assert "def _leaflet_map_payload(" in source
    assert '"filter_fields": [' in source
    assert '"filter_options": filter_options_by_layer.get(layer_id, {})' in source
    assert "filter_options_request = build_map_features_request(layer_ids)" in source
    assert "features_request = build_map_features_request(layer_ids)" in source
    assert "leaflet_payload = _leaflet_map_payload(features_payload, catalog_layers, options_by_layer)" in source
    assert "with st.container(key=\"map_page_layout\")" in source
    assert "filter_col, map_col = st.columns" not in source
    assert "with map_col" not in source
    assert "st.columns" not in source
    assert "st.expander" not in source
    assert "st.multiselect" not in source
    assert "height_px=MAP_HTML_HEIGHT_PX" in source
    assert "height=MAP_IFRAME_HEIGHT_PX" in source
    assert "flex-direction: column !important" not in source
    assert "order: 2" not in source
    assert "order: 1" not in source
    assert "Mapa je na telefonu zobrazena nad timto panelem." not in source


def test_map_page_does_not_pass_main_token_to_iframe():
    source = MAP_PAGE_PATH.read_text(encoding="utf-8")

    assert "access_token=access_token" not in source
    assert "image_endpoint_url=_map_image_endpoint_url()" in source
    assert "get_dashboard_browser_api_base_url" not in source
    assert "DASHBOARD_BROWSER_API_BASE_URL" not in source
