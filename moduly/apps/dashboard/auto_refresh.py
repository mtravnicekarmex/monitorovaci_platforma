from __future__ import annotations

import datetime
import math
from collections.abc import Callable, Iterable, Sequence

import streamlit as st

from app.time_utils import prague_now_naive


SENSOR_DB_WRITE_MINUTES: tuple[int, ...] = (5, 16, 35, 50)
SENSOR_REFRESH_BUFFER_MINUTES = 1


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


SENSOR_REFRESH_MINUTES: tuple[int, ...] = build_post_write_refresh_minutes()


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
