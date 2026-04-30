from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DashboardSection:
    key: str
    label: str
    icon: str
    requires_device_permissions: bool = True


@dataclass(frozen=True)
class DashboardPage:
    key: str
    path: str
    title: str
    icon: str
    section_key: str | None = None
    sidebar_location: str = "main"
    admin_only: bool = False
    configurable: bool = False


SECTIONS: tuple[DashboardSection, ...] = (
    DashboardSection(key="vodomery", label="Vodoměry", icon="💧"),
    DashboardSection(key="manometry", label="Manometry", icon="🎚️"),
    DashboardSection(key="plynomery", label="Plynoměry", icon="🔥"),
    DashboardSection(key="elektromery", label="Elektroměry", icon="⚡"),
    DashboardSection(key="kalorimetry", label="Kalorimetry", icon="♨️"),
)


PAGES: tuple[DashboardPage, ...] = (
    DashboardPage(
        key="dashboard_overview",
        path="pages/0_overview.py",
        title="Overview",
        icon="🏠",
    ),
    DashboardPage(
        key="vodomery_overview",
        path="pages/2_vodomery.py",
        title="Přehled",
        icon="💧",
        section_key="vodomery",
        configurable=True,
    ),
    DashboardPage(
        key="vodomery_branch_overview",
        path="pages/8_prehled_vetve.py",
        title="Přehled větve",
        icon="🌿",
        section_key="vodomery",
        admin_only=True,
    ),
    DashboardPage(
        key="vodomery_billing",
        path="pages/19_vodomery_fakturace.py",
        title="Fakturace",
        icon="🧾",
        section_key="vodomery",
        admin_only=True,
    ),
    DashboardPage(
        key="vodomery_anomalie_eventy",
        path="pages/4_vodomery_anomalie_eventy.py",
        title="Anomalie a eventy",
        icon="🚨",
        section_key="vodomery",
        configurable=True,
    ),
    DashboardPage(
        key="vodomery_detail",
        path="pages/5_vodomery_detail.py",
        title="Detail",
        icon="🧭",
        section_key="vodomery",
        configurable=True,
    ),
    DashboardPage(
        key="manometry_overview",
        path="pages/18_manometry.py",
        title="Přehled",
        icon="🎚️",
        section_key="manometry",
        configurable=True,
    ),
    DashboardPage(
        key="plynomery_overview",
        path="pages/9_plynomery.py",
        title="Přehled",
        icon="🔥",
        section_key="plynomery",
        configurable=True,
    ),
    DashboardPage(
        key="plynomery_anomalie_eventy",
        path="pages/21_plynomery_anomalie_eventy.py",
        title="Anomalie a eventy",
        icon="🚨",
        section_key="plynomery",
        configurable=True,
    ),
    DashboardPage(
        key="plynomery_detail",
        path="pages/10_plynomery_detail.py",
        title="Detail",
        icon="🧭",
        section_key="plynomery",
        configurable=True,
    ),
    DashboardPage(
        key="elektromery_overview",
        path="pages/13_elektromery.py",
        title="Přehled",
        icon="⚡",
        section_key="elektromery",
        configurable=True,
    ),
    DashboardPage(
        key="elektromery_detail",
        path="pages/14_elektromery_detail.py",
        title="Detail",
        icon="🧭",
        section_key="elektromery",
        configurable=True,
    ),
    DashboardPage(
        key="elektromery_import",
        path="pages/23_elektromery_import.py",
        title="Import XLSX",
        icon="📤",
        section_key="elektromery",
        admin_only=True,
    ),
    DashboardPage(
        key="elektromery_reports",
        path="pages/24_elektromery_reporty.py",
        title="Reporty",
        icon="📈",
        section_key="elektromery",
        admin_only=True,
    ),
    DashboardPage(
        key="elektromery_new_devices",
        path="pages/25_elektromery_nove.py",
        title="Nové elektroměry",
        icon="🆕",
        section_key="elektromery",
        admin_only=True,
    ),
    DashboardPage(
        key="kalorimetry_overview",
        path="pages/11_kalorimetry.py",
        title="Přehled",
        icon="♨️",
        section_key="kalorimetry",
        configurable=True,
    ),
    DashboardPage(
        key="kalorimetry_detail",
        path="pages/12_kalorimetry_detail.py",
        title="Detail",
        icon="🧭",
        section_key="kalorimetry",
        configurable=True,
    ),
    DashboardPage(
        key="sprava_uzivatelu",
        path="pages/1_sprava_uzivatelu.py",
        title="Sprava uzivatelu",
        icon="👤",
        sidebar_location="footer",
        admin_only=True,
    ),
    DashboardPage(
        key="web_search_monitor",
        path="pages/15_web_search.py",
        title="Web search",
        icon="🔍",
        sidebar_location="footer",
        admin_only=True,
    ),
    DashboardPage(
        key="alerting",
        path="pages/7_alerting.py",
        title="Alerting",
        icon="📣",
        sidebar_location="footer",
        admin_only=True,
    ),
    DashboardPage(
        key="scheduler_health",
        path="pages/16_scheduler_health.py",
        title="Health scheduleru",
        icon="🩺",
        sidebar_location="footer",
        admin_only=True,
    ),
    DashboardPage(
        key="outlier_review",
        path="pages/17_outlier_review.py",
        title="Review outlieru",
        icon="🔎",
        sidebar_location="footer",
        admin_only=True,
    ),
    DashboardPage(
        key="muj_ucet",
        path="pages/3_muj_ucet.py",
        title="Můj účet",
        icon="🔑",
        sidebar_location="footer",
    ),
)


