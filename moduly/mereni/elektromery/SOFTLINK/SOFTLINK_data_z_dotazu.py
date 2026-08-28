from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic

from decouple import config
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


USERNAME = config("SOFTUSE")
PASSWORD = config("SOFTPASS")
SOFTLINK_PORTAL_URL = "https://ldsportal.softlink.cz"
SOFTLINK_MEASUREMENTS_API_URL = "https://cem2.softlink.cz/cemapi/api?id=45"
DEFAULT_TIMEOUT_MS = 180000


class SoftlinkMeasurementAuthError(RuntimeError):
    """Raised when SOFTLINK accepts neither the saved session nor login."""


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


def _api_response_to_json(response):
    status = response.status
    try:
        data = response.json()
    except Exception:
        data = None
    return {"status": status, "data": data}


def _build_measurements_headers(auth_token: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    return headers


def _extract_auth_token_from_storage_state(storage_state: object) -> str | None:
    if not isinstance(storage_state, dict):
        return None

    for origin in storage_state.get("origins") or ():
        if not isinstance(origin, dict):
            continue
        for item in origin.get("localStorage") or ():
            if not isinstance(item, dict) or item.get("name") != "cem_lds_auth":
                continue
            try:
                auth_data = json.loads(item.get("value") or "{}")
            except json.JSONDecodeError:
                return None
            token = auth_data.get("access_token")
            return token if isinstance(token, str) and token else None
    return None


def _load_auth_token_from_state_file(path: Path) -> str | None:
    try:
        storage_state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _extract_auth_token_from_storage_state(storage_state)


def _read_auth_token_from_page(page) -> str | None:
    token = page.evaluate(
        """
        () => {
            const raw = window.localStorage.getItem("cem_lds_auth");
            if (!raw) {
                return null;
            }
            try {
                const parsed = JSON.parse(raw);
                return parsed && typeof parsed.access_token === "string" ? parsed.access_token : null;
            } catch {
                return null;
            }
        }
        """
    )
    return token if isinstance(token, str) and token else None


def _wait_for_auth_token(page, *, timeout_ms: int) -> str:
    deadline = monotonic() + max(timeout_ms, 1) / 1000.0
    last_error = None

    while monotonic() < deadline:
        try:
            token = _read_auth_token_from_page(page)
            if token:
                return token
        except PlaywrightError as exc:
            last_error = exc

        remaining_ms = max(int((deadline - monotonic()) * 1000), 0)
        if remaining_ms <= 0:
            break
        page.wait_for_timeout(min(1000, remaining_ms))

    if last_error is not None:
        raise last_error
    raise SoftlinkMeasurementAuthError("SOFTLINK login nevratil autorizacni token pro mereni.")


def _fetch_measurements_with_request_context(
    context,
    request_window: _SoftlinkRequestWindow,
    *,
    auth_token: str | None = None,
):
    response = context.request.post(
        SOFTLINK_MEASUREMENTS_API_URL,
        headers=_build_measurements_headers(auth_token),
        data={
            "mit_id": 105,
            "od": request_window.date_from_ms,
            "do": request_window.date_to_ms,
            "typ": "DEN",
        },
    )
    return _api_response_to_json(response)


def _apply_timeouts(context, page, timeout_ms: int) -> None:
    context.set_default_timeout(timeout_ms)
    context.set_default_navigation_timeout(timeout_ms)
    page.set_default_timeout(timeout_ms)
    page.set_default_navigation_timeout(timeout_ms)


def _measurements_response_looks_valid(response: object) -> bool:
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
            lambda: page.get_by_role("link", name="Vstoupit do portalu").click(timeout=step_timeout),
            lambda: page.get_by_role("link", name="Vstoupit do portálu").click(timeout=step_timeout),
            lambda: page.get_by_role("link", name="Enter").click(timeout=step_timeout),
            lambda: page.locator("a").first.click(timeout=step_timeout),
        )
    )


