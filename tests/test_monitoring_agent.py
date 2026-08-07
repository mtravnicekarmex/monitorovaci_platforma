from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import socket
import ssl
import sys
from threading import Thread
import zipfile
from urllib.error import URLError

import pytest

from monitoring_agent.__main__ import calculate_next_cycle_delay, main
from monitoring_agent.audit import StateAuditError, build_state_audit
from monitoring_agent.client import (
    APPROVED_ENDPOINTS,
    HealthClient as RuntimeHealthClient,
    Observation,
    validate_base_url,
    validate_external_web_url,
)
from monitoring_agent.config import AgentConfig
from monitoring_agent.credentials import load_bearer_credential
from monitoring_agent.observer import run_observation_cycle
from monitoring_agent.settings import ENV_KEYS, RuntimeSettings
from monitoring_agent.store import ObserverStore
from monitoring_agent.synthetic_server import create_server
from scripts.build_monitoring_agent_bundle import BUNDLE_FILES, build_bundle


def _write_runtime_env(
    path: Path,
    *,
    env_version: int = 2,
    base_url: str = "http://127.0.0.1:8020",
    external_web_url: str | None = None,
    state_dir: str = "../state",
    token: str = "t" * 48,
    extra: dict[str, str] | None = None,
) -> None:
    if env_version not in {1, 2}:
        raise ValueError("test environment version is unsupported")
    values = {
        "MONITORING_AGENT_ENV_VERSION": str(env_version),
        "MONITORING_AGENT_MODE": "test",
        "MONITORING_AGENT_INSTANCE_ID": "center-test",
        "MONITORING_AGENT_BASE_URL": base_url,
        "MONITORING_AGENT_STATE_DIR": state_dir,
        "MONITORING_AGENT_TIMEOUT_SECONDS": "2",
        "MONITORING_AGENT_MAX_ATTEMPTS": "3",
        "MONITORING_AGENT_RETRY_BACKOFF_SECONDS": "0.5",
        "MONITORING_AGENT_POLL_INTERVAL_SECONDS": "30",
        "MONITORING_AGENT_POLL_JITTER_SECONDS": "5",
        "MONITORING_AGENT_ENDPOINT_KEYS": (
            "live,ready,system_scheduler,system_runtime"
            if env_version == 1
            else (
                "live,ready,system_scheduler,scheduler_detail,system_runtime,"
                "system_database,system_proxy,system_smartfuelpass,external_web"
            )
        ),
        "MONITORING_AGENT_BEARER_TOKEN": token,
    }
    if env_version == 2:
        values["MONITORING_AGENT_EXTERNAL_WEB_URL"] = external_web_url or base_url
    values.update(extra or {})
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )


class HealthClient(RuntimeHealthClient):
    """Test convenience that points both boundaries at one loopback server."""

    def __init__(self, *, base_url: str, external_web_url: str | None = None, **kwargs):
        super().__init__(
            base_url=base_url,
            external_web_url=external_web_url or base_url,
            **kwargs,
        )


def _start_server(*, scenario: str = "healthy"):
    server = create_server(port=0, scenario=scenario)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _audit_observation(
    *,
    endpoint_key: str,
    started_at: datetime,
    transport_status: str = "success",
    attempt_count: int = 1,
    duration_seconds: float = 1.0,
    run_id: str = "private-run-marker",
    cycle_id: str = "private-cycle-marker",
    cycle_sequence: int = 1,
    contract_version: int = 4,
    endpoint_set_version: int = 3,
) -> Observation:
    return Observation(
        observation_id=f"observation-{endpoint_key}-{started_at.timestamp()}",
        observer_instance_id="private-instance-marker",
        run_id=run_id,
        cycle_id=cycle_id,
        cycle_sequence=cycle_sequence,
        endpoint_key=endpoint_key,
        poll_started_at=started_at.isoformat(),
        poll_finished_at=(
            started_at + timedelta(seconds=duration_seconds)
        ).isoformat(),
        http_status=200 if transport_status == "success" else None,
        transport_status=transport_status,
        attempt_count=attempt_count,
        contract_version=contract_version,
        endpoint_set_version=endpoint_set_version,
        source_checked_at=None,
        clock_skew_seconds=None,
        payload={"private_payload_marker": "must-not-appear"},
    )


def _append_serial_audit_cycle(
    *,
    store: ObserverStore,
    endpoint_keys: tuple[str, ...],
    cycle_start: datetime,
    outcomes: tuple[tuple[str, int, float], ...],
    cycle_sequence: int,
    run_id: str = "private-run-marker",
) -> datetime:
    elapsed_seconds = 0.0
    for endpoint_key, (transport_status, attempt_count, duration_seconds) in zip(
        endpoint_keys, outcomes, strict=True
    ):
        store.append(
            _audit_observation(
                endpoint_key=endpoint_key,
                started_at=cycle_start + timedelta(seconds=elapsed_seconds),
                transport_status=transport_status,
                attempt_count=attempt_count,
                duration_seconds=duration_seconds,
                run_id=run_id,
                cycle_id=f"private-cycle-{run_id}-{cycle_sequence}",
                cycle_sequence=cycle_sequence,
            )
        )
        elapsed_seconds += duration_seconds
    return cycle_start + timedelta(seconds=elapsed_seconds)


def _append_legacy_v2_cycle(
    *,
    store: ObserverStore,
    cycle_start: datetime,
    cycle_sequence: int,
    run_id: str = "private-run-marker",
) -> datetime:
    endpoint_keys = ("live", "ready", "system_scheduler")
    store.observations_path.parent.mkdir(parents=True, exist_ok=True)
    for endpoint_index, endpoint_key in enumerate(endpoint_keys):
        record = _audit_observation(
            endpoint_key=endpoint_key,
            started_at=cycle_start + timedelta(seconds=endpoint_index),
            run_id=run_id,
            cycle_id=f"private-legacy-cycle-{cycle_sequence}",
            cycle_sequence=cycle_sequence,
        ).to_dict()
        record["contract_version"] = 2
        record.pop("endpoint_set_version")
        record.pop("clock_skew_seconds", None)
        with store.observations_path.open(
            "a", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            handle.write("\n")
    return cycle_start + timedelta(seconds=len(endpoint_keys))


def _append_legacy_v3_cycle(
    *,
    store: ObserverStore,
    cycle_start: datetime,
    cycle_sequence: int,
    run_id: str = "private-run-marker",
) -> datetime:
    endpoint_keys = ("live", "ready", "system_scheduler", "system_runtime")
    for endpoint_index, endpoint_key in enumerate(endpoint_keys):
        record = _audit_observation(
                endpoint_key=endpoint_key,
                started_at=cycle_start + timedelta(seconds=endpoint_index),
                run_id=run_id,
                cycle_id=f"private-v3-cycle-{cycle_sequence}",
                cycle_sequence=cycle_sequence,
                contract_version=3,
                endpoint_set_version=2,
            ).to_dict()
        record.pop("clock_skew_seconds", None)
        store.observations_path.parent.mkdir(parents=True, exist_ok=True)
        with store.observations_path.open(
            "a", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            handle.write("\n")
    return cycle_start + timedelta(seconds=len(endpoint_keys))


def _append_running_lifecycle(
    store: ObserverStore,
    *,
    run_id: str = "private-run-marker",
) -> None:
    store.append_lifecycle(
        observer_instance_id="private-instance-marker",
        run_id=run_id,
        event="process_started",
        reason="observer_started",
    )


def _hold_state_writer_lock(state_dir: str, ready, release) -> None:
    with ObserverStore(Path(state_dir)).writer_lock():
        ready.set()
        release.wait(30)


def test_approved_endpoints_exclude_logs_and_mutations():
    assert set(APPROVED_ENDPOINTS) == {
        "external_web",
        "live",
        "ready",
        "scheduler_detail",
        "system_database",
        "system_proxy",
        "system_scheduler",
        "system_runtime",
        "system_smartfuelpass",
    }
    assert all("log" not in spec.path for spec in APPROVED_ENDPOINTS.values())
    assert all(
        not spec.path.rstrip("/").endswith("/run")
        for spec in APPROVED_ENDPOINTS.values()
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://192.0.2.10:8020",
        "ftp://127.0.0.1:8020",
        "https://user:password@example.invalid",
        "https://example.invalid/path",
        "https://example.invalid?token=secret",
    ],
)
def test_base_url_rejects_unsafe_forms(base_url):
    with pytest.raises(ValueError):
        validate_base_url(base_url)


def test_base_url_allows_loopback_http_and_remote_https():
    assert validate_base_url("http://127.0.0.1:8020") == "http://127.0.0.1:8020/"
    assert validate_base_url("https://observer-target.example.ts.net:9443") == (
        "https://observer-target.example.ts.net:9443/"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://192.0.2.10/",
        "https://user:password@example.invalid/",
        "https://example.invalid/dashboard",
        "https://example.invalid/?token=secret",
    ],
)
def test_external_web_url_rejects_unsafe_or_non_root_forms(url):
    with pytest.raises(ValueError):
        validate_external_web_url(url)