SECTION_MAP = {section.key: section for section in SECTIONS}
PAGE_MAP = {page.key: page for page in PAGES}
PAGE_FILENAME_MAP = {Path(page.path).name: page for page in PAGES}


def get_section_definition(section_key: str) -> DashboardSection | None:
    return SECTION_MAP.get(section_key)


def get_page_definition(page_key: str) -> DashboardPage | None:
    return PAGE_MAP.get(page_key)


def get_page_definition_by_path(page_path: str | PathLike[str] | object) -> DashboardPage | None:
    if not isinstance(page_path, (str, PathLike)):
        return None
    return PAGE_FILENAME_MAP.get(Path(page_path).name)


def get_configurable_section_keys() -> list[str]:
    return [section.key for section in SECTIONS]


def get_configurable_page_keys(section_keys: Iterable[str] | None = None) -> list[str]:
    allowed_sections = None if section_keys is None else set(normalize_section_keys(section_keys))
    page_keys: list[str] = []
    for page in PAGES:
        if not page.configurable:
            continue
        if allowed_sections is not None and page.section_key not in allowed_sections:
            continue
        page_keys.append(page.key)
    return page_keys


def get_dashboard_pages(sidebar_location: str | None = None) -> tuple[DashboardPage, ...]:
    if sidebar_location is None:
        return PAGES
    return tuple(page for page in PAGES if page.sidebar_location == sidebar_location)


def normalize_section_keys(section_keys: Iterable[str] | None) -> list[str]:
    if section_keys is None:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for section_key in section_keys:
        if section_key not in SECTION_MAP or section_key in seen:
            continue
        seen.add(section_key)
        normalized.append(section_key)
    return normalized


def normalize_page_keys(page_keys: Iterable[str] | None, allowed_section_keys: Iterable[str] | None = None) -> list[str]:
    if page_keys is None:
        return []

    allowed_sections = None if allowed_section_keys is None else set(normalize_section_keys(allowed_section_keys))
    normalized: list[str] = []
    seen: set[str] = set()

    for page_key in page_keys:
        page = PAGE_MAP.get(page_key)
        if page is None or not page.configurable or page_key in seen:
            continue
        if allowed_sections is not None and page.section_key not in allowed_sections:
            continue
        seen.add(page_key)
        normalized.append(page_key)
    return normalized


def format_section_label(section_key: str) -> str:
    section = get_section_definition(section_key)
    if section is None:
        return section_key
    return f"{section.icon} {section.label}"


def format_page_label(page_key: str, include_section: bool = True) -> str:
    page = get_page_definition(page_key)
    if page is None:
        return page_key

    if include_section and page.section_key:
        section = get_section_definition(page.section_key)
        if section is not None:
            return f"{section.label} / {page.title}"

    return page.title


def get_default_section_keys(is_admin: bool, allowed_devices: Iterable[str]) -> list[str]:
    del allowed_devices
    if is_admin:
        return get_configurable_section_keys()
    return []


def get_default_page_keys(is_admin: bool, section_keys: Iterable[str], allowed_devices: Iterable[str]) -> list[str]:
    del allowed_devices
    resolved_sections = normalize_section_keys(section_keys)
    if is_admin:
        return get_configurable_page_keys(resolved_sections)
    return []
