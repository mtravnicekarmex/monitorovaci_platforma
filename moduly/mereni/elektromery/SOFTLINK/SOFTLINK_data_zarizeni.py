from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic

from decouple import config
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


USERNAME = config("SOFTUSE")
PASSWORD = config("SOFTPASS")
SOFTLINK_PORTAL_URL = "https://ldsportal.softlink.cz"
SOFTLINK_DEVICE_API_URL = "https://cem2.softlink.cz/cemapi/api?id=46"
DEFAULT_TIMEOUT_MS = 180000

SOFTLINK_ZARIZENI_COLUMNS = [
    "me_id",
    "me_desc",
    "me_serial",
    "me_typ_pzn",
    "me_plom",
    "me_zapoc",
    "mis_id",
    "met_id",
    "me_od",
    "me_do",
    "me_over",
]
SOFTLINK_DATE_COLUMNS = ["me_od", "me_do", "me_over"]


@dataclass(frozen=True)
class _SoftlinkRequestWindow:
    date_from_ms: int
    date_to_ms: int


def _auth_state_path() -> Path:
    return Path(__file__).resolve().parent / "lds_auth.json"


def _build_request_window() -> _SoftlinkRequestWindow:
    date_from_ms = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
    date_to_ms = int(datetime.now().timestamp() * 1000)
    return _SoftlinkRequestWindow(date_from_ms=date_from_ms, date_to_ms=date_to_ms)


def _fetch_devices_from_page(portal_page, request_window: _SoftlinkRequestWindow):
    return portal_page.evaluate(
        """
        async ({date_from, date_to, apiUrl}) => {
            const response = await fetch(apiUrl, {
                method: "POST",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    mit_id: 105,
                    od: date_from,
                    do: date_to,
                    typ: "DEN"
                })
            });

            return {
                status: response.status,
                data: await response.json()
            };
        }
        """,
        {
            "date_from": request_window.date_from_ms,
            "date_to": request_window.date_to_ms,
            "apiUrl": SOFTLINK_DEVICE_API_URL,
        },
    )


def _apply_timeouts(context, page, timeout_ms: int) -> None:
    context.set_default_timeout(timeout_ms)
    context.set_default_navigation_timeout(timeout_ms)
    page.set_default_timeout(timeout_ms)
    page.set_default_navigation_timeout(timeout_ms)


def _saved_session_looks_valid(response: object) -> bool:
    if not isinstance(response, dict):
        return False
    status = response.get("status")
    data = response.get("data")
    return int(status or 0) == 200 and isinstance(data, list)


def _run_playwright_action_fallbacks(actions):
    last_timeout_error = None
    for action in actions:
        try:
            return action()
        except PlaywrightTimeoutError as exc:
            last_timeout_error = exc
    if last_timeout_error is not None:
        raise last_timeout_error
    raise RuntimeError("Nebyla zadana zadna Playwright akce.")


def _fallback_step_timeout(timeout_ms: int) -> int:
    return max(750, min(timeout_ms, 1500))


def _click_portal_entry(page, timeout_ms: int) -> None:
    step_timeout = _fallback_step_timeout(timeout_ms)
    _run_playwright_action_fallbacks(
        (
            lambda: page.get_by_role("link", name="Vstoupit do portálu").click(timeout=step_timeout),
            lambda: page.get_by_role("link", name="Enter").click(timeout=step_timeout),
            lambda: page.locator("a").first.click(timeout=step_timeout),
        )
    )


def _fill_login_username(portal, *, username: str, timeout_ms: int) -> None:
    step_timeout = _fallback_step_timeout(timeout_ms)
    _run_playwright_action_fallbacks(
        (
            lambda: portal.get_by_label("Přístupové jméno").fill(username, timeout=step_timeout),
            lambda: portal.get_by_label("Login").fill(username, timeout=step_timeout),
            lambda: portal.get_by_placeholder("Login").fill(username, timeout=step_timeout),
        )
    )


