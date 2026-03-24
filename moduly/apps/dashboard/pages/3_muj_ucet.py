from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import current_username, is_admin, require_page_access
from moduly.apps.dashboard.database.users import get_user, update_email, update_password, verify_user_password


st.set_page_config(
    page_title="Můj účet",
    page_icon="🔑",
    layout="wide",
)


require_page_access("muj_ucet")


username = current_username()
user = get_user(username)
current_email = user.email if user else None

st.title("Můj účet")
st.caption("Správa vlastního přístupu do dashboardu")

user_is_admin = is_admin()

if user_is_admin:
    info_col_1, info_col_2 = st.columns(2)
    info_col_1.metric("Uživatel", username)
    info_col_2.metric("Role", "admin")
else:
    st.metric("Uživatel", username)

st.metric("Email", current_email or "-")

st.markdown("---")
st.subheader("Email")

with st.form("change_email_form"):
    email_value = st.text_input("Email", value=current_email or "")
    email_submitted = st.form_submit_button("Uložit email")

if email_submitted:
    normalized_email = email_value.strip()
    if normalized_email and "@" not in normalized_email:
        st.error("Email musí obsahovat znak @.")
    else:
        update_email(username, normalized_email or None)
        st.success("Email byl uložen.")
        st.rerun()

st.markdown("---")
st.subheader("Změna hesla")

with st.form("change_password_form"):
    current_password = st.text_input("Současné heslo", type="password")
    new_password = st.text_input("Nové heslo", type="password")
    new_password_confirm = st.text_input("Potvrzení nového hesla", type="password")
    submitted = st.form_submit_button("Změnit heslo")

if submitted:
    if not current_password or not new_password or not new_password_confirm:
        st.error("Vyplň všechna pole.")
    elif not verify_user_password(username, current_password):
        st.error("Současné heslo není spravně.")
    elif new_password != new_password_confirm:
        st.error("Nové heslo a potvrzení se neshoduji.")
    elif len(new_password) < 8:
        st.error("Nové heslo musí mít alespoň 8 znaků.")
    else:
        update_password(username, new_password)
        st.success("Heslo bylo změněno.")
