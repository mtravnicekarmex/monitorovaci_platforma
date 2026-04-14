from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from html import escape
from io import StringIO
import json
import base64
import mimetypes
import re
import time
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from decouple import config

from app.time_utils import utc_now_naive

if TYPE_CHECKING:
    from playwright.sync_api import Page, Playwright


DEFAULT_BASE_URL = "https://portal.smartfuelpass.com/"
DEFAULT_LOGIN_URL = "https://portal.smartfuelpass.com/User/Login"
DEFAULT_SESSION_COOKIE_PATH = Path("data") / "smartfuelpass" / "session_cookies.json"
DEFAULT_REPORT_EXPORT_PATH = Path("data") / "smartfuelpass" / "reporting_snapshot.json"
DEFAULT_REPORTS_DIR = Path("data") / "smartfuelpass" / "reports"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_LOGIN_TIMEOUT_SECONDS = 300
DEFAULT_TABLE_WAIT_TIMEOUT_SECONDS = 45
DEFAULT_NAVIGATION_TIMEOUT_MS = 15000
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/135.0 Safari/537.36"
DEFAULT_DASHBOARD_PATH = "/Fuel/Merchant/Dashboard?contractId=12147&accountId=0"
DEFAULT_CHARGING_SESSIONS_LABEL = "Nabíjecí relace"
DEFAULT_SUMMARY_LABEL = "Celkově"
DEFAULT_REPORT_SUBJECT_NAME = "ARMEX HOLDING, a.s."
DEFAULT_LOGO_PATH = Path("data") / "smartfuelpass" / "smfp_logo_white.svg"
LOGIN_PATH_FRAGMENT = "/User/Login"


class SmartFuelPassError(RuntimeError):
    pass


class SmartFuelPassAuthenticationError(SmartFuelPassError):
    pass


@dataclass(frozen=True)
class SmartFuelPassReportTarget:
    key: str
    url: str


@dataclass(frozen=True)
class SmartFuelPassPageSnapshot:
    key: str
    url: str
    title: str
    text: str
    html: str


@dataclass(frozen=True)
class SmartFuelPassChargeSessionRow:
    occurred_at: datetime
    occurred_at_label: str
    location_name: str
    connector_id: str
    amount_czk: float
    amount_label: str
    date_range_label: str
    kwh_label: str
    tariff_label: str
    price_label: str


@dataclass(frozen=True)
class SmartFuelPassPeriodSummary:
    key: str
    label: str
    start: datetime | None
    end: datetime | None
    session_count: int
    total_amount: float
    location_count: int
    connector_count: int
    first_session_at: datetime | None
    last_session_at: datetime | None


@dataclass(frozen=True)
class SmartFuelPassChargeSessionsReport:
    subject_name: str
    generated_at: datetime
    source_row_count: int
    valid_row_count: int
    invalid_row_count: int
    last_week: SmartFuelPassPeriodSummary
    previous_month: SmartFuelPassPeriodSummary
    total: SmartFuelPassPeriodSummary
    last_week_rows: tuple[SmartFuelPassChargeSessionRow, ...]
    current_month_rows: tuple[SmartFuelPassChargeSessionRow, ...]
    previous_month_rows: tuple[SmartFuelPassChargeSessionRow, ...]


def _resolve_path(raw_value: str | Path | None, default_path: Path) -> Path:
    if isinstance(raw_value, Path):
        path = raw_value
    elif isinstance(raw_value, str) and raw_value.strip():
        path = Path(raw_value.strip()).expanduser()
    else:
        path = default_path

    if path.is_absolute():
        return path
    return Path.cwd() / path


