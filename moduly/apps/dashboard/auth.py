from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.api_client import (
    any_dashboard_users_exist,
    get_me as api_get_me,
    login as api_login,
    logout as api_logout,
)
from moduly.apps.dashboard.navigation_config import (
    SECTIONS,
    DashboardPage,
    get_dashboard_pages,
    get_page_definition,
    get_page_definition_by_path,
    get_section_definition,
)


def init_auth_state() -> None:
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("auth_token", "")
    st.session_state.setdefault("auth_token_expires_at", None)
    st.session_state.setdefault("auth_user", "")
    st.session_state.setdefault("auth_email", None)
    st.session_state.setdefault("auth_is_admin", False)
    st.session_state.setdefault("auth_allowed_sections", ())
    st.session_state.setdefault("auth_allowed_pages", ())
    st.session_state.setdefault("auth_allowed_devices", ())
    st.session_state.setdefault("auth_last_login_at", None)
    st.session_state.setdefault("post_login_redirect", "")
    st.session_state.setdefault("requested_login_redirect", "")


def any_dashboard_users() -> bool:
    return any_dashboard_users_exist()


def get_auth_token() -> str:
    init_auth_state()
    return str(st.session_state["auth_token"])


def current_user_email() -> str | None:
    init_auth_state()
    email = st.session_state.get("auth_email")
    return str(email) if email else None


def current_user_last_login_at():
    init_auth_state()
    return st.session_state.get("auth_last_login_at")


def get_allowed_devices() -> tuple[str, ...]:
    init_auth_state()
    return tuple(st.session_state["auth_allowed_devices"])


def get_allowed_sections() -> tuple[str, ...]:
    init_auth_state()
    return tuple(st.session_state["auth_allowed_sections"])


def get_allowed_pages() -> tuple[str, ...]:
    init_auth_state()
    return tuple(st.session_state["auth_allowed_pages"])


def current_username() -> str:
    init_auth_state()
    return str(st.session_state["auth_user"])


def is_admin() -> bool:
    init_auth_state()
    return bool(st.session_state["auth_is_admin"])


def can_access_vodomery() -> bool:
    return has_section_access("vodomery")


def has_section_access(section_key: str) -> bool:
    init_auth_state()
    section = get_section_definition(section_key)
    if section is None:
        return False
    if is_admin():
        return True
    if section_key not in get_allowed_sections():
        return False
    if section.requires_device_permissions and not get_allowed_devices():
        return False
    return True


def has_page_access(page_key: str) -> bool:
    init_auth_state()
    if not st.session_state["authenticated"]:
        return False

    page = get_page_definition(page_key)
    if page is None:
        return False
    if page.admin_only:
        return is_admin()
    if is_admin():
        return True
    if page.section_key and not has_section_access(page.section_key):
        return False
    if page.configurable and page.key not in get_allowed_pages():
        return False
    return True


def get_accessible_page_definitions(sidebar_location: str | None = None) -> tuple[DashboardPage, ...]:
    return tuple(page for page in get_dashboard_pages(sidebar_location) if has_page_access(page.key))


def get_default_target_page() -> str:
    for page in get_accessible_page_definitions("main"):
        return page.path
    return "pages/3_muj_ucet.py"


def apply_authenticated_user(
    user_payload: dict[str, object],
    *,
    access_token: str | None = None,
    expires_at: object = None,
) -> None:
    st.session_state["authenticated"] = True
    if access_token is not None:
        st.session_state["auth_token"] = access_token
    if expires_at is not None:
        st.session_state["auth_token_expires_at"] = expires_at
    st.session_state["auth_user"] = str(user_payload.get("username") or "")
    st.session_state["auth_email"] = user_payload.get("email")
    st.session_state["auth_is_admin"] = bool(user_payload.get("is_admin"))
    st.session_state["auth_allowed_sections"] = tuple(user_payload.get("allowed_sections") or ())
    st.session_state["auth_allowed_pages"] = tuple(user_payload.get("allowed_pages") or ())
    st.session_state["auth_allowed_devices"] = tuple(user_payload.get("allowed_devices") or ())
    st.session_state["auth_last_login_at"] = user_payload.get("last_login_at")


def login(username: str, password: str) -> bool:
    session_payload = api_login(username, password)
    apply_authenticated_user(
        session_payload.user,
        access_token=session_payload.access_token,
        expires_at=session_payload.expires_at,
    )
    return True