def test_external_web_url_allows_loopback_http_and_remote_https():
    assert validate_external_web_url("http://127.0.0.1:8020") == (
        "http://127.0.0.1:8020/"
    )
    assert validate_external_web_url("https://monitoring.example.invalid/") == (
        "https://monitoring.example.invalid/"
    )


def test_remote_https_client_requires_credential():
    with pytest.raises(ValueError, match="requires a bearer credential"):
        HealthClient(
            base_url="https://observer-target.example.ts.net:9443",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
        )


def test_client_requires_process_and_cycle_identity():
    with pytest.raises(ValueError, match="run_id"):
        HealthClient(
            base_url="http://127.0.0.1:8020",
            observer_instance_id="test-observer",
            run_id="",
        )
    client = HealthClient(
        base_url="http://127.0.0.1:8020",
        observer_instance_id="test-observer",
        run_id="private-run-marker",
    )
    with pytest.raises(ValueError, match="cycle_id"):
        client.poll("live", cycle_id="", cycle_sequence=1)
    with pytest.raises(ValueError, match="cycle_sequence"):
        client.poll("live", cycle_id="private-cycle-marker", cycle_sequence=0)


def test_credential_file_is_separate_and_strict(tmp_path):
    credential_path = tmp_path / "facade.token"
    credential_path.write_text("a" * 48 + "\n", encoding="utf-8")

    assert load_bearer_credential(credential_path) == "a" * 48

    credential_path.write_text("short", encoding="utf-8")
    with pytest.raises(ValueError, match="at least 32"):
        load_bearer_credential(credential_path)


def test_synthetic_server_rejects_non_loopback_bind():
    with pytest.raises(ValueError):
        create_server(host="0.0.0.0", port=0)


def test_client_reads_healthy_synthetic_contract():
    server, thread = _start_server()
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
        )
        observation = client.poll(
            "system_scheduler", cycle_id="private-cycle-marker", cycle_sequence=1
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "success"
    assert observation.http_status == 200
    assert observation.payload["scheduler_running"] is True
    assert observation.payload["jobs"][0]["job_id"] == "quarter_hour_job"
    assert "label" not in observation.payload["jobs"][0]
    assert "detail" not in observation.payload["jobs"][0]


def test_client_normalizes_system_runtime_to_safe_contract():
    server, thread = _start_server()
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
        )
        observation = client.poll(
            "system_runtime",
            cycle_id="private-cycle-marker",
            cycle_sequence=1,
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "success"
    assert observation.contract_version == 4
    assert observation.endpoint_set_version == 3
    assert set(observation.payload["boot"]) == {"status", "boot_time"}
    assert set(observation.payload["startup_task"]) == {
        "task_name",
        "status",
        "last_run_time",
        "last_task_result",
    }
    assert set(observation.payload["expected_listeners"][0]) == {
        "key",
        "status",
        "expected",
        "present",
        "local_port",
    }
    serialized = json.dumps(observation.to_dict()).lower()
    assert "detail" not in serialized
    assert "process_ids" not in serialized
    assert "local_address" not in serialized
    assert "next_run_time" not in serialized


@pytest.mark.parametrize(
    "endpoint_key",
    [
        "scheduler_detail",
        "system_database",
        "system_proxy",
        "system_smartfuelpass",
    ],
)
def test_client_normalizes_remaining_health_page_contracts(endpoint_key):
    server, thread = _start_server()
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
        )
        observation = client.poll(
            endpoint_key,
            cycle_id="private-cycle-marker",
            cycle_sequence=1,
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "success"
    assert observation.http_status == 200
    assert observation.source_checked_at is not None
    serialized = json.dumps(observation.to_dict(), sort_keys=True).lower()
    for forbidden in (
        "description",
        "detail",
        "is_manual_runnable",
        "process_ids",
        "public_host",
        "server_version",
        "total_amount",
        "report_periods",
    ):
        assert f'"{forbidden}"' not in serialized


def test_external_web_probe_validates_html_without_sending_facade_bearer():
    server, thread = _start_server()
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
            bearer_credential="private-test-bearer",
        )
        observation = client.poll(
            "external_web",
            cycle_id="private-cycle-marker",
            cycle_sequence=1,
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "success"
    assert observation.http_status == 200
    assert observation.source_checked_at is None
    assert observation.payload == {"status": "ok", "content_type_valid": True}
    assert "synthetic" not in json.dumps(observation.to_dict()).lower()


def test_external_web_probe_rejects_non_html_without_retry():
    server, thread = _start_server(scenario="invalid_schema")
    delays = []
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
            sleep_fn=delays.append,
        )
        observation = client.poll(
            "external_web",
            cycle_id="private-cycle-marker",
            cycle_sequence=1,
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "schema_error"
    assert observation.attempt_count == 1
    assert observation.payload == {}
    assert delays == []


def test_external_web_probe_does_not_follow_redirects_or_retry_them():
    server, thread = _start_server(scenario="external_redirect")
    delays = []
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
            sleep_fn=delays.append,
        )
        observation = client.poll(
            "external_web",
            cycle_id="private-cycle-marker",
            cycle_sequence=1,
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "http_error"
    assert observation.http_status == 302
    assert observation.attempt_count == 1
    assert observation.payload == {}
    assert delays == []


def test_tls_failure_is_sanitized_and_not_retried(monkeypatch):
    delays = []
    client = HealthClient(
        base_url="http://127.0.0.1:8020",
        external_web_url="https://monitoring.example.invalid/",
        observer_instance_id="test-observer",
        run_id="private-run-marker",
        sleep_fn=delays.append,
    )

    def fail_tls(*args, **kwargs):
        del args, kwargs
        raise URLError(ssl.SSLCertVerificationError("certificate rejected"))

    monkeypatch.setattr(client._opener, "open", fail_tls)
    observation = client.poll(
        "external_web",
        cycle_id="private-cycle-marker",
        cycle_sequence=1,
    )

    assert observation.transport_status == "tls_error"
    assert observation.http_status is None
    assert observation.attempt_count == 1
    assert observation.payload == {}
    assert delays == []


def test_system_runtime_schema_mismatch_fails_closed_without_retry():
    server, thread = _start_server(scenario="invalid_schema")
    delays = []
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
            sleep_fn=delays.append,
        )
        observation = client.poll(
            "system_runtime",
            cycle_id="private-cycle-marker",
            cycle_sequence=1,
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "schema_error"
    assert observation.attempt_count == 1
    assert observation.payload == {}
    assert delays == []


def test_readiness_503_is_application_state_not_transport_failure():
    server, thread = _start_server(scenario="readiness_unavailable")
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
        )
        observation = client.poll(
            "ready", cycle_id="private-cycle-marker", cycle_sequence=1
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "success"
    assert observation.http_status == 503
    assert observation.attempt_count == 1
    assert observation.payload == {"status": "unavailable"}


def test_stopped_scheduler_remains_normalized_evidence():
    server, thread = _start_server(scenario="scheduler_stopped")
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
        )
        observation = client.poll(
            "system_scheduler", cycle_id="private-cycle-marker", cycle_sequence=1
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "success"
    assert observation.payload["status"] == "error"
    assert observation.payload["scheduler_running"] is False
    assert observation.payload["heartbeat_age_seconds"] == 1200.0


@pytest.mark.parametrize(
    ("scenario", "expected_status", "expected_http_status"),
    [
        ("unauthorized", "http_error", 401),
        ("invalid_schema", "schema_error", 200),
    ],
)
def test_non_retryable_response_fails_closed_without_retry(
    scenario,
    expected_status,
    expected_http_status,
):
    server, thread = _start_server(scenario=scenario)
    delays = []
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
            max_attempts=3,
            retry_backoff_seconds=0.25,
            sleep_fn=delays.append,
        )
        observation = client.poll(
            "live", cycle_id="private-cycle-marker", cycle_sequence=1
        )
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == expected_status
    assert observation.http_status == expected_http_status
    assert observation.attempt_count == 1
    assert observation.payload == {}
    assert delays == []


