from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from monitoring_agent.incidents import IncidentEvaluation, IncidentTransition
from monitoring_agent.shadow_pilot import (
    SOURCE_LEGACY_ALERT,
    SOURCE_MONITORING_AGENT,
    SHADOW_PILOT_MODE,
    ShadowPilotBlindSpot,
    ShadowPilotEvent,
    build_shadow_pilot_comparison,
    events_from_incident_evaluation,
    render_shadow_pilot_comparison,
)


BASE_TIME = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
PERIOD_START = BASE_TIME
PERIOD_END = BASE_TIME + timedelta(hours=2)


def _agent_event(
    incident_key: str,
    action: str,
    offset_seconds: int,
    *,
    summary: str = "",
) -> ShadowPilotEvent:
    return ShadowPilotEvent(
        source=SOURCE_MONITORING_AGENT,
        incident_key=incident_key,
        action=action,
        occurred_at=BASE_TIME + timedelta(seconds=offset_seconds),
        severity="critical",
        summary=summary,
    )


def _legacy_event(
    incident_key: str,
    action: str,
    offset_seconds: int,
    *,
    summary: str = "",
) -> ShadowPilotEvent:
    return ShadowPilotEvent(
        source=SOURCE_LEGACY_ALERT,
        incident_key=incident_key,
        action=action,
        occurred_at=BASE_TIME + timedelta(seconds=offset_seconds),
        severity="critical",
        summary=summary,
    )


def test_shadow_comparison_matches_detection_and_recovery_with_delay_metrics():
    comparison = build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=(
            _agent_event("endpoint:system_database", "opened", 120),
            _agent_event("endpoint:system_database", "recovered", 420),
        ),
        legacy_events=(
            _legacy_event("endpoint:system_database", "alerted", 60),
            _legacy_event("endpoint:system_database", "resolved", 360),
        ),
        match_window_seconds=120,
        duplicate_window_seconds=90,
        generated_at=BASE_TIME,
    )

    metrics = comparison.metrics
    assert comparison.mode == SHADOW_PILOT_MODE
    assert metrics["matched_detection_count"] == 1
    assert metrics["matched_recovery_count"] == 1
    assert metrics["false_positive_count"] == 0
    assert metrics["false_negative_count"] == 0
    assert metrics["confirmation_delay_seconds"] == {
        "agent_earlier_count": 0,
        "agent_later_count": 1,
        "average": 60.0,
        "count": 1,
        "maximum": 60.0,
        "minimum": 60.0,
        "same_time_count": 0,
    }
    assert metrics["recovery_delay_seconds"]["average"] == 60.0
    payload = comparison.to_dict()
    assert payload["event"] == "monitoring_shadow_pilot_comparison"
    assert payload["configuration"]["period_boundary"] == (
        "start_inclusive_end_exclusive"
    )


def test_agent_only_detection_is_reported_as_false_positive():
    comparison = build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=(_agent_event("endpoint:system_proxy", "opened", 120),),
        legacy_events=(),
        generated_at=BASE_TIME,
    )

    metrics = comparison.metrics
    assert metrics["matched_detection_count"] == 0
    assert metrics["false_positive_count"] == 1
    assert metrics["false_negative_count"] == 0
    assert comparison.agent_only_events[0].incident_key == "endpoint:system_proxy"


def test_legacy_only_detection_is_reported_as_false_negative():
    comparison = build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=(),
        legacy_events=(_legacy_event("endpoint:system_scheduler", "alerted", 120),),
        generated_at=BASE_TIME,
    )

    metrics = comparison.metrics
    assert metrics["matched_detection_count"] == 0
    assert metrics["false_positive_count"] == 0
    assert metrics["false_negative_count"] == 1
    assert comparison.legacy_only_events[0].incident_key == "endpoint:system_scheduler"


def test_duplicate_events_are_counted_without_creating_extra_mismatches():
    comparison = build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=(
            _agent_event("endpoint:system_database", "opened", 120),
            _agent_event("endpoint:system_database", "reopened", 160),
        ),
        legacy_events=(_legacy_event("endpoint:system_database", "alerted", 110),),
        match_window_seconds=120,
        duplicate_window_seconds=60,
        generated_at=BASE_TIME,
    )

    metrics = comparison.metrics
    assert metrics["matched_detection_count"] == 1
    assert metrics["false_positive_count"] == 0
    assert metrics["agent_duplicate_event_count"] == 1
    assert metrics["agent_duplicate_rate"] == 0.5
    assert comparison.duplicates[0].duplicate_event.action == "reopened"


