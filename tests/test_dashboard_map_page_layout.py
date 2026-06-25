from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAP_PAGE_PATH = PROJECT_ROOT / "moduly" / "apps" / "dashboard" / "pages" / "36_mapove_podklady.py"


def test_mobile_map_page_keeps_filters_before_map():
    source = MAP_PAGE_PATH.read_text(encoding="utf-8")

    assert "filter_col, map_col = st.columns" in source
    assert "flex-direction: column !important" in source
    assert "order: 2" not in source
    assert "order: 1" not in source
    assert "Mapa je na telefonu zobrazena nad timto panelem." not in source


def test_map_page_does_not_pass_main_token_to_iframe():
    source = MAP_PAGE_PATH.read_text(encoding="utf-8")

    assert "access_token=access_token" not in source
    assert "image_endpoint_url=_map_image_endpoint_url()" in source
    assert "get_dashboard_browser_api_base_url" not in source
    assert "DASHBOARD_BROWSER_API_BASE_URL" not in source