def test_unknown_endpoint_is_rejected_before_request():
    client = HealthClient(
        base_url="http://127.0.0.1:8020",
        observer_instance_id="test-observer",
        run_id="private-run-marker",
    )
    with pytest.raises(ValueError):
        client.poll(
            "scheduler_log", cycle_id="private-cycle-marker", cycle_sequence=1
        )


def test_observation_cycle_writes_only_agent_owned_state(tmp_path):
    server, thread = _start_server()
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
        )
        store = ObserverStore(tmp_path / "state")
        observations = run_observation_cycle(
            client=client,
            store=store,
            observer_instance_id="test-observer",
            run_id="private-run-marker",
            cycle_sequence=1,
        )
    finally:
        _stop_server(server, thread)

    assert len(observations) == 9
    lines = store.observations_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 9
    persisted = [json.loads(line) for line in lines]
    assert {row["endpoint_key"] for row in persisted} == set(APPROVED_ENDPOINTS)
    assert {row["run_id"] for row in persisted} == {"private-run-marker"}
    assert len({row["cycle_id"] for row in persisted}) == 1
    assert {row["cycle_sequence"] for row in persisted} == {1}
    assert {row["contract_version"] for row in persisted} == {4}
    assert {row["endpoint_set_version"] for row in persisted} == {3}
    assert all("authorization" not in line.lower() for line in lines)
    assert all("synthetic test data" not in line.lower() for line in lines)
    heartbeat = json.loads(store.heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["observer_instance_id"] == "test-observer"
    assert heartbeat["run_id"] == "private-run-marker"
    assert heartbeat["cycle_id"] == persisted[0]["cycle_id"]
    assert heartbeat["status"] == "healthy"
    assert heartbeat["cycle_finished_at"] is not None
    assert heartbeat["observation_count"] == 9
    assert heartbeat["transport_failure_count"] == 0


def test_connection_failure_is_sanitized():
    temporary_socket = socket.socket()
    temporary_socket.bind(("127.0.0.1", 0))
    unused_port = temporary_socket.getsockname()[1]
    temporary_socket.close()
    client = HealthClient(
        base_url=f"http://127.0.0.1:{unused_port}",
        observer_instance_id="test-observer",
        run_id="private-run-marker",
        timeout_seconds=1.0,
        retry_backoff_seconds=0,
    )
    observation = client.poll(
        "live", cycle_id="private-cycle-marker", cycle_sequence=1
    )

    assert observation.transport_status in {"connection_error", "timeout"}
    assert observation.http_status is None
    assert observation.payload == {}
    assert observation.attempt_count == 3


def test_transport_retry_is_bounded_with_exponential_backoff():
    temporary_socket = socket.socket()
    temporary_socket.bind(("127.0.0.1", 0))
    unused_port = temporary_socket.getsockname()[1]
    temporary_socket.close()
    delays = []
    client = HealthClient(
        base_url=f"http://127.0.0.1:{unused_port}",
        observer_instance_id="test-observer",
        run_id="private-run-marker",
        timeout_seconds=0.1,
        max_attempts=3,
        retry_backoff_seconds=0.25,
        sleep_fn=delays.append,
    )

    observation = client.poll(
        "live", cycle_id="private-cycle-marker", cycle_sequence=1
    )

    assert observation.transport_status in {"connection_error", "timeout"}
    assert observation.attempt_count == 3
    assert delays == [0.25, 0.5]


def test_failed_cycle_marks_agent_heartbeat_degraded(tmp_path):
    temporary_socket = socket.socket()
    temporary_socket.bind(("127.0.0.1", 0))
    unused_port = temporary_socket.getsockname()[1]
    temporary_socket.close()
    client = HealthClient(
        base_url=f"http://127.0.0.1:{unused_port}",
        observer_instance_id="test-observer",
        run_id="private-run-marker",
        timeout_seconds=0.1,
        max_attempts=1,
    )
    store = ObserverStore(tmp_path / "state")

    run_observation_cycle(
        client=client,
        store=store,
        observer_instance_id="test-observer",
        run_id="private-run-marker",
        cycle_sequence=1,
        endpoint_keys=("live",),
    )

    heartbeat = json.loads(store.heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["status"] == "degraded"
    assert heartbeat["observation_count"] == 1
    assert heartbeat["transport_failure_count"] == 1


def test_unhealthy_target_does_not_mark_observer_transport_degraded(tmp_path):
    server, thread = _start_server(scenario="scheduler_stopped")
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
            run_id="private-run-marker",
        )
        store = ObserverStore(tmp_path / "state")
        observations = run_observation_cycle(
            client=client,
            store=store,
            observer_instance_id="test-observer",
            run_id="private-run-marker",
            cycle_sequence=1,
        )
    finally:
        _stop_server(server, thread)

    scheduler = next(
        item for item in observations if item.endpoint_key == "system_scheduler"
    )
    heartbeat = json.loads(store.heartbeat_path.read_text(encoding="utf-8"))
    assert scheduler.payload["scheduler_running"] is False
    assert heartbeat["status"] == "healthy"
    assert heartbeat["transport_failure_count"] == 0


def test_state_audit_reports_safe_loss_and_recovery_aggregates(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(
        env_path,
        state_dir=str(state_dir),
        extra={
            "MONITORING_AGENT_MAX_ATTEMPTS": "3",
            "MONITORING_AGENT_POLL_INTERVAL_SECONDS": "60",
            "MONITORING_AGENT_POLL_JITTER_SECONDS": "5",
        },
    )
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    base = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    healthy_cycle = tuple(("success", 1) for _ in settings.endpoint_keys)
    timeout_cycle = tuple(("timeout", 3) for _ in settings.endpoint_keys)
    mixed_cycle = (("timeout", 3), *healthy_cycle[1:])
    cycles = (healthy_cycle, timeout_cycle, mixed_cycle, healthy_cycle)
    for cycle_index, cycle in enumerate(cycles):
        cycle_start = base + timedelta(seconds=60 * cycle_index)
        for endpoint_index, (endpoint_key, outcome) in enumerate(
            zip(settings.endpoint_keys, cycle, strict=True)
        ):
            status, attempts = outcome
            store.append(
                _audit_observation(
                    endpoint_key=endpoint_key,
                    started_at=cycle_start + timedelta(seconds=2 * endpoint_index),
                    transport_status=status,
                    attempt_count=attempts,
                    cycle_id=f"private-cycle-{cycle_index + 1}",
                    cycle_sequence=cycle_index + 1,
                )
            )
    _append_running_lifecycle(store)
    last_cycle_start = base + timedelta(seconds=180)
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id="private-run-marker",
        status="healthy",
        cycle_id="private-cycle-4",
        cycle_started_at=last_cycle_start.isoformat(),
        cycle_finished_at=(last_cycle_start + timedelta(seconds=17)).isoformat(),
        observation_count=9,
        transport_failure_count=0,
    )

    audit = build_state_audit(settings)

    assert audit["audit_contract_version"] == 7
    assert audit["event"] == "agent_state_audit"
    assert audit["configuration"] == {
        "endpoint_count": 9,
        "endpoint_set_version": 3,
        "max_attempts": 3,
        "request_timeout_seconds": 2.0,
        "retry_backoff_seconds": 0.5,
        "poll_interval_seconds": 60.0,
        "poll_jitter_seconds": 5.0,
        "configured_timeout_cycle_budget_seconds": 67.5,
    }
    assert audit["observations"] == {
        "total_count": 36,
        "complete_cycle_count": 4,
        "trailing_observation_count": 0,
        "incomplete_cycle_count": 0,
        "incomplete_observation_count": 0,
        "in_progress_cycle_count": 0,
        "in_progress_observation_count": 0,
        "trailing_cycle_classification": None,
        "observer_instance_count": 1,
        "process_run_count": 1,
        "transport_status_counts": {"success": 26, "timeout": 10},
        "attempt_count_counts": {"1": 26, "3": 10},
        "contract_version_counts": {"4": 36},
        "endpoint_set_version_counts": {"3": 36},
        "max_attempt_count": 3,
        "attempt_over_limit_count": 0,
        "retryable_not_exhausted_count": 0,
        "non_retryable_retried_count": 0,
        "success_after_retry_count": 0,
        "attempt_bounds_valid": True,
        "retry_contract_valid": True,
        "current_run": {
            "observation_count": 36,
            "attempt_over_limit_count": 0,
            "retryable_not_exhausted_count": 0,
            "non_retryable_retried_count": 0,
            "success_after_retry_count": 0,
            "attempt_bounds_valid": True,
            "retry_contract_valid": True,
        },
    }
    assert audit["cycles"] == {
        "endpoint_sequence_mismatch_count": 0,
        "endpoint_sequence_valid": True,
        "cycle_sequence_mismatch_count": 0,
        "cycle_sequence_valid": True,
        "process_run_transition_count": 0,
        "process_run_reentry_count": 0,
        "single_writer_observation_history_valid": True,
        "self_health_counts": {"degraded": 2, "healthy": 2},
        "outcome_counts": {"healthy": 2, "partial_failure": 1, "unreachable": 1},
        "mixed_transport_status_count": 1,
        "first_degraded_cycle_index": 2,
        "first_recovery_cycle_index": 4,
        "transition_counts": {
            "degraded_to_degraded": 1,
            "degraded_to_healthy": 1,
            "healthy_to_degraded": 1,
        },
    }
    assert audit["timing"] == {
        "interval_count": 3,
        "interval_min_seconds": 60.0,
        "interval_max_seconds": 60.0,
        "interval_average_seconds": 60.0,
        "overlap_count": 0,
        "early_start_count": 0,
        "late_beyond_jitter_count": 0,
        "cross_run_interval_count": 0,
        "cross_run_interval_min_seconds": None,
        "cross_run_interval_max_seconds": None,
        "cross_run_interval_average_seconds": None,
        "cross_run_overlap_count": 0,
        "longest_cross_run_interval": None,
        "tolerance_seconds": 2.0,
        "cycle_duration_count": 4,
        "cycle_duration_min_seconds": 17.0,
        "cycle_duration_max_seconds": 17.0,
        "cycle_duration_average_seconds": 17.0,
        "cycle_duration_beyond_configured_budget_count": 0,
        "longest_cycle": {
            "cycle_index": 1,
            "duration_seconds": 17.0,
            "outcome": "healthy",
            "endpoint_set_version": 3,
            "configured_timeout_budget_seconds": 67.5,
            "excess_beyond_configured_budget_seconds": 0.0,
        },
        "longest_interval": {
            "ending_cycle_index": 2,
            "interval_seconds": 60.0,
            "previous_cycle_duration_seconds": 17.0,
            "previous_cycle_outcome": "healthy",
            "expected_minimum_seconds": 60.0,
            "allowed_maximum_seconds": 67.0,
            "excess_beyond_allowed_seconds": 0.0,
            "classification": "scheduled_interval",
        },
        "largest_late_interval": None,
    }
    assert audit["latest_heartbeat"] == {
        "status": "healthy",
        "observation_count": 9,
        "transport_failure_count": 0,
        "process_id_present": True,
        "observer_instance_matches_observations": True,
        "run_matches_last_complete_cycle": True,
        "matches_last_complete_cycle": True,
    }
    assert audit["lifecycle"] == {
        "contract_version": 1,
        "event_count": 1,
        "process_start_count": 1,
        "process_stop_count": 0,
        "distinct_run_count": 1,
        "observation_run_count": 1,
        "restart_detected": False,
        "clean_restart_count": 0,
        "start_while_prior_run_open_count": 0,
        "concurrent_start_count": 0,
        "unclean_restart_count": 0,
        "single_writer_history_valid": True,
        "unclosed_run_count": 1,
        "abandoned_unclosed_run_count": 0,
        "duplicate_start_count": 0,
        "duplicate_stop_count": 0,
        "orphan_stop_count": 0,
        "process_id_mismatch_run_count": 0,
        "timestamp_regression_count": 0,
        "observation_runs_without_start_count": 0,
        "lifecycle_runs_without_observations_count": 0,
        "observer_instance_count": 1,
        "observer_instance_matches_observations": True,
        "current_run_has_start": True,
        "current_run_has_stop": False,
        "current_run_is_unclosed": True,
        "stop_reason_counts": {},
        "history_valid": True,
    }
    assert audit["evidence_gaps"] == [
        "heartbeat_transition_history_not_persisted",
    ]


def test_state_audit_preserves_legacy_v2_and_v3_cycles_after_endpoint_set_upgrade(
    tmp_path,
):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(env_path, state_dir=str(state_dir))
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    base = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)

    _append_legacy_v2_cycle(
        store=store,
        cycle_start=base,
        cycle_sequence=1,
    )
    _append_legacy_v3_cycle(
        store=store,
        cycle_start=base + timedelta(seconds=60),
        cycle_sequence=2,
    )
    current_start = base + timedelta(seconds=120)
    current_finished = _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=current_start,
        outcomes=tuple(("success", 1, 1.0) for _ in settings.endpoint_keys),
        cycle_sequence=3,
    )
    _append_running_lifecycle(store)
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id="private-run-marker",
        status="healthy",
        cycle_id="private-cycle-private-run-marker-3",
        cycle_started_at=current_start.isoformat(),
        cycle_finished_at=current_finished.isoformat(),
        observation_count=9,
        transport_failure_count=0,
    )

    audit = build_state_audit(settings)

    assert audit["audit_contract_version"] == 7
    assert audit["configuration"]["endpoint_set_version"] == 3
    assert audit["observations"]["total_count"] == 16
    assert audit["observations"]["complete_cycle_count"] == 3
    assert audit["observations"]["contract_version_counts"] == {
        "2": 3,
        "3": 4,
        "4": 9,
    }
    assert audit["observations"]["endpoint_set_version_counts"] == {
        "1": 3,
        "2": 4,
        "3": 9,
    }
    assert audit["cycles"]["endpoint_sequence_valid"] is True
    assert audit["cycles"]["cycle_sequence_valid"] is True
    assert audit["latest_heartbeat"]["matches_last_complete_cycle"] is True
    serialized = json.dumps(audit, sort_keys=True)
    assert "private-instance-marker" not in serialized
    assert "private-cycle-marker" not in serialized
    assert "private-run-marker" not in serialized
    assert "private_payload_marker" not in serialized
    assert "observation-live" not in serialized
    assert "2026-" not in serialized


