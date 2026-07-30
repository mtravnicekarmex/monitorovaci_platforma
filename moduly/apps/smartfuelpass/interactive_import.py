from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from core.db.connect import get_session_pg
from moduly.apps.smartfuelpass.database.db_init import ensure_smartfuelpass_tables
from moduly.apps.smartfuelpass.service import (
    LOGIN_PATH_FRAGMENT,
    SmartFuelPassError,
    _create_playwright_context,
    _load_playwright_api,
    _smartfuel_login_timeout_seconds,
    _smartfuel_login_url,
    load_main_table,
    open_charging_sessions,
    open_company_dashboard,
    set_charge_sessions_page_length,
)
from moduly.apps.smartfuelpass.sync import (
    build_charge_sessions_sync_rows,
    upsert_charge_sessions_sync_rows,
)


INTERACTIVE_IMPORT_TASK_NAME = "Monitoring_SmartFuelPass_Interactive_Import"
INTERACTIVE_IMPORT_STATES = frozenset(
    {"idle", "starting", "waiting_for_login", "importing", "success", "error"}
)
DEFAULT_INTERACTIVE_LOGIN_TIMEOUT_SECONDS = 900
DEFAULT_STATE_DIRECTORY = Path(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData")
) / "monitorovaci_platforma" / "smartfuelpass"
DEFAULT_STATUS_PATH = DEFAULT_STATE_DIRECTORY / "interactive_import_status.json"
DEFAULT_LOCK_PATH = DEFAULT_STATE_DIRECTORY / "interactive_import.lock"


@dataclass(frozen=True)
class InteractiveImportStatus:
    state: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    raw_row_count: int | None = None
    completed_row_count: int | None = None
    invalid_row_count: int | None = None
    skipped_missing_id_count: int | None = None
    upserted_count: int | None = None
    error_category: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.state not in INTERACTIVE_IMPORT_STATES:
            raise ValueError(f"Unsupported interactive import state: {self.state!r}")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _configured_login_wait_seconds() -> int:
    raw = os.environ.get("SMARTFUELPASS_INTERACTIVE_LOGIN_TIMEOUT_SECONDS", "")
    if raw.strip():
        return max(60, int(raw))
    return max(DEFAULT_INTERACTIVE_LOGIN_TIMEOUT_SECONDS, _smartfuel_login_timeout_seconds())


