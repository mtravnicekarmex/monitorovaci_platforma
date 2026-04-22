from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    create_plynomery_alert_rule,
    delete_plynomery_alert_rule,
    get_plynomery_devices,
    get_plynomery_expected_zero,
    list_plynomery_alert_rules,
    update_plynomery_expected_zero,
    update_plynomery_alert_rule,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access
from moduly.mereni.plynomery.database.alerting import EVENT_TYPE_OPTIONS, SEND_ON_OPTIONS, SEVERITY_OPTIONS


st.set_page_config(
    page_title="Alerting plynomeru",
    page_icon="📣",
    layout="wide",
)


require_page_access("plynomery_alerting")


EVENT_TYPE_LABELS = {
    "": "Vsechny eventy",
    "NIGHT_USAGE": "NIGHT_USAGE",
    "SPIKE": "SPIKE",
    "LONG_HIGH_USAGE": "LONG_HIGH_USAGE",
    "EXPECTED_ZERO_USAGE": "EXPECTED_ZERO",
}
SEND_ON_LABELS = {
    "ACTIVE": "Pri prekroceni limitu u aktivniho eventu",
    "RESOLVED": "Pri vyreseni eventu",
    "BOTH": "Aktivni i vyreseny event",
}


@st.cache_data(ttl=60)
def load_rules_cached() -> list[dict[str, object]]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return list_plynomery_alert_rules(access_token)


@st.cache_data(ttl=60)
def load_devices_cached() -> list[str]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return get_plynomery_devices(access_token, limit=5000)


@st.cache_data(ttl=60)
def load_expected_zero_rows_cached() -> list[dict[str, object]]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return get_plynomery_expected_zero(access_token)


def format_timestamp(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)


def require_non_empty(value: str, message: str) -> str | None:
    cleaned = value.strip()
    if cleaned:
        return cleaned
    st.error(message)
    return None