@pytest.mark.parametrize(
    ("contract_version", "endpoint_set_version"),
    [(3, 3), (4, 2)],
)
def test_state_audit_rejects_contract_endpoint_set_mismatch(
    tmp_path,
    contract_version,
    endpoint_set_version,
):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(env_path, state_dir=str(state_dir))
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    record = _audit_observation(
        endpoint_key="live",
        started_at=datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc),
        contract_version=contract_version,
        endpoint_set_version=endpoint_set_version,
    ).to_dict()
    if contract_version == 3:
        record.pop("clock_skew_seconds", None)
    store.observations_path.parent.mkdir(parents=True, exist_ok=True)
    store.observations_path.write_text(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(StateAuditError, match="contract endpoint set"):
        build_state_audit(settings)


def test_state_audit_classifies_unexplained_gap_between_cycles(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(
        env_path,
        state_dir=str(state_dir),
        extra={
            "MONITORING_AGENT_TIMEOUT_SECONDS": "3",
            "MONITORING_AGENT_POLL_INTERVAL_SECONDS": "60",
            "MONITORING_AGENT_POLL_JITTER_SECONDS": "5",
        },
    )
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    base = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    timeout_cycle = tuple(("timeout", 3, 10.5) for _ in settings.endpoint_keys)
    healthy_cycle = tuple(("success", 1, 1.0) for _ in settings.endpoint_keys)
    _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=base,
        outcomes=timeout_cycle,
        cycle_sequence=1,
    )
    recovered_at = base + timedelta(seconds=4545.121)
    recovered_finished_at = _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=recovered_at,
        outcomes=healthy_cycle,
        cycle_sequence=2,
    )
    _append_running_lifecycle(store)
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id="private-run-marker",
        status="healthy",
        cycle_id="private-cycle-private-run-marker-2",
        cycle_started_at=recovered_at.isoformat(),
        cycle_finished_at=recovered_finished_at.isoformat(),
        observation_count=9,
        transport_failure_count=0,
    )

    timing = build_state_audit(settings)["timing"]

    assert timing["cycle_duration_max_seconds"] == 94.5
    assert timing["cycle_duration_beyond_configured_budget_count"] == 0
    assert timing["late_beyond_jitter_count"] == 1
    assert timing["longest_interval"] == {
        "ending_cycle_index": 2,
        "interval_seconds": 4545.121,
        "previous_cycle_duration_seconds": 94.5,
        "previous_cycle_outcome": "unreachable",
        "expected_minimum_seconds": 94.5,
        "allowed_maximum_seconds": 101.5,
        "excess_beyond_allowed_seconds": 4443.621,
        "classification": "unexplained_between_cycles_or_clock_discontinuity",
    }
    assert timing["largest_late_interval"] == timing["longest_interval"]