def _fill_login_username(portal, *, username: str, timeout_ms: int) -> None:
    step_timeout = _fallback_step_timeout(timeout_ms)
    _run_playwright_action_fallbacks(
        (
            lambda: portal.get_by_label("Pristupove jmeno").fill(username, timeout=step_timeout),
            lambda: portal.get_by_label("Přístupové jméno").fill(username, timeout=step_timeout),
            lambda: portal.get_by_role("textbox", name="Pristupove jmeno").fill(username, timeout=step_timeout),
            lambda: portal.get_by_role("textbox", name="Přístupové jméno").fill(username, timeout=step_timeout),
            lambda: portal.get_by_label("Login").fill(username, timeout=step_timeout),
            lambda: portal.get_by_placeholder("Login").fill(username, timeout=step_timeout),
        )
    )


def _fill_login_password(portal, *, password: str, timeout_ms: int) -> None:
    step_timeout = _fallback_step_timeout(timeout_ms)
    _run_playwright_action_fallbacks(
        (
            lambda: portal.get_by_label("Pristupove heslo").fill(password, timeout=step_timeout),
            lambda: portal.get_by_label("Přístupové heslo").fill(password, timeout=step_timeout),
            lambda: portal.get_by_role("textbox", name="Pristupove heslo").fill(password, timeout=step_timeout),
            lambda: portal.get_by_role("textbox", name="Přístupové heslo").fill(password, timeout=step_timeout),
            lambda: portal.get_by_label("Password").fill(password, timeout=step_timeout),
            lambda: portal.get_by_placeholder("Password").fill(password, timeout=step_timeout),
        )
    )


def _submit_login(portal, timeout_ms: int) -> None:
    step_timeout = _fallback_step_timeout(timeout_ms)
    _run_playwright_action_fallbacks(
        (
            lambda: portal.get_by_role("button", name="Prihlasit").click(timeout=step_timeout),
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


def _raise_for_invalid_measurements_response(response: object) -> None:
    if not isinstance(response, dict):
        raise RuntimeError("SOFTLINK mereni nevratilo ocekavanou odpoved.")

    status = int(response.get("status") or 0)
    if status in (401, 403):
        raise SoftlinkMeasurementAuthError("SOFTLINK session/login neautorizovany pro mereni.")
    if status != 200:
        raise RuntimeError(f"SOFTLINK mereni vratilo neocekavany HTTP status {status}.")
    if not isinstance(response.get("data"), list):
        raise RuntimeError("SOFTLINK mereni nevratilo ocekavany seznam dat.")


def _wait_for_authenticated_measurements_fetch(
    context,
    request_window: _SoftlinkRequestWindow,
    *,
    timeout_ms: int,
    auth_token: str | None = None,
):
    deadline = monotonic() + max(timeout_ms, 1) / 1000.0
    last_response = None
    last_error = None

    while monotonic() < deadline:
        try:
            last_response = _fetch_measurements_with_request_context(
                context,
                request_window,
                auth_token=auth_token,
            )
            if _measurements_response_looks_valid(last_response):
                return last_response
        except PlaywrightError as exc:
            last_error = exc

        remaining_ms = max(int((deadline - monotonic()) * 1000), 0)
        if remaining_ms <= 0:
            break
        context.pages[0].wait_for_timeout(min(1000, remaining_ms))

    if last_response is not None:
        _raise_for_invalid_measurements_response(last_response)
    if last_error is not None:
        raise last_error
    raise PlaywrightTimeoutError("SOFTLINK login nedokoncil autorizovany dotaz na mereni.")


def _try_fetch_with_saved_session(*, headless: bool, timeout_ms: int):
    auth_path = _auth_state_path()
    if not auth_path.exists():
        return None

    auth_token = _load_auth_token_from_state_file(auth_path)
    if not auth_token:
        return None

    request_window = _build_request_window()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(auth_path))
        page = context.new_page()
        _apply_timeouts(context, page, timeout_ms)

        try:
            response = _fetch_measurements_with_request_context(
                context,
                request_window,
                auth_token=auth_token,
            )
            if _measurements_response_looks_valid(response):
                return response
            return None
        except PlaywrightError:
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
            auth_token = _wait_for_auth_token(portal, timeout_ms=timeout_ms)
            response = _wait_for_authenticated_measurements_fetch(
                context,
                request_window,
                timeout_ms=timeout_ms,
                auth_token=auth_token,
            )
            context.storage_state(path=str(auth_path))
            print("SOFTLINK login and measurements API succeeded")
            return response
        finally:
            browser.close()


def SOFTLINK_dotaz(
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
