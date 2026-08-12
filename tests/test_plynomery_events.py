from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery.plynomery_events import (
    EVENT_CONFIG,
    EVENT_EXPECTED_ZERO_USAGE,
    EVENT_LONG_HIGH_USAGE,
    EVENT_NIGHT_USAGE,
    _duration_minutes,
    _record_triggered_score,
    _score_triggers_event,
)


def _score(
    *,
    timestamp: datetime,
    z_score: float = 0.0,
    actual_value: float = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        date=timestamp,
        actual_value=actual_value,
        z_score=z_score,
    )


def test_long_high_usage_trigger_uses_z_score_threshold():
    cfg = EVENT_CONFIG[EVENT_LONG_HIGH_USAGE]
    timestamp = datetime(2026, 8, 11, 8, 0)

    assert _score_triggers_event(
        _score(timestamp=timestamp, z_score=2.01),
        event_type=EVENT_LONG_HIGH_USAGE,
        cfg=cfg,
        expected_zero=False,
    )
    assert not _score_triggers_event(
        _score(timestamp=timestamp, z_score=2.0),
        event_type=EVENT_LONG_HIGH_USAGE,
        cfg=cfg,
        expected_zero=False,
    )


def test_night_usage_trigger_requires_night_time_and_threshold():
    cfg = EVENT_CONFIG[EVENT_NIGHT_USAGE]

    assert _score_triggers_event(
        _score(timestamp=datetime(2026, 8, 11, 23, 15), z_score=3.1),
        event_type=EVENT_NIGHT_USAGE,
        cfg=cfg,
        expected_zero=False,
    )
    assert not _score_triggers_event(
        _score(timestamp=datetime(2026, 8, 11, 14, 15), z_score=4.0),
        event_type=EVENT_NIGHT_USAGE,
        cfg=cfg,
        expected_zero=False,
    )


def test_expected_zero_usage_trigger_uses_expected_zero_flag():
    cfg = EVENT_CONFIG[EVENT_EXPECTED_ZERO_USAGE]
    timestamp = datetime(2026, 8, 11, 8, 0)

    assert _score_triggers_event(
        _score(timestamp=timestamp, actual_value=0.1),
        event_type=EVENT_EXPECTED_ZERO_USAGE,
        cfg=cfg,
        expected_zero=True,
    )
    assert not _score_triggers_event(
        _score(timestamp=timestamp, actual_value=0.1),
        event_type=EVENT_EXPECTED_ZERO_USAGE,
        cfg=cfg,
        expected_zero=False,
    )


def test_long_high_usage_requires_eight_consecutive_scores():
    assert EVENT_CONFIG[EVENT_LONG_HIGH_USAGE]["min_consecutive"] == 8


def test_triggered_state_preserves_first_qualifying_timestamp():
    first_timestamp = datetime(2026, 8, 11, 8, 0)
    state = SimpleNamespace(
        consecutive_count=0,
        accumulator=0.0,
        event_start_time=None,
    )

    for index in range(EVENT_CONFIG[EVENT_LONG_HIGH_USAGE]["min_consecutive"]):
        _record_triggered_score(
            state,
            _score(
                timestamp=first_timestamp + timedelta(minutes=15 * index),
                z_score=2.5,
            ),
        )

    assert state.consecutive_count == 8
    assert state.event_start_time == first_timestamp
    assert state.accumulator == 20.0
    assert _duration_minutes(
        state.event_start_time,
        first_timestamp + timedelta(minutes=105),
    ) == 105