def test_state_audit_retains_unclean_restart_and_partial_cycle_evidence(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(env_path, state_dir=str(state_dir))
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    base = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    first_run_id = "private-run-one"
    current_run_id = "private-run-two"
    _append_running_lifecycle(store, run_id=first_run_id)
    store.append(
        _audit_observation(
            endpoint_key=settings.endpoint_keys[0],
            started_at=base,
            run_id=first_run_id,
            cycle_id="private-interrupted-cycle",
            cycle_sequence=1,
        )
    )
    _append_running_lifecycle(store, run_id=current_run_id)
    healthy_cycle = tuple(("success", 1, 1.0) for _ in settings.endpoint_keys)
    resumed_at = base + timedelta(seconds=120)
    resumed_finished_at = _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=resumed_at,
        outcomes=healthy_cycle,
        cycle_sequence=1,
        run_id=current_run_id,
    )
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id=current_run_id,
        status="healthy",
        cycle_id=f"private-cycle-{current_run_id}-1",
        cycle_started_at=resumed_at.isoformat(),
        cycle_finished_at=resumed_finished_at.isoformat(),
        observation_count=9,
        transport_failure_count=0,
    )

    audit = build_state_audit(settings)

    assert audit["observations"]["total_count"] == 10
    assert audit["observations"]["complete_cycle_count"] == 1
    assert audit["observations"]["incomplete_cycle_count"] == 1
    assert audit["observations"]["incomplete_observation_count"] == 1
    assert audit["observations"]["process_run_count"] == 2
    assert audit["cycles"]["cycle_sequence_valid"] is True
    assert audit["cycles"]["process_run_reentry_count"] == 0
    assert audit["latest_heartbeat"]["matches_last_complete_cycle"] is True
    assert audit["lifecycle"]["restart_detected"] is True
    assert audit["lifecycle"]["clean_restart_count"] == 0
    assert audit["lifecycle"]["start_while_prior_run_open_count"] == 1
    assert audit["lifecycle"]["concurrent_start_count"] == 0
    assert audit["lifecycle"]["unclean_restart_count"] == 1
    assert audit["lifecycle"]["single_writer_history_valid"] is True
    assert audit["lifecycle"]["unclosed_run_count"] == 2
    assert audit["lifecycle"]["abandoned_unclosed_run_count"] == 1
    assert audit["lifecycle"]["current_run_is_unclosed"] is True
    assert audit["lifecycle"]["history_valid"] is True
    serialized = json.dumps(audit, sort_keys=True)
    assert first_run_id not in serialized
    assert current_run_id not in serialized
    assert "private-interrupted-cycle" not in serialized


def test_state_audit_separates_cross_run_gap_from_scheduled_timing(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(
        env_path,
        state_dir=str(state_dir),
        extra={
            "MONITORING_AGENT_POLL_INTERVAL_SECONDS": "60",
            "MONITORING_AGENT_POLL_JITTER_SECONDS": "5",
        },
    )
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    base = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    first_run_id = "private-run-one"
    second_run_id = "private-run-two"
    healthy_cycle = tuple(("success", 1, 1.0) for _ in settings.endpoint_keys)
    _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=base,
        outcomes=healthy_cycle,
        cycle_sequence=1,
        run_id=first_run_id,
    )
    second_cycle_at = base + timedelta(seconds=46.83)
    second_finished_at = _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=second_cycle_at,
        outcomes=healthy_cycle,
        cycle_sequence=1,
        run_id=second_run_id,
    )
    _append_running_lifecycle(store, run_id=first_run_id)
    _append_running_lifecycle(store, run_id=second_run_id)
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id=second_run_id,
        status="healthy",
        cycle_id=f"private-cycle-{second_run_id}-1",
        cycle_started_at=second_cycle_at.isoformat(),
        cycle_finished_at=second_finished_at.isoformat(),
        observation_count=9,
        transport_failure_count=0,
    )

    audit = build_state_audit(settings)
    timing = audit["timing"]

    assert audit["cycles"]["process_run_transition_count"] == 1
    assert audit["cycles"]["process_run_reentry_count"] == 0
    assert audit["cycles"]["single_writer_observation_history_valid"] is True
    assert timing["interval_count"] == 0
    assert timing["interval_min_seconds"] is None
    assert timing["interval_max_seconds"] is None
    assert timing["interval_average_seconds"] is None
    assert timing["early_start_count"] == 0
    assert timing["late_beyond_jitter_count"] == 0
    assert timing["longest_interval"] is None
    assert timing["largest_late_interval"] is None
    assert timing["cross_run_interval_count"] == 1
    assert timing["cross_run_interval_min_seconds"] == 46.83
    assert timing["cross_run_interval_max_seconds"] == 46.83
    assert timing["cross_run_interval_average_seconds"] == 46.83
    assert timing["cross_run_overlap_count"] == 0
    assert timing["longest_cross_run_interval"] == {
        "ending_cycle_index": 2,
        "interval_seconds": 46.83,
        "previous_cycle_duration_seconds": 9.0,
        "previous_cycle_outcome": "healthy",
        "classification": "process_run_transition",
    }
    serialized = json.dumps(audit, sort_keys=True)
    assert first_run_id not in serialized
    assert second_run_id not in serialized


def test_state_audit_distinguishes_concurrent_run_reentry_from_unclean_restart(
    tmp_path,
):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(env_path, state_dir=str(state_dir))
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    base = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    first_run_id = "private-run-one"
    once_run_id = "private-run-once"
    current_run_id = "private-run-current"
    healthy_cycle = tuple(("success", 1, 1.0) for _ in settings.endpoint_keys)

    _append_running_lifecycle(store, run_id=first_run_id)
    _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=base,
        outcomes=healthy_cycle,
        cycle_sequence=1,
        run_id=first_run_id,
    )
    _append_running_lifecycle(store, run_id=once_run_id)
    _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=base + timedelta(seconds=46.83),
        outcomes=healthy_cycle,
        cycle_sequence=1,
        run_id=once_run_id,
    )
    store.append_lifecycle(
        observer_instance_id="private-instance-marker",
        run_id=once_run_id,
        event="process_stopped",
        reason="once_completed",
    )
    _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=base + timedelta(seconds=60.111),
        outcomes=healthy_cycle,
        cycle_sequence=2,
        run_id=first_run_id,
    )
    store.append_lifecycle(
        observer_instance_id="private-instance-marker",
        run_id=first_run_id,
        event="process_stopped",
        reason="keyboard_interrupt",
    )
    _append_running_lifecycle(store, run_id=current_run_id)
    current_cycle_at = base + timedelta(seconds=169.511)
    current_finished_at = _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=current_cycle_at,
        outcomes=healthy_cycle,
        cycle_sequence=1,
        run_id=current_run_id,
    )
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id=current_run_id,
        status="healthy",
        cycle_id=f"private-cycle-{current_run_id}-1",
        cycle_started_at=current_cycle_at.isoformat(),
        cycle_finished_at=current_finished_at.isoformat(),
        observation_count=9,
        transport_failure_count=0,
    )

    audit = build_state_audit(settings)

    assert audit["cycles"]["process_run_transition_count"] == 3
    assert audit["cycles"]["process_run_reentry_count"] == 1
    assert audit["cycles"]["single_writer_observation_history_valid"] is False
    assert audit["lifecycle"]["clean_restart_count"] == 1
    assert audit["lifecycle"]["start_while_prior_run_open_count"] == 1
    assert audit["lifecycle"]["concurrent_start_count"] == 1
    assert audit["lifecycle"]["unclean_restart_count"] == 0
    assert audit["lifecycle"]["single_writer_history_valid"] is False
    assert audit["lifecycle"]["abandoned_unclosed_run_count"] == 0
    assert audit["lifecycle"]["current_run_is_unclosed"] is True
    assert audit["lifecycle"]["history_valid"] is True
    serialized = json.dumps(audit, sort_keys=True)
    assert first_run_id not in serialized
    assert once_run_id not in serialized
    assert current_run_id not in serialized