def _fill_login_password(portal, *, password: str, timeout_ms: int) -> None:
    step_timeout = _fallback_step_timeout(timeout_ms)
    _run_playwright_action_fallbacks(
        (
            lambda: portal.get_by_label("Přístupové heslo").fill(password, timeout=step_timeout),
            lambda: portal.get_by_label("Password").fill(password, timeout=step_timeout),
            lambda: portal.get_by_placeholder("Password").fill(password, timeout=step_timeout),
        )
    )


def _submit_login(portal, timeout_ms: int) -> None:
    step_timeout = _fallback_step_timeout(timeout_ms)
    _run_playwright_action_fallbacks(
        (
            lambda: portal.get_by_role("button", name="Přihlásit").click(timeout=step_timeout),
            lambda: portal.get_by_role("button", name="Sign in").click(timeout=step_timeout),
        )
    )


def _open_portal_login_page(context, page, timeout_ms: int):
    try:
        with context.expect_page(timeout=min(timeout_ms, 7000)) as page_info:
            _click_portal_entry(page, timeout_ms)
        portal = page_info.value
        portal.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        return portal
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        return page


def _wait_for_authenticated_device_fetch(portal, request_window: _SoftlinkRequestWindow, *, timeout_ms: int):
    deadline = monotonic() + max(timeout_ms, 1) / 1000.0
    last_response = None
    while monotonic() < deadline:
        last_response = _fetch_devices_from_page(portal, request_window)
        if _saved_session_looks_valid(last_response):
            return last_response
        remaining_ms = max(int((deadline - monotonic()) * 1000), 0)
        if remaining_ms <= 0:
            break
        portal.wait_for_timeout(min(1000, remaining_ms))
    raise PlaywrightTimeoutError("SOFTLINK login nedokoncil autorizovany dotaz na seznam zarizeni.")


def _try_fetch_with_saved_session(*, headless: bool, timeout_ms: int):
    auth_path = _auth_state_path()
    if not auth_path.exists():
        return None

    request_window = _build_request_window()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        try:
            context.close()
        except Exception:
            pass
        context = browser.new_context(storage_state=str(auth_path))
        page = context.new_page()
        _apply_timeouts(context, page, timeout_ms)

        try:
            page.goto(SOFTLINK_PORTAL_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            response = _fetch_devices_from_page(page, request_window)
            if _saved_session_looks_valid(response):
                return response
            return None
        finally:
            browser.close()


def _login_and_fetch(*, headless: bool, timeout_ms: int):
    request_window = _build_request_window()
    auth_path = _auth_state_path()
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        _apply_timeouts(context, page, timeout_ms)

        try:
            page.goto(SOFTLINK_PORTAL_URL, wait_until="domcontentloaded", timeout=timeout_ms)

            portal = _open_portal_login_page(context, page, timeout_ms)
            _apply_timeouts(context, portal, timeout_ms)
            _fill_login_username(portal, username=USERNAME, timeout_ms=timeout_ms)
            _fill_login_password(portal, password=PASSWORD, timeout_ms=timeout_ms)
            _submit_login(portal, timeout_ms)
            context.storage_state(path=str(auth_path))
            return _wait_for_authenticated_device_fetch(portal, request_window, timeout_ms=timeout_ms)
        finally:
            browser.close()


def SOFTLINK_dotaz_zarizeni(
    *,
    headless: bool = True,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    retry_headful_on_timeout: bool = False,
):
    saved_session_response = _try_fetch_with_saved_session(headless=headless, timeout_ms=timeout_ms)
    if saved_session_response is not None:
        return saved_session_response

    try:
        return _login_and_fetch(headless=headless, timeout_ms=timeout_ms)
    except PlaywrightTimeoutError:
        if retry_headful_on_timeout and headless:
            return _login_and_fetch(headless=False, timeout_ms=max(timeout_ms, DEFAULT_TIMEOUT_MS))
        raise
