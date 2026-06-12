from datetime import UTC, datetime
import json

from services.api.core.auth_audit import (
    AuthAlertMonitor,
    AuthAlertPolicy,
    AuthAuditRecorder,
    AuthAuditService,
)
from services.api.core.login_throttle import (
    LoginFailureStatus,
    LoginThrottlePolicy,
)


class _RecorderStub:
    def __init__(self) -> None:
        self.events = []

    def record(self, **kwargs) -> None:
        self.events.append(kwargs)


def _failure_status(
    *,
    account_count: int = 1,
    ip_count: int = 1,
    account_lock_started: bool = False,
    ip_lock_started: bool = False,
) -> LoginFailureStatus:
    return LoginFailureStatus(
        retry_after=30 if account_lock_started or ip_lock_started else 0,
        account_failure_count=account_count,
        ip_failure_count=ip_count,
        account_lock_started=account_lock_started,
        ip_lock_started=ip_lock_started,
    )


def test_recorder_writes_structured_json_without_credentials(tmp_path):
    log_path = tmp_path / "auth_audit.jsonl"
    recorder = AuthAuditRecorder(
        log_path=log_path,
        retention_days=7,
        now=lambda: datetime(2026, 6, 12, 8, 0, tzinfo=UTC),
    )

    recorder.record(
        event_type="login",
        result="failure",
        reason="invalid_password",
        username=" Admin ",
        source_ip="192.0.2.10",
        details={"account_failure_count": 2},
    )

    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["timestamp"] == "2026-06-12T08:00:00Z"
    assert payload["username"] == "admin"
    assert payload["source_ip"] == "192.0.2.10"
    assert payload["reason"] == "invalid_password"
    assert "password" not in payload
    assert "token" not in payload


def test_alert_monitor_emits_admin_threshold_once_per_window():
    now = [0.0]
    monitor = AuthAlertMonitor(
        policy=AuthAlertPolicy(admin_failure_limit=3, window_seconds=60),
        clock=lambda: now[0],
    )
    status = _failure_status()

    assert monitor.evaluate_failure(
        username="Admin",
        is_admin_account=True,
        failure_status=status,
    ) == ()
    assert monitor.evaluate_failure(
        username="admin",
        is_admin_account=True,
        failure_status=status,
    ) == ()
    assert monitor.evaluate_failure(
        username="ADMIN",
        is_admin_account=True,
        failure_status=status,
    ) == ("admin_account_failures",)
    assert monitor.evaluate_failure(
        username="admin",
        is_admin_account=True,
        failure_status=status,
    ) == ()

    now[0] = 61
    assert monitor.evaluate_failure(
        username="admin",
        is_admin_account=True,
        failure_status=status,
    ) == ()


def test_audit_service_emits_brute_force_and_password_spray_alerts():
    recorder = _RecorderStub()
    service = AuthAuditService(
        recorder=recorder,
        alert_monitor=AuthAlertMonitor(
            policy=AuthAlertPolicy(admin_failure_limit=3, window_seconds=60)
        ),
        throttle_policy=LoginThrottlePolicy(
            account_failure_limit=5,
            ip_failure_limit=20,
        ),
    )

    service.record_login_failure(
        username="target",
        source_ip="192.0.2.10",
        reason="invalid_password",
        is_admin_account=False,
        failure_status=_failure_status(
            account_count=5,
            ip_count=20,
            account_lock_started=True,
            ip_lock_started=True,
        ),
    )

    assert [event["event_type"] for event in recorder.events] == [
        "login",
        "security_alert",
        "security_alert",
    ]
    assert [event["reason"] for event in recorder.events[1:]] == [
        "account_brute_force",
        "ip_password_spray",
    ]
    assert all(event["severity"] == "warning" for event in recorder.events[1:])
