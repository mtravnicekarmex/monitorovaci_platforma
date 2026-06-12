from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
import ipaddress
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
from pathlib import Path
import threading
import time
from typing import Callable

from decouple import config

from services.api.core.login_throttle import LoginFailureStatus, LoginThrottlePolicy


_FALLBACK_LOGGER = logging.getLogger(__name__)


def normalize_auth_identifier(value: str | None) -> str:
    return (value or "").strip().casefold() or "<empty>"


def normalize_client_ip(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return "<unknown>"
    try:
        return ipaddress.ip_address(cleaned).compressed
    except ValueError:
        return "<unknown>"


def _default_audit_log_path() -> Path:
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        return Path(program_data) / "monitorovaci_platforma" / "logs" / "auth_audit.jsonl"
    return Path("services") / "api" / "logs" / "auth_audit.jsonl"


def _configured_audit_log_path() -> Path:
    configured = str(config("AUTH_AUDIT_LOG_PATH", default="")).strip()
    return Path(configured) if configured else _default_audit_log_path()


class AuthAuditRecorder:
    def __init__(
        self,
        *,
        log_path: Path | None = None,
        retention_days: int | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.log_path = log_path or _configured_audit_log_path()
        self.retention_days = (
            int(retention_days)
            if retention_days is not None
            else config("AUTH_AUDIT_RETENTION_DAYS", default=90, cast=int)
        )
        self._now = now or (lambda: datetime.now(UTC))
        self._logger: logging.Logger | None = None
        self._lock = threading.Lock()

    def record(
        self,
        *,
        event_type: str,
        result: str,
        reason: str,
        username: str | None = None,
        actor_username: str | None = None,
        target_username: str | None = None,
        source_ip: str | None = None,
        severity: str = "info",
        details: dict[str, object] | None = None,
    ) -> None:
        payload = {
            "timestamp": self._now().astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "event_type": event_type,
            "severity": severity,
            "result": result,
            "reason": reason,
            "username": normalize_auth_identifier(username) if username is not None else None,
            "actor_username": (
                normalize_auth_identifier(actor_username)
                if actor_username is not None
                else None
            ),
            "target_username": (
                normalize_auth_identifier(target_username)
                if target_username is not None
                else None
            ),
            "source_ip": normalize_client_ip(source_ip),
            "details": details or {},
        }
        try:
            self._get_logger().info(
                json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            )
        except Exception:
            _FALLBACK_LOGGER.exception(
                "Authentication audit event could not be written: event_type=%s",
                event_type,
            )

    def _get_logger(self) -> logging.Logger:
        if self._logger is not None:
            return self._logger

        with self._lock:
            if self._logger is not None:
                return self._logger

            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.touch(mode=0o600, exist_ok=True)
            logger = logging.getLogger(f"monitoring.auth_audit.{id(self)}")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            handler = TimedRotatingFileHandler(
                self.log_path,
                when="midnight",
                backupCount=max(1, int(self.retention_days)),
                encoding="utf-8",
                utc=True,
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            self._logger = logger
            return logger


@dataclass(frozen=True)
class AuthAlertPolicy:
    admin_failure_limit: int = 3
    window_seconds: float = 15 * 60


class AuthAlertMonitor:
    def __init__(
        self,
        *,
        policy: AuthAlertPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy or AuthAlertPolicy(
            admin_failure_limit=config(
                "AUTH_ADMIN_FAILURE_ALERT_LIMIT",
                default=3,
                cast=int,
            ),
            window_seconds=config(
                "AUTH_SECURITY_ALERT_WINDOW_SECONDS",
                default=15 * 60,
                cast=float,
            ),
        )
        self._clock = clock
        self._admin_failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def evaluate_failure(
        self,
        *,
        username: str,
        is_admin_account: bool,
        failure_status: LoginFailureStatus,
    ) -> tuple[str, ...]:
        alerts: list[str] = []
        if failure_status.account_lock_started:
            alerts.append("account_brute_force")
        if failure_status.ip_lock_started:
            alerts.append("ip_password_spray")
        if not is_admin_account:
            return tuple(alerts)

        now = self._clock()
        key = normalize_auth_identifier(username)
        with self._lock:
            failures = self._admin_failures[key]
            cutoff = now - self.policy.window_seconds
            while failures and failures[0] <= cutoff:
                failures.popleft()
            failures.append(now)
            if len(failures) == self.policy.admin_failure_limit:
                alerts.append("admin_account_failures")
        return tuple(alerts)

    def register_success(self, username: str) -> None:
        with self._lock:
            self._admin_failures.pop(normalize_auth_identifier(username), None)


class AuthAuditService:
    def __init__(
        self,
        *,
        recorder: AuthAuditRecorder | None = None,
        alert_monitor: AuthAlertMonitor | None = None,
        throttle_policy: LoginThrottlePolicy | None = None,
    ) -> None:
        self.recorder = recorder or AuthAuditRecorder()
        self.alert_monitor = alert_monitor or AuthAlertMonitor()
        self.throttle_policy = throttle_policy or LoginThrottlePolicy()

    def record_login_success(
        self,
        *,
        username: str,
        source_ip: str,
        is_admin: bool,
    ) -> None:
        self.alert_monitor.register_success(username)
        self.recorder.record(
            event_type="login",
            result="success",
            reason="authenticated",
            username=username,
            source_ip=source_ip,
            details={"is_admin": bool(is_admin)},
        )

    def record_login_failure(
        self,
        *,
        username: str,
        source_ip: str,
        reason: str,
        is_admin_account: bool,
        failure_status: LoginFailureStatus,
    ) -> None:
        details = {
            "is_admin_account": bool(is_admin_account),
            "account_failure_count": failure_status.account_failure_count,
            "ip_failure_count": failure_status.ip_failure_count,
            "retry_after_seconds": failure_status.retry_after,
        }
        self.recorder.record(
            event_type="login",
            result="failure",
            reason=reason,
            username=username,
            source_ip=source_ip,
            details=details,
        )
        for alert_reason in self.alert_monitor.evaluate_failure(
            username=username,
            is_admin_account=is_admin_account,
            failure_status=failure_status,
        ):
            self.recorder.record(
                event_type="security_alert",
                result="triggered",
                reason=alert_reason,
                username=username,
                source_ip=source_ip,
                severity="warning",
                details={
                    **details,
                    "account_failure_limit": self.throttle_policy.account_failure_limit,
                    "ip_failure_limit": self.throttle_policy.ip_failure_limit,
                    "admin_failure_limit": self.alert_monitor.policy.admin_failure_limit,
                    "window_seconds": self.alert_monitor.policy.window_seconds,
                },
            )
            _FALLBACK_LOGGER.warning(
                "Authentication security alert: reason=%s username=%s source_ip=%s",
                alert_reason,
                normalize_auth_identifier(username),
                normalize_client_ip(source_ip),
            )

    def record_login_throttled(
        self,
        *,
        username: str,
        source_ip: str,
        retry_after: int,
    ) -> None:
        self.recorder.record(
            event_type="login",
            result="failure",
            reason="throttled",
            username=username,
            source_ip=source_ip,
            details={"retry_after_seconds": int(retry_after)},
        )

    def record_security_event(
        self,
        *,
        event_type: str,
        result: str,
        reason: str,
        actor_username: str,
        target_username: str | None = None,
        source_ip: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self.recorder.record(
            event_type=event_type,
            result=result,
            reason=reason,
            actor_username=actor_username,
            target_username=target_username,
            source_ip=source_ip,
            details=details,
        )


auth_audit_service = AuthAuditService()
