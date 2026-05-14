from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.api_client import (
    change_my_password,
    update_my_email,
)
from moduly.apps.dashboard.auth import (
    apply_authenticated_user,
    current_user_email,
    current_username,
    get_auth_token,
    is_admin,
    logout,
    refresh_current_user,
    require_page_access,
)


st.set_page_config(
    page_title="Můj účet",
    page_icon="🔑",
    layout="wide",
)


require_page_access("muj_ucet")


username = current_username()
refresh_current_user()
current_email = current_user_email()

st.title("Můj účet")
st.caption("Správa vlastního přístupu do dashboardu")

user_is_admin = is_admin()

info_col_1, info_col_2 = st.columns(2)
info_col_1.metric("Uživatel", username)
info_col_2.metric("Email", current_email or "-")

if user_is_admin:
    st.caption("Role: admin")

st.markdown("---")
email_col, password_col = st.columns(2, gap="large")

with email_col:
    st.subheader("Email")
    with st.form("change_email_form"):
        email_value = st.text_input("Email", value=current_email or "")
        email_submitted = st.form_submit_button("Uložit email")

if email_submitted:
    normalized_email = email_value.strip()
    if normalized_email and "@" not in normalized_email:
        email_col.error("Email musí obsahovat znak @.")
    else:
        try:
            user_payload = update_my_email(get_auth_token(), normalized_email or None)
        except DashboardApiError as exc:
            email_col.error(str(exc))
        else:
            apply_authenticated_user(user_payload)
            email_col.success("Email byl uložen.")
            st.rerun()

with password_col:
    st.subheader("Změna hesla")
    with st.form("change_password_form"):
        current_password = st.text_input("Současné heslo", type="password")
        new_password = st.text_input("Nové heslo", type="password")
        new_password_confirm = st.text_input("Potvrzení nového hesla", type="password")
        submitted = st.form_submit_button("Změnit heslo")

if submitted:
    if not current_password or not new_password or not new_password_confirm:
        password_col.error("Vyplň všechna pole.")
    elif new_password != new_password_confirm:
        password_col.error("Nové heslo a potvrzení se neshoduji.")
    elif len(new_password) < 8:
        password_col.error("Nové heslo musí mít alespoň 8 znaků.")
    else:
        try:
            change_my_password(get_auth_token(), current_password, new_password)
        except DashboardApiError as exc:
            password_col.error(str(exc))
        else:
            logout()
            st.session_state["auth_notice"] = "Heslo bylo změněno. Přihlaste se znovu."
            st.rerun()
