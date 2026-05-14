from moduly.apps.dashboard.scheduler_log_view import extract_error_log_blocks


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
