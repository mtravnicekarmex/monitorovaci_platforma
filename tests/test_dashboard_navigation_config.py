import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.navigation_config import (
    SIDEBAR_SECTION_ORDER,
    get_configurable_page_keys,
    get_configurable_section_keys,
    get_dashboard_pages,
    get_page_definition,
    normalize_page_keys,
)


def test_sidebar_section_order_matches_requested_dashboard_order():
    assert SIDEBAR_SECTION_ORDER == (
        "vodomery",
        "elektromery",
        "plynomery",
        "kalorimetry",
        "manometry",
        "nabijecky",
        "revize",
        "mapove_podklady",
    )


def test_expected_zero_footer_page_was_merged_into_alerting():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "web_search_monitor" in footer_page_keys
    assert "expected_zero" not in footer_page_keys
    assert "alerting" in footer_page_keys
    assert "vodomery_alerting" not in footer_page_keys
    assert "plynomery_alerting" not in footer_page_keys
    assert footer_page_keys.index("web_search_monitor") < footer_page_keys.index("alerting")


def test_scheduler_health_footer_page_is_after_alerting():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "alerting" in footer_page_keys
    assert "scheduler_health" in footer_page_keys
    assert "muj_ucet" in footer_page_keys
    assert footer_page_keys.index("alerting") < footer_page_keys.index("scheduler_health")
    assert footer_page_keys.index("scheduler_health") < footer_page_keys.index("muj_ucet")


def test_system_health_footer_page_is_after_scheduler_health():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "scheduler_health" in footer_page_keys
    assert "system_health" in footer_page_keys
    assert "outlier_review" in footer_page_keys
    assert footer_page_keys.index("scheduler_health") < footer_page_keys.index("system_health")
    assert footer_page_keys.index("system_health") < footer_page_keys.index("outlier_review")


def test_shared_outlier_review_footer_page_is_after_system_health():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert "system_health" in footer_page_keys
    assert "prediction_performance" in footer_page_keys
    assert "outlier_review" in footer_page_keys
    assert "vodomery_outlier_review" not in footer_page_keys
    assert "plynomery_outlier_review" not in footer_page_keys
    assert footer_page_keys.index("system_health") < footer_page_keys.index("prediction_performance")
    assert footer_page_keys.index("prediction_performance") < footer_page_keys.index("outlier_review")


def test_prediction_performance_footer_page_is_admin_only():
    page = get_page_definition("prediction_performance")
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]

    assert page is not None
    assert page.admin_only is True
    assert page.configurable is False
    assert "prediction_performance" in footer_page_keys


def test_manometry_section_and_page_are_configurable():
    section_keys = get_configurable_section_keys()
    page_keys = get_configurable_page_keys(section_keys)

    assert "manometry" in section_keys
    assert "manometry_overview" in page_keys
    assert "manometry_list" in page_keys


def test_meter_list_pages_are_configurable():
    page_keys = get_configurable_page_keys(("vodomery", "plynomery", "elektromery", "kalorimetry", "manometry"))

    assert "vodomery_list" in page_keys
    assert "plynomery_list" in page_keys
    assert "elektromery_list" in page_keys
    assert "kalorimetry_list" in page_keys
    assert "manometry_list" in page_keys


def test_nabijecky_section_and_page_are_configurable():
    section_keys = get_configurable_section_keys()
    page_keys = get_configurable_page_keys(section_keys)

    assert "nabijecky" in section_keys
    assert "nabijecky_overview" in page_keys


def test_revize_section_and_page_are_configurable():
    section_keys = get_configurable_section_keys()
    page_keys = get_configurable_page_keys(section_keys)

    assert "revize" in section_keys
    assert "revize_overview" in page_keys


def test_mapove_podklady_section_and_page_are_configurable():
    section_keys = get_configurable_section_keys()
    page_keys = get_configurable_page_keys(section_keys)
    page = get_page_definition("mapove_podklady_map")

    assert "mapove_podklady" in section_keys
    assert page is not None
    assert page.section_key == "mapove_podklady"
    assert page.configurable is True
    assert "mapove_podklady_map" in page_keys


def test_sprava_section_exposes_only_web_search_to_users():
    section_keys = get_configurable_section_keys()
    page_keys = get_configurable_page_keys(("sprava",))

    assert "sprava" in section_keys
    assert page_keys == ["web_search_monitor"]


def test_map_layers_admin_page_is_admin_footer_page():
    footer_page_keys = [page.key for page in get_dashboard_pages("footer")]
    page = get_page_definition("map_layers_admin")

    assert page is not None
    assert page.section_key == "sprava"
    assert page.admin_only is True
    assert page.configurable is False
    assert "map_layers_admin" in footer_page_keys
    assert footer_page_keys.index("web_search_monitor") < footer_page_keys.index("map_layers_admin")
    assert footer_page_keys.index("map_layers_admin") < footer_page_keys.index("alerting")


