from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import socket
import sys
from threading import Thread
import zipfile

import pytest

from monitoring_agent.__main__ import calculate_next_cycle_delay, main
from monitoring_agent.client import APPROVED_ENDPOINTS, HealthClient, validate_base_url
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
    base_url: str = "http://127.0.0.1:8020",
    state_dir: str = "../state",
    token: str = "t" * 48,
    extra: dict[str, str] | None = None,
) -> None:
    values = {
        "MONITORING_AGENT_ENV_VERSION": "1",
        "MONITORING_AGENT_MODE": "test",
        "MONITORING_AGENT_INSTANCE_ID": "center-test",
        "MONITORING_AGENT_BASE_URL": base_url,
        "MONITORING_AGENT_STATE_DIR": state_dir,
        "MONITORING_AGENT_TIMEOUT_SECONDS": "2",
        "MONITORING_AGENT_MAX_ATTEMPTS": "3",
        "MONITORING_AGENT_RETRY_BACKOFF_SECONDS": "0.5",
        "MONITORING_AGENT_POLL_INTERVAL_SECONDS": "30",
        "MONITORING_AGENT_POLL_JITTER_SECONDS": "5",
        "MONITORING_AGENT_ENDPOINT_KEYS": "live,ready,system_scheduler",
        "MONITORING_AGENT_BEARER_TOKEN": token,
    }
    values.update(extra or {})
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
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


def test_approved_endpoints_exclude_logs_and_mutations():
    assert set(APPROVED_ENDPOINTS) == {"live", "ready", "system_scheduler"}
    assert all("log" not in spec.path for spec in APPROVED_ENDPOINTS.values())
    assert all("/run" not in spec.path for spec in APPROVED_ENDPOINTS.values())


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


def test_remote_https_client_requires_credential():
    with pytest.raises(ValueError, match="requires a bearer credential"):
        HealthClient(
            base_url="https://observer-target.example.ts.net:9443",
            observer_instance_id="test-observer",
        )


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
        )
        observation = client.poll("system_scheduler")
    finally:
        _stop_server(server, thread)

    assert observation.transport_status == "success"
    assert observation.http_status == 200
    assert observation.payload["scheduler_running"] is True
    assert observation.payload["jobs"][0]["job_id"] == "quarter_hour_job"
    assert "label" not in observation.payload["jobs"][0]
    assert "detail" not in observation.payload["jobs"][0]


def test_readiness_503_is_application_state_not_transport_failure():
    server, thread = _start_server(scenario="readiness_unavailable")
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
        )
        observation = client.poll("ready")
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
        )
        observation = client.poll("system_scheduler")
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
            max_attempts=3,
            retry_backoff_seconds=0.25,
            sleep_fn=delays.append,
        )
        observation = client.poll("live")
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
    )
    with pytest.raises(ValueError):
        client.poll("scheduler_log")


def test_observation_cycle_writes_only_agent_owned_state(tmp_path):
    server, thread = _start_server()
    try:
        client = HealthClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
            observer_instance_id="test-observer",
        )
        store = ObserverStore(tmp_path / "state")
        observations = run_observation_cycle(
            client=client,
            store=store,
            observer_instance_id="test-observer",
        )
    finally:
        _stop_server(server, thread)

    assert len(observations) == 3
    lines = store.observations_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    persisted = [json.loads(line) for line in lines]
    assert {row["endpoint_key"] for row in persisted} == set(APPROVED_ENDPOINTS)
    assert all("authorization" not in line.lower() for line in lines)
    assert all("synthetic test data" not in line.lower() for line in lines)
    heartbeat = json.loads(store.heartbeat_path.read_text(encoding="utf-8"))
    assert heartbeat["observer_instance_id"] == "test-observer"
    assert heartbeat["status"] == "healthy"
    assert heartbeat["cycle_finished_at"] is not None
    assert heartbeat["observation_count"] == 3
    assert heartbeat["transport_failure_count"] == 0


def test_connection_failure_is_sanitized():
    temporary_socket = socket.socket()
    temporary_socket.bind(("127.0.0.1", 0))
    unused_port = temporary_socket.getsockname()[1]
    temporary_socket.close()
    client = HealthClient(
        base_url=f"http://127.0.0.1:{unused_port}",
        observer_instance_id="test-observer",
        timeout_seconds=1.0,
        retry_backoff_seconds=0,
    )
    observation = client.poll("live")

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
        timeout_seconds=0.1,
        max_attempts=3,
        retry_backoff_seconds=0.25,
        sleep_fn=delays.append,
    )

    observation = client.poll("live")

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
        timeout_seconds=0.1,
        max_attempts=1,
    )
    store = ObserverStore(tmp_path / "state")

    run_observation_cycle(
        client=client,
        store=store,
        observer_instance_id="test-observer",
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
        )
        store = ObserverStore(tmp_path / "state")
        observations = run_observation_cycle(
            client=client,
            store=store,
            observer_instance_id="test-observer",
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

    assert settings.env_contract_version == 1
    assert settings.mode == "test"
    assert settings.instance_id == "center-test"
    assert settings.state_dir == (project_dir / "../state").resolve()
    assert settings.max_attempts == 3
    assert settings.endpoint_keys == ("live", "ready", "system_scheduler")
    assert settings.safe_summary() == {
        "endpoint_count": 3,
        "env_contract_version": 1,
        "mode": "test",
    }
    assert "t" * 48 not in repr(settings)


def test_runtime_settings_accepts_powershell_utf8_bom(tmp_path):
    env_path = tmp_path / ".env"
    _write_runtime_env(env_path)
    content = env_path.read_text(encoding="utf-8")
    env_path.write_text(content, encoding="utf-8-sig")

    assert RuntimeSettings.load(env_path).env_contract_version == 1


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"UNEXPECTED": "value"}, "unexpected"),
        ({"MONITORING_AGENT_MODE": "production"}, "test mode"),
        ({"MONITORING_AGENT_BASE_URL": "https://example.invalid:9443"}, "placeholder"),
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
        "endpoint_count": 3,
        "env_contract_version": 1,
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
        "observation_count": 3,
        "transport_statuses": ["success"],
    }
    heartbeat = json.loads(
        (state_dir / "observer_heartbeat.json").read_text(encoding="utf-8")
    )
    assert heartbeat["status"] == "healthy"


def test_bundle_builder_uses_exact_allowlist_and_verified_manifest(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    first_output = tmp_path / "first.zip"
    second_output = tmp_path / "second.zip"

    first = build_bundle(
        repository_root=repository_root,
        output_path=first_output,
        bundle_version="0.3.0-test",
        created_date=date(2026, 8, 4),
    )
    second = build_bundle(
        repository_root=repository_root,
        output_path=second_output,
        bundle_version="0.3.0-test",
        created_date=date(2026, 8, 4),
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
        assert manifest["bundle_version"] == "0.3.0-test"
        assert [entry["path"] for entry in manifest["files"]] == list(BUNDLE_FILES)
        assert ".env" not in archive.namelist()
        assert ".env.example" in archive.namelist()
        assert ".gitignore" in archive.namelist()
        assert "run_monitoring_agent.py" in archive.namelist()
        assert "monitoring_agent/config.py" not in archive.namelist()
        assert "monitoring_agent/credentials.py" not in archive.namelist()
        for entry in manifest["files"]:
            content = archive.read(entry["path"])
            assert entry["size"] == len(content)
            assert entry["sha256"] == hashlib.sha256(content).hexdigest()
