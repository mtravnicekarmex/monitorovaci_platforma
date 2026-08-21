from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from monitoring_agent.client import CURRENT_ENDPOINT_KEYS
from monitoring_agent.incidents import (
    CycleSnapshot,
    EndpointObservationFact,
    evaluate_incident_lifecycle,
)
from monitoring_agent.interpretation import (
    INTERPRETATION_ERROR_DISABLED,
    INTERPRETATION_ERROR_NO_CONFIRMED_INCIDENT,
    INTERPRETATION_ERROR_PROVIDER_FAILED,
    INTERPRETATION_ERROR_PROVIDER_NOT_CONFIGURED,
    INTERPRETATION_ERROR_PROVIDER_OUTPUT_INVALID,
    INTERPRETATION_MODE_DRAFT,
    INTERPRETATION_STATUS_DISABLED,
    INTERPRETATION_STATUS_FALLBACK,
    INTERPRETATION_STATUS_INTERPRETED,
    INTERPRETATION_STATUS_SKIPPED,
    InterpretationPolicy,
    InterpretationProviderOutput,
    build_interpretation_prompt,
    interpret_confirmed_incidents,
)
from monitoring_agent.reporting import build_monitoring_report_snapshot


BASE_TIME = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)


class RecordingProvider:
    def __init__(
        self,
        output: InterpretationProviderOutput | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.output = output or InterpretationProviderOutput(
            summary="The confirmed incident most likely belongs to the database health boundary.",
            hypotheses=("The system database payload reported degraded status.",),
            recommended_read_only_checks=(
                "Review the latest sanitized monitoring audit and compare endpoint status counts.",
            ),
            evidence_gaps=("No target logs or raw payloads were supplied.",),
        )
        self.fail = fail
        self.requests = []

    def interpret(self, request):
        self.requests.append(request)
        if self.fail:
            raise RuntimeError(
                "password=SHOULD_NOT_LEAK Bearer SHOULD_NOT_LEAK C:\\Users\\tra\\.env"
            )
        return self.output


def _cycle(
    sequence: int,
    *,
    payload_status: dict[str, str] | None = None,
) -> CycleSnapshot:
    payload_status = payload_status or {}
    return CycleSnapshot(
        cycle_sequence=sequence,
        observed_at=BASE_TIME + timedelta(seconds=60 * sequence),
        endpoint_observations=tuple(
            EndpointObservationFact(
                endpoint_key=endpoint_key,
                transport_status="success",
                http_status=200,
                payload_status=payload_status.get(endpoint_key, "ok"),
            )
            for endpoint_key in CURRENT_ENDPOINT_KEYS
        ),
    )


def _policy(**overrides) -> InterpretationPolicy:
    values = {
        "enabled": True,
        "mode": INTERPRETATION_MODE_DRAFT,
        "provider_name": "synthetic-provider",
        "model_name": "synthetic-model",
        "timeout_seconds": 5.0,
        "max_cost_usd": 0.01,
    }
    values.update(overrides)
    return InterpretationPolicy(**values)


def _active_snapshot():
    evaluation = evaluate_incident_lifecycle(
        [
            _cycle(1, payload_status={"system_database": "degraded"}),
            _cycle(2, payload_status={"system_database": "degraded"}),
        ]
    )
    return build_monitoring_report_snapshot(
        generated_at=BASE_TIME,
        incident_evaluation=evaluation,
        latest_heartbeat_status="degraded",
        observation_count=9,
        transport_failure_count=0,
    )


def _candidate_snapshot():
    evaluation = evaluate_incident_lifecycle(
        [_cycle(1, payload_status={"system_database": "degraded"})]
    )
    return build_monitoring_report_snapshot(
        generated_at=BASE_TIME,
        incident_evaluation=evaluation,
        latest_heartbeat_status="degraded",
        observation_count=9,
        transport_failure_count=0,
    )


def test_disabled_interpretation_returns_report_fallback_without_provider_call():
    provider = RecordingProvider()

    result = interpret_confirmed_incidents(
        _active_snapshot(),
        policy=InterpretationPolicy(),
        provider=provider,
        now=BASE_TIME,
    )

    assert result.status == INTERPRETATION_STATUS_DISABLED
    assert result.error_code == INTERPRETATION_ERROR_DISABLED
    assert result.confirmed_incident_keys == ("endpoint:system_database",)
    assert provider.requests == []
    assert "Summary status: incident" in result.fallback_report
    assert "legacy alerts remain authoritative" in " ".join(result.safety_boundary)


def test_candidate_incident_skips_provider_until_confirmation():
    provider = RecordingProvider()

    result = interpret_confirmed_incidents(
        _candidate_snapshot(),
        policy=_policy(),
        provider=provider,
        now=BASE_TIME,
    )

    assert result.status == INTERPRETATION_STATUS_SKIPPED
    assert result.error_code == INTERPRETATION_ERROR_NO_CONFIRMED_INCIDENT
    assert result.confirmed_incident_keys == ()
    assert provider.requests == []
    assert "Summary status: degraded" in result.fallback_report


def test_active_incident_invokes_provider_with_bounded_sanitized_prompt():
    provider = RecordingProvider()
    snapshot = _active_snapshot()
    policy = _policy(max_prompt_chars=2_500)

    result = interpret_confirmed_incidents(
        snapshot,
        policy=policy,
        provider=provider,
        now=BASE_TIME,
    )

    assert result.status == INTERPRETATION_STATUS_INTERPRETED
    assert result.error_code is None
    assert result.deterministic_summary_status == "incident"
    assert result.confirmed_incident_keys == ("endpoint:system_database",)
    assert result.fallback_report is None
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.confirmed_incident_keys == ("endpoint:system_database",)
    assert request.timeout_seconds == 5.0
    assert request.max_cost_usd == 0.01
    assert len(request.prompt) <= 2_500
    assert "INTERPRETATION REQUEST - DRAFT ONLY" in request.prompt
    assert "Confirmed incident keys: endpoint:system_database" in request.prompt
    assert "commands, network actions, state writes" in request.prompt
    payload = result.to_dict()
    assert "prompt" not in payload
    assert payload["prompt_sha256"] == request.prompt_sha256
    assert payload["prompt_chars"] == len(request.prompt)


def test_missing_provider_uses_deterministic_fallback_with_prompt_audit():
    result = interpret_confirmed_incidents(
        _active_snapshot(),
        policy=_policy(),
        provider=None,
        now=BASE_TIME,
    )

    assert result.status == INTERPRETATION_STATUS_FALLBACK
    assert result.error_code == INTERPRETATION_ERROR_PROVIDER_NOT_CONFIGURED
    assert result.prompt_sha256 is not None
    assert result.prompt_chars is not None
    assert "Summary status: incident" in result.fallback_report


def test_provider_exception_falls_back_without_leaking_exception_text():
    result = interpret_confirmed_incidents(
        _active_snapshot(),
        policy=_policy(),
        provider=RecordingProvider(fail=True),
        now=BASE_TIME,
    )

    payload = str(result.to_dict())
    assert result.status == INTERPRETATION_STATUS_FALLBACK
    assert result.error_code == INTERPRETATION_ERROR_PROVIDER_FAILED
    assert "SHOULD_NOT_LEAK" not in payload
    assert "password=" not in payload
    assert "Bearer SHOULD_NOT_LEAK" not in payload
    assert r"C:\Users\tra" not in payload


def test_unsafe_provider_output_is_rejected_and_cannot_authorize_remediation():
    provider = RecordingProvider(
        InterpretationProviderOutput(
            summary="Restart the service now",
            hypotheses=("The target should be remediated immediately.",),
            recommended_read_only_checks=("Disable alert suppression.",),
        )
    )

    result = interpret_confirmed_incidents(
        _active_snapshot(),
        policy=_policy(),
        provider=provider,
        now=BASE_TIME,
    )

    payload = str(result.to_dict()).lower()
    assert result.status == INTERPRETATION_STATUS_FALLBACK
    assert result.error_code == INTERPRETATION_ERROR_PROVIDER_OUTPUT_INVALID
    assert "restart the service now" not in payload
    assert "disable alert" not in payload
    assert "deterministic incident rules" in payload


def test_provider_output_is_redacted_bounded_and_count_limited():
    provider = RecordingProvider(
        InterpretationProviderOutput(
            summary="token=SHOULD_NOT_LEAK " + ("safe text " * 30),
            hypotheses=(
                "Authorization: Bearer SHOULD_NOT_LEAK_123456789",
                "second hypothesis should be trimmed",
            ),
            recommended_read_only_checks=(
                "Compare sanitized aggregate status in the latest audit.",
                "second check should be trimmed",
            ),
            evidence_gaps=(
                "https://example.invalid/path?secret=SHOULD_NOT_LEAK",
                "second gap should be trimmed",
            ),
        )
    )

    result = interpret_confirmed_incidents(
        _active_snapshot(),
        policy=_policy(
            max_output_chars=90,
            max_hypotheses=1,
            max_read_only_checks=1,
            max_evidence_gaps=1,
        ),
        provider=provider,
        now=BASE_TIME,
    )

    payload = str(result.to_dict())
    assert result.status == INTERPRETATION_STATUS_INTERPRETED
    assert len(result.summary) <= 90
    assert len(result.hypotheses) == 1
    assert len(result.recommended_read_only_checks) == 1
    assert len(result.evidence_gaps) == 1
    assert "SHOULD_NOT_LEAK" not in payload
    assert "[redacted]" in payload
    assert "[redacted-query]" in payload


def test_policy_rejects_permissions_that_would_cross_item_6_boundary():
    with pytest.raises(ValueError, match="allow_network"):
        _policy(allow_network=True)
    with pytest.raises(ValueError, match="allow_state_mutation"):
        _policy(allow_state_mutation=True)
    with pytest.raises(ValueError, match="allow_process_control"):
        _policy(allow_process_control=True)
    with pytest.raises(ValueError, match="allow_delivery"):
        _policy(allow_delivery=True)
    with pytest.raises(ValueError, match="allow_alert_suppression"):
        _policy(allow_alert_suppression=True)


def test_prompt_builder_requires_confirmed_incident():
    with pytest.raises(ValueError, match="confirmed incident"):
        build_interpretation_prompt(
            _candidate_snapshot(),
            policy=_policy(),
            now=BASE_TIME,
        )
