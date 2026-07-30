from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime

from moduly.apps.smartfuelpass.interactive_import import (
    INTERACTIVE_IMPORT_TASK_NAME,
    read_interactive_import_status,
)
from services.api.schemas.admin import (
    SmartFuelPassInteractiveImportStartResponse,
    SmartFuelPassInteractiveImportStatusResponse,
)


POWERSHELL_EXECUTABLE = (
    r"C:\windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)
ACTIVE_IMPORT_STATES = frozenset({"starting", "waiting_for_login", "importing"})


class SmartFuelPassInteractiveUnavailableError(RuntimeError):
    pass


class SmartFuelPassInteractiveConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class InteractiveTaskProbe:
    registered: bool
    state: str | None
    interactive_user_available: bool


def _run_powershell_json(script: str) -> object:
    completed = subprocess.run(
        [
            POWERSHELL_EXECUTABLE,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = completed.stdout.strip()
    return json.loads(output) if output else None


def probe_interactive_task() -> InteractiveTaskProbe:
    if platform.system() != "Windows":
        return InteractiveTaskProbe(False, None, False)
    script = (
        f"$task = Get-ScheduledTask -TaskName "
        f"'{INTERACTIVE_IMPORT_TASK_NAME}' -ErrorAction SilentlyContinue; "
        "$interactiveSession = Get-Process explorer -ErrorAction SilentlyContinue | "
        "Where-Object { $_.SessionId -gt 0 } | Select-Object -First 1; "
        "[pscustomobject]@{"
        "registered = [bool]$task; "
        "state = if ($task) { [string]$task.State } else { $null }; "
        "interactive_user_available = [bool]$interactiveSession"
        "} | ConvertTo-Json -Compress"
    )
    try:
        payload = _run_powershell_json(script)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return InteractiveTaskProbe(False, None, False)
    if not isinstance(payload, dict):
        return InteractiveTaskProbe(False, None, False)
    return InteractiveTaskProbe(
        registered=bool(payload.get("registered")),
        state=str(payload["state"]) if payload.get("state") else None,
        interactive_user_available=bool(payload.get("interactive_user_available")),
    )


def collect_interactive_import_status() -> SmartFuelPassInteractiveImportStatusResponse:
    stored = read_interactive_import_status()
    task = probe_interactive_task()
    return SmartFuelPassInteractiveImportStatusResponse(
        **stored.to_dict(),
        task_registered=task.registered,
        task_state=task.state,
        interactive_user_available=task.interactive_user_available,
    )


def start_interactive_import() -> SmartFuelPassInteractiveImportStartResponse:
    if platform.system() != "Windows":
        raise SmartFuelPassInteractiveUnavailableError(
            "Interaktivni SmartFuelPass import je dostupny pouze na Windows."
        )
    current = read_interactive_import_status()
    task = probe_interactive_task()
    if not task.registered:
        raise SmartFuelPassInteractiveUnavailableError(
            "Interaktivni SmartFuelPass task neni zaregistrovan."
        )
    if not task.interactive_user_available:
        raise SmartFuelPassInteractiveUnavailableError(
            "Na produkcni stanici neni dostupna prihlasena interaktivni relace."
        )
    if current.state in ACTIVE_IMPORT_STATES or str(task.state).casefold() == "running":
        raise SmartFuelPassInteractiveConflictError(
            "Interaktivni SmartFuelPass import jiz probiha."
        )
    script = (
        f"Start-ScheduledTask -TaskName '{INTERACTIVE_IMPORT_TASK_NAME}' "
        "-ErrorAction Stop"
    )
    try:
        subprocess.run(
            [
                POWERSHELL_EXECUTABLE,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SmartFuelPassInteractiveUnavailableError(
            "Interaktivni SmartFuelPass task se nepodarilo spustit."
        ) from exc
    return SmartFuelPassInteractiveImportStartResponse(
        status="started",
        requested_at=datetime.now().astimezone(),
        detail="Interaktivni import byl spusten na produkcni stanici.",
    )
