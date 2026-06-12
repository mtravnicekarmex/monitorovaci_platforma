from __future__ import annotations

import importlib
from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard import auth as dashboard_auth


if not getattr(dashboard_auth, "LOGIN_CLIENT_IP_FORWARDING_ENABLED", False):
    from moduly.apps.dashboard import api_client as dashboard_api_client

    importlib.reload(dashboard_api_client)
    dashboard_auth = importlib.reload(dashboard_auth)


from moduly.apps.dashboard.auth import (
    DashboardApiError,
    any_dashboard_users,
    current_username,
    get_accessible_page_definitions,
    get_default_target_page,
    get_page_sidebar_location,
    init_auth_state,
    login,
    restore_auth_state_from_browser_cookie,
    render_sidebar_footer,
    render_sidebar_nav,
    sync_browser_auth_session,
)
from moduly.apps.dashboard.navigation_config import format_page_label, get_page_definition
from moduly.apps.dashboard import responsive as dashboard_responsive


dashboard_responsive = importlib.reload(dashboard_responsive)


st.set_page_config(
    page_title="Login",
    page_icon="🔐",
    layout="wide",
)


init_auth_state()
restore_auth_state_from_browser_cookie()
sync_browser_auth_session()
dashboard_responsive.render_responsive_page_styles()


LOGIN_PAGE_STYLE = """
<style>
section.main > div.block-container,
div[data-testid="stMainBlockContainer"] {
    max-width: 46rem;
    margin-left: auto;
    margin-right: auto;
    padding-left: 2rem;
    padding-right: 2rem;
}
</style>
"""


def default_target_page() -> str:
    return get_default_target_page()


def render_login_page() -> None:
    st.markdown(LOGIN_PAGE_STYLE, unsafe_allow_html=True)
    st.title("Login do dashboardu")
    st.caption("Uvodni stranka pro pristup k interni aplikaci monitorovaci platformy.")
    auth_notice = str(st.session_state.pop("auth_notice", "") or "")
    if auth_notice:
        st.success(auth_notice)

    try:
        users_exist = any_dashboard_users()
    except DashboardApiError as exc:
        st.error(str(exc))
        users_exist = True

    if not users_exist:
        st.warning("V databazi zatim neni zadny uzivatel dashboardu.")
        st.code(
            "py moduly\\apps\\dashboard\\database\\create_user.py "
            "--username admin --admin",
            language="powershell",
        )

    if st.session_state["authenticated"]:
        st.success(f"Prihlasen jako {current_username()}.")
        accessible_pages = get_accessible_page_definitions("main")
        if accessible_pages:
            for page in accessible_pages:
                st.page_link(page.path, label=f"Pokracovat na stranku {format_page_label(page.key, include_section=True)}")
        else:
            account_page = get_page_definition("muj_ucet")
            if account_page is not None:
                st.page_link(account_page.path, label=f"Pokracovat na stranku {account_page.title}")
    else:
        with st.form("login_form"):
            username = st.text_input("Uzivatel")
            password = st.text_input("Heslo", type="password")
            submitted = st.form_submit_button("Prihlasit")

        if submitted:
            try:
                login(username.strip(), password)
            except DashboardApiError as exc:
                st.error(str(exc))
            else:
                redirect_target = st.session_state.pop("requested_login_redirect", "") or default_target_page()
                st.session_state["post_login_redirect"] = redirect_target
                st.rerun()


def build_navigation():
    pages = [
        st.Page(render_login_page, title="Login", icon="🔐", default=True),
    ]

    if st.session_state["authenticated"]:
        for page in get_accessible_page_definitions("main"):
            pages.append(st.Page(page.path, title=page.title, icon=page.icon))
        for page in get_accessible_page_definitions("footer"):
            pages.append(st.Page(page.path, title=page.title, icon=page.icon))

    return pages


pages = build_navigation()
current_page = st.navigation(pages, position="hidden")
nav_pages = [page for page in pages if get_page_sidebar_location(page) == "main"]
render_sidebar_nav(nav_pages, current_page)

redirect_target = st.session_state.get("post_login_redirect", "")
if redirect_target:
    st.session_state["post_login_redirect"] = ""
    redirect_path = (Path(__file__).resolve().parent / redirect_target).resolve()
    for page in pages:
        if getattr(page, "_page", None) == redirect_path:
            st.switch_page(page)
    st.switch_page(redirect_target)

current_page.run()
render_sidebar_footer(pages, current_page)
