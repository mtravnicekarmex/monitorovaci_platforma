from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.alerting_shared import (
    ALERTING_MODULE_LABELS,
    ALERTING_MODULE_OPTIONS,
    SEND_ON_LABELS,
    format_alerting_timestamp,
    get_alerting_module_config,
    require_non_empty_alerting_value,
)
from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import get_auth_token, require_page_access


st.set_page_config(
    page_title="Alerting",
    page_icon="📣",
    layout="wide",
)


require_page_access("alerting")


@st.cache_data(ttl=60)
def load_rules_cached(module_key: str) -> list[dict[str, object]]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return get_alerting_module_config(module_key).load_rules(access_token)


@st.cache_data(ttl=60)
def load_devices_cached(module_key: str) -> list[str]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return get_alerting_module_config(module_key).load_devices(access_token)


@st.cache_data(ttl=60)
def load_expected_zero_rows_cached(module_key: str) -> list[dict[str, object]]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    config = get_alerting_module_config(module_key)
    if config.load_expected_zero_rows is None:
        return []
    return config.load_expected_zero_rows(access_token)


def render_expected_zero_section(module_key: str, device_options: list[str]) -> None:
    config = get_alerting_module_config(module_key)
    expected_zero_config = config.expected_zero
    if expected_zero_config is None or config.update_expected_zero is None:
        return

    expected_zero_rows = load_expected_zero_rows_cached(module_key)

    st.subheader(expected_zero_config.section_title)
    st.caption(expected_zero_config.caption)

    selected_expected_zero = [str(row["identifikace"]) for row in expected_zero_rows]
    expected_zero_options = sorted({*device_options, *selected_expected_zero})
    with st.form(f"{module_key}_expected_zero_form"):
        selected_devices = st.multiselect(
            expected_zero_config.select_label,
            options=expected_zero_options,
            default=selected_expected_zero,
            help=expected_zero_config.help_text,
        )
        expected_zero_submitted = st.form_submit_button("Ulozit expected zero")

    if expected_zero_submitted:
        config.update_expected_zero(get_auth_token(), selected_devices)
        st.cache_data.clear()
        st.success(expected_zero_config.success_message)
        st.rerun()

    if expected_zero_rows:
        expected_zero_df = pd.DataFrame(
            [
                {
                    "identifikace": row["identifikace"],
                    "upravil": row["updated_by"] or "-",
                    "vytvoreno": format_alerting_timestamp(row["created_at"]),
                    "aktualizovano": format_alerting_timestamp(row["updated_at"]),
                }
                for row in expected_zero_rows
            ]
        )
        st.dataframe(expected_zero_df, width="stretch", hide_index=True)
    else:
        st.info(expected_zero_config.empty_message)


def render_create_rule_form(module_key: str, device_options: list[str]) -> None:
    config = get_alerting_module_config(module_key)

    st.subheader("Nove pravidlo")
    with st.form(f"create_alert_rule_form_{module_key}"):
        rule_name = st.text_input("Nazev pravidla", placeholder=config.rule_name_placeholder)
        recipient_email = st.text_input("Prijemce emailu", placeholder="uzivatel@firma.cz")
        identifikace = st.selectbox(
            "Zarizeni",
            options=[""] + device_options,
            format_func=lambda value: "Vsechna zarizeni" if value == "" else value,
        )
        event_type = st.selectbox(
            "Typ eventu",
            options=list(config.event_type_options),
            format_func=lambda value: config.event_type_labels.get(value, value),
        )
        severity_min = st.selectbox("Minimalni zavaznost", options=list(config.severity_options), index=2)
        min_duration_minutes = st.number_input("Odeslat az po prekroceni trvani [min]", min_value=0, value=120, step=5)
        send_on = st.selectbox(
            "Odeslat pri",
            options=list(config.send_on_options),
            format_func=lambda value: SEND_ON_LABELS.get(value, value),
        )
        enabled = st.checkbox("Pravidlo je aktivni", value=True)
        note = st.text_area("Poznamka", placeholder="Volitelne interni upresneni")
        create_submitted = st.form_submit_button("Ulozit pravidlo")

    if create_submitted:
        clean_name = require_non_empty_alerting_value(rule_name, st.error, "Nazev pravidla je povinny.")
        clean_email = require_non_empty_alerting_value(recipient_email, st.error, "Email prijemce je povinny.")
        if clean_name and clean_email:
            config.create_rule(
                get_auth_token(),
                {
                    "rule_name": clean_name,
                    "recipient_email": clean_email,
                    "identifikace": identifikace or None,
                    "event_type": event_type or None,
                    "severity_min": severity_min,
                    "min_duration_minutes": int(min_duration_minutes),
                    "send_on": send_on,
                    "enabled": enabled,
                    "note": note.strip() or None,
                },
            )
            st.success(f"Pravidlo '{clean_name}' bylo ulozeno.")
            st.cache_data.clear()
            st.rerun()