def write_interactive_import_status(
    status: InteractiveImportStatus,
    *,
    status_path: Path = DEFAULT_STATUS_PATH,
) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(status.to_dict(), ensure_ascii=True, sort_keys=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=status_path.parent,
            prefix=f".{status_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, status_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def read_interactive_import_status(
    *,
    status_path: Path = DEFAULT_STATUS_PATH,
) -> InteractiveImportStatus:
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        return InteractiveImportStatus(**payload)
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return InteractiveImportStatus(
            state="idle",
            updated_at=_now_iso(),
            message="Interaktivni import zatim nema zaznamenany beh.",
        )


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextmanager
def interactive_import_lock(
    *,
    lock_path: Path = DEFAULT_LOCK_PATH,
) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                existing_pid = int(lock_path.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                existing_pid = -1
            if _pid_is_running(existing_pid):
                raise SmartFuelPassError("Interaktivni SmartFuelPass import jiz probiha.")
            lock_path.unlink(missing_ok=True)
            continue
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            descriptor = -1
            yield
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            lock_path.unlink(missing_ok=True)
        return
    raise SmartFuelPassError("Nelze ziskat zamek interaktivniho SmartFuelPass importu.")


def _wait_for_manual_login(page, *, timeout_seconds: int) -> None:
    login_path = urlparse(_smartfuel_login_url()).path.rstrip("/").casefold()
    deadline = time.monotonic() + max(timeout_seconds, 60)
    while time.monotonic() < deadline:
        current_path = urlparse(str(page.url or "")).path.rstrip("/").casefold()
        if (
            current_path
            and current_path != login_path
            and LOGIN_PATH_FRAGMENT.casefold() not in current_path
        ):
            return
        page.wait_for_timeout(1000)
    raise SmartFuelPassError(
        "Vyprsel cas pro rucni prihlaseni do SmartFuelPass."
    )


def _sanitized_error_category(error: Exception) -> str:
    message = str(error).casefold()
    if "jiz probiha" in message or "zamek" in message:
        return "already_running"
    if "vyprsel cas" in message:
        return "login_timeout"
    if "table" in message or "tabulk" in message:
        return "portal_table_unavailable"
    if "database" in message or "sql" in message:
        return "database_error"
    return "interactive_import_error"


def _launch_interactive_browser(playwright):
    try:
        return playwright.chromium.launch(channel="chrome", headless=False)
    except Exception:
        return playwright.chromium.launch(headless=False)


def run_interactive_import(
    *,
    status_path: Path = DEFAULT_STATUS_PATH,
    lock_path: Path = DEFAULT_LOCK_PATH,
    login_timeout_seconds: int | None = None,
) -> InteractiveImportStatus:
    started_at = _now_iso()
    with interactive_import_lock(lock_path=lock_path):
        write_interactive_import_status(
            InteractiveImportStatus(
                state="starting",
                updated_at=started_at,
                started_at=started_at,
                message="Oteviram interaktivni prohlizec.",
            ),
            status_path=status_path,
        )
        browser = None
        context = None
        try:
            sync_playwright, _ = _load_playwright_api()
            with sync_playwright() as playwright:
                browser = _launch_interactive_browser(playwright)
                context = _create_playwright_context(browser)
                page = context.new_page()
                page.goto(
                    _smartfuel_login_url(),
                    wait_until="domcontentloaded",
                    timeout=_smartfuel_login_timeout_seconds() * 1000,
                )
                waiting_status = InteractiveImportStatus(
                    state="waiting_for_login",
                    updated_at=_now_iso(),
                    started_at=started_at,
                    message="Dokoncete prihlaseni v otevrenem okne prohlizece.",
                )
                write_interactive_import_status(waiting_status, status_path=status_path)
                _wait_for_manual_login(
                    page,
                    timeout_seconds=(
                        login_timeout_seconds or _configured_login_wait_seconds()
                    ),
                )
                importing_status = InteractiveImportStatus(
                    state="importing",
                    updated_at=_now_iso(),
                    started_at=started_at,
                    message="Prihlaseni dokonceno, nacitam nabijeci relace.",
                )
                write_interactive_import_status(importing_status, status_path=status_path)
                open_company_dashboard(page)
                open_charging_sessions(page)
                set_charge_sessions_page_length(page)
                dataframe = load_main_table(page)

                ensure_smartfuelpass_tables()
                rows, stats = build_charge_sessions_sync_rows(dataframe)
                session = get_session_pg()
                try:
                    stats["upserted_count"] = upsert_charge_sessions_sync_rows(
                        session,
                        rows,
                    )
                finally:
                    session.close()

                finished_at = _now_iso()
                result = InteractiveImportStatus(
                    state="success",
                    updated_at=finished_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    raw_row_count=int(stats["raw_row_count"]),
                    completed_row_count=int(stats["completed_row_count"]),
                    invalid_row_count=int(stats["invalid_row_count"]),
                    skipped_missing_id_count=int(stats["skipped_missing_id_count"]),
                    upserted_count=int(stats["upserted_count"]),
                    message="Interaktivni SmartFuelPass import byl dokoncen.",
                )
                write_interactive_import_status(result, status_path=status_path)
                return result
        except Exception as exc:
            finished_at = _now_iso()
            result = InteractiveImportStatus(
                state="error",
                updated_at=finished_at,
                started_at=started_at,
                finished_at=finished_at,
                error_category=_sanitized_error_category(exc),
                message="Interaktivni SmartFuelPass import nebyl dokoncen.",
            )
            write_interactive_import_status(result, status_path=status_path)
            return result
        finally:
            if context is not None:
                with suppress(Exception):
                    context.close()
            if browser is not None:
                with suppress(Exception):
                    browser.close()