def test_dashboard_overview_is_configurable_without_section():
    page = get_page_definition("dashboard_overview")
    page_keys = get_configurable_page_keys()

    assert page is not None
    assert page.section_key is None
    assert page.configurable is True
    assert "dashboard_overview" in page_keys
    assert normalize_page_keys(["dashboard_overview"], allowed_section_keys=("sprava",)) == ["dashboard_overview"]


def test_dashboard_overview_is_first_main_page():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert main_page_keys[0] == "dashboard_overview"
    assert "vodomery_overview" in main_page_keys
    assert main_page_keys.index("dashboard_overview") < main_page_keys.index("vodomery_overview")


def test_vodomery_billing_page_is_in_main_navigation_after_branch_overview():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "vodomery_list" in main_page_keys
    assert "vodomery_branch_overview" in main_page_keys
    assert "vodomery_billing" in main_page_keys
    assert main_page_keys.index("vodomery_overview") < main_page_keys.index("vodomery_list")
    assert main_page_keys.index("vodomery_list") < main_page_keys.index("vodomery_branch_overview")
    assert main_page_keys.index("vodomery_branch_overview") < main_page_keys.index("vodomery_billing")


def test_meter_list_pages_are_after_section_overviews():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert main_page_keys.index("manometry_overview") < main_page_keys.index("manometry_list")
    assert main_page_keys.index("plynomery_overview") < main_page_keys.index("plynomery_list")
    assert main_page_keys.index("elektromery_overview") < main_page_keys.index("elektromery_list")
    assert main_page_keys.index("kalorimetry_overview") < main_page_keys.index("kalorimetry_list")


def test_vodomery_reports_page_is_after_billing():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "vodomery_billing" in main_page_keys
    assert "vodomery_reports" in main_page_keys
    assert "vodomery_anomalie_eventy" in main_page_keys
    assert main_page_keys.index("vodomery_billing") < main_page_keys.index("vodomery_reports")
    assert main_page_keys.index("vodomery_reports") < main_page_keys.index("vodomery_anomalie_eventy")


def test_plynomery_anomalie_eventy_page_is_between_overview_and_detail():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "plynomery_overview" in main_page_keys
    assert "plynomery_list" in main_page_keys
    assert "plynomery_anomalie_eventy" in main_page_keys
    assert "plynomery_detail" in main_page_keys
    assert main_page_keys.index("plynomery_overview") < main_page_keys.index("plynomery_list")
    assert main_page_keys.index("plynomery_list") < main_page_keys.index("plynomery_anomalie_eventy")
    assert main_page_keys.index("plynomery_anomalie_eventy") < main_page_keys.index("plynomery_detail")


def test_elektromery_reports_page_is_after_detail():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "elektromery_import" in main_page_keys
    assert "elektromery_list" in main_page_keys
    assert "elektromery_detail" in main_page_keys
    assert "elektromery_reports" in main_page_keys
    assert main_page_keys.index("elektromery_overview") < main_page_keys.index("elektromery_list")
    assert main_page_keys.index("elektromery_list") < main_page_keys.index("elektromery_detail")
    assert main_page_keys.index("elektromery_detail") < main_page_keys.index("elektromery_import")
    assert main_page_keys.index("elektromery_import") < main_page_keys.index("elektromery_reports")


def test_elektromery_new_devices_page_is_after_reports():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "elektromery_reports" in main_page_keys
    assert "elektromery_new_devices" in main_page_keys
    assert main_page_keys.index("elektromery_reports") < main_page_keys.index("elektromery_new_devices")


def test_nabijecky_page_is_after_elektromery_pages():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "elektromery_new_devices" in main_page_keys
    assert "nabijecky_overview" in main_page_keys
    assert main_page_keys.index("elektromery_new_devices") < main_page_keys.index("nabijecky_overview")


def test_revize_page_is_after_kalorimetry_pages():
    main_page_keys = [page.key for page in get_dashboard_pages("main")]

    assert "kalorimetry_list" in main_page_keys
    assert "kalorimetry_detail" in main_page_keys
    assert "revize_overview" in main_page_keys
    assert "mapove_podklady_map" in main_page_keys
    assert main_page_keys.index("kalorimetry_overview") < main_page_keys.index("kalorimetry_list")
    assert main_page_keys.index("kalorimetry_list") < main_page_keys.index("kalorimetry_detail")
    assert main_page_keys.index("kalorimetry_detail") < main_page_keys.index("revize_overview")
    assert main_page_keys.index("revize_overview") < main_page_keys.index("mapove_podklady_map")
