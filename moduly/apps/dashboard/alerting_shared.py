from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping

from moduly.apps.dashboard.api_client import (
    create_plynomery_alert_rule,
    create_vodomery_alert_rule,
    delete_plynomery_alert_rule,
    delete_vodomery_alert_rule,
    get_plynomery_devices,
    get_plynomery_expected_zero,
    get_vodomery_devices,
    get_vodomery_expected_zero,
    list_plynomery_alert_rules,
    list_vodomery_alert_rules,
    update_plynomery_alert_rule,
    update_plynomery_expected_zero,
    update_vodomery_alert_rule,
    update_vodomery_expected_zero,
)
from moduly.mereni.plynomery.database.alerting import (
    EVENT_TYPE_OPTIONS as PLYNOMERY_EVENT_TYPE_OPTIONS,
    SEND_ON_OPTIONS as PLYNOMERY_SEND_ON_OPTIONS,
    SEVERITY_OPTIONS as PLYNOMERY_SEVERITY_OPTIONS,
)
from moduly.mereni.vodomery.database.alerting import (
    EVENT_TYPE_OPTIONS as VODOMERY_EVENT_TYPE_OPTIONS,
    SEND_ON_OPTIONS as VODOMERY_SEND_ON_OPTIONS,
    SEVERITY_OPTIONS as VODOMERY_SEVERITY_OPTIONS,
)


SEND_ON_LABELS = {
    "ACTIVE": "Pri prekroceni limitu u aktivniho eventu",
    "RESOLVED": "Pri vyreseni eventu",
    "BOTH": "Aktivni i vyreseny event",
}


@dataclass(frozen=True)
class ExpectedZeroConfig:
    section_title: str
    caption: str
    select_label: str
    help_text: str
    success_message: str
    empty_message: str


@dataclass(frozen=True)
class AlertingModuleConfig:
    key: str
    label: str
    page_caption: str
    rule_name_placeholder: str
    event_type_options: tuple[str, ...]
    event_type_labels: Mapping[str, str]
    severity_options: tuple[str, ...]
    send_on_options: tuple[str, ...]
    expected_zero: ExpectedZeroConfig | None
    load_rules: Callable[[str], list[dict[str, object]]]
    load_devices: Callable[[str], list[str]]
    load_expected_zero_rows: Callable[[str], list[dict[str, object]]] | None
    update_expected_zero: Callable[[str, list[str]], list[dict[str, object]]] | None
    create_rule: Callable[[str, dict[str, object]], dict[str, object]]
    update_rule: Callable[[str, int, dict[str, object]], dict[str, object]]
    delete_rule: Callable[[str, int], None]


ALERTING_MODULES: tuple[AlertingModuleConfig, ...] = (
    AlertingModuleConfig(
        key="vodomery",
        label="Vodomery",
        page_caption="Admin rozhrani pro konfiguraci alert pravidel vodomeru.",
        rule_name_placeholder="Napriklad Dlouhy unik - objekt A",
        event_type_options=VODOMERY_EVENT_TYPE_OPTIONS,
        event_type_labels={
            "": "Vsechny eventy",
            "NIGHT_USAGE": "NIGHT_USAGE",
            "SPIKE": "SPIKE",
            "LONG_LEAK": "LONG_LEAK",
            "ZERO_FLOW": "ZERO_FLOW",
            "EXPECTED_ZERO_USAGE": "EXPECTED_ZERO_USAGE",
            "OUTLIER_REVIEW": "OUTLIER_REVIEW",
        },
        severity_options=VODOMERY_SEVERITY_OPTIONS,
        send_on_options=VODOMERY_SEND_ON_OPTIONS,
        expected_zero=ExpectedZeroConfig(
            section_title="Expected zero",
            caption=(
                "Odberna mista, u kterych se ocekava nulovy odber. "
                "Nebude se pro ne zobrazovat ZERO_FLOW a jakykoliv odber vytvari event EXPECTED_ZERO_USAGE."
            ),
            select_label="Vodomery s ocekavanym nulovym odberem",
            help_text=(
                "Pro vybrana odberna mista se nebude zobrazovat ZERO_FLOW "
                "a jakykoliv kladny odber se vyhodnoti jako EXPECTED_ZERO_USAGE."
            ),
            success_message="Seznam expected zero pro vodomery byl ulozen.",
            empty_message="Zatim neni nastavene zadne odberne misto s expected zero.",
        ),
        load_rules=list_vodomery_alert_rules,
        load_devices=lambda access_token: get_vodomery_devices(access_token, source_filter="VSE", limit=5000),
        load_expected_zero_rows=get_vodomery_expected_zero,
        update_expected_zero=update_vodomery_expected_zero,
        create_rule=create_vodomery_alert_rule,
        update_rule=update_vodomery_alert_rule,
        delete_rule=delete_vodomery_alert_rule,
    ),
    AlertingModuleConfig(
        key="plynomery",
        label="Plynomery",
        page_caption="Admin rozhrani pro konfiguraci alert pravidel plynomeru.",
        rule_name_placeholder="Napriklad Dlouha vysoka spotreba - objekt A",
        event_type_options=PLYNOMERY_EVENT_TYPE_OPTIONS,
        event_type_labels={
            "": "Vsechny eventy",
            "NIGHT_USAGE": "NIGHT_USAGE",
            "SPIKE": "SPIKE",
            "LONG_HIGH_USAGE": "LONG_HIGH_USAGE",
            "EXPECTED_ZERO_USAGE": "EXPECTED_ZERO",
            "OUTLIER_REVIEW": "OUTLIER_REVIEW",
        },
        severity_options=PLYNOMERY_SEVERITY_OPTIONS,
        send_on_options=PLYNOMERY_SEND_ON_OPTIONS,
        expected_zero=ExpectedZeroConfig(
            section_title="Expected zero",
            caption="Zarizeni, u kterych se ocekava nulova spotreba. Jakykoliv odber pak vytvari event EXPECTED_ZERO.",
            select_label="Plynomery s ocekavanym nulovym odberem",
            help_text="Pro vybrana zarizeni se jakakoliv kladna spotreba vyhodnoti jako EXPECTED_ZERO.",
            success_message="Seznam expected zero pro plynomery byl ulozen.",
            empty_message="Zatim neni nastavene zadne zarizeni s expected zero.",
        ),
        load_rules=list_plynomery_alert_rules,
        load_devices=lambda access_token: get_plynomery_devices(access_token, limit=5000),
        load_expected_zero_rows=get_plynomery_expected_zero,
        update_expected_zero=update_plynomery_expected_zero,
        create_rule=create_plynomery_alert_rule,
        update_rule=update_plynomery_alert_rule,
        delete_rule=delete_plynomery_alert_rule,
    ),
)
ALERTING_MODULE_MAP = {config.key: config for config in ALERTING_MODULES}
ALERTING_MODULE_OPTIONS = tuple(config.key for config in ALERTING_MODULES)
ALERTING_MODULE_LABELS = {config.key: config.label for config in ALERTING_MODULES}


def get_alerting_module_config(module_key: str) -> AlertingModuleConfig:
    try:
        return ALERTING_MODULE_MAP[module_key]
    except KeyError as exc:
        raise KeyError(f"Neznamy alerting modul: {module_key}") from exc


def format_alerting_timestamp(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)


def require_non_empty_alerting_value(value: str, error_callback: Callable[[str], None], message: str) -> str | None:
    cleaned = value.strip()
    if cleaned:
        return cleaned
    error_callback(message)
    return None