def render_rules_overview(module_key: str, rules: list[dict[str, object]]) -> None:
    config = get_alerting_module_config(module_key)

    st.subheader("Prehled pravidel")
    if not rules:
        st.info("Zatim neni nastavene zadne alert pravidlo.")
        return

    overview_df = pd.DataFrame(
        [
            {
                "nazev": rule["rule_name"],
                "email": rule["recipient_email"],
                "zarizeni": rule["identifikace"] or "vsechna",
                "typ_eventu": config.event_type_labels.get(str(rule["event_type"] or ""), str(rule["event_type"] or "")),
                "min_zavaznost": rule["severity_min"],
                "min_trvani_min": int(rule["min_duration_minutes"]),
                "odeslat_pri": SEND_ON_LABELS.get(str(rule["send_on"]), str(rule["send_on"])),
                "aktivni": "ANO" if rule["enabled"] else "NE",
                "upravil": rule["updated_by"] or "-",
            }
            for rule in rules
        ]
    )
    st.dataframe(overview_df, width="stretch", hide_index=True)


def render_rule_editors(module_key: str, device_options: list[str], rules: list[dict[str, object]]) -> None:
    config = get_alerting_module_config(module_key)

    st.markdown("---")
    st.subheader("Editace pravidel")

    for rule in rules:
        rule_id = int(rule["id"])
        expander_title = f"{rule['rule_name']} | {rule['recipient_email']}"
        with st.expander(expander_title, expanded=False):
            st.caption(
                f"Vytvoreno: {format_alerting_timestamp(rule['created_at'])} | "
                f"Naposledy upraveno: {format_alerting_timestamp(rule['updated_at'])} | "
                f"Vytvoril: {rule['created_by'] or '-'} | Upravil: {rule['updated_by'] or '-'}"
            )
            with st.form(f"edit_alert_rule_{module_key}_{rule_id}"):
                edit_rule_name = st.text_input("Nazev pravidla", value=str(rule["rule_name"]))
                edit_recipient_email = st.text_input("Prijemce emailu", value=str(rule["recipient_email"]))
                current_ident = str(rule["identifikace"] or "")
                resolved_device_options = device_options
                if current_ident and current_ident not in resolved_device_options:
                    resolved_device_options = sorted(resolved_device_options + [current_ident])
                select_options = [""] + resolved_device_options
                edit_identifikace = st.selectbox(
                    "Zarizeni",
                    options=select_options,
                    index=select_options.index(current_ident) if current_ident in select_options else 0,
                    format_func=lambda value: "Vsechna zarizeni" if value == "" else value,
                    key=f"ident_{module_key}_{rule_id}",
                )
                current_event_type = str(rule["event_type"] or "")
                edit_event_type = st.selectbox(
                    "Typ eventu",
                    options=list(config.event_type_options),
                    index=list(config.event_type_options).index(current_event_type) if current_event_type in config.event_type_options else 0,
                    format_func=lambda value: config.event_type_labels.get(value, value),
                    key=f"event_type_{module_key}_{rule_id}",
                )
                edit_severity_min = st.selectbox(
                    "Minimalni zavaznost",
                    options=list(config.severity_options),
                    index=list(config.severity_options).index(str(rule["severity_min"])),
                    key=f"severity_{module_key}_{rule_id}",
                )
                edit_min_duration = st.number_input(
                    "Odeslat az po prekroceni trvani [min]",
                    min_value=0,
                    value=int(rule["min_duration_minutes"]),
                    step=5,
                    key=f"duration_{module_key}_{rule_id}",
                )
                edit_send_on = st.selectbox(
                    "Odeslat pri",
                    options=list(config.send_on_options),
                    index=list(config.send_on_options).index(str(rule["send_on"])),
                    format_func=lambda value: SEND_ON_LABELS.get(value, value),
                    key=f"send_on_{module_key}_{rule_id}",
                )
                edit_enabled = st.checkbox("Pravidlo je aktivni", value=bool(rule["enabled"]), key=f"enabled_{module_key}_{rule_id}")
                edit_note = st.text_area("Poznamka", value=str(rule["note"] or ""), key=f"note_{module_key}_{rule_id}")
                confirm_delete = st.checkbox(
                    "Potvrzuji smazani pravidla",
                    value=False,
                    key=f"confirm_delete_{module_key}_{rule_id}",
                )

                save_col, delete_col = st.columns(2)
                save_pressed = save_col.form_submit_button("Ulozit zmeny")
                delete_pressed = delete_col.form_submit_button("Smazat pravidlo")

            if save_pressed:
                clean_name = require_non_empty_alerting_value(edit_rule_name, st.error, "Nazev pravidla je povinny.")
                clean_email = require_non_empty_alerting_value(edit_recipient_email, st.error, "Email prijemce je povinny.")
                if clean_name and clean_email:
                    config.update_rule(
                        get_auth_token(),
                        rule_id,
                        {
                            "rule_name": clean_name,
                            "recipient_email": clean_email,
                            "identifikace": edit_identifikace or None,
                            "event_type": edit_event_type or None,
                            "severity_min": edit_severity_min,
                            "min_duration_minutes": int(edit_min_duration),
                            "send_on": edit_send_on,
                            "enabled": edit_enabled,
                            "note": edit_note.strip() or None,
                        },
                    )
                    st.success(f"Pravidlo '{clean_name}' bylo aktualizovano.")
                    st.cache_data.clear()
                    st.rerun()

            if delete_pressed:
                if not confirm_delete:
                    st.error("Pro smazani pravidla musis zaskrtnout potvrzeni.")
                else:
                    config.delete_rule(get_auth_token(), rule_id)
                    st.warning(f"Pravidlo '{rule['rule_name']}' bylo smazano.")
                    st.cache_data.clear()
                    st.rerun()


def render_page() -> None:
    st.title("Alerting")
    selected_module = st.selectbox(
        "Modul",
        options=list(ALERTING_MODULE_OPTIONS),
        format_func=lambda value: ALERTING_MODULE_LABELS.get(value, value),
    )
    config = get_alerting_module_config(selected_module)

    st.caption(config.page_caption)
    st.info("Vsechna pravidla pro stejny email budou pri odesilani seskupena do jednoho souhrnneho emailu.")
    st.caption("Pro event type OUTLIER_REVIEW se minimalni trvani uklada automaticky jako 0 minut.")

    device_options = load_devices_cached(selected_module)
    rules = load_rules_cached(selected_module)

    render_expected_zero_section(selected_module, device_options)
    st.markdown("---")

    create_col, overview_col = st.columns([2, 3])
    with create_col:
        render_create_rule_form(selected_module, device_options)
    with overview_col:
        render_rules_overview(selected_module, rules)

    render_rule_editors(selected_module, device_options, rules)


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist alerting.")
    st.exception(exc)
