from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connect import get_session_ms, get_session_pg
from moduly.apps.dashboard.auth import current_username, require_page_access
from moduly.apps.dashboard.database.users import delete_user, list_users, upsert_user
from moduly.apps.dashboard.navigation_config import (
    format_page_label,
    format_section_label,
    get_configurable_page_keys,
    get_configurable_section_keys,
    normalize_page_keys,
)
from moduly.mereni.kalorimetry.database.models import Kalorimetr_areal_Mereni
from moduly.mereni.plynomery.database.models import Plynomer_areal_Mereni
from moduly.mereni.vodomery.database.models import Mereni_vodomery


st.set_page_config(
    page_title="Sprava uzivatelu",
    page_icon="👤",
    layout="wide",
)


require_page_access("sprava_uzivatelu")


SECTION_OPTIONS = get_configurable_section_keys()
PAGE_OPTIONS = get_configurable_page_keys()


@st.cache_data(ttl=60)
def load_device_options() -> list[str]:
    identifiers: set[str] = set()

    session_pg = get_session_pg()
    try:
        vodomery_rows = (
            session_pg.query(Mereni_vodomery.identifikace)
            .distinct()
            .order_by(Mereni_vodomery.identifikace)
            .all()
        )
        identifiers.update(str(row[0]) for row in vodomery_rows if row[0])
    finally:
        session_pg.close()

    session_ms = get_session_ms()
    try:
        plynomery_rows = (
            session_ms.query(Plynomer_areal_Mereni.identifikace)
            .distinct()
            .order_by(Plynomer_areal_Mereni.identifikace)
            .all()
        )
        identifiers.update(str(row[0]) for row in plynomery_rows if row[0])

        kalorimetry_rows = (
            session_ms.query(Kalorimetr_areal_Mereni.identifikace)
            .distinct()
            .order_by(Kalorimetr_areal_Mereni.identifikace)
            .all()
        )
        identifiers.update(str(row[0]) for row in kalorimetry_rows if row[0])
    finally:
        session_ms.close()

    return sorted(identifiers)


def format_timestamp(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)


def format_section_summary(section_keys: list[str]) -> str:
    if not section_keys:
        return "-"
    labels = []
    for section_key in section_keys:
        label = format_section_label(section_key)
        labels.append(label.split(" ", 1)[1] if " " in label else label)
    return ", ".join(labels)


def normalize_selected_pages(section_keys: list[str], page_keys: list[str]) -> list[str]:
    return normalize_page_keys(page_keys, allowed_section_keys=section_keys)


st.title("Sprava uzivatelu")
st.caption("Admin stranka pro spravu pristupu do dashboardu.")

device_options = load_device_options()
users = list_users()

create_col, list_col = st.columns([2, 3])

with create_col:
    st.subheader("Novy uzivatel")
    with st.form("create_user_form"):
        new_username = st.text_input("Uzivatel")
        new_email = st.text_input("Email")
        new_password = st.text_input("Heslo", type="password")
        new_is_admin = st.checkbox("Admin", value=False)
        new_is_active = st.checkbox("Aktivni", value=True)
        new_sections = st.multiselect(
            "Dostupne sekce",
            options=SECTION_OPTIONS,
            default=SECTION_OPTIONS,
            format_func=format_section_label,
            help="Admin vidi vsechny sekce bez ohledu na tento vyber.",
        )
        new_pages = st.multiselect(
            "Dostupne stranky",
            options=PAGE_OPTIONS,
            default=PAGE_OPTIONS,
            format_func=lambda page_key: format_page_label(page_key, include_section=True),
            help="Zobrazene budou jen stranky z vybranych sekci. Admin vidi vsechny stranky.",
        )
        new_devices = st.multiselect(
            "Povolena zarizeni",
            options=device_options,
            help="Admin muze videt vsechna zarizeni, seznam se v tom pripade nepouziva.",
        )
        create_submitted = st.form_submit_button("Vytvorit uzivatele")

    if create_submitted:
        if not new_username.strip():
            st.error("Uzivatel je povinny.")
        elif not new_password:
            st.error("Heslo je povinne.")
        else:
            resolved_pages = normalize_selected_pages(new_sections, new_pages)
            upsert_user(
                username=new_username.strip(),
                password=new_password,
                email=new_email.strip() or None,
                dostupne_sekce=new_sections,
                dostupne_stranky=resolved_pages,
                seznam_zarizeni=new_devices,
                is_admin=new_is_admin,
                is_active=new_is_active,
            )
            st.success(f"Uzivatel '{new_username.strip()}' byl ulozen.")
            st.cache_data.clear()
            st.rerun()