def test_recovery_mismatches_are_separate_from_detection_false_rates():
    comparison = build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=(
            _agent_event("endpoint:ready", "opened", 120),
            _agent_event("endpoint:ready", "recovered", 600),
        ),
        legacy_events=(_legacy_event("endpoint:ready", "alerted", 120),),
        generated_at=BASE_TIME,
    )

    metrics = comparison.metrics
    assert metrics["matched_detection_count"] == 1
    assert metrics["false_positive_count"] == 0
    assert metrics["false_negative_count"] == 0
    assert metrics["agent_only_recovery_count"] == 1
    assert metrics["legacy_only_recovery_count"] == 0


def test_period_filtering_and_window_validation_are_explicit():
    comparison = build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=(
            _agent_event("endpoint:live", "opened", -1),
            _agent_event("endpoint:live", "opened", 60),
        ),
        legacy_events=(_legacy_event("endpoint:live", "alerted", 60),),
        generated_at=BASE_TIME,
    )

    assert comparison.metrics["agent_event_count"] == {
        "deduplicated": 1,
        "excluded_outside_period": 1,
        "included": 1,
        "raw": 2,
    }
    with pytest.raises(ValueError, match="period_start"):
        build_shadow_pilot_comparison(
            period_start=PERIOD_END,
            period_end=PERIOD_START,
            agent_events=(),
            legacy_events=(),
        )
    with pytest.raises(ValueError, match="match_window_seconds"):
        build_shadow_pilot_comparison(
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            agent_events=(),
            legacy_events=(),
            match_window_seconds=0,
        )


def test_blind_spot_events_and_review_notes_are_reported():
    comparison = build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=(
            _agent_event(
                "supervision_center_blind_spot:latest_cycle_stale",
                "opened",
                300,
            ),
        ),
        legacy_events=(),
        blind_spots=(
            ShadowPilotBlindSpot(
                source="operator_review",
                category="legacy_has_no_supervision_center_visibility",
                observed_at=BASE_TIME + timedelta(seconds=360),
                summary="Legacy alert stream does not observe supervision station gaps.",
            ),
        ),
        generated_at=BASE_TIME,
    )

    metrics = comparison.metrics
    assert metrics["agent_blind_spot_event_count"] == 1
    assert metrics["operator_blind_spot_count"] == 1
    assert comparison.to_dict()["shadow_outputs"]["blind_spots"][0]["category"] == (
        "legacy_has_no_supervision_center_visibility"
    )


def test_events_from_incident_evaluation_keeps_only_comparable_transitions():
    evaluation = IncidentEvaluation(
        rule_version=1,
        states=(),
        transitions=(
            _transition("endpoint:system_database", "suppressed", 60),
            _transition("endpoint:system_database", "opened", 120),
            _transition("endpoint:system_database", "updated", 180),
            _transition("endpoint:system_database", "recovered", 240),
        ),
    )

    events = events_from_incident_evaluation(evaluation)

    assert [(event.action, event.incident_key) for event in events] == [
        ("opened", "endpoint:system_database"),
        ("recovered", "endpoint:system_database"),
    ]


def test_output_is_sanitized_and_keeps_shadow_safety_boundary():
    comparison = build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=(
            _agent_event(
                "endpoint:system_database",
                "opened",
                120,
                summary=(
                    "password=SHOULD_NOT_LEAK Bearer SHOULD_NOT_LEAK "
                    "C:\\Users\\tra\\PycharmProjects\\monitorovaci_platforma\\.env"
                ),
            ),
        ),
        legacy_events=(),
        generated_at=BASE_TIME,
    )

    rendered = render_shadow_pilot_comparison(comparison)
    payload = str(comparison.to_dict())
    assert "SHOULD_NOT_LEAK" not in payload
    assert "password=[redacted]" in payload
    assert "C:\\Users\\tra" not in payload
    assert "legacy alerts remain authoritative" in rendered
    assert "send email" in rendered
    assert "shadow_only" in rendered


def test_build_comparison_does_not_mutate_input_event_order():
    agent_events = [
        _agent_event("endpoint:live", "opened", 300),
        _agent_event("endpoint:live", "opened", 60),
    ]
    original_order = tuple(event.occurred_at for event in agent_events)

    build_shadow_pilot_comparison(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        agent_events=agent_events,
        legacy_events=(),
        generated_at=BASE_TIME,
    )

    assert tuple(event.occurred_at for event in agent_events) == original_order


def _transition(
    incident_key: str,
    action: str,
    offset_seconds: int,
) -> IncidentTransition:
    return IncidentTransition(
        incident_key=incident_key,
        action=action,
        kind=incident_key.split(":", 1)[0],
        subject=incident_key.split(":", 1)[1],
        severity="critical",
        status="active" if action != "recovered" else "resolved",
        reason=f"synthetic_{action}",
        observed_at=BASE_TIME + timedelta(seconds=offset_seconds),
        cycle_sequence=offset_seconds // 60,
        failure_count=2,
        recovery_count=2 if action == "recovered" else 0,
        occurrence_count=1,
    )
