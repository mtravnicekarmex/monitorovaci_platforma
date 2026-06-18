from __future__ import annotations

from datetime import datetime, timedelta
import re


LOG_RECORD_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| "
)
ERROR_LOG_RECORD_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \| ERROR \| ")
MANUAL_RUN_STATUS_RE = re.compile(
    r"\bJOB MANUAL (?P<status>SUCCESS|ERROR|SKIPPED) \| id=(?P<job_id>[^ |]+)"
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


def _split_log_records(content: str) -> list[list[str]]:
    records: list[list[str]] = []
    current_record: list[str] = []

    for line in content.splitlines():
        if LOG_RECORD_RE.match(line):
            if current_record:
                records.append(current_record)
            current_record = [line]
            continue

        if current_record:
            current_record.append(line)

    if current_record:
        records.append(current_record)

    return records


def filter_log_content_since(
    content: str,
    since: datetime,
    *,
    margin_seconds: float = 2.0,
) -> str:
    if not content:
        return ""

    threshold = _local_naive_timestamp(since) - timedelta(seconds=margin_seconds)
    selected_records: list[list[str]] = []
    for record in _split_log_records(content):
        timestamp = _parse_log_record_timestamp(record[0])
        if timestamp is not None and timestamp >= threshold:
            selected_records.append(record)

    return "\n".join(line for record in selected_records for line in record)


def get_manual_run_completion_status(content: str, job_id: str) -> str | None:
    if not content or not job_id:
        return None

    status_by_log_text = {
        "SUCCESS": "success",
        "ERROR": "error",
        "SKIPPED": "skipped",
    }
    completion_status: str | None = None
    for match in MANUAL_RUN_STATUS_RE.finditer(content):
        if match.group("job_id") == job_id:
            completion_status = status_by_log_text[match.group("status")]
    return completion_status


def extract_manual_run_log_content(
    content: str,
    *,
    job_id: str,
    requested_at: datetime,
    margin_seconds: float = 2.0,
) -> str:
    if not content or not job_id:
        return ""

    threshold = _local_naive_timestamp(requested_at) - timedelta(seconds=margin_seconds)
    selected_records: list[list[str]] = []
    for record in _split_log_records(content):
        timestamp = _parse_log_record_timestamp(record[0])
        if timestamp is None or timestamp < threshold:
            continue

        selected_records.append(record)
        first_line = record[0]
        match = MANUAL_RUN_STATUS_RE.search(first_line)
        if match is not None and match.group("job_id") == job_id:
            break

    return "\n".join(line for record in selected_records for line in record)


def extract_error_log_blocks(content: str, *, max_blocks: int = 8) -> tuple[str, ...]:
    if not content or max_blocks <= 0:
        return ()

    blocks: list[str] = []
    current_block: list[str] | None = None
    for line in content.splitlines():
        starts_record = LOG_RECORD_RE.match(line) is not None
        starts_error = ERROR_LOG_RECORD_RE.match(line) is not None

        if starts_error:
            if current_block:
                blocks.append("\n".join(current_block))
            current_block = [line]
            continue

        if starts_record:
            if current_block:
                blocks.append("\n".join(current_block))
                current_block = None
            continue

        if current_block is not None:
            current_block.append(line)

    if current_block:
        blocks.append("\n".join(current_block))

    return tuple(blocks[-max_blocks:])