def test_state_audit_distinguishes_current_polling_cycle_from_interruption(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(env_path, state_dir=str(state_dir))
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    cycle_start = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    cycle_id = "private-current-cycle"
    store.append(
        _audit_observation(
            endpoint_key=settings.endpoint_keys[0],
            started_at=cycle_start,
            cycle_id=cycle_id,
            cycle_sequence=1,
        )
    )
    _append_running_lifecycle(store)
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id="private-run-marker",
        status="polling",
        cycle_id=cycle_id,
        cycle_started_at=cycle_start.isoformat(),
    )

    audit = build_state_audit(settings)

    assert audit["observations"]["complete_cycle_count"] == 0
    assert audit["observations"]["trailing_observation_count"] == 1
    assert audit["observations"]["incomplete_cycle_count"] == 0
    assert audit["observations"]["incomplete_observation_count"] == 0
    assert audit["observations"]["in_progress_cycle_count"] == 1
    assert audit["observations"]["in_progress_observation_count"] == 1
    assert (
        audit["observations"]["trailing_cycle_classification"]
        == "current_polling_cycle"
    )
    assert audit["latest_heartbeat"]["status"] == "polling"
    assert audit["latest_heartbeat"]["matches_last_complete_cycle"] is None
    assert audit["lifecycle"]["history_valid"] is True


def test_state_audit_classifies_long_running_previous_cycle(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(
        env_path,
        state_dir=str(state_dir),
        extra={
            "MONITORING_AGENT_TIMEOUT_SECONDS": "3",
            "MONITORING_AGENT_POLL_INTERVAL_SECONDS": "60",
            "MONITORING_AGENT_POLL_JITTER_SECONDS": "5",
        },
    )
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    base = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    stalled_cycle = (("timeout", 3, 4533.0),) + tuple(
        ("timeout", 3, 1.0) for _ in settings.endpoint_keys[1:]
    )
    healthy_cycle = tuple(("success", 1, 1.0) for _ in settings.endpoint_keys)
    _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=base,
        outcomes=stalled_cycle,
        cycle_sequence=1,
    )
    recovered_at = base + timedelta(seconds=4545.121)
    recovered_finished_at = _append_serial_audit_cycle(
        store=store,
        endpoint_keys=settings.endpoint_keys,
        cycle_start=recovered_at,
        outcomes=healthy_cycle,
        cycle_sequence=2,
    )
    _append_running_lifecycle(store)
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id="private-run-marker",
        status="healthy",
        cycle_id="private-cycle-private-run-marker-2",
        cycle_started_at=recovered_at.isoformat(),
        cycle_finished_at=recovered_finished_at.isoformat(),
        observation_count=9,
        transport_failure_count=0,
    )

    timing = build_state_audit(settings)["timing"]

    assert timing["cycle_duration_max_seconds"] == 4541.0
    assert timing["cycle_duration_beyond_configured_budget_count"] == 1
    assert timing["late_beyond_jitter_count"] == 0
    assert timing["longest_cycle"] == {
        "cycle_index": 1,
        "duration_seconds": 4541.0,
        "outcome": "unreachable",
        "endpoint_set_version": 3,
        "configured_timeout_budget_seconds": 94.5,
        "excess_beyond_configured_budget_seconds": 4446.5,
    }
    assert timing["longest_interval"] == {
        "ending_cycle_index": 2,
        "interval_seconds": 4545.121,
            "previous_cycle_duration_seconds": 4541.0,
        "previous_cycle_outcome": "unreachable",
            "expected_minimum_seconds": 4541.0,
            "allowed_maximum_seconds": 4548.0,
        "excess_beyond_allowed_seconds": 0.0,
        "classification": "long_running_previous_cycle",
    }
    assert timing["largest_late_interval"] is None


def test_state_audit_cli_is_read_only_and_does_not_require_network(
    tmp_path,
    monkeypatch,
    capsys,
):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    env_path = project_dir / ".env"
    _write_runtime_env(env_path, state_dir=str(state_dir))
    settings = RuntimeSettings.load(env_path)
    store = ObserverStore(state_dir)
    cycle_start = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
    for endpoint_index, endpoint_key in enumerate(settings.endpoint_keys):
        store.append(
            _audit_observation(
                endpoint_key=endpoint_key,
                started_at=cycle_start + timedelta(seconds=endpoint_index),
                cycle_id="private-cycle-1",
                cycle_sequence=1,
            )
        )
    _append_running_lifecycle(store)
    store.write_heartbeat(
        observer_instance_id="private-instance-marker",
        run_id="private-run-marker",
        status="healthy",
        cycle_id="private-cycle-1",
        cycle_started_at=cycle_start.isoformat(),
        cycle_finished_at=(cycle_start + timedelta(seconds=9)).isoformat(),
        observation_count=9,
        transport_failure_count=0,
    )
    observations_before = store.observations_path.read_bytes()
    heartbeat_before = store.heartbeat_path.read_bytes()
    lifecycle_before = store.lifecycle_path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["run_monitoring_agent.py", "--audit-state"])

    assert main(default_env_file=env_path) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["event"] == "agent_state_audit"
    assert output["observations"]["complete_cycle_count"] == 1
    assert store.observations_path.read_bytes() == observations_before
    assert store.heartbeat_path.read_bytes() == heartbeat_before
    assert store.lifecycle_path.read_bytes() == lifecycle_before


def test_state_audit_fails_closed_without_leaking_invalid_record(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    env_path = project_dir / ".env"
    _write_runtime_env(env_path, state_dir=str(state_dir))
    settings = RuntimeSettings.load(env_path)
    (state_dir / "observations.jsonl").write_text(
        "private-invalid-record-marker\n", encoding="utf-8"
    )

    with pytest.raises(StateAuditError) as exc_info:
        build_state_audit(settings)

    assert "invalid JSON" in str(exc_info.value)
    assert "private-invalid-record-marker" not in str(exc_info.value)


def test_next_cycle_delay_uses_start_to_start_interval_and_bounded_jitter():
    delay = calculate_next_cycle_delay(
        poll_interval_seconds=60,
        cycle_elapsed_seconds=12,
        poll_jitter_seconds=5,
        uniform_fn=lambda lower, upper: (lower + upper) / 2,
    )

    assert delay == 50.5


def test_agent_config_loads_strict_test_profile(tmp_path):
    config_path = tmp_path / "agent.json"
    config_path.write_text(
        json.dumps(
            {
                "config_version": 2,
                "mode": "test",
                "instance_id": "center-test",
                "base_url": "http://127.0.0.1:8020",
                "state_dir": "state",
                "timeout_seconds": 2,
                "max_attempts": 3,
                "retry_backoff_seconds": 0.5,
                "poll_interval_seconds": 30,
                "poll_jitter_seconds": 5,
                "endpoint_keys": ["live", "ready", "system_scheduler"],
            }
        ),
        encoding="utf-8",
    )

    config = AgentConfig.load(config_path)

    assert config.instance_id == "center-test"
    assert config.state_dir == (tmp_path / "state").resolve()
    assert config.endpoint_keys == ("live", "ready", "system_scheduler")
    assert config.max_attempts == 3
    assert config.retry_backoff_seconds == 0.5
    assert config.poll_jitter_seconds == 5.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "production"),
        ("base_url", "http://192.0.2.10:8020"),
        ("endpoint_keys", ["live", "manual_run"]),
        ("poll_interval_seconds", 0),
        ("max_attempts", 6),
        ("retry_backoff_seconds", -1),
        ("poll_jitter_seconds", 31),
    ],
)
def test_agent_config_rejects_unsafe_values(tmp_path, field, value):
    payload = {
        "config_version": 2,
        "mode": "test",
        "instance_id": "center-test",
        "base_url": "http://127.0.0.1:8020",
        "state_dir": "state",
        "timeout_seconds": 2,
        "max_attempts": 3,
        "retry_backoff_seconds": 0.5,
        "poll_interval_seconds": 30,
        "poll_jitter_seconds": 5,
        "endpoint_keys": ["live"],
    }
    payload[field] = value
    config_path = tmp_path / "agent.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        AgentConfig.load(config_path)


