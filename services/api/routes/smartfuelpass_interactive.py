from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.admin import (
    SmartFuelPassInteractiveImportStartResponse,
    SmartFuelPassInteractiveImportStatusResponse,
)
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.smartfuelpass_interactive import (
    SmartFuelPassInteractiveConflictError,
    SmartFuelPassInteractiveUnavailableError,
    collect_interactive_import_status,
    start_interactive_import,
)


router = APIRouter(
    prefix="/api/v1/admin/smartfuelpass/interactive-import",
    tags=["admin", "smartfuelpass"],
)


@router.get(
    "/status",
    response_model=SmartFuelPassInteractiveImportStatusResponse,
)
def get_interactive_import_status(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SmartFuelPassInteractiveImportStatusResponse:
    del current_user
    return collect_interactive_import_status()


@router.post(
    "/start",
    response_model=SmartFuelPassInteractiveImportStartResponse,
)
def start_interactive_import_from_dashboard(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SmartFuelPassInteractiveImportStartResponse:
    del current_user
    try:
        return start_interactive_import()
    except SmartFuelPassInteractiveConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SmartFuelPassInteractiveUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
