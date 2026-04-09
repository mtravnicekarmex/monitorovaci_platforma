from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.web_search import (
    WebSearchMonitorRecord,
    WebSearchMonitorsResponse,
    WebSearchMonitorUpsertRequest,
    WebSearchMonitorUpsertResponse,
    WebSearchPreviewRequest,
    WebSearchPreviewResponse,
    WebSearchResultRow,
    WebSearchResultsResponse,
)
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.web_search import (
    WebSearchOperationError,
    delete_monitor_admin,
    list_monitors_admin,
    list_results_admin,
    preview_hits_admin,
    update_monitor_admin,
    upsert_monitor_admin,
)


router = APIRouter(prefix="/api/v1/web-search", tags=["web-search"])


@router.get("/monitors", response_model=WebSearchMonitorsResponse)
def get_web_search_monitors(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> WebSearchMonitorsResponse:
    rows = list_monitors_admin(current_user)
    return WebSearchMonitorsResponse(total=len(rows), rows=rows)


@router.post("/preview", response_model=WebSearchPreviewResponse)
def preview_web_search(
    payload: WebSearchPreviewRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> WebSearchPreviewResponse:
    try:
        preview = preview_hits_admin(
            current_user,
            url=payload.url,
            expressions=payload.expressions,
        )
    except WebSearchOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return WebSearchPreviewResponse(**preview)


@router.get("/results", response_model=WebSearchResultsResponse)
def get_web_search_results(
    limit: int = Query(default=200, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> WebSearchResultsResponse:
    rows = list_results_admin(current_user, limit=limit)
    return WebSearchResultsResponse(total=len(rows), rows=rows)


@router.post("/monitors", response_model=WebSearchMonitorUpsertResponse)
def create_web_search_monitor(
    payload: WebSearchMonitorUpsertRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> WebSearchMonitorUpsertResponse:
    try:
        response = upsert_monitor_admin(
            current_user,
            url=payload.url,
            email=payload.email,
            expressions=payload.expressions,
        )
    except WebSearchOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return WebSearchMonitorUpsertResponse(
        monitor=WebSearchMonitorRecord(**response["monitor"]),
        created=bool(response["created"]),
        added_expressions=list(response["added_expressions"]),
    )


@router.patch("/monitors/{monitor_id}", response_model=WebSearchMonitorRecord)
def update_web_search_monitor(
    monitor_id: int,
    payload: WebSearchMonitorUpsertRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> WebSearchMonitorRecord:
    try:
        row = update_monitor_admin(
            current_user,
            monitor_id=monitor_id,
            url=payload.url,
            email=payload.email,
            expressions=payload.expressions,
        )
    except WebSearchOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return WebSearchMonitorRecord(**row)


@router.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_web_search_monitor(
    monitor_id: int,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> Response:
    delete_monitor_admin(current_user, monitor_id=monitor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
