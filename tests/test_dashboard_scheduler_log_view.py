from datetime import datetime

from moduly.apps.dashboard.scheduler_log_view import (
    extract_error_log_blocks,
    extract_manual_run_log_content,
    filter_log_content_since,
    get_manual_run_completion_status,
)


def test_extract_error_log_blocks_includes_traceback_until_next_record():
    content = "\n".join(
        [
            "2026-05-14 10:00:00,000 | INFO | core.scheduler.scheduler | START daily_job",
            "2026-05-14 10:00:01,000 | ERROR | core.scheduler.scheduler | JOB ERROR | id=daily_job | reason=boom",
            "Traceback (most recent call last):",
            '  File "scheduler.py", line 1, in job',
            "RuntimeError: boom",
            "2026-05-14 10:00:02,000 | INFO | core.scheduler.scheduler | START hourly_job",
        ]
    )

    assert extract_error_log_blocks(content) == (
        "\n".join(
            [
                "2026-05-14 10:00:01,000 | ERROR | core.scheduler.scheduler | JOB ERROR | id=daily_job | reason=boom",
                "Traceback (most recent call last):",
                '  File "scheduler.py", line 1, in job',
                "RuntimeError: boom",
            ]
        ),
    )


def test_extract_error_log_blocks_keeps_latest_blocks_limit():
    content = "\n".join(
        [
            "2026-05-14 10:00:00,000 | ERROR | core.scheduler.scheduler | first",
            "detail first",
            "2026-05-14 10:01:00,000 | ERROR | core.scheduler.scheduler | second",
            "detail second",
            "2026-05-14 10:02:00,000 | ERROR | core.scheduler.scheduler | third",
            "detail third",
        ]
    )

    assert extract_error_log_blocks(content, max_blocks=2) == (
        "2026-05-14 10:01:00,000 | ERROR | core.scheduler.scheduler | second\ndetail second",
        "2026-05-14 10:02:00,000 | ERROR | core.scheduler.scheduler | third\ndetail third",
    )


def test_filter_log_content_since_keeps_records_after_timestamp_with_continuations():
    content = "\n".join(
        [
            "2026-05-14 09:59:50,000 | INFO | core.scheduler.scheduler | old",
            "2026-05-14 10:00:01,000 | INFO | core.scheduler.scheduler | current",
            "continued current",
            "2026-05-14 10:00:02,000 | INFO | core.scheduler.scheduler | next",
        ]
    )

    assert filter_log_content_since(
        content,
        datetime(2026, 5, 14, 10, 0, 2),
        margin_seconds=1,
    ) == "\n".join(
        [
            "2026-05-14 10:00:01,000 | INFO | core.scheduler.scheduler | current",
            "continued current",
            "2026-05-14 10:00:02,000 | INFO | core.scheduler.scheduler | next",
        ]
    )


def test_extract_manual_run_log_content_stops_after_matching_completion_record():
    content = "\n".join(
        [
            "2026-05-14 09:59:59,000 | INFO | core.scheduler.scheduler | before",
            "2026-05-14 10:00:00,000 | INFO | core.scheduler.scheduler | JOB MANUAL START | id=daily_job | requested=2026-05-14 10:00:00+02:00 | started=2026-05-14 10:00:00+02:00",
            "2026-05-14 10:00:01,000 | INFO | core.scheduler.scheduler | START sync_charge_sessions_to_db",
            "2026-05-14 10:00:02,000 | INFO | core.scheduler.scheduler | JOB MANUAL SUCCESS | id=daily_job | duration=2.0s",
            "2026-05-14 10:00:03,000 | ERROR | core.scheduler.scheduler | unrelated later error",
        ]
    )

    assert extract_manual_run_log_content(
        content,
        job_id="daily_job",
        requested_at=datetime(2026, 5, 14, 10, 0, 0),
        margin_seconds=0,
    ) == "\n".join(
        [
            "2026-05-14 10:00:00,000 | INFO | core.scheduler.scheduler | JOB MANUAL START | id=daily_job | requested=2026-05-14 10:00:00+02:00 | started=2026-05-14 10:00:00+02:00",
            "2026-05-14 10:00:01,000 | INFO | core.scheduler.scheduler | START sync_charge_sessions_to_db",
            "2026-05-14 10:00:02,000 | INFO | core.scheduler.scheduler | JOB MANUAL SUCCESS | id=daily_job | duration=2.0s",
        ]
    )


def test_get_manual_run_completion_status_returns_latest_matching_status():
    content = "\n".join(
        [
            "2026-05-14 10:00:00,000 | INFO | core.scheduler.scheduler | JOB MANUAL SUCCESS | id=hourly_job | duration=1.0s",
            "2026-05-14 10:01:00,000 | ERROR | core.scheduler.scheduler | JOB MANUAL ERROR | id=daily_job | requested=2026-05-14 10:00:00+02:00 | duration=1.0s | reason=boom",
        ]
    )

    assert get_manual_run_completion_status(content, "daily_job") == "error"
    assert get_manual_run_completion_status(content, "hourly_job") == "success"
    assert get_manual_run_completion_status(content, "weekly_job") is None