def logout() -> None:
    access_token = get_auth_token()
    if access_token:
        try:
            api_logout(access_token)
        except DashboardApiError:
            pass
    st.session_state["authenticated"] = False
    st.session_state["auth_token"] = ""
    st.session_state["auth_token_expires_at"] = None
    st.session_state["auth_user"] = ""
    st.session_state["auth_email"] = None
    st.session_state["auth_is_admin"] = False
    st.session_state["auth_allowed_sections"] = ()
    st.session_state["auth_allowed_pages"] = ()
    st.session_state["auth_allowed_devices"] = ()
    st.session_state["auth_last_login_at"] = None
    st.session_state["post_login_redirect"] = ""


def refresh_current_user() -> bool:
    access_token = get_auth_token()
    if not access_token:
        return False
    try:
        user_payload = api_get_me(access_token)
    except DashboardApiError:
        logout()
        return False
    apply_authenticated_user(user_payload)
    return True


def require_login(redirect_target: str | None = None) -> None:
    init_auth_state()
    if not st.session_state["authenticated"]:
        if redirect_target:
            st.session_state["requested_login_redirect"] = redirect_target
        st.warning("Nejprve se prihlas na strance Login.")
        st.page_link("login.py", label="Prejit na Login")
        st.stop()
    if not refresh_current_user():
        st.warning("Prihlaseni expirovalo nebo API neni dostupne. Prihlas se znovu.")
        st.stop()


def require_admin() -> None:
    require_login()
    if not is_admin():
        st.error("Tato stranka je dostupna pouze adminovi.")
        st.stop()


def require_page_access(page_key: str) -> None:
    page = get_page_definition(page_key)
    require_login(page.path if page is not None else None)

    if page is None:
        st.error("Neznama stranka dashboardu.")
        st.stop()

    if page.admin_only and not is_admin():
        st.error("Tato stranka je dostupna pouze adminovi.")
        st.stop()

    if page.section_key and not has_section_access(page.section_key):
        section = get_section_definition(page.section_key)
        if section is not None and section.requires_device_permissions and not get_allowed_devices():
            st.error("Prihlasenemu uzivateli nejsou prirazena zadna zarizeni pro tuto sekci.")
        else:
            st.error("Na tuto stranku nemas opravneni.")
        st.stop()

    if page.configurable and not is_admin() and page.key not in get_allowed_pages():
        st.error("Na tuto stranku nemas opravneni.")
        st.stop()


def get_page_sidebar_location(page: object) -> str | None:
    definition = get_page_definition_by_path(getattr(page, "_page", None))
    if definition is None:
        return None
    return definition.sidebar_location


def render_sidebar_nav(pages: list[object], current_page: object) -> None:
    init_auth_state()
    if not pages:
        return

    with st.sidebar:
        general_pages: list[object] = []
        section_pages: dict[str, list[object]] = {section.key: [] for section in SECTIONS}

        for page in pages:
            definition = get_page_definition_by_path(getattr(page, "_page", None))
            if definition is None or definition.section_key is None:
                general_pages.append(page)
                continue
            section_pages.setdefault(definition.section_key, []).append(page)

        rendered_any = False
        for page in general_pages:
            st.page_link(
                page,
                label=getattr(page, "title", None),
                icon=getattr(page, "icon", None) or None,
                disabled=page == current_page,
            )
            rendered_any = True

        for section in SECTIONS:
            current_section_pages = section_pages.get(section.key, [])
            if not current_section_pages:
                continue
            if rendered_any:
                st.markdown("---")
            st.caption(section.label)
            for page in current_section_pages:
                st.page_link(
                    page,
                    label=getattr(page, "title", None),
                    icon=getattr(page, "icon", None) or None,
                    disabled=page == current_page,
                )
            rendered_any = True


def render_sidebar_footer(pages: list[object], current_page: object) -> None:
    init_auth_state()
    if not st.session_state["authenticated"]:
        return

    footer_pages: dict[str, object] = {}
    for page in pages:
        definition = get_page_definition_by_path(getattr(page, "_page", None))
        if definition is None or definition.sidebar_location != "footer":
            continue
        footer_pages[definition.key] = page

    with st.sidebar:
        st.markdown("---")
        st.caption("Správa")

        for page_definition in get_dashboard_pages("footer"):
            page = footer_pages.get(page_definition.key)
            if page is None:
                continue
            st.page_link(
                page,
                label=page_definition.title,
                icon=page_definition.icon or None,
                disabled=page == current_page,
            )

        st.caption(f"Přihlášen: {st.session_state['auth_user']}")
        if st.button("Odhlásit"):
            logout()
            st.rerun()