def test_agent_config_rejects_unexpected_secret_field(tmp_path):
    payload = {
        "config_version": 2,
        "mode": "test",
        "instance_id": "center-test",
        "base_url": "http://127.0.0.1:8020",
        "state_dir": "state",
        "timeout_seconds": 2,
        "max_attempts": 3,
        "retry_backoff_seconds": 0.5,
        "poll_interval_seconds": 30,
        "poll_jitter_seconds": 5,
        "endpoint_keys": ["live"],
        "token": "must-not-be-accepted",
    }
    config_path = tmp_path / "agent.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected"):
        AgentConfig.load(config_path)


def test_runtime_settings_load_single_strict_env_contract(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    env_path = project_dir / ".env"
    _write_runtime_env(env_path)

    settings = RuntimeSettings.load(env_path)

    assert settings.env_contract_version == 2
    assert settings.mode == "test"
    assert settings.instance_id == "center-test"
    assert settings.state_dir == (project_dir / "../state").resolve()
    assert settings.max_attempts == 3
    assert settings.endpoint_set_version == 3
    assert settings.observation_contract_version == 4
    assert settings.endpoint_keys == (
        "live",
        "ready",
        "system_scheduler",
        "scheduler_detail",
        "system_runtime",
        "system_database",
        "system_proxy",
        "system_smartfuelpass",
        "external_web",
    )
    assert settings.safe_summary() == {
        "endpoint_count": 9,
        "env_contract_version": 2,
        "mode": "test",
    }
    assert "t" * 48 not in repr(settings)


def test_runtime_settings_loads_strict_legacy_upgrade_contract(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    env_path = project_dir / ".env"
    _write_runtime_env(env_path, env_version=1)

    settings = RuntimeSettings.load(env_path)

    assert settings.env_contract_version == 1
    assert settings.external_web_url is None
    assert settings.endpoint_keys == (
        "live",
        "ready",
        "system_scheduler",
        "system_runtime",
    )
    assert settings.endpoint_set_version == 2
    assert settings.observation_contract_version == 3
    assert settings.safe_summary() == {
        "endpoint_count": 4,
        "env_contract_version": 1,
        "mode": "test",
    }


def test_runtime_settings_rejects_v2_only_key_in_legacy_contract(tmp_path):
    env_path = tmp_path / ".env"
    _write_runtime_env(
        env_path,
        env_version=1,
        extra={"MONITORING_AGENT_EXTERNAL_WEB_URL": "https://monitoring.invalid/"},
    )

    with pytest.raises(ValueError, match="unexpected"):
        RuntimeSettings.load(env_path)


def test_runtime_settings_accepts_powershell_utf8_bom(tmp_path):
    env_path = tmp_path / ".env"
    _write_runtime_env(env_path)
    content = env_path.read_text(encoding="utf-8")
    env_path.write_text(content, encoding="utf-8-sig")

    assert RuntimeSettings.load(env_path).env_contract_version == 2


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"UNEXPECTED": "value"}, "unexpected"),
        ({"MONITORING_AGENT_MODE": "production"}, "test mode"),
        ({"MONITORING_AGENT_BASE_URL": "https://example.invalid:9443"}, "placeholder"),
        (
            {"MONITORING_AGENT_EXTERNAL_WEB_URL": "https://example.invalid/"},
            "placeholder",
        ),
        (
            {"MONITORING_AGENT_EXTERNAL_WEB_URL": "http://192.0.2.10/"},
            "loopback",
        ),
        ({"MONITORING_AGENT_BEARER_TOKEN": "change-me"}, "invalid format"),
        ({"MONITORING_AGENT_ENDPOINT_KEYS": "live,manual_run"}, "unapproved"),
        ({"MONITORING_AGENT_MAX_ATTEMPTS": "6"}, "between 1 and 5"),
        ({"MONITORING_AGENT_STATE_DIR": ".state"}, "outside"),
    ],
)
def test_runtime_settings_rejects_unsafe_or_placeholder_values(
    tmp_path,
    extra,
    message,
):
    env_path = tmp_path / ".env"
    _write_runtime_env(env_path, extra=extra)

    with pytest.raises(ValueError, match=message):
        RuntimeSettings.load(env_path)


def test_runtime_settings_rejects_duplicate_keys_without_echoing_secret(tmp_path):
    env_path = tmp_path / ".env"
    token = "private-value-" + "x" * 40
    _write_runtime_env(env_path, token=token)
    with env_path.open("a", encoding="utf-8") as handle:
        handle.write(f"MONITORING_AGENT_BEARER_TOKEN={token}\n")

    with pytest.raises(ValueError) as captured:
        RuntimeSettings.load(env_path)

    assert token not in str(captured.value)


def test_env_contract_has_only_monitoring_agent_keys():
    assert ENV_KEYS
    assert all(key.startswith("MONITORING_AGENT_") for key in ENV_KEYS)
    assert "MONITORING_AGENT_BEARER_TOKEN" in ENV_KEYS


def test_runner_check_config_uses_default_env_without_secret_output(
    tmp_path,
    monkeypatch,
    capsys,
):
    env_path = tmp_path / ".env"
    token = "private-value-" + "x" * 40
    _write_runtime_env(env_path, token=token)
    monkeypatch.setattr(sys, "argv", ["run_monitoring_agent.py", "--check-config"])

    assert main(default_env_file=env_path) == 0

    output = capsys.readouterr().out
    assert json.loads(output) == {
        "endpoint_count": 9,
        "env_contract_version": 2,
        "event": "configuration_valid",
        "mode": "test",
    }
    assert token not in output
    assert str(env_path) not in output


