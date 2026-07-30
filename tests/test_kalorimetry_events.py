from datetime import datetime, timedelta
from types import SimpleNamespace

from moduly.mereni.kalorimetry.events import (
    EVENT_SPIKE,
    EVENT_SUSTAINED_HIGH_USAGE,
    build_alert_transition_plan,
    evaluate_event_transitions,
)


def _score(row_id: int, timestamp: datetime, z_score: float):
    return SimpleNamespace(
        id=row_id,
        identifikace="KAL-01",
        date=timestamp,
        z_score=z_score,
    )


def test_spike_creates_and_resolves_deterministically():
    start = datetime(2026, 4, 22, 12)
    states, transitions = evaluate_event_transitions(
        [
            _score(1, start, 6.0),
            _score(2, start + timedelta(minutes=15), 0.0),
        ]
    )

    spike_transitions = [
        row for row in transitions if row.event_type == EVENT_SPIKE
    ]
    assert [row.transition for row in spike_transitions] == [
        "CREATED",
        "RESOLVED",
    ]
    assert spike_transitions[0].severity == "HIGH"
    spike_state = next(
        state for state in states if state.event_type == EVENT_SPIKE
    )
    assert spike_state.is_active is False
    assert spike_state.consecutive_count == 0


def test_sustained_event_requires_eight_consecutive_scores():
    start = datetime(2026, 4, 22, 12)
    scores = [
        _score(index, start + timedelta(minutes=15 * index), 3.5)
        for index in range(1, 9)
    ]

    states, transitions = evaluate_event_transitions(scores)

    sustained = [
        row
        for row in transitions
        if row.event_type == EVENT_SUSTAINED_HIGH_USAGE
    ]
    assert len(sustained) == 1
    assert sustained[0].transition == "CREATED"
    state = next(
        state
        for state in states
        if state.event_type == EVENT_SUSTAINED_HIGH_USAGE
    )
    assert state.is_active is True
    assert state.consecutive_count == 8


def test_interrupted_high_usage_does_not_create_sustained_event():
    start = datetime(2026, 4, 22, 12)
    scores = [
        _score(index, start + timedelta(minutes=15 * index), 3.5)
        for index in range(1, 8)
    ]
    scores.append(_score(8, start + timedelta(hours=2), 0.0))

    states, transitions = evaluate_event_transitions(scores)

    assert all(
        row.event_type != EVENT_SUSTAINED_HIGH_USAGE
        for row in transitions
    )
    state = next(
        state
        for state in states
        if state.event_type == EVENT_SUSTAINED_HIGH_USAGE
    )
    assert state.consecutive_count == 0
    assert state.is_active is False


def test_alert_plan_is_delivery_disabled():
    start = datetime(2026, 4, 22, 12)
    _, transitions = evaluate_event_transitions([_score(1, start, 6.0)])

    plan = build_alert_transition_plan(transitions)

    assert plan
    assert all(item.delivery_enabled is False for item in plan)
