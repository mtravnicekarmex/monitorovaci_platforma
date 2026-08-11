from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.vodomery_events import (
    EVENT_CONFIG,
    EVENT_SUSTAINED_HIGH_USAGE,
    _score_triggers_event,
)


def _score(*, actual: float, expected: float, z_score: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        date=datetime(2026, 8, 10, 8, 0),
        actual_value=actual,
        expected_mean=expected,
        z_score=z_score,
    )


def test_sustained_high_usage_trigger_uses_ratio_and_absolute_guards():
    cfg = EVENT_CONFIG[EVENT_SUSTAINED_HIGH_USAGE]

    assert _score_triggers_event(
        _score(actual=0.20, expected=0.09),
        event_type=EVENT_SUSTAINED_HIGH_USAGE,
        cfg=cfg,
        expected_zero=False,
    )
    assert not _score_triggers_event(
        _score(actual=0.20, expected=0.11),
        event_type=EVENT_SUSTAINED_HIGH_USAGE,
        cfg=cfg,
        expected_zero=False,
    )
    assert not _score_triggers_event(
        _score(actual=0.09, expected=0.05),
        event_type=EVENT_SUSTAINED_HIGH_USAGE,
        cfg=cfg,
        expected_zero=False,
    )
    assert not _score_triggers_event(
        _score(actual=0.07, expected=0.02),
        event_type=EVENT_SUSTAINED_HIGH_USAGE,
        cfg=cfg,
        expected_zero=False,
    )
    assert _score_triggers_event(
        _score(actual=0.08, expected=0.0),
        event_type=EVENT_SUSTAINED_HIGH_USAGE,
        cfg=cfg,
        expected_zero=False,
    )


def test_sustained_high_usage_requires_four_consecutive_scores():
    assert EVENT_CONFIG[EVENT_SUSTAINED_HIGH_USAGE]["min_consecutive"] == 4