def _smartfuel_base_url() -> str:
    return config("SMARTFUELPASS_BASE_URL", default=DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL


def _smartfuel_login_url() -> str:
    return config("SMARTFUELPASS_LOGIN_URL", default=DEFAULT_LOGIN_URL).strip() or DEFAULT_LOGIN_URL


def _smartfuel_dashboard_path() -> str:
    return config("SMARTFUELPASS_DASHBOARD_PATH", default=DEFAULT_DASHBOARD_PATH).strip() or DEFAULT_DASHBOARD_PATH


def _smartfuel_charging_sessions_label() -> str:
    return (
        config(
            "SMARTFUELPASS_CHARGING_SESSIONS_LABEL",
            default=DEFAULT_CHARGING_SESSIONS_LABEL,
        ).strip()
        or DEFAULT_CHARGING_SESSIONS_LABEL
    )


def _smartfuel_summary_label() -> str:
    return config("SMARTFUELPASS_SUMMARY_LABEL", default=DEFAULT_SUMMARY_LABEL).strip() or DEFAULT_SUMMARY_LABEL


def _smartfuel_report_subject_name() -> str:
    return (
        config(
            "SMARTFUELPASS_REPORT_SUBJECT_NAME",
            default=DEFAULT_REPORT_SUBJECT_NAME,
        ).strip()
        or DEFAULT_REPORT_SUBJECT_NAME
    )


def _smartfuel_logo_path() -> Path:
    return _resolve_path(
        config("SMARTFUELPASS_LOGO_PATH", default=str(DEFAULT_LOGO_PATH)),
        DEFAULT_LOGO_PATH,
    )


def _smartfuel_reports_dir() -> Path:
    return _resolve_path(
        config("SMARTFUELPASS_REPORTS_DIR", default=str(DEFAULT_REPORTS_DIR)),
        DEFAULT_REPORTS_DIR,
    )


def _smartfuel_email() -> str:
    return config(
        "SMARTFUELPASS_EMAIL",
        default=config("SMARTFUELPASSUSE", default=""),
    ).strip()


def _smartfuel_password() -> str:
    return config(
        "SMARTFUELPASS_PASSWORD",
        default=config("SMARTFUELPASSPASS", default=""),
    ).strip()


def _canonicalize_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold()


def _normalize_target_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if not cleaned:
        raise SmartFuelPassError("SmartFuelPass report target URL is empty.")
    return urljoin(_smartfuel_base_url(), cleaned)


def _slugify_target_key(raw_value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", raw_value.casefold()).strip("_")
    return normalized or "page"


def _derive_target_key_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return "dashboard"
    return _slugify_target_key("_".join(parts))


def _flatten_dataframe_column(column: object) -> str:
    if isinstance(column, tuple):
        parts = []
        for part in column:
            text = str(part or "").strip()
            if not text or text.startswith("Unnamed:"):
                continue
            parts.append(text)
        return " ".join(parts).strip()
    return str(column or "").strip()


def _resolve_cookie_path(cookie_path: str | Path | None = None) -> Path:
    return _resolve_path(
        cookie_path or config(
            "SMARTFUELPASS_SESSION_COOKIES_PATH",
            default=str(DEFAULT_SESSION_COOKIE_PATH),
        ),
        DEFAULT_SESSION_COOKIE_PATH,
    )


def _write_cookie_payload(cookies: list[dict[str, Any]], cookie_path: str | Path | None = None) -> Path:
    resolved_cookie_path = _resolve_cookie_path(cookie_path)
    resolved_cookie_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_cookie_path.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return resolved_cookie_path


def parse_report_targets(raw_targets: str | None) -> tuple[SmartFuelPassReportTarget, ...]:
    if raw_targets is None:
        raw_targets = ""

    lines = [
        item.strip()
        for chunk in raw_targets.splitlines()
        for item in chunk.split(";")
        if item.strip()
    ]
    if not lines:
        return (SmartFuelPassReportTarget(key="dashboard", url=_smartfuel_base_url()),)

    targets: list[SmartFuelPassReportTarget] = []
    seen_keys: set[str] = set()
    for line in lines:
        raw_key: str | None = None
        raw_url = line
        if "=" in line:
            potential_key, potential_url = line.split("=", 1)
            if re.fullmatch(r"[A-Za-z0-9_-]+", potential_key.strip()):
                raw_key = potential_key.strip()
                raw_url = potential_url

        url = _normalize_target_url(raw_url)
        key = _slugify_target_key(raw_key) if raw_key else _derive_target_key_from_url(url)
        if key in seen_keys:
            raise SmartFuelPassError(f"Duplicate SmartFuelPass report target key '{key}'.")
        seen_keys.add(key)
        targets.append(SmartFuelPassReportTarget(key=key, url=url))

    return tuple(targets)


def load_report_targets_from_config() -> tuple[SmartFuelPassReportTarget, ...]:
    raw_targets = config("SMARTFUELPASS_REPORT_TARGETS", default="")
    return parse_report_targets(raw_targets)


def _load_cookie_payload(cookie_path: str | Path | None = None) -> list[dict[str, Any]]:
    resolved_cookie_path = _resolve_cookie_path(cookie_path)
    if not resolved_cookie_path.exists():
        raise SmartFuelPassAuthenticationError(
            "SmartFuelPass session cookie file was not found. "
            f"Expected path: {resolved_cookie_path}"
        )

    try:
        payload = json.loads(resolved_cookie_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SmartFuelPassAuthenticationError(
            f"SmartFuelPass session cookie file is not valid JSON: {resolved_cookie_path}"
        ) from exc

    raw_cookies = payload.get("cookies", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_cookies, list):
        raise SmartFuelPassAuthenticationError(
            "SmartFuelPass session cookie payload must be a list or an object with 'cookies'."
        )

    cookies: list[dict[str, Any]] = []
    for raw_cookie in raw_cookies:
        if not isinstance(raw_cookie, dict):
            continue

        name = str(raw_cookie.get("name") or "").strip()
        if not name:
            continue

        cookie_payload = {
            "name": name,
            "value": str(raw_cookie.get("value") or ""),
            "domain": str(raw_cookie.get("domain") or "").strip(),
            "path": str(raw_cookie.get("path") or "/").strip() or "/",
        }
        for bool_key in ("secure", "httpOnly"):
            if bool_key in raw_cookie:
                cookie_payload[bool_key] = bool(raw_cookie[bool_key])
        same_site = raw_cookie.get("sameSite")
        if isinstance(same_site, str) and same_site.strip():
            cookie_payload["sameSite"] = same_site.strip()
        expires = raw_cookie.get("expires", raw_cookie.get("expiry"))
        if isinstance(expires, (int, float)):
            cookie_payload["expires"] = float(expires)

        cookies.append(cookie_payload)

    if not cookies:
        raise SmartFuelPassAuthenticationError(
            f"SmartFuelPass session cookie file does not contain usable cookies: {resolved_cookie_path}"
        )

    return cookies


def create_authenticated_session(
    *,
    cookie_path: str | Path | None = None,
    user_agent: str | None = None,
) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent
            or config("SMARTFUELPASS_USER_AGENT", default=DEFAULT_USER_AGENT).strip()
            or DEFAULT_USER_AGENT,
        }
    )

    for cookie in _load_cookie_payload(cookie_path):
        cookie_kwargs = {
            "path": cookie["path"],
        }
        if cookie["domain"]:
            cookie_kwargs["domain"] = cookie["domain"]
        session.cookies.set(cookie["name"], cookie["value"], **cookie_kwargs)

    return session


def _looks_like_login_page(url: str, html_content: str) -> bool:
    if LOGIN_PATH_FRAGMENT.casefold() in urlparse(url).path.casefold():
        return True

    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.title.get_text(" ", strip=True).casefold() if soup.title else ""
    if "login - smart fuel pass" in title:
        return True

    login_form = soup.find("form", id="loginForm")
    if login_form is not None:
        return True

    body_text = soup.get_text(" ", strip=True).casefold()
    return "please log in" in body_text and "smart fuel pass" in body_text


def _extract_page_text(html_content: str) -> tuple[str, str]:
    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    lines = [
        line.strip()
        for line in soup.get_text(separator="\n").splitlines()
        if line.strip()
    ]
    return title, "\n".join(lines)


def fetch_reporting_snapshots(
    *,
    targets: Iterable[SmartFuelPassReportTarget] | None = None,
    cookie_path: str | Path | None = None,
    timeout_seconds: int | None = None,
    auto_login: bool = True,
    headless: bool = True,
) -> tuple[SmartFuelPassPageSnapshot, ...]:
    resolved_targets = tuple(targets or load_report_targets_from_config())
    if not resolved_targets:
        raise SmartFuelPassError("No SmartFuelPass report targets are configured.")

    resolved_timeout = timeout_seconds or config(
        "SMARTFUELPASS_REQUEST_TIMEOUT_SECONDS",
        default=DEFAULT_TIMEOUT_SECONDS,
        cast=int,
    )
    resolved_cookie_path = _resolve_cookie_path(cookie_path)

    for attempt in range(2 if auto_login else 1):
        try:
            session = create_authenticated_session(cookie_path=resolved_cookie_path)
        except SmartFuelPassAuthenticationError:
            if attempt > 0 or not auto_login:
                raise
            login_and_save_session_with_playwright(
                cookie_path=resolved_cookie_path,
                timeout_seconds=resolved_timeout,
                headless=headless,
            )
            continue

        try:
            snapshots: list[SmartFuelPassPageSnapshot] = []
            for target in resolved_targets:
                response = session.get(target.url, timeout=resolved_timeout, allow_redirects=True)
                response.raise_for_status()

                if _looks_like_login_page(response.url, response.text):
                    raise SmartFuelPassAuthenticationError(
                        "SmartFuelPass session appears to be expired or unauthenticated. "
                        f"Portal returned the login page for {target.url}."
                    )

                title, page_text = _extract_page_text(response.text)
                snapshots.append(
                    SmartFuelPassPageSnapshot(
                        key=target.key,
                        url=target.url,
                        title=title,
                        text=page_text,
                        html=response.text,
                    )
                )

            return tuple(snapshots)
        except SmartFuelPassAuthenticationError:
            if attempt > 0 or not auto_login:
                raise
            login_and_save_session_with_playwright(
                cookie_path=resolved_cookie_path,
                timeout_seconds=resolved_timeout,
                headless=headless,
            )
        finally:
            session.close()

    raise SmartFuelPassAuthenticationError(
        "SmartFuelPass automatic login retry did not produce an authenticated session."
    )


def build_reporting_export(
    *,
    targets: Iterable[SmartFuelPassReportTarget] | None = None,
    cookie_path: str | Path | None = None,
    timeout_seconds: int | None = None,
    auto_login: bool = True,
    headless: bool = True,
) -> dict[str, Any]:
    snapshots = fetch_reporting_snapshots(
        targets=targets,
        cookie_path=cookie_path,
        timeout_seconds=timeout_seconds,
        auto_login=auto_login,
        headless=headless,
    )
    return {
        "generated_at": utc_now_naive().isoformat(),
        "source": "smartfuelpass",
        "page_count": len(snapshots),
        "pages": [asdict(snapshot) for snapshot in snapshots],
    }


def save_reporting_export(
    *,
    output_path: str | Path | None = None,
    targets: Iterable[SmartFuelPassReportTarget] | None = None,
    cookie_path: str | Path | None = None,
    timeout_seconds: int | None = None,
    auto_login: bool = True,
    headless: bool = True,
) -> Path:
    export_payload = build_reporting_export(
        targets=targets,
        cookie_path=cookie_path,
        timeout_seconds=timeout_seconds,
        auto_login=auto_login,
        headless=headless,
    )
    resolved_output_path = _resolve_path(
        output_path or config(
            "SMARTFUELPASS_REPORT_OUTPUT_PATH",
            default=str(DEFAULT_REPORT_EXPORT_PATH),
        ),
        DEFAULT_REPORT_EXPORT_PATH,
    )
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(
        json.dumps(export_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return resolved_output_path


def _fill_input_by_id(driver: Any, input_id: str, value: str | None) -> None:
    if not value:
        return

    try:
        element = driver.find_element("id", input_id)
    except Exception:
        return

    clear = getattr(element, "clear", None)
    if callable(clear):
        clear()
    element.send_keys(value)


def _default_browser_driver_factory() -> Any:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:
        raise SmartFuelPassError(
            "Selenium is required to bootstrap a SmartFuelPass browser session."
        ) from exc

    options = Options()
    options.add_argument("--start-maximized")

    user_data_dir = config("SMARTFUELPASS_CHROME_USER_DATA_DIR", default="").strip()
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")

    profile_dir = config("SMARTFUELPASS_CHROME_PROFILE_DIR", default="").strip()
    if profile_dir:
        options.add_argument(f"--profile-directory={profile_dir}")

    return webdriver.Chrome(options=options)


def _wait_for_login_completion(driver: Any, login_url: str, timeout_seconds: int) -> None:
    login_path = urlparse(login_url).path.rstrip("/").casefold()
    deadline = time.time() + max(timeout_seconds, 1)

    while time.time() < deadline:
        current_url = str(getattr(driver, "current_url", "") or "")
        current_path = urlparse(current_url).path.rstrip("/").casefold()
        if current_path and current_path != login_path and LOGIN_PATH_FRAGMENT.casefold() not in current_path:
            return
        time.sleep(1)

    raise SmartFuelPassError(
        "Timed out waiting for SmartFuelPass login. "
        "Complete the browser login and reCAPTCHA in the opened window, then retry."
    )


def bootstrap_browser_session(
    *,
    cookie_path: str | Path | None = None,
    login_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
    timeout_seconds: int | None = None,
    driver_factory: Callable[[], Any] | None = None,
    wait_for_login_completion: Callable[[Any, str, int], None] | None = None,
) -> Path:
    if driver_factory is None and wait_for_login_completion is None:
        return login_and_save_session_with_playwright(
            cookie_path=cookie_path,
            login_url=login_url,
            email=email,
            password=password,
            timeout_seconds=timeout_seconds,
            headless=True,
        )

    resolved_login_url = login_url or _smartfuel_login_url()
    resolved_timeout = timeout_seconds or config(
        "SMARTFUELPASS_LOGIN_TIMEOUT_SECONDS",
        default=DEFAULT_LOGIN_TIMEOUT_SECONDS,
        cast=int,
    )
    resolved_cookie_path = _resolve_cookie_path(cookie_path)

    driver = (driver_factory or _default_browser_driver_factory)()
    try:
        driver.get(resolved_login_url)
        _fill_input_by_id(
            driver,
            "Email",
            email if email is not None else _smartfuel_email(),
        )
        _fill_input_by_id(
            driver,
            "Password",
            password if password is not None else _smartfuel_password(),
        )

        (wait_for_login_completion or _wait_for_login_completion)(
            driver,
            resolved_login_url,
            resolved_timeout,
        )

        cookies = driver.get_cookies()
        if not cookies:
            raise SmartFuelPassError("SmartFuelPass browser session did not expose any cookies to persist.")

        return _write_cookie_payload(cookies, resolved_cookie_path)
    finally:
        quit_method = getattr(driver, "quit", None)
        if callable(quit_method):
            quit_method()


def _load_playwright_api():
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    except ImportError as exc:
        raise SmartFuelPassError(
            "Playwright is required to load SmartFuelPass charge sessions and render the PDF report."
        ) from exc

    return sync_playwright, PlaywrightTimeoutError


def _click_playwright_login_button(page: Any, *, timeout_ms: int) -> None:
    _, playwright_timeout_error = _load_playwright_api()
    candidates = (
        page.get_by_role("button", name="Log in"),
        page.get_by_role("button", name="Přihlásit"),
        page.locator("button.g-recaptcha"),
        page.locator('button[type="submit"]'),
    )

    for locator in candidates:
        target = locator.first
        try:
            target.wait_for(state="visible", timeout=timeout_ms)
            target.click(timeout=timeout_ms)
            return
        except playwright_timeout_error:
            continue

    raise SmartFuelPassError("SmartFuelPass login form does not expose a clickable submit button.")


def perform_playwright_login(
    page: Any,
    *,
    login_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
    timeout_seconds: int | None = None,
) -> str:
    _, playwright_timeout_error = _load_playwright_api()
    resolved_login_url = login_url or _smartfuel_login_url()
    resolved_timeout_seconds = timeout_seconds or config(
        "SMARTFUELPASS_LOGIN_TIMEOUT_SECONDS",
        default=DEFAULT_LOGIN_TIMEOUT_SECONDS,
        cast=int,
    )
    resolved_timeout_ms = resolved_timeout_seconds * 1000
    resolved_email = email if email is not None else _smartfuel_email()
    resolved_password = password if password is not None else _smartfuel_password()

    if not resolved_email or not resolved_password:
        raise SmartFuelPassError("SmartFuelPass automatic login requires SMARTFUELPASS_EMAIL and SMARTFUELPASS_PASSWORD.")

    page.goto(resolved_login_url, wait_until="domcontentloaded")
    page.locator("#Email").fill(resolved_email)
    page.locator("#Password").fill(resolved_password)
    _click_playwright_login_button(page, timeout_ms=resolved_timeout_ms)

    try:
        page.wait_for_url(lambda url: LOGIN_PATH_FRAGMENT not in url, timeout=resolved_timeout_ms)
        page.wait_for_load_state("networkidle", timeout=resolved_timeout_ms)
    except playwright_timeout_error as exc:
        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=3000)
        except Exception:
            body_text = ""
        raise SmartFuelPassError(
            "Automatic SmartFuelPass login did not complete successfully. "
            f"Current URL: {page.url}. Body preview: {body_text[:400]!r}"
        ) from exc

    if _looks_like_login_page(page.url, page.content()):
        raise SmartFuelPassError(
            "Automatic SmartFuelPass login returned to the login page unexpectedly."
        )

    return page.url


def login_and_save_session_with_playwright(
    *,
    cookie_path: str | Path | None = None,
    login_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
    timeout_seconds: int | None = None,
    headless: bool = True,
) -> Path:
    sync_playwright, _ = _load_playwright_api()
    resolved_cookie_path = _resolve_cookie_path(cookie_path)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            perform_playwright_login(
                page,
                login_url=login_url,
                email=email,
                password=password,
                timeout_seconds=timeout_seconds,
            )
            cookies = context.cookies()
            if not cookies:
                raise SmartFuelPassError("SmartFuelPass automatic login succeeded but no cookies were returned.")
            return _write_cookie_payload(cookies, resolved_cookie_path)
        finally:
            context.close()
            browser.close()


def _normalize_playwright_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "name": cookie["name"],
        "value": cookie["value"],
        "path": cookie.get("path") or "/",
    }
    domain = str(cookie.get("domain") or "").strip()
    if domain:
        normalized["domain"] = domain
    else:
        normalized["url"] = _smartfuel_base_url()

    for key in ("secure", "httpOnly", "sameSite", "expires"):
        if key in cookie:
            normalized[key] = cookie[key]

    return normalized


def _create_playwright_context(
    browser: Any,
    *,
    cookie_path: str | Path | None = None,
    ignore_missing_cookie_path: bool = False,
) -> Any:
    context = browser.new_context()
    try:
        cookies = _load_cookie_payload(cookie_path)
    except SmartFuelPassError:
        if not ignore_missing_cookie_path:
            raise
        cookies = []

    if cookies:
        context.add_cookies([
            _normalize_playwright_cookie(cookie)
            for cookie in cookies
        ])
    return context


def _assert_authenticated_page(page: Any, *, source_url: str) -> None:
    html_content = page.content()
    if _looks_like_login_page(page.url, html_content):
        raise SmartFuelPassAuthenticationError(
            "SmartFuelPass session appears to be expired or unauthenticated. "
            f"Portal returned the login page for {source_url}."
        )


def _auto_login_if_needed(
    page: Any,
    context: Any,
    *,
    cookie_path: str | Path | None = None,
    login_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
    timeout_seconds: int | None = None,
) -> bool:
    if not _looks_like_login_page(page.url, page.content()):
        return False

    perform_playwright_login(
        page,
        login_url=login_url,
        email=email,
        password=password,
        timeout_seconds=timeout_seconds,
    )
    _write_cookie_payload(context.cookies(), cookie_path)
    return True


def open_company_dashboard(page: Any, *, dashboard_path: str | None = None, timeout_ms: int | None = None) -> None:
    _, playwright_timeout_error = _load_playwright_api()
    resolved_dashboard_path = dashboard_path or _smartfuel_dashboard_path()
    resolved_timeout = timeout_ms or DEFAULT_NAVIGATION_TIMEOUT_MS
    target_url = urljoin(_smartfuel_base_url(), resolved_dashboard_path.lstrip("/"))

    page.goto(target_url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=resolved_timeout)
    except playwright_timeout_error:
        pass

    _assert_authenticated_page(page, source_url=target_url)
    if "/fuel/merchant/dashboard" in urlparse(page.url).path.casefold():
        return

    select = page.locator(
        f'xpath=//select[option[@value="{resolved_dashboard_path}"]]'
    ).first
    try:
        select.wait_for(state="visible", timeout=resolved_timeout)
        select.select_option(value=resolved_dashboard_path)
        page.wait_for_url(
            lambda url: "/Fuel/Merchant/Dashboard" in url,
            timeout=resolved_timeout,
        )
        page.wait_for_load_state("networkidle", timeout=resolved_timeout)
    except playwright_timeout_error as exc:
        raise SmartFuelPassError(
            f"Nepodarilo se otevrit dashboard {resolved_dashboard_path}."
        ) from exc


def _candidate_labels(primary_label: str, *fallback_labels: str) -> tuple[str, ...]:
    unique_labels = []
    for label in (primary_label, *fallback_labels):
        cleaned = label.strip()
        if cleaned and cleaned not in unique_labels:
            unique_labels.append(cleaned)
    return tuple(unique_labels)


def _click_navigation_candidate(page: Any, labels: Iterable[str], *, timeout_ms: int) -> str:
    _, playwright_timeout_error = _load_playwright_api()
    previous_url = page.url

    for label in labels:
        candidates = (
            page.get_by_role("link", name=label),
            page.get_by_role("button", name=label),
            page.locator("nav").get_by_text(label, exact=True),
            page.get_by_text(label, exact=True),
        )
        for locator in candidates:
            target = locator.first
            try:
                target.wait_for(state="visible", timeout=timeout_ms)
                target.click(timeout=timeout_ms)
                try:
                    page.wait_for_url(lambda url: url != previous_url, timeout=timeout_ms)
                except playwright_timeout_error:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                return label
            except playwright_timeout_error:
                continue

    raise SmartFuelPassError(f"Nepodarilo se kliknout na zadny navigation label: {tuple(labels)}")


def open_charging_sessions(page: Any, *, timeout_ms: int | None = None) -> None:
    _click_navigation_candidate(
        page,
        _candidate_labels(
            _smartfuel_charging_sessions_label(),
            "Charging sessions",
        ),
        timeout_ms=timeout_ms or DEFAULT_NAVIGATION_TIMEOUT_MS,
    )


def open_summary(page: Any, *, timeout_ms: int | None = None) -> None:
    _click_navigation_candidate(
        page,
        _candidate_labels(
            _smartfuel_summary_label(),
            "Summary",
            "All",
        ),
        timeout_ms=timeout_ms or DEFAULT_NAVIGATION_TIMEOUT_MS,
    )


def _score_charge_sessions_dataframe(dataframe: pd.DataFrame) -> int:
    canonical_columns = {
        _canonicalize_text(_flatten_dataframe_column(column))
        for column in dataframe.columns
    }
    score = 0
    if {"hodnoty meridel", "datum mereni", "datum"} & canonical_columns:
        score += 100
    if {"suma", "castka", "price", "amount"} & canonical_columns:
        score += 80
    if {"nazev ev lokace", "ev lokace", "location"} & canonical_columns:
        score += 20
    if {"konektor evse id", "evse id", "connector"} & canonical_columns:
        score += 10
    score += min(dataframe.shape[0], 50)
    return score


def _is_loading_placeholder_dataframe(dataframe: pd.DataFrame) -> bool:
    if dataframe.empty:
        return False

    flattened_values = [
        _canonicalize_text(value)
        for row in dataframe.fillna("").itertuples(index=False)
        for value in row
        if str(value).strip()
    ]
    if not flattened_values:
        return False

    loading_markers = {
        "nacitam, prosim cekejte ...",
        "nacitam, prosim cekejte...",
        "loading",
        "loading...",
    }
    return all(value in loading_markers for value in flattened_values)


def _parse_html_table_fallback(table_html: str) -> list[pd.DataFrame]:
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("HTML snippet does not contain a table element.")

    parsed_rows: list[list[str]] = []
    header_row_index: int | None = None
    max_columns = 0

    for row_index, row in enumerate(table.find_all("tr")):
        cells = row.find_all(["th", "td"])
        if not cells:
            continue

        values: list[str] = []
        for cell in cells:
            cell_text = " ".join(cell.stripped_strings)
            colspan = max(int(cell.get("colspan") or 1), 1)
            values.extend([cell_text] * colspan)

        parsed_rows.append(values)
        max_columns = max(max_columns, len(values))

        if header_row_index is None and row.find("th") is not None:
            header_row_index = len(parsed_rows) - 1

    if not parsed_rows:
        raise ValueError("HTML table does not contain any data rows.")

    normalized_rows = [
        row + [""] * (max_columns - len(row))
        for row in parsed_rows
    ]

    resolved_header_index = 0 if header_row_index is None else header_row_index
    header = normalized_rows[resolved_header_index]
    data_rows = normalized_rows[resolved_header_index + 1:]
    return [pd.DataFrame(data_rows, columns=header)]


def _read_table_html(table_html: str) -> list[pd.DataFrame]:
    try:
        return pd.read_html(StringIO(table_html))
    except ImportError:
        return _parse_html_table_fallback(table_html)


def load_main_table(page: Any, *, timeout_seconds: int | None = None) -> pd.DataFrame:
    resolved_timeout_seconds = timeout_seconds or config(
        "SMARTFUELPASS_TABLE_WAIT_TIMEOUT_SECONDS",
        default=DEFAULT_TABLE_WAIT_TIMEOUT_SECONDS,
        cast=int,
    )
    deadline = time.time() + max(resolved_timeout_seconds, 1)
    selectors = (
        "main table:visible",
        '[role="main"] table:visible',
        "table:visible",
    )

    best_dataframe: pd.DataFrame | None = None
    best_score = -1
    best_area = -1
    last_error: Exception | None = None

    while time.time() < deadline:
        for selector in selectors:
            tables = page.locator(selector)
            table_count = tables.count()

            for index in range(table_count):
                table = tables.nth(index)

                try:
                    table_html = table.evaluate("element => element.outerHTML")
                    dataframes = _read_table_html(table_html)
                except ValueError as exc:
                    last_error = exc
                    continue

                for dataframe in dataframes:
                    if _is_loading_placeholder_dataframe(dataframe):
                        continue

                    score = _score_charge_sessions_dataframe(dataframe)
                    area = dataframe.shape[0] * max(dataframe.shape[1], 1)
                    if score > best_score or (score == best_score and area > best_area):
                        best_dataframe = dataframe
                        best_score = score
                        best_area = area

                    if score >= 180 and not dataframe.empty:
                        return dataframe

        page.wait_for_timeout(1500)

    if best_dataframe is not None:
        return best_dataframe

    raise SmartFuelPassError("Nepodarilo se nacist zadnou viditelnou HTML tabulku.") from last_error


def fetch_charge_sessions_dataframe(
    *,
    cookie_path: str | Path | None = None,
    headless: bool = True,
    dashboard_path: str | None = None,
    timeout_seconds: int | None = None,
) -> pd.DataFrame:
    sync_playwright, _ = _load_playwright_api()
    resolved_timeout_seconds = timeout_seconds or config(
        "SMARTFUELPASS_REQUEST_TIMEOUT_SECONDS",
        default=DEFAULT_TIMEOUT_SECONDS,
        cast=int,
    )
    resolved_cookie_path = _resolve_cookie_path(cookie_path)
    target_url = urljoin(_smartfuel_base_url(), (dashboard_path or _smartfuel_dashboard_path()).lstrip("/"))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = _create_playwright_context(
            browser,
            cookie_path=resolved_cookie_path,
            ignore_missing_cookie_path=True,
        )
        page = context.new_page()
        try:
            page.set_default_timeout(resolved_timeout_seconds * 1000)
            page.goto(target_url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=resolved_timeout_seconds * 1000)
            except Exception:
                pass

            _auto_login_if_needed(
                page,
                context,
                cookie_path=resolved_cookie_path,
                timeout_seconds=resolved_timeout_seconds,
            )
            open_company_dashboard(page, dashboard_path=dashboard_path)
            open_charging_sessions(page)
            open_summary(page)
            return load_main_table(page)
        finally:
            context.close()
            browser.close()


def parse_czech_currency(value: object) -> float:
    if pd.isna(value):
        return 0.0

    normalized = (
        str(value)
        .replace("\xa0", "")
        .replace(" ", "")
        .replace("Kč", "")
        .replace("CZK", "")
        .replace("(", "-")
        .replace(")", "")
        .strip()
    )
    normalized = re.sub(r"[^0-9,.\-]", "", normalized)
    if normalized.count(",") and normalized.count("."):
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif normalized.count(",") > 1:
        head, tail = normalized.rsplit(",", 1)
        normalized = head.replace(",", "") + "." + tail
    elif normalized.count(".") > 1:
        head, tail = normalized.rsplit(".", 1)
        normalized = head.replace(".", "") + "." + tail
    elif "," in normalized:
        normalized = normalized.replace(",", ".")

    return float(normalized) if normalized not in {"", "-"} else 0.0


def _parse_datetime_text(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None

    for pattern in ("%d.%m.%Y %H:%M", "%m/%d/%Y %I:%M %p"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue

    try:
        fallback = pd.to_datetime(text, dayfirst=True, errors="coerce")
    except Exception:
        fallback = pd.NaT

    if pd.isna(fallback):
        return None
    return fallback.to_pydatetime()


def _extract_first_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None

    match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2})", text)
    if match:
        return _parse_datetime_text(match.group(1))

    match = re.search(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)", text, flags=re.IGNORECASE)
    if match:
        return _parse_datetime_text(match.group(1).upper())

    return None


def _extract_kwh_label(value: object) -> str:
    text = str(value or "")
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*kWh", text, flags=re.IGNORECASE)
    if not match:
        return "-"
    return f"{match.group(1).replace('.', ',')} kWh"


def _extract_tariff_label(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    match = re.search(
        r"AdHoc(?: nabíjení| charging)\s*-\s*[^()]+?\([^)]*\)\s+(.+?)\s+\([^)]*\)\s+\d",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        tariff = re.sub(r"\s+", " ", match.group(1)).strip(" -")
        tariff = re.sub(r"\s+%", "%", tariff)
        tariff = tariff.replace("Kè", "Kč")
        if tariff:
            return tariff

    match = re.search(r"AdHoc(?: nabíjení| charging)\s*-\s*([^(]+)", text, flags=re.IGNORECASE)
    if match:
        tariff = re.sub(r"\s+", " ", match.group(1)).strip(" -")
        tariff = re.sub(r"\s+%", "%", tariff)
        tariff = tariff.replace("Kè", "Kč")
        if tariff:
            return tariff
    return "-"


def _clean_location_name(value: object) -> str:
    text = re.sub(r"\bnull\b", "", str(value or ""), flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "-"


def _format_charge_session_period(started_at: datetime | None, ended_at: datetime | None) -> str:
    if pd.isna(started_at):
        started_at = None
    if pd.isna(ended_at):
        ended_at = None

    if started_at is None and ended_at is None:
        return "-"
    if started_at is None:
        return ended_at.strftime("%d.%m.%Y %H:%M")
    if ended_at is None:
        return started_at.strftime("%d.%m.%Y %H:%M")
    if started_at.date() == ended_at.date():
        return f"{started_at.strftime('%d.%m.%Y %H:%M')} - {ended_at.strftime('%H:%M')}"
    return f"{started_at.strftime('%d.%m.%Y %H:%M')} - {ended_at.strftime('%d.%m.%Y %H:%M')}"


def last_completed_week_period(reference: datetime | None = None) -> tuple[datetime, datetime]:
    current = reference or datetime.now()
    start_of_today = current.replace(hour=0, minute=0, second=0, microsecond=0)
    period_start = start_of_today - timedelta(days=7)
    period_end = start_of_today - timedelta(microseconds=1)
    return period_start, period_end


def previous_month_period(reference: datetime | None = None) -> tuple[datetime, datetime]:
    current = reference or datetime.now()
    first_day_this_month = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day_previous_month = first_day_this_month - timedelta(days=1)
    first_day_previous_month = last_day_previous_month.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    end_of_previous_month = last_day_previous_month.replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    return first_day_previous_month, end_of_previous_month


def current_month_period(reference: datetime | None = None) -> tuple[datetime, datetime]:
    current = reference or datetime.now()
    first_day_this_month = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return first_day_this_month, current


def format_czk(value: float) -> str:
    whole, fraction = f"{value:.2f}".split(".")
    return f"{int(whole):,}".replace(",", " ") + f",{fraction} Kč"


def _resolve_dataframe_column(columns: Iterable[object], aliases: Iterable[str], *, required: bool = True) -> str | None:
    flattened_columns = [_flatten_dataframe_column(column) for column in columns]
    mapping = {
        _canonicalize_text(column): column
        for column in flattened_columns
        if column
    }

    for alias in aliases:
        resolved = mapping.get(_canonicalize_text(alias))
        if resolved:
            return resolved

    if required:
        raise SmartFuelPassError(
            "V tabulce chybi pozadovany sloupec. "
            f"Hledane varianty: {tuple(aliases)}. Dostupne sloupce: {flattened_columns}"
        )
    return None


def _parse_charge_session_datetimes(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.map(_parse_datetime_text), errors="coerce")


def _prepare_charge_sessions_dataframe(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    prepared = dataframe.copy()
    prepared.columns = [_flatten_dataframe_column(column) for column in prepared.columns]

    occurred_at_column = _resolve_dataframe_column(
        prepared.columns,
        ("Hodnoty měřidel", "Datum měření", "Datum", "Meter values", "Measurement date", "Date"),
    )
    amount_column = _resolve_dataframe_column(
        prepared.columns,
        ("Suma", "Částka", "Amount", "Price"),
    )
    location_column = _resolve_dataframe_column(
        prepared.columns,
        ("Název EV lokace", "EV lokace", "Location", "EV location name"),
        required=False,
    )
    connector_column = _resolve_dataframe_column(
        prepared.columns,
        ("Konektor EVSE ID", "EVSE ID", "Connector", "Connector evse id"),
        required=False,
    )
    started_column = _resolve_dataframe_column(
        prepared.columns,
        ("Čas spuštění", "Cas spusteni", "Start time"),
        required=False,
    )
    ended_column = _resolve_dataframe_column(
        prepared.columns,
        ("Čas ukončení", "Cas ukonceni", "End time"),
        required=False,
    )
    public_id_column = _resolve_dataframe_column(
        prepared.columns,
        ("Veřejné ID", "Verejne ID", "Public ID", "Public id"),
        required=False,
    )

    prepared["session_at"] = _parse_charge_session_datetimes(prepared[occurred_at_column])
    prepared["amount_czk"] = prepared[amount_column].map(parse_czech_currency)
    prepared["occurred_at_label"] = prepared[occurred_at_column].astype(str).str.strip()
    prepared["amount_label"] = prepared[amount_column].astype(str).str.strip()
    prepared["started_at"] = (
        prepared[started_column].map(_extract_first_datetime)
        if started_column
        else pd.Series([None] * len(prepared), index=prepared.index)
    )
    prepared["ended_at"] = (
        prepared[ended_column].map(_extract_first_datetime)
        if ended_column
        else pd.Series([None] * len(prepared), index=prepared.index)
    )
    prepared["location_name"] = (
        prepared[location_column].map(_clean_location_name)
        if location_column
        else "-"
    )
    prepared["connector_id"] = (
        prepared[connector_column].fillna("").astype(str).str.strip()
        if connector_column
        else ""
    )
    prepared["kwh_label"] = (
        prepared[public_id_column].map(_extract_kwh_label)
        if public_id_column
        else "-"
    )
    prepared["tariff_label"] = (
        prepared[public_id_column].map(_extract_tariff_label)
        if public_id_column
        else "-"
    )
    prepared["price_label"] = prepared["amount_label"]
    prepared["date_range_label"] = prepared.apply(
        lambda row: _format_charge_session_period(row["started_at"], row["ended_at"]),
        axis=1,
    )

    prepared = prepared[~prepared["amount_label"].isin(("", "-"))].copy()
    invalid_row_count = int(prepared["session_at"].isna().sum())
    prepared = prepared[prepared["session_at"].notna()].copy()
    prepared.sort_values("session_at", inplace=True)
    prepared.reset_index(drop=True, inplace=True)

    return prepared, invalid_row_count


def _non_empty_unique_count(series: pd.Series) -> int:
    return int(series.replace("", pd.NA).dropna().nunique())


def _build_charge_session_rows(dataframe: pd.DataFrame) -> tuple[SmartFuelPassChargeSessionRow, ...]:
    rows = dataframe.sort_values("session_at", ascending=False)
    return tuple(
        SmartFuelPassChargeSessionRow(
            occurred_at=row.session_at.to_pydatetime(),
            occurred_at_label=str(row.occurred_at_label),
            location_name=str(row.location_name),
            connector_id=str(row.connector_id),
            amount_czk=float(row.amount_czk),
            amount_label=str(row.amount_label),
            date_range_label=str(row.date_range_label),
            kwh_label=str(row.kwh_label),
            tariff_label=str(row.tariff_label),
            price_label=str(row.price_label),
        )
        for row in rows.itertuples(index=False)
    )


def _build_period_summary(
    *,
    key: str,
    label: str,
    dataframe: pd.DataFrame,
    start: datetime | None,
    end: datetime | None,
) -> SmartFuelPassPeriodSummary:
    if dataframe.empty:
        return SmartFuelPassPeriodSummary(
            key=key,
            label=label,
            start=start,
            end=end,
            session_count=0,
            total_amount=0.0,
            location_count=0,
            connector_count=0,
            first_session_at=None,
            last_session_at=None,
        )

    return SmartFuelPassPeriodSummary(
        key=key,
        label=label,
        start=start,
        end=end,
        session_count=int(len(dataframe)),
        total_amount=round(float(dataframe["amount_czk"].sum()), 2),
        location_count=_non_empty_unique_count(dataframe["location_name"]),
        connector_count=_non_empty_unique_count(dataframe["connector_id"]),
        first_session_at=dataframe["session_at"].min().to_pydatetime(),
        last_session_at=dataframe["session_at"].max().to_pydatetime(),
    )


def build_charge_sessions_report(
    dataframe: pd.DataFrame,
    *,
    reference_datetime: datetime | None = None,
    subject_name: str | None = None,
) -> SmartFuelPassChargeSessionsReport:
    resolved_reference = reference_datetime or datetime.now()
    prepared, invalid_row_count = _prepare_charge_sessions_dataframe(dataframe)

    last_week_start, last_week_end = last_completed_week_period(resolved_reference)
    current_month_start, current_month_end = current_month_period(resolved_reference)
    previous_month_start, previous_month_end = previous_month_period(resolved_reference)

    last_week_rows = prepared[
        prepared["session_at"].between(last_week_start, last_week_end, inclusive="both")
    ].copy()
    current_month_rows = prepared[
        prepared["session_at"].between(current_month_start, current_month_end, inclusive="both")
    ].copy()
    current_month_rows = current_month_rows[
        ~current_month_rows["session_at"].between(last_week_start, last_week_end, inclusive="both")
    ].copy()
    previous_month_rows = prepared[
        prepared["session_at"].between(previous_month_start, previous_month_end, inclusive="both")
    ].copy()

    total_start = None if prepared.empty else prepared["session_at"].min().to_pydatetime()
    total_end = None if prepared.empty else prepared["session_at"].max().to_pydatetime()

    return SmartFuelPassChargeSessionsReport(
        subject_name=subject_name or _smartfuel_report_subject_name(),
        generated_at=resolved_reference,
        source_row_count=int(len(dataframe)),
        valid_row_count=int(len(prepared)),
        invalid_row_count=invalid_row_count,
        last_week=_build_period_summary(
            key="last_week",
            label="Poslední týden",
            dataframe=last_week_rows,
            start=last_week_start,
            end=last_week_end,
        ),
        previous_month=_build_period_summary(
            key="previous_month",
            label="Minulý měsíc",
            dataframe=previous_month_rows,
            start=previous_month_start,
            end=previous_month_end,
        ),
        total=_build_period_summary(
            key="total",
            label="Celkem",
            dataframe=prepared,
            start=total_start,
            end=total_end,
        ),
        last_week_rows=_build_charge_session_rows(last_week_rows),
        current_month_rows=_build_charge_session_rows(current_month_rows),
        previous_month_rows=_build_charge_session_rows(previous_month_rows),
    )


def _format_datetime(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%d.%m.%Y %H:%M")


def _format_date_range(start: datetime | None, end: datetime | None) -> str:
    if start is None or end is None:
        return "-"
    return f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"


def _load_logo_data_uri() -> str:
    logo_path = _smartfuel_logo_path()
    if not logo_path.exists():
        raise SmartFuelPassError(f"Logo file was not found: {logo_path}")

    mime_type = mimetypes.guess_type(str(logo_path))[0] or "image/png"
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _build_summary_card(summary: SmartFuelPassPeriodSummary) -> str:
    return (
        "<div class='summary-card'>"
        f"<div class='summary-title'>{escape(summary.label)}</div>"
        f"<div class='summary-range'>{escape(_format_date_range(summary.start, summary.end))}</div>"
        "<div class='summary-metrics'>"
        f"<div><span class='metric-label'>Relace</span><span class='metric-value'>{summary.session_count}</span></div>"
        f"<div><span class='metric-label'>Částka</span><span class='metric-value'>{escape(format_czk(summary.total_amount))}</span></div>"
        f"<div><span class='metric-label'>Lokace</span><span class='metric-value'>{summary.location_count}</span></div>"
        f"<div><span class='metric-label'>Konektory</span><span class='metric-value'>{summary.connector_count}</span></div>"
        "</div>"
        "</div>"
    )


def _build_rows_section(title: str, rows: Iterable[SmartFuelPassChargeSessionRow]) -> str:
    materialized_rows = tuple(rows)
    if not materialized_rows:
        return (
            "<section class='section'>"
            f"<h2>{escape(title)}</h2>"
            "<p class='empty-state'>V tomto období nebyly nalezeny žádné nabíjecí relace.</p>"
            "</section>"
        )

    rows_html = []
    for row in materialized_rows:
        rows_html.append(
            "<tr>"
            f"<td>{escape(row.date_range_label)}</td>"
            f"<td>{escape(row.kwh_label)}</td>"
            f"<td>{escape(row.location_name)}</td>"
            f"<td>{escape(row.tariff_label)}</td>"
            f"<td class='amount'>{escape(row.price_label)}</td>"
            "</tr>"
        )

    return (
        "<section class='section'>"
        f"<h2>{escape(title)}</h2>"
        "<table>"
        "<thead><tr><th>Datum</th><th>kWh</th><th>Lokace</th><th>Tarif</th><th class='amount'>Cena</th></tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
        "</section>"
    )


def build_charge_sessions_report_html(report: SmartFuelPassChargeSessionsReport) -> str:
    logo_data_uri = _load_logo_data_uri()

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Smart Fuel Pass report nabíjecích relací</title>
  <style>
    @page {{
      size: A4;
      margin: 14mm 12mm;
    }}
    body {{
      font-family: "Segoe UI", Arial, sans-serif;
      color: #16202a;
      font-size: 11px;
      line-height: 1.45;
      margin: 0;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 2px solid #0f4c81;
      padding-bottom: 12px;
      margin-bottom: 18px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      background: #0f4c81;
      border-radius: 10px;
      padding: 10px 16px;
    }}
    .brand img {{
      max-height: 68px;
      max-width: 260px;
      object-fit: contain;
    }}
    .meta {{
      color: #52606d;
      font-size: 12px;
      text-align: right;
      line-height: 1.6;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 18px;
    }}
    .summary-card {{
      border: 1px solid #d7dee5;
      border-radius: 10px;
      background: #f8fafc;
      padding: 12px;
      break-inside: avoid;
    }}
    .summary-title {{
      font-size: 16px;
      font-weight: 700;
      color: #0f4c81;
    }}
    .summary-range {{
      margin: 4px 0 10px;
      color: #52606d;
      font-size: 11px;
    }}
    .summary-metrics {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px 10px;
    }}
    .metric-label {{
      display: block;
      color: #6b7280;
      text-transform: uppercase;
      font-size: 10px;
      letter-spacing: 0.04em;
    }}
    .metric-value {{
      display: block;
      font-size: 15px;
      font-weight: 700;
      margin-top: 2px;
    }}
    .section {{
      margin-top: 18px;
      break-inside: avoid;
    }}
    .section h2 {{
      margin: 0 0 8px;
      font-size: 16px;
      color: #0f4c81;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    thead th {{
      text-align: left;
      padding: 8px;
      background: #0f4c81;
      color: #ffffff;
      font-size: 10px;
    }}
    tbody td {{
      padding: 7px 8px;
      border-bottom: 1px solid #e5e7eb;
      vertical-align: top;
    }}
    tbody tr:nth-child(even) {{
      background: #f8fafc;
    }}
    .amount {{
      text-align: right;
      white-space: nowrap;
    }}
    .empty-state {{
      margin: 0;
      color: #52606d;
    }}
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <img src="{logo_data_uri}" alt="Smart Fuel Pass logo">
    </div>
    <div class="meta">
      <strong>Subjekt:</strong> {escape(report.subject_name)}<br>
      <strong>Vygenerováno:</strong> {escape(_format_datetime(report.generated_at))}
    </div>
  </div>

  <div class="summary-grid">
    {_build_summary_card(report.last_week)}
    {_build_summary_card(report.previous_month)}
    {_build_summary_card(report.total)}
  </div>

  {_build_rows_section("Poslední týden", report.last_week_rows)}
  {_build_rows_section("Tento měsíc", report.current_month_rows)}
  {_build_rows_section("Minulý měsíc", report.previous_month_rows)}
</body>
</html>"""


def save_charge_sessions_report_pdf(
    report: SmartFuelPassChargeSessionsReport,
    *,
    output_path: str | Path | None = None,
) -> Path:
    sync_playwright, _ = _load_playwright_api()
    default_output_path = _smartfuel_reports_dir() / f"smartfuelpass_charge_sessions_{report.generated_at:%Y%m%d_%H%M%S}.pdf"
    resolved_output_path = _resolve_path(output_path or default_output_path, default_output_path)
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    html = build_charge_sessions_report_html(report)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.emulate_media(media="screen")
            page.pdf(
                path=str(resolved_output_path),
                format="A4",
                print_background=True,
                margin={"top": "12mm", "right": "10mm", "bottom": "12mm", "left": "10mm"},
            )
        finally:
            browser.close()

    return resolved_output_path


def build_charge_sessions_report_from_portal(
    *,
    cookie_path: str | Path | None = None,
    reference_datetime: datetime | None = None,
    subject_name: str | None = None,
    headless: bool = True,
) -> SmartFuelPassChargeSessionsReport:
    dataframe = fetch_charge_sessions_dataframe(
        cookie_path=cookie_path,
        headless=headless,
    )
    return build_charge_sessions_report(
        dataframe,
        reference_datetime=reference_datetime,
        subject_name=subject_name,
    )


def generate_charge_sessions_report_pdf(
    *,
    cookie_path: str | Path | None = None,
    output_path: str | Path | None = None,
    reference_datetime: datetime | None = None,
    subject_name: str | None = None,
    headless: bool = True,
) -> Path:
    report = build_charge_sessions_report_from_portal(
        cookie_path=cookie_path,
        reference_datetime=reference_datetime,
        subject_name=subject_name,
        headless=headless,
    )
    return save_charge_sessions_report_pdf(report, output_path=output_path)
