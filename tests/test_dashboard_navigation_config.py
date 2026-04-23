import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.navigation_config import (
    get_configurable_page_keys,
    get_configurable_section_keys,
    get_dashboard_pages,
)


def test_expected_zero_footer_page_was_merged_into_vodomery_alerting():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "web_search_monitor" in footer_page_keys
    assert "expected_zero" not in footer_page_keys
    assert "vodomery_alerting" in footer_page_keys
    assert footer_page_keys.index("web_search_monitor") < footer_page_keys.index("vodomery_alerting")


def test_scheduler_health_footer_page_is_after_vodomery_alerting():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "vodomery_alerting" in footer_page_keys
    assert "plynomery_alerting" in footer_page_keys
    assert "scheduler_health" in footer_page_keys
    assert "muj_ucet" in footer_page_keys
    assert footer_page_keys.index("vodomery_alerting") < footer_page_keys.index("scheduler_health")
    assert footer_page_keys.index("scheduler_health") < footer_page_keys.index("muj_ucet")


def test_plynomery_outlier_review_footer_page_is_after_vodomery_outlier_review():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "vodomery_outlier_review" in footer_page_keys
    assert "plynomery_outlier_review" in footer_page_keys
    assert footer_page_keys.index("vodomery_outlier_review") < footer_page_keys.index("plynomery_outlier_review")


def test_manometry_section_and_page_are_configurable():
    section_keys = get_configurable_section_keys()
    page_keys = get_configurable_page_keys(section_keys)

    assert "manometry" in section_keys
    assert "manometry_overview" in page_keys


def test_dashboard_overview_is_first_main_page():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert main_page_keys[0] == "dashboard_overview"
    assert "vodomery_overview" in main_page_keys
    assert main_page_keys.index("dashboard_overview") < main_page_keys.index("vodomery_overview")


def test_vodomery_billing_page_is_in_main_navigation_after_branch_overview():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "vodomery_branch_overview" in main_page_keys
    assert "vodomery_billing" in main_page_keys
    assert main_page_keys.index("vodomery_branch_overview") < main_page_keys.index("vodomery_billing")


def test_plynomery_anomalie_eventy_page_is_between_overview_and_detail():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "plynomery_overview" in main_page_keys
    assert "plynomery_anomalie_eventy" in main_page_keys
    assert "plynomery_detail" in main_page_keys
    assert main_page_keys.index("plynomery_overview") < main_page_keys.index("plynomery_anomalie_eventy")
    assert main_page_keys.index("plynomery_anomalie_eventy") < main_page_keys.index("plynomery_detail")
