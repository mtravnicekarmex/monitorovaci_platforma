from moduly.apps.dashboard.navigation_config import get_dashboard_pages


def test_web_search_footer_page_is_before_expected_zero():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "web_search_monitor" in footer_page_keys
    assert "expected_zero" in footer_page_keys
    assert footer_page_keys.index("web_search_monitor") < footer_page_keys.index("expected_zero")
