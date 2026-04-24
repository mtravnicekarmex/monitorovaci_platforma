from __future__ import annotations

import datetime
import math
from collections.abc import Callable, Iterable, Sequence

import streamlit as st

from app.time_utils import prague_now_naive
from core.scheduler.job_schedule import SCHEDULER_TIMEZONE, get_scheduler_job_specs


SENSOR_DB_WRITE_MINUTES: tuple[int, ...] = (5, 16, 35, 50)
SENSOR_REFRESH_BUFFER_MINUTES = 1
QUARTER_HOUR_JOB_ID = "quarter_hour_job"
QUARTER_HOUR_PAGE_INTERVAL_MINUTES = 15
SCHEDULER_REFERENCE_START = datetime.datetime(2026, 1, 1, 0, 0, tzinfo=SCHEDULER_TIMEZONE)


def normalize_refresh_minutes(refresh_minutes: Sequence[int]) -> tuple[int, ...]:
    normalized = tuple(sorted({int(minute) for minute in refresh_minutes}))
    if not normalized:
        raise ValueError("Refresh schedule must contain at least one minute.")
    if any(minute < 0 or minute > 59 for minute in normalized):
        raise ValueError("Refresh minutes must be in range 0-59.")
    return normalized


def build_post_write_refresh_minutes(
    write_minutes: Sequence[int] = SENSOR_DB_WRITE_MINUTES,
    *,
    buffer_minutes: int = SENSOR_REFRESH_BUFFER_MINUTES,
) -> tuple[int, ...]:
    normalized_write_minutes = normalize_refresh_minutes(write_minutes)
    normalized_buffer = int(buffer_minutes)
    if normalized_buffer < 0 or normalized_buffer > 59:
        raise ValueError("Refresh buffer must be in range 0-59 minutes.")
    return tuple(sorted({(minute + normalized_buffer) % 60 for minute in normalized_write_minutes}))


def get_scheduler_job_anchor_minute(job_id: str) -> int:
    for job_spec in get_scheduler_job_specs():
        if job_spec.id != job_id:
            continue
        next_fire_time = job_spec.build_trigger().get_next_fire_time(None, SCHEDULER_REFERENCE_START)
        if next_fire_time is None:
            raise ValueError(f"Scheduler job '{job_id}' does not have any future fire times.")
        return int(next_fire_time.minute)
    raise ValueError(f"Scheduler job '{job_id}' was not found.")


def build_interval_refresh_minutes(
    anchor_minute: int,
    *,
    interval_minutes: int,
    buffer_minutes: int = SENSOR_REFRESH_BUFFER_MINUTES,
) -> tuple[int, ...]:
    normalized_anchor = int(anchor_minute)
    normalized_interval = int(interval_minutes)
    normalized_buffer = int(buffer_minutes)
    if normalized_anchor < 0 or normalized_anchor > 59:
        raise ValueError("Refresh anchor minute must be in range 0-59.")
    if normalized_interval <= 0 or 60 % normalized_interval != 0:
        raise ValueError("Refresh interval must be a positive divisor of 60 minutes.")
    if normalized_buffer < 0 or normalized_buffer > 59:
        raise ValueError("Refresh buffer must be in range 0-59 minutes.")

    first_refresh_minute = (normalized_anchor + normalized_buffer) % 60
    refresh_minutes = tuple(
        sorted((first_refresh_minute + index * normalized_interval) % 60 for index in range(60 // normalized_interval))
    )
    return normalize_refresh_minutes(refresh_minutes)


SENSOR_REFRESH_MINUTES: tuple[int, ...] = build_post_write_refresh_minutes()
QUARTER_HOUR_PAGE_REFRESH_MINUTES: tuple[int, ...] = build_interval_refresh_minutes(
    get_scheduler_job_anchor_minute(QUARTER_HOUR_JOB_ID),
    interval_minutes=QUARTER_HOUR_PAGE_INTERVAL_MINUTES,
)


def get_next_scheduled_refresh(
    now: datetime.datetime,
    refresh_minutes: Sequence[int] = SENSOR_REFRESH_MINUTES,
) -> datetime.datetime:
    normalized_minutes = normalize_refresh_minutes(refresh_minutes)
    current_minute = now.replace(second=0, microsecond=0)

    for minute in normalized_minutes:
        candidate = current_minute.replace(minute=minute)
        if candidate > now:
            return candidate

    next_hour = current_minute + datetime.timedelta(hours=1)
    return next_hour.replace(minute=normalized_minutes[0], second=0, microsecond=0)


def enable_scheduled_page_refresh(
    page_key: str,
    *,
    cache_clearers: Iterable[Callable[[], None]] = (),
    refresh_minutes: Sequence[int] = SENSOR_REFRESH_MINUTES,
) -> None:
    clearers = tuple(cache_clearers)
    next_refresh = get_next_scheduled_refresh(prague_now_naive(), refresh_minutes)
    refresh_slot = next_refresh.strftime("%Y-%m-%d %H:%M")
    state_key = f"{page_key}_scheduled_refresh_slot"
    run_every = datetime.timedelta(
        seconds=max(1, math.ceil((next_refresh - prague_now_naive()).total_seconds()))
    )

    @st.fragment(run_every=run_every)
    def _scheduled_refresh_fragment(
        target_refresh_iso: str = next_refresh.isoformat(),
        target_refresh_slot: str = refresh_slot,
    ) -> None:
        target_refresh = datetime.datetime.fromisoformat(target_refresh_iso)
        if prague_now_naive() < target_refresh:
            return
        if st.session_state.get(state_key) == target_refresh_slot:
            return

        for clear_cache in clearers:
            clear_cache()

        st.session_state[state_key] = target_refresh_slot
        st.rerun(scope="app")

    _scheduled_refresh_fragment()
