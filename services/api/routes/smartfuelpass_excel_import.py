from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from moduly.apps.smartfuelpass.excel_import import (
    SmartFuelPassExcelImportError,
    build_smartfuelpass_excel_preview,
    import_smartfuelpass_excel_records,
)
from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.admin import (
    SmartFuelPassExcelImportApplyResponse,
    SmartFuelPassExcelImportPreviewResponse,
)
from services.api.services.dashboard_auth import DashboardUserContext


MAX_EXCEL_IMPORT_BYTES = 10 * 1024 * 1024

router = APIRouter(
    prefix="/api/v1/admin/smartfuelpass/excel-import",
    tags=["admin", "smartfuelpass"],
)


async def _read_excel_body(
    request: Request,
    filename_header: str | None,
) -> tuple[bytes, str | None]:
    content = await request.body()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="XLSX soubor je prázdný.",
        )
    if len(content) > MAX_EXCEL_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="XLSX soubor je příliš velký.",
        )

    filename = unquote(filename_header) if filename_header else None
    if filename and not filename.casefold().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import podporuje pouze .xlsx soubory.",
        )
    return content, filename


@router.post(
    "/preview",
    response_model=SmartFuelPassExcelImportPreviewResponse,
)
async def preview_smartfuelpass_excel_import(
    request: Request,
    x_filename: str | None = Header(default=None, alias="X-Filename"),
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SmartFuelPassExcelImportPreviewResponse:
    del current_user
    content, filename = await _read_excel_body(request, x_filename)
    try:
        return build_smartfuelpass_excel_preview(content=content, filename=filename)
    except SmartFuelPassExcelImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/import",
    response_model=SmartFuelPassExcelImportApplyResponse,
)
async def import_smartfuelpass_excel_import(
    request: Request,
    x_filename: str | None = Header(default=None, alias="X-Filename"),
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SmartFuelPassExcelImportApplyResponse:
    del current_user
    content, filename = await _read_excel_body(request, x_filename)
    try:
        return import_smartfuelpass_excel_records(content=content, filename=filename)
    except SmartFuelPassExcelImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