def test_runner_once_uses_env_for_authenticated_foreground_cycle(
    tmp_path,
    monkeypatch,
    capsys,
):
    server, thread = _start_server()
    try:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        env_path = project_dir / ".env"
        state_dir = tmp_path / "state"
        _write_runtime_env(
            env_path,
            base_url=f"http://127.0.0.1:{server.server_port}",
            state_dir=str(state_dir),
        )
        monkeypatch.setattr(sys, "argv", ["run_monitoring_agent.py", "--once"])

        assert main(default_env_file=env_path) == 0
    finally:
        _stop_server(server, thread)

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "event": "observation_cycle",
        "observation_count": 9,
        "transport_statuses": ["success"],
    }
    heartbeat = json.loads(
        (state_dir / "observer_heartbeat.json").read_text(encoding="utf-8")
    )
    assert heartbeat["status"] == "healthy"
    observations = [
        json.loads(line)
        for line in (state_dir / "observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    lifecycle = [
        json.loads(line)
        for line in (state_dir / "observer_lifecycle.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [record["event"] for record in lifecycle] == [
        "process_started",
        "process_stopped",
    ]
    assert lifecycle[0]["reason"] == "observer_started"
    assert lifecycle[1]["reason"] == "once_completed"
    assert lifecycle[0]["run_id"] == lifecycle[1]["run_id"]
    assert {item["run_id"] for item in observations} == {lifecycle[0]["run_id"]}
    assert heartbeat["run_id"] == lifecycle[0]["run_id"]


def test_runner_once_supports_legacy_env_as_safe_upgrade_bridge(
    tmp_path,
    monkeypatch,
    capsys,
):
    server, thread = _start_server()
    try:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        env_path = project_dir / ".env"
        state_dir = tmp_path / "state"
        _write_runtime_env(
            env_path,
            env_version=1,
            base_url=f"http://127.0.0.1:{server.server_port}",
            state_dir=str(state_dir),
        )
        monkeypatch.setattr(sys, "argv", ["run_monitoring_agent.py", "--once"])

        assert main(default_env_file=env_path) == 0
    finally:
        _stop_server(server, thread)

    assert json.loads(capsys.readouterr().out) == {
        "event": "observation_cycle",
        "observation_count": 4,
        "transport_statuses": ["success"],
    }
    observations = [
        json.loads(line)
        for line in (state_dir / "observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [item["endpoint_key"] for item in observations] == [
        "live",
        "ready",
        "system_scheduler",
        "system_runtime",
    ]
    assert {item["contract_version"] for item in observations} == {3}
    assert {item["endpoint_set_version"] for item in observations} == {2}
    assert all("clock_skew_seconds" not in item for item in observations)
    heartbeat = json.loads(
        (state_dir / "observer_heartbeat.json").read_text(encoding="utf-8")
    )
    assert heartbeat["status"] == "healthy"
    assert heartbeat["observation_count"] == 4
    assert heartbeat["transport_failure_count"] == 0


def test_runner_rejects_concurrent_state_writer_before_runtime_writes(
    tmp_path,
    monkeypatch,
):
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    state_dir = tmp_path / "state"
    holder = context.Process(
        target=_hold_state_writer_lock,
        args=(str(state_dir), ready, release),
    )
    holder.start()
    try:
        assert ready.wait(10)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        env_path = project_dir / ".env"
        token = "private-value-" + "x" * 40
        _write_runtime_env(env_path, state_dir=str(state_dir), token=token)
        monkeypatch.setattr(sys, "argv", ["run_monitoring_agent.py", "--once"])
        monkeypatch.setattr(
            "monitoring_agent.__main__.run_observation_cycle",
            lambda **kwargs: pytest.fail("rejected writer reached network cycle"),
        )

        with pytest.raises(SystemExit) as exc_info:
            main(default_env_file=env_path)

        message = str(exc_info.value)
        assert message == "agent startup error: state writer lock is unavailable"
        assert token not in message
        assert str(state_dir) not in message
        assert not (state_dir / "observations.jsonl").exists()
        assert not (state_dir / "observer_heartbeat.json").exists()
        assert not (state_dir / "observer_lifecycle.jsonl").exists()
    finally:
        release.set()
        holder.join(10)
        if holder.is_alive():
            holder.terminate()
            holder.join(10)
    assert holder.exitcode == 0


def test_writer_lock_is_released_by_os_after_process_termination(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    state_dir = tmp_path / "state"
    holder = context.Process(
        target=_hold_state_writer_lock,
        args=(str(state_dir), ready, release),
    )
    holder.start()
    try:
        assert ready.wait(10)
        holder.terminate()
        holder.join(10)
        assert not holder.is_alive()
        with ObserverStore(state_dir).writer_lock():
            pass
    finally:
        if holder.is_alive():
            holder.terminate()
            holder.join(10)


def test_two_clean_once_runs_produce_auditable_process_transition(
    tmp_path,
    monkeypatch,
    capsys,
):
    server, thread = _start_server()
    try:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        env_path = project_dir / ".env"
        state_dir = tmp_path / "state"
        _write_runtime_env(
            env_path,
            base_url=f"http://127.0.0.1:{server.server_port}",
            state_dir=str(state_dir),
        )
        monkeypatch.setattr(sys, "argv", ["run_monitoring_agent.py", "--once"])

        assert main(default_env_file=env_path) == 0
        assert main(default_env_file=env_path) == 0
    finally:
        _stop_server(server, thread)

    assert len(capsys.readouterr().out.splitlines()) == 2
    audit = build_state_audit(RuntimeSettings.load(env_path))
    assert audit["observations"]["complete_cycle_count"] == 2
    assert audit["observations"]["process_run_count"] == 2
    assert audit["cycles"]["cycle_sequence_valid"] is True
    assert audit["cycles"]["process_run_transition_count"] == 1
    assert audit["timing"]["interval_count"] == 0
    assert audit["timing"]["early_start_count"] == 0
    assert audit["timing"]["late_beyond_jitter_count"] == 0
    assert audit["timing"]["cross_run_interval_count"] == 1
    assert (
        audit["timing"]["longest_cross_run_interval"]["classification"]
        == "process_run_transition"
    )
    assert audit["lifecycle"]["event_count"] == 4
    assert audit["lifecycle"]["restart_detected"] is True
    assert audit["lifecycle"]["clean_restart_count"] == 1
    assert audit["lifecycle"]["start_while_prior_run_open_count"] == 0
    assert audit["lifecycle"]["concurrent_start_count"] == 0
    assert audit["lifecycle"]["unclean_restart_count"] == 0
    assert audit["lifecycle"]["single_writer_history_valid"] is True
    assert audit["lifecycle"]["unclosed_run_count"] == 0
    assert audit["lifecycle"]["current_run_has_stop"] is True
    assert audit["lifecycle"]["current_run_is_unclosed"] is False
    assert audit["lifecycle"]["stop_reason_counts"] == {"once_completed": 2}
    assert audit["lifecycle"]["history_valid"] is True


def test_bundle_builder_uses_exact_allowlist_and_verified_manifest(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    first_output = tmp_path / "first.zip"
    second_output = tmp_path / "second.zip"

    first = build_bundle(
        repository_root=repository_root,
        output_path=first_output,
        bundle_version="0.7.0-test",
        created_date=date(2026, 8, 5),
    )
    second = build_bundle(
        repository_root=repository_root,
        output_path=second_output,
        bundle_version="0.7.0-test",
        created_date=date(2026, 8, 5),
    )

    assert first["sha256"] == second["sha256"]
    with zipfile.ZipFile(first_output) as archive:
        assert set(archive.namelist()) == {
            *BUNDLE_FILES,
            "manifest.json",
            "manifest.sha256",
        }
        manifest_content = archive.read("manifest.json")
        manifest = json.loads(manifest_content)
        manifest_digest = archive.read("manifest.sha256").decode("ascii")
        expected_digest = hashlib.sha256(manifest_content).hexdigest()
        assert manifest_digest == f"{expected_digest}  manifest.json\n"
        assert manifest["bundle_version"] == "0.7.0-test"
        assert [entry["path"] for entry in manifest["files"]] == list(BUNDLE_FILES)
        assert ".env" not in archive.namelist()
        assert ".env.example" in archive.namelist()
        assert ".gitignore" in archive.namelist()
        assert ".venv/" in archive.read(".gitignore").decode("utf-8").splitlines()
        assert "run_monitoring_agent.py" in archive.namelist()
        assert "register_monitoring_agent_task.ps1" in archive.namelist()
        assert "monitoring_agent/audit.py" in archive.namelist()
        assert "monitoring_agent/config.py" not in archive.namelist()
        assert "monitoring_agent/credentials.py" not in archive.namelist()
        for entry in manifest["files"]:
            content = archive.read(entry["path"])
            assert entry["size"] == len(content)
            assert entry["sha256"] == hashlib.sha256(content).hexdigest()


def test_scheduled_task_registration_script_is_gated_and_contains_no_secret():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "monitoring_agent"
        / "register_monitoring_agent_task.ps1"
    )
    content = script_path.read_text(encoding="utf-8")
    lowered = content.lower()

    assert "SupportsShouldProcess = $true" in content
    assert 'ConfirmImpact = "High"' in content
    assert "New-ScheduledTaskTrigger -AtStartup" in content
    assert '-UserId "SYSTEM"' in content
    assert "-LogonType ServiceAccount" in content
    assert "-WorkingDirectory $resolvedProjectRoot" in content
    assert "-StartWhenAvailable" in content
    assert "-MultipleInstances IgnoreNew" in content
    assert "-RestartCount 999" in content
    assert "Register-ScheduledTask" in content
    assert "-Force" in content
    assert ".venv\\Scripts\\python.exe" in content
    assert "run_monitoring_agent.py" in content
    assert "Unregister-ScheduledTask" not in content
    assert "bearer" not in lowered
    assert "token" not in lowered
    assert "password" not in lowered
