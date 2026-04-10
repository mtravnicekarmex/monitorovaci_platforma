from moduly.apps.dashboard.navigation_config import get_dashboard_pages


def test_web_search_footer_page_is_before_expected_zero():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "web_search_monitor" in footer_page_keys
    assert "expected_zero" in footer_page_keys
    assert footer_page_keys.index("web_search_monitor") < footer_page_keys.index("expected_zero")


def test_scheduler_health_footer_page_is_after_vodomery_alerting():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "vodomery_alerting" in footer_page_keys
    assert "scheduler_health" in footer_page_keys
    assert "muj_ucet" in footer_page_keys
    assert footer_page_keys.index("vodomery_alerting") < footer_page_keys.index("scheduler_health")
    assert footer_page_keys.index("scheduler_health") < footer_page_keys.index("muj_ucet")
