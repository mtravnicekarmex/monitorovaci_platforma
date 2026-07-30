from __future__ import annotations

from collections.abc import Mapping


ACTIVE_STATES = frozenset({"starting", "waiting_for_login", "importing"})
STATUS_LABELS = {
    "idle": "Připraveno",
    "starting": "Spouštím",
    "waiting_for_login": "Čeká na přihlášení",
    "importing": "Importuji",
    "success": "Dokončeno",
    "error": "Chyba",
}


def interactive_import_is_active(status: Mapping[str, object]) -> bool:
    return str(status.get("state") or "").strip().casefold() in ACTIVE_STATES


def interactive_import_can_start(status: Mapping[str, object]) -> bool:
    return (
        bool(status.get("task_registered"))
        and bool(status.get("interactive_user_available"))
        and not interactive_import_is_active(status)
        and str(status.get("task_state") or "").casefold() != "running"
    )


def interactive_import_status_label(status: Mapping[str, object]) -> str:
    state = str(status.get("state") or "idle").strip().casefold()
    return STATUS_LABELS.get(state, state or "Neznámý stav")
