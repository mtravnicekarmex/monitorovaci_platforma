from __future__ import annotations

import json
import socket
from threading import Thread

import pytest

from monitoring_agent.client import APPROVED_ENDPOINTS, HealthClient, validate_base_url
from monitoring_agent.config import AgentConfig
from monitoring_agent.observer import run_observation_cycle
from monitoring_agent.store import ObserverStore
from monitoring_agent.synthetic_server import create_server


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


def test_connection_failure_is_sanitized():
    temporary_socket = socket.socket()
    temporary_socket.bind(("127.0.0.1", 0))
    unused_port = temporary_socket.getsockname()[1]
    temporary_socket.close()
    client = HealthClient(
        base_url=f"http://127.0.0.1:{unused_port}",
        observer_instance_id="test-observer",
        timeout_seconds=1.0,
    )
    observation = client.poll("live")

    assert observation.transport_status in {"connection_error", "timeout"}
    assert observation.http_status is None
    assert observation.payload == {}


def test_agent_config_loads_strict_test_profile(tmp_path):
    config_path = tmp_path / "agent.json"
    config_path.write_text(
        json.dumps(
            {
                "config_version": 1,
                "mode": "test",
                "instance_id": "center-test",
                "base_url": "http://127.0.0.1:8020",
                "state_dir": "state",
                "timeout_seconds": 2,
                "poll_interval_seconds": 30,
                "endpoint_keys": ["live", "ready", "system_scheduler"],
            }
        ),
        encoding="utf-8",
    )

    config = AgentConfig.load(config_path)

    assert config.instance_id == "center-test"
    assert config.state_dir == (tmp_path / "state").resolve()
    assert config.endpoint_keys == ("live", "ready", "system_scheduler")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "production"),
        ("base_url", "http://192.0.2.10:8020"),
        ("endpoint_keys", ["live", "manual_run"]),
        ("poll_interval_seconds", 0),
    ],
)
def test_agent_config_rejects_unsafe_values(tmp_path, field, value):
    payload = {
        "config_version": 1,
        "mode": "test",
        "instance_id": "center-test",
        "base_url": "http://127.0.0.1:8020",
        "state_dir": "state",
        "timeout_seconds": 2,
        "poll_interval_seconds": 30,
        "endpoint_keys": ["live"],
    }
    payload[field] = value
    config_path = tmp_path / "agent.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        AgentConfig.load(config_path)


def test_agent_config_rejects_unexpected_secret_field(tmp_path):
    payload = {
        "config_version": 1,
        "mode": "test",
        "instance_id": "center-test",
        "base_url": "http://127.0.0.1:8020",
        "state_dir": "state",
        "timeout_seconds": 2,
        "poll_interval_seconds": 30,
        "endpoint_keys": ["live"],
        "token": "must-not-be-accepted",
    }
    config_path = tmp_path / "agent.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected"):
        AgentConfig.load(config_path)