with list_col:
    st.subheader("Prehled uzivatelu")
    if not users:
        st.info("Zatim neni zalozen zadny uzivatel.")
    else:
        overview_df = pd.DataFrame(
            [
                {
                    "uzivatel": user["uzivatel"],
                    "email": user["email"] or "-",
                    "admin": "ANO" if user["is_admin"] else "NE",
                    "aktivni": "ANO" if user["is_active"] else "NE",
                    "sekce": "vsechny" if user["is_admin"] else format_section_summary(list(user["dostupne_sekce"])),
                    "stranky": "vsechny" if user["is_admin"] else len(user["dostupne_stranky"]),
                    "zarizeni": "vsechna" if user["is_admin"] else len(user["seznam_zarizeni"]),
                    "posledni_login": format_timestamp(user["last_login_at"]),
                }
                for user in users
            ]
        )
        st.dataframe(overview_df, width="stretch", hide_index=True)

st.markdown("---")
st.subheader("Editace uzivatelu")

for user in users:
    username = str(user["uzivatel"])
    with st.expander(username, expanded=False):
        st.caption(
            f"Vytvoren: {format_timestamp(user['created_at'])} | "
            f"Naposledy upraven: {format_timestamp(user['updated_at'])} | "
            f"Posledni login: {format_timestamp(user['last_login_at'])} | "
            f"Sekce: {'vsechny' if user['is_admin'] else format_section_summary(list(user['dostupne_sekce']))}"
        )
        with st.form(f"edit_user_{username}"):
            edit_email = st.text_input("Email", value=user["email"] or "")
            edit_is_admin = st.checkbox("Admin", value=bool(user["is_admin"]))
            edit_is_active = st.checkbox("Aktivni", value=bool(user["is_active"]))
            edit_password = st.text_input(
                "Nove heslo",
                type="password",
                help="Nech prazdne, pokud heslo nechces menit.",
            )
            edit_sections = st.multiselect(
                "Dostupne sekce",
                options=SECTION_OPTIONS,
                default=list(user["dostupne_sekce"]),
                format_func=format_section_label,
                help="Admin vidi vsechny sekce bez ohledu na tento vyber.",
                key=f"sections_{username}",
            )
            edit_pages = st.multiselect(
                "Dostupne stranky",
                options=PAGE_OPTIONS,
                default=list(user["dostupne_stranky"]),
                format_func=lambda page_key: format_page_label(page_key, include_section=True),
                help="Zobrazene budou jen stranky z vybranych sekci. Admin vidi vsechny stranky.",
                key=f"pages_{username}",
            )
            edit_devices = st.multiselect(
                "Povolena zarizeni",
                options=device_options,
                default=list(user["seznam_zarizeni"]),
                help="Admin muze videt vsechna zarizeni, seznam se v tom pripade nepouziva.",
                key=f"devices_{username}",
            )
            confirm_delete = st.checkbox(
                "Potvrzuji smazani tohoto uzivatele",
                value=False,
                key=f"confirm_delete_{username}",
            )

            save_col, delete_col = st.columns(2)
            save_pressed = save_col.form_submit_button("Ulozit zmeny")
            delete_pressed = delete_col.form_submit_button("Smazat uzivatele")

        if save_pressed:
            resolved_pages = normalize_selected_pages(edit_sections, edit_pages)
            upsert_user(
                username=username,
                password=edit_password or None,
                email=edit_email.strip() or None,
                dostupne_sekce=edit_sections,
                dostupne_stranky=resolved_pages,
                seznam_zarizeni=edit_devices,
                is_admin=edit_is_admin,
                is_active=edit_is_active,
            )
            st.success(f"Uzivatel '{username}' byl aktualizovan.")
            st.cache_data.clear()
            st.rerun()

        if delete_pressed:
            if username == current_username():
                st.error("Nemuzes smazat prave prihlaseneho uzivatele.")
            elif not confirm_delete:
                st.error("Pro smazani uzivatele musis zaskrtnout potvrzeni.")
            else:
                delete_user(username)
                st.warning(f"Uzivatel '{username}' byl smazan.")
                st.cache_data.clear()
                st.rerun()
