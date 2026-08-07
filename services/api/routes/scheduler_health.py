from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from core.scheduler.scheduler import (
    SCHEDULER_LOG_PATH,
    get_manual_run_specs,
    trigger_manual_job,
)
from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.admin import (
    SchedulerHealthResponse,
    SchedulerLogResponse,
    SchedulerJobRunResponse,
)
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.scheduler_health import collect_scheduler_health


router = APIRouter(prefix="/health", tags=["health"])


LOG_RECORD_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| "
)


def _parse_log_record_timestamp(line: str) -> datetime | None:
    match = LOG_RECORD_RE.match(line)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None


def _local_naive_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def _tail_text_file(path: Path, *, max_lines: int) -> str:
    if max_lines <= 0:
        return ""

    chunk_size = 8192
    chunks: list[bytes] = []
    newline_count = 0
    with path.open("rb") as file_handle:
        file_handle.seek(0, 2)
        position = file_handle.tell()
        while position > 0 and newline_count <= max_lines:
            read_size = min(chunk_size, position)
            position -= read_size
            file_handle.seek(position)
            chunk = file_handle.read(read_size)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")

    data = b"".join(reversed(chunks))
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def _read_text_file_since(
    path: Path,
    *,
    since: datetime,
    max_lines: int,
    margin_seconds: float = 2.0,
) -> str:
    if max_lines <= 0:
        return ""

    threshold = _local_naive_timestamp(since) - timedelta(seconds=margin_seconds)
    selected_lines: list[str] = []
    include_record = False

    with path.open("r", encoding="utf-8", errors="replace") as file_handle:
        for line in file_handle:
            line = line.rstrip("\r\n")
            timestamp = _parse_log_record_timestamp(line)
            if timestamp is not None:
                include_record = timestamp >= threshold

            if include_record:
                selected_lines.append(line)

    return "\n".join(selected_lines[-max_lines:])


@router.get(
    "/scheduler",
    response_model=SchedulerHealthResponse,
    summary="Scheduler health status",
    description="Vrací komplexní přehled o stavu scheduleru: běžící/ zastavený, "
    "metriky jednotlivých jobů a vnitřních kroků (úspěšnost, doba běhu), naplánované spuštění na 24h dopředu. "
    "Vyžaduje admin oprávnění.",
)
def get_scheduler_health(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SchedulerHealthResponse:
    del current_user
    return collect_scheduler_health()


@router.get(
    "/scheduler/log",
    response_model=SchedulerLogResponse,
    summary="Scheduler log tail",
    description="Vraci posledni radky aktualniho souboru scheduler.log. Vyzaduje admin opravneni.",
)
def get_scheduler_log(
    lines: Annotated[int, Query(ge=1, le=2000)] = 300,
    since: Annotated[
        datetime | None,
        Query(description="Optional lower bound for returned scheduler log records."),
    ] = None,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SchedulerLogResponse:
    del current_user

    log_path = SCHEDULER_LOG_PATH
    if not log_path.exists():
        return SchedulerLogResponse(
            path=str(log_path),
            exists=False,
            max_lines=lines,
            lines_returned=0,
            content="",
            updated_at=None,
        )

    try:
        if since is None:
            content = _tail_text_file(log_path, max_lines=lines)
        else:
            content = _read_text_file_since(log_path, since=since, max_lines=lines)
        stat = log_path.stat()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Nepodarilo se nacist scheduler log: {exc}") from exc

    returned_lines = 0 if not content else len(content.splitlines())
    return SchedulerLogResponse(
        path=str(log_path),
        exists=True,
        max_lines=lines,
        lines_returned=returned_lines,
        content=content,
        updated_at=datetime.fromtimestamp(stat.st_mtime),
    )


@router.post(
    "/scheduler/jobs/{job_id}/run",
    response_model=SchedulerJobRunResponse,
    summary="Run scheduler job or internal step once",
    description="Prijme jednorazovy manualni beh konkretniho scheduler jobu nebo vnitrniho kroku. "
    "Vyvolani probiha na pozadi a vyzaduje admin opravneni.",
)
def run_scheduler_job(
    job_id: str,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SchedulerJobRunResponse:
    del current_user

    manual_run_spec = get_manual_run_specs().get(job_id)
    if manual_run_spec is None:
        raise HTTPException(status_code=404, detail=f"Neznamy scheduler job nebo krok '{job_id}'.")

    result = trigger_manual_job(job_id)
    return SchedulerJobRunResponse(
        job_id=job_id,
        job_label=manual_run_spec.label,
        status=result.status,
        detail=result.detail,
        requested_at=result.requested_at,
    )
