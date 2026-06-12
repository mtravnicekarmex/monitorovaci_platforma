from __future__ import annotations

from datetime import timedelta
import ipaddress
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.time_utils import utc_now_naive
from app.dashboard_session import DASHBOARD_SESSION_COOKIE_NAME
from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.api_client import (
    any_dashboard_users_exist,
    get_me as api_get_me,
    login as api_login,
    logout as api_logout,
    refresh_session as api_refresh_session,
)
from moduly.apps.dashboard.navigation_config import (
    SECTIONS,
    SIDEBAR_SECTION_ORDER,
    DashboardPage,
    get_dashboard_pages,
    get_page_definition,
    get_page_definition_by_path,
    get_section_definition,
)


LOGIN_CLIENT_IP_FORWARDING_ENABLED = True
SESSION_RENEWAL_INTERVAL = timedelta(minutes=5)


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
    st.session_state.setdefault("auth_cookie_restore_attempted", False)
    st.session_state.setdefault("auth_cookie_clear_pending", False)
    st.session_state.setdefault("auth_cookie_sync_runs_remaining", 0)
    st.session_state.setdefault("auth_last_token_refresh_at", None)


def _clear_auth_state(*, clear_browser_cookie: bool) -> None:
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
    st.session_state["auth_cookie_sync_runs_remaining"] = 0
    st.session_state["auth_last_token_refresh_at"] = None
    if clear_browser_cookie:
        st.session_state["auth_cookie_clear_pending"] = True


def restore_auth_state_from_browser_cookie() -> bool:
    init_auth_state()
    if st.session_state["authenticated"]:
        return True
    if st.session_state["auth_cookie_restore_attempted"]:
        return False
    if st.session_state["auth_cookie_clear_pending"]:
        return False

    st.session_state["auth_cookie_restore_attempted"] = True
    access_token = str(st.context.cookies.get(DASHBOARD_SESSION_COOKIE_NAME, "") or "")
    if not access_token:
        return False

    try:
        session_payload = api_refresh_session(access_token)
    except DashboardApiError as exc:
        if exc.status_code == 401:
            _clear_auth_state(clear_browser_cookie=True)
        return False

    apply_authenticated_user(
        session_payload.user,
        access_token=session_payload.access_token,
        expires_at=session_payload.expires_at,
    )
    return True


def _build_browser_session_sync_html(*, access_token: str | None = None, clear: bool = False) -> str:
    method = "DELETE" if clear else "POST"
    headers = "{}"
    if access_token:
        headers = json.dumps({"Authorization": f"Bearer {access_token}"})

    return f"""
<script>
(async () => {{
    const options = {{
        method: {json.dumps(method)},
        headers: {headers},
        credentials: "same-origin",
        cache: "no-store"
    }};
    for (let attempt = 0; attempt < 3; attempt += 1) {{
        try {{
            const response = await fetch("/api/v1/auth/browser-session", options);
            if (response.ok || (response.status >= 400 && response.status < 500)) {{
                return;
            }}
        }} catch (error) {{
            // A short retry covers navigation immediately after login.
        }}
        await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }}
}})();
</script>
"""


def sync_browser_auth_session() -> None:
    init_auth_state()
    if st.session_state["auth_cookie_clear_pending"]:
        st.html(
            _build_browser_session_sync_html(clear=True),
            unsafe_allow_javascript=True,
        )
        st.session_state["auth_cookie_clear_pending"] = False
        return

    remaining_runs = int(st.session_state["auth_cookie_sync_runs_remaining"])
    access_token = get_auth_token()
    if not st.session_state["authenticated"] or not access_token or remaining_runs <= 0:
        return

    st.html(
        _build_browser_session_sync_html(access_token=access_token),
        unsafe_allow_javascript=True,
    )
    st.session_state["auth_cookie_sync_runs_remaining"] = remaining_runs - 1


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


def _get_dashboard_client_ip() -> str | None:
    headers = getattr(st.context, "headers", {})
    forwarded_for = str(headers.get("X-Forwarded-For", "") or "")
    candidate = forwarded_for.split(",", 1)[0].strip()
    if not candidate:
        return None
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        return None


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
        st.session_state["auth_cookie_sync_runs_remaining"] = 2
        st.session_state["auth_last_token_refresh_at"] = utc_now_naive()
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
    client_ip = _get_dashboard_client_ip()
    if client_ip:
        session_payload = api_login(username, password, client_ip=client_ip)
    else:
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
    _clear_auth_state(clear_browser_cookie=True)


def _session_renewal_due() -> bool:
    last_refresh_at = st.session_state.get("auth_last_token_refresh_at")
    if last_refresh_at is None:
        return True
    return utc_now_naive() - last_refresh_at >= SESSION_RENEWAL_INTERVAL


def refresh_current_user() -> bool:
    access_token = get_auth_token()
    if not access_token:
        return False
    try:
        if _session_renewal_due():
            session_payload = api_refresh_session(access_token)
            apply_authenticated_user(
                session_payload.user,
                access_token=session_payload.access_token,
                expires_at=session_payload.expires_at,
            )
        else:
            user_payload = api_get_me(access_token)
            apply_authenticated_user(user_payload)
    except DashboardApiError as exc:
        if exc.status_code == 401:
            _clear_auth_state(clear_browser_cookie=True)
        return False
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
        sections_by_key = {section.key: section for section in SECTIONS}
        ordered_sections = [
            sections_by_key[section_key]
            for section_key in SIDEBAR_SECTION_ORDER
            if section_key in sections_by_key
        ]
        ordered_sections.extend(
            section
            for section in SECTIONS
            if section.key not in SIDEBAR_SECTION_ORDER
        )

        for page in general_pages:
            st.page_link(
                page,
                label=getattr(page, "title", None),
                icon=getattr(page, "icon", None) or None,
                disabled=page == current_page,
            )
            rendered_any = True

        for section in ordered_sections:
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
