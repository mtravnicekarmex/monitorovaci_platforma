from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from moduly.apps.dashboard.smartfuelpass_interactive_view import (
    interactive_import_can_start,
    interactive_import_is_active,
    interactive_import_status_label,
)
from moduly.apps.dashboard import api_client
from moduly.apps.smartfuelpass import interactive_import
from services.api.routes import smartfuelpass_interactive as route
from services.api.services import smartfuelpass_interactive as api_service


def test_status_round_trip_is_aggregate_only(tmp_path):
    status_path = tmp_path / "status.json"
    expected = interactive_import.InteractiveImportStatus(
        state="success",
        updated_at="2026-07-28T16:00:00+02:00",
        started_at="2026-07-28T15:55:00+02:00",
        finished_at="2026-07-28T16:00:00+02:00",
        raw_row_count=25,
        completed_row_count=24,
        invalid_row_count=1,
        skipped_missing_id_count=0,
        upserted_count=24,
        message="done",
    )

    interactive_import.write_interactive_import_status(
        expected,
        status_path=status_path,
    )

    assert interactive_import.read_interactive_import_status(
        status_path=status_path
    ) == expected
    serialized = status_path.read_text(encoding="utf-8")
    assert "cookie" not in serialized.casefold()
    assert "password" not in serialized.casefold()


def test_missing_or_invalid_status_fails_to_idle(tmp_path):
    status_path = tmp_path / "status.json"
    assert interactive_import.read_interactive_import_status(
        status_path=status_path
    ).state == "idle"
    status_path.write_text("{invalid", encoding="utf-8")
    assert interactive_import.read_interactive_import_status(
        status_path=status_path
    ).state == "idle"


def test_lock_refuses_live_owner(monkeypatch, tmp_path):
    lock_path = tmp_path / "import.lock"
    lock_path.write_text("123", encoding="ascii")
    monkeypatch.setattr(interactive_import, "_pid_is_running", lambda pid: pid == 123)

    with pytest.raises(interactive_import.SmartFuelPassError, match="jiz probiha"):
        with interactive_import.interactive_import_lock(lock_path=lock_path):
            pass


def test_lock_replaces_stale_owner(monkeypatch, tmp_path):
    lock_path = tmp_path / "import.lock"
    lock_path.write_text("123", encoding="ascii")
    monkeypatch.setattr(interactive_import, "_pid_is_running", lambda pid: False)

    with interactive_import.interactive_import_lock(lock_path=lock_path):
        assert lock_path.exists()

    assert not lock_path.exists()


def test_dashboard_view_requires_task_user_and_inactive_state():
    ready = {
        "state": "idle",
        "task_registered": True,
        "interactive_user_available": True,
        "task_state": "Ready",
    }
    assert interactive_import_can_start(ready) is True
    assert interactive_import_is_active(ready) is False
    assert interactive_import_status_label(ready) == "Připraveno"
    assert interactive_import_can_start({**ready, "state": "importing"}) is False
    assert interactive_import_can_start(
        {**ready, "interactive_user_available": False}
    ) is False


def test_dashboard_api_client_uses_fixed_admin_endpoints(monkeypatch):
    calls = []

    class FakeResponse:
        @staticmethod
        def json():
            return {"state": "idle"}

    monkeypatch.setattr(
        api_client,
        "_request",
        lambda method, path, **kwargs: calls.append((method, path, kwargs))
        or FakeResponse(),
    )

    api_client.get_smartfuelpass_interactive_import_status("token")
    api_client.start_smartfuelpass_interactive_import("token")

    assert calls == [
        (
            "GET",
            "/api/v1/admin/smartfuelpass/interactive-import/status",
            {"access_token": "token"},
        ),
        (
            "POST",
            "/api/v1/admin/smartfuelpass/interactive-import/start",
            {"access_token": "token"},
        ),
    ]


def test_api_status_combines_task_probe_and_sanitized_file(monkeypatch):
    monkeypatch.setattr(
        api_service,
        "read_interactive_import_status",
        lambda: interactive_import.InteractiveImportStatus(
            state="success",
            updated_at="2026-07-28T16:00:00+02:00",
            upserted_count=24,
        ),
    )
    monkeypatch.setattr(
        api_service,
        "probe_interactive_task",
        lambda: api_service.InteractiveTaskProbe(True, "Ready", True),
    )

    result = api_service.collect_interactive_import_status()

    assert result.state == "success"
    assert result.task_registered is True
    assert result.interactive_user_available is True
    assert result.upserted_count == 24


def test_api_start_uses_only_fixed_task(monkeypatch):
    calls = []
    monkeypatch.setattr(api_service.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        api_service,
        "read_interactive_import_status",
        lambda: interactive_import.InteractiveImportStatus(
            state="idle",
            updated_at="2026-07-28T16:00:00+02:00",
        ),
    )
    monkeypatch.setattr(
        api_service,
        "probe_interactive_task",
        lambda: api_service.InteractiveTaskProbe(True, "Ready", True),
    )
    monkeypatch.setattr(
        api_service.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs))
        or SimpleNamespace(returncode=0),
    )

    result = api_service.start_interactive_import()

    assert result.status == "started"
    assert len(calls) == 1
    assert interactive_import.INTERACTIVE_IMPORT_TASK_NAME in calls[0][0][-1]


def test_route_maps_conflict_to_http_409(monkeypatch):
    monkeypatch.setattr(
        route,
        "start_interactive_import",
        lambda: (_ for _ in ()).throw(
            api_service.SmartFuelPassInteractiveConflictError("busy")
        ),
    )

    with pytest.raises(route.HTTPException) as exc_info:
        route.start_interactive_import_from_dashboard(
            current_user=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 409


def test_task_registration_has_no_trigger_and_uses_interactive_logon():
    source = Path(
        "scripts/register_smartfuelpass_interactive_import_task.ps1"
    ).read_text(encoding="utf-8")

    assert "New-ScheduledTaskTrigger" not in source
    assert "-LogonType Interactive" in source
    assert "-MultipleInstances IgnoreNew" in source
    assert ".venv-production" in source