def render_page() -> None:
    st.title("Alerting plynomeru")
    st.caption("Admin rozhrani pro konfiguraci alert pravidel plynomeru.")
    st.info(
        "Vsechna pravidla pro stejny email budou pri odesilani seskupena do jednoho souhrnneho emailu."
    )

    device_options = load_devices_cached()
    expected_zero_rows = load_expected_zero_rows_cached()
    rules = load_rules_cached()

    st.subheader("Expected zero")
    st.caption("Zarizeni, u kterych se ocekava nulova spotreba. Jakykoliv odber pak vytvari event EXPECTED_ZERO.")

    selected_expected_zero = [str(row["identifikace"]) for row in expected_zero_rows]
    expected_zero_options = sorted({*device_options, *selected_expected_zero})
    with st.form("plynomery_expected_zero_form"):
        selected_devices = st.multiselect(
            "Plynomery s ocekavanym nulovym odberem",
            options=expected_zero_options,
            default=selected_expected_zero,
            help="Pro vybrana zarizeni se jakakoliv kladna spotreba vyhodnoti jako EXPECTED_ZERO.",
        )
        expected_zero_submitted = st.form_submit_button("Ulozit expected zero")

    if expected_zero_submitted:
        update_plynomery_expected_zero(get_auth_token(), selected_devices)
        st.cache_data.clear()
        st.success("Seznam expected zero pro plynomery byl ulozen.")
        st.rerun()

    if expected_zero_rows:
        expected_zero_df = pd.DataFrame(
            [
                {
                    "identifikace": row["identifikace"],
                    "upravil": row["updated_by"] or "-",
                    "vytvoreno": format_timestamp(row["created_at"]),
                    "aktualizovano": format_timestamp(row["updated_at"]),
                }
                for row in expected_zero_rows
            ]
        )
        st.dataframe(expected_zero_df, width="stretch", hide_index=True)
    else:
        st.info("Zatim neni nastavene zadne zarizeni s expected zero.")

    st.markdown("---")
    create_col, overview_col = st.columns([2, 3])

    with create_col:
        st.subheader("Nove pravidlo")
        with st.form("create_plynomery_alert_rule_form"):
            rule_name = st.text_input("Nazev pravidla", placeholder="Napriklad Dlouha vysoka spotreba - objekt A")
            recipient_email = st.text_input("Prijemce emailu", placeholder="uzivatel@firma.cz")
            identifikace = st.selectbox(
                "Zarizeni",
                options=[""] + device_options,
                format_func=lambda value: "Vsechna zarizeni" if value == "" else value,
            )
            event_type = st.selectbox(
                "Typ eventu",
                options=list(EVENT_TYPE_OPTIONS),
                format_func=lambda value: EVENT_TYPE_LABELS.get(value, value),
            )
            severity_min = st.selectbox("Minimalni zavaznost", options=list(SEVERITY_OPTIONS), index=2)
            min_duration_minutes = st.number_input("Odeslat az po prekroceni trvani [min]", min_value=0, value=120, step=5)
            send_on = st.selectbox(
                "Odeslat pri",
                options=list(SEND_ON_OPTIONS),
                format_func=lambda value: SEND_ON_LABELS.get(value, value),
            )
            enabled = st.checkbox("Pravidlo je aktivni", value=True)
            note = st.text_area("Poznamka", placeholder="Volitelne interni upresneni")
            create_submitted = st.form_submit_button("Ulozit pravidlo")

        if create_submitted:
            clean_name = require_non_empty(rule_name, "Nazev pravidla je povinny.")
            clean_email = require_non_empty(recipient_email, "Email prijemce je povinny.")
            if clean_name and clean_email:
                create_plynomery_alert_rule(
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

    with overview_col:
        st.subheader("Prehled pravidel")
        if not rules:
            st.info("Zatim neni nastavene zadne alert pravidlo.")
        else:
            overview_df = pd.DataFrame(
                [
                    {
                        "nazev": rule["rule_name"],
                        "email": rule["recipient_email"],
                        "zarizeni": rule["identifikace"] or "vsechna",
                        "typ_eventu": EVENT_TYPE_LABELS.get(str(rule["event_type"] or ""), str(rule["event_type"] or "")),
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

    st.markdown("---")
    st.subheader("Editace pravidel")

    for rule in rules:
        rule_id = int(rule["id"])
        expander_title = f"{rule['rule_name']} | {rule['recipient_email']}"
        with st.expander(expander_title, expanded=False):
            st.caption(
                f"Vytvoreno: {format_timestamp(rule['created_at'])} | "
                f"Naposledy upraveno: {format_timestamp(rule['updated_at'])} | "
                f"Vytvoril: {rule['created_by'] or '-'} | Upravil: {rule['updated_by'] or '-'}"
            )
            with st.form(f"edit_plynomery_alert_rule_{rule_id}"):
                edit_rule_name = st.text_input("Nazev pravidla", value=str(rule["rule_name"]))
                edit_recipient_email = st.text_input("Prijemce emailu", value=str(rule["recipient_email"]))
                current_ident = str(rule["identifikace"] or "")
                resolved_device_options = device_options
                if current_ident and current_ident not in resolved_device_options:
                    resolved_device_options = sorted(resolved_device_options + [current_ident])
                edit_identifikace = st.selectbox(
                    "Zarizeni",
                    options=[""] + resolved_device_options,
                    index=([""] + resolved_device_options).index(current_ident) if current_ident in ([""] + resolved_device_options) else 0,
                    format_func=lambda value: "Vsechna zarizeni" if value == "" else value,
                    key=f"plynomery_ident_{rule_id}",
                )
                current_event_type = str(rule["event_type"] or "")
                edit_event_type = st.selectbox(
                    "Typ eventu",
                    options=list(EVENT_TYPE_OPTIONS),
                    index=list(EVENT_TYPE_OPTIONS).index(current_event_type) if current_event_type in EVENT_TYPE_OPTIONS else 0,
                    format_func=lambda value: EVENT_TYPE_LABELS.get(value, value),
                    key=f"plynomery_event_type_{rule_id}",
                )
                edit_severity_min = st.selectbox(
                    "Minimalni zavaznost",
                    options=list(SEVERITY_OPTIONS),
                    index=list(SEVERITY_OPTIONS).index(str(rule["severity_min"])),
                    key=f"plynomery_severity_{rule_id}",
                )
                edit_min_duration = st.number_input(
                    "Odeslat az po prekroceni trvani [min]",
                    min_value=0,
                    value=int(rule["min_duration_minutes"]),
                    step=5,
                    key=f"plynomery_duration_{rule_id}",
                )
                edit_send_on = st.selectbox(
                    "Odeslat pri",
                    options=list(SEND_ON_OPTIONS),
                    index=list(SEND_ON_OPTIONS).index(str(rule["send_on"])),
                    format_func=lambda value: SEND_ON_LABELS.get(value, value),
                    key=f"plynomery_send_on_{rule_id}",
                )
                edit_enabled = st.checkbox("Pravidlo je aktivni", value=bool(rule["enabled"]), key=f"plynomery_enabled_{rule_id}")
                edit_note = st.text_area("Poznamka", value=str(rule["note"] or ""), key=f"plynomery_note_{rule_id}")
                confirm_delete = st.checkbox(
                    "Potvrzuji smazani pravidla",
                    value=False,
                    key=f"plynomery_confirm_delete_{rule_id}",
                )

                save_col, delete_col = st.columns(2)
                save_pressed = save_col.form_submit_button("Ulozit zmeny")
                delete_pressed = delete_col.form_submit_button("Smazat pravidlo")

            if save_pressed:
                clean_name = require_non_empty(edit_rule_name, "Nazev pravidla je povinny.")
                clean_email = require_non_empty(edit_recipient_email, "Email prijemce je povinny.")
                if clean_name and clean_email:
                    update_plynomery_alert_rule(
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
                    delete_plynomery_alert_rule(get_auth_token(), rule_id)
                    st.warning(f"Pravidlo '{rule['rule_name']}' bylo smazano.")
                    st.cache_data.clear()
                    st.rerun()


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist alerting plynomeru.")
    st.exception(exc)
