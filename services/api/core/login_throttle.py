from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import ipaddress
import math
import threading
import time
from typing import Callable

from starlette.requests import Request


@dataclass(frozen=True)
class LoginThrottlePolicy:
    window_seconds: float = 15 * 60
    account_failure_limit: int = 5
    account_lock_seconds: tuple[float, ...] = (30, 120, 300, 900)
    ip_failure_limit: int = 20
    ip_lock_seconds: float = 15 * 60
    max_account_states: int = 10_000
    max_ip_states: int = 10_000


@dataclass
class _AttemptState:
    failures: deque[float] = field(default_factory=deque)
    blocked_until: float = 0.0
    last_seen: float = 0.0


@dataclass(frozen=True)
class LoginFailureStatus:
    retry_after: int
    account_failure_count: int
    ip_failure_count: int
    account_lock_started: bool
    ip_lock_started: bool


class LoginAttemptLimiter:
    def __init__(
        self,
        *,
        policy: LoginThrottlePolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy = policy or LoginThrottlePolicy()
        self._clock = clock
        self._account_states: dict[str, _AttemptState] = {}
        self._ip_states: dict[str, _AttemptState] = {}
        self._lock = threading.Lock()

    @property
    def policy(self) -> LoginThrottlePolicy:
        return self._policy

    @staticmethod
    def _account_key(username: str) -> str:
        return username.strip().casefold() or "<empty>"

    @staticmethod
    def _ip_key(client_ip: str) -> str:
        return client_ip.strip().casefold() or "<unknown>"

    def retry_after(self, username: str, client_ip: str) -> int:
        now = self._clock()
        with self._lock:
            account_state = self._get_existing_state(
                self._account_states,
                self._account_key(username),
                now,
            )
            ip_state = self._get_existing_state(
                self._ip_states,
                self._ip_key(client_ip),
                now,
            )
            blocked_until = max(
                account_state.blocked_until if account_state else 0.0,
                ip_state.blocked_until if ip_state else 0.0,
            )
            return max(0, math.ceil(blocked_until - now))

    def register_failure(self, username: str, client_ip: str) -> int:
        return self.register_failure_status(username, client_ip).retry_after

    def register_failure_status(
        self,
        username: str,
        client_ip: str,
    ) -> LoginFailureStatus:
        now = self._clock()
        with self._lock:
            account_state = self._get_or_create_state(
                self._account_states,
                self._account_key(username),
                now,
                self._policy.max_account_states,
            )
            ip_state = self._get_or_create_state(
                self._ip_states,
                self._ip_key(client_ip),
                now,
                self._policy.max_ip_states,
            )

            account_state.failures.append(now)
            account_state.last_seen = now
            ip_state.failures.append(now)
            ip_state.last_seen = now

            previous_account_blocked_until = account_state.blocked_until
            previous_ip_blocked_until = ip_state.blocked_until
            account_failure_count = len(account_state.failures)
            if account_failure_count >= self._policy.account_failure_limit:
                lock_index = min(
                    account_failure_count - self._policy.account_failure_limit,
                    len(self._policy.account_lock_seconds) - 1,
                )
                account_state.blocked_until = max(
                    account_state.blocked_until,
                    now + self._policy.account_lock_seconds[lock_index],
                )

            if len(ip_state.failures) >= self._policy.ip_failure_limit:
                ip_state.blocked_until = max(
                    ip_state.blocked_until,
                    now + self._policy.ip_lock_seconds,
                )

            blocked_until = max(account_state.blocked_until, ip_state.blocked_until)
            return LoginFailureStatus(
                retry_after=max(0, math.ceil(blocked_until - now)),
                account_failure_count=account_failure_count,
                ip_failure_count=len(ip_state.failures),
                account_lock_started=(
                    account_state.blocked_until > now
                    and account_state.blocked_until > previous_account_blocked_until
                ),
                ip_lock_started=(
                    ip_state.blocked_until > now
                    and ip_state.blocked_until > previous_ip_blocked_until
                ),
            )

    def register_success(self, username: str) -> None:
        with self._lock:
            self._account_states.pop(self._account_key(username), None)

    def clear(self) -> None:
        with self._lock:
            self._account_states.clear()
            self._ip_states.clear()

    def _get_existing_state(
        self,
        states: dict[str, _AttemptState],
        key: str,
        now: float,
    ) -> _AttemptState | None:
        state = states.get(key)
        if state is None:
            return None
        self._prune_state(state, now)
        if not state.failures and state.blocked_until <= now:
            states.pop(key, None)
            return None
        state.last_seen = now
        return state

    def _get_or_create_state(
        self,
        states: dict[str, _AttemptState],
        key: str,
        now: float,
        max_states: int,
    ) -> _AttemptState:
        state = self._get_existing_state(states, key, now)
        if state is not None:
            return state

        if len(states) >= max_states:
            oldest_key = min(states, key=lambda item: states[item].last_seen)
            states.pop(oldest_key, None)

        state = _AttemptState(last_seen=now)
        states[key] = state
        return state

    def _prune_state(self, state: _AttemptState, now: float) -> None:
        cutoff = now - self._policy.window_seconds
        while state.failures and state.failures[0] <= cutoff:
            state.failures.popleft()


login_attempt_limiter = LoginAttemptLimiter()
INTERNAL_CLIENT_IP_HEADER = "x-dashboard-client-ip"
TRUSTED_INTERNAL_CLIENTS = frozenset({"127.0.0.1", "::1"})


def get_login_client_ip(request: Request) -> str:
    if request.client is None:
        return "<unknown>"

    request_client = request.client.host
    if request_client not in TRUSTED_INTERNAL_CLIENTS:
        return request_client

    forwarded_client = request.headers.get(INTERNAL_CLIENT_IP_HEADER, "").strip()
    if not forwarded_client:
        return request_client

    try:
        return ipaddress.ip_address(forwarded_client).compressed
    except ValueError:
        return request_client
