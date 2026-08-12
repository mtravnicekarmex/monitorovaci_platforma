from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery.alerting.service import _rule_matches_event
from moduly.mereni.plynomery.plynomery_events import EVENT_LONG_HIGH_USAGE


def _rule(*, min_duration_minutes: int) -> SimpleNamespace:
    return SimpleNamespace(
        enabled=True,
        identifikace=None,
        event_type=EVENT_LONG_HIGH_USAGE,
        severity_min="LOW",
        min_duration_minutes=min_duration_minutes,
        send_on="ACTIVE",
    )


def _event(*, duration_minutes: int) -> SimpleNamespace:
    return SimpleNamespace(
        identifikace="G_P1",
        event_type=EVENT_LONG_HIGH_USAGE,
        severity="LOW",
        duration_minutes=duration_minutes,
        is_active=True,
        resolved=False,
    )


def test_rule_matches_event_allows_zero_min_duration_after_event_opens():
    assert _rule_matches_event(
        rule=_rule(min_duration_minutes=0),
        event=_event(duration_minutes=0),
        alert_state="ACTIVE_THRESHOLD",
    )


def test_rule_matches_event_duration_threshold_is_inclusive():
    rule = _rule(min_duration_minutes=30)

    assert not _rule_matches_event(
        rule=rule,
        event=_event(duration_minutes=29),
        alert_state="ACTIVE_THRESHOLD",
    )
    assert _rule_matches_event(
        rule=rule,
        event=_event(duration_minutes=30),
        alert_state="ACTIVE_THRESHOLD",
    )
