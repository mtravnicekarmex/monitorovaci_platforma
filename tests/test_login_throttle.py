from starlette.requests import Request

from services.api.core.login_throttle import (
    LoginAttemptLimiter,
    LoginThrottlePolicy,
    get_login_client_ip,
)


class MutableClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_account_failures_use_increasing_temporary_lockouts():
    clock = MutableClock()
    limiter = LoginAttemptLimiter(
        policy=LoginThrottlePolicy(
            window_seconds=60,
            account_failure_limit=3,
            account_lock_seconds=(10, 20),
            ip_failure_limit=100,
            ip_lock_seconds=60,
        ),
        clock=clock,
    )

    assert limiter.register_failure(" Admin ", "192.0.2.10") == 0
    assert limiter.register_failure("admin", "192.0.2.10") == 0
    assert limiter.register_failure("ADMIN", "192.0.2.10") == 10
    assert limiter.retry_after("admin", "192.0.2.10") == 10

    clock.advance(11)
    assert limiter.register_failure("admin", "192.0.2.10") == 20
    assert limiter.retry_after("admin", "192.0.2.10") == 20


def test_ip_limit_applies_across_different_accounts():
    clock = MutableClock()
    limiter = LoginAttemptLimiter(
        policy=LoginThrottlePolicy(
            window_seconds=60,
            account_failure_limit=100,
            account_lock_seconds=(10,),
            ip_failure_limit=3,
            ip_lock_seconds=30,
        ),
        clock=clock,
    )

    assert limiter.register_failure("user-1", "192.0.2.10") == 0
    assert limiter.register_failure("user-2", "192.0.2.10") == 0
    assert limiter.register_failure("user-3", "192.0.2.10") == 30
    assert limiter.retry_after("unrelated-user", "192.0.2.10") == 30
    assert limiter.retry_after("unrelated-user", "192.0.2.11") == 0


def test_success_clears_account_lock_but_not_shared_ip_history():
    clock = MutableClock()
    limiter = LoginAttemptLimiter(
        policy=LoginThrottlePolicy(
            window_seconds=60,
            account_failure_limit=2,
            account_lock_seconds=(10,),
            ip_failure_limit=3,
            ip_lock_seconds=30,
        ),
        clock=clock,
    )

    limiter.register_failure("admin", "192.0.2.10")
    limiter.register_failure("admin", "192.0.2.10")
    limiter.register_success(" ADMIN ")

    assert limiter.retry_after("admin", "192.0.2.11") == 0
    assert limiter.register_failure("another-user", "192.0.2.10") == 30


def test_failures_and_lock_expire_after_the_configured_window():
    clock = MutableClock()
    limiter = LoginAttemptLimiter(
        policy=LoginThrottlePolicy(
            window_seconds=10,
            account_failure_limit=2,
            account_lock_seconds=(5,),
            ip_failure_limit=100,
            ip_lock_seconds=30,
        ),
        clock=clock,
    )

    limiter.register_failure("admin", "192.0.2.10")
    assert limiter.register_failure("admin", "192.0.2.10") == 5

    clock.advance(11)

    assert limiter.retry_after("admin", "192.0.2.10") == 0
    assert limiter.register_failure("admin", "192.0.2.10") == 0


def test_client_ip_comes_from_trusted_request_scope_not_raw_forwarded_header():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/auth/login",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"203.0.113.99")],
            "client": ("127.0.0.1", 54321),
            "server": ("testserver", 443),
        }
    )

    assert get_login_client_ip(request) == "127.0.0.1"


def test_internal_streamlit_client_can_forward_valid_browser_ip():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/auth/login",
            "query_string": b"",
            "headers": [(b"x-dashboard-client-ip", b"203.0.113.99")],
            "client": ("127.0.0.1", 54321),
            "server": ("127.0.0.1", 8000),
        }
    )

    assert get_login_client_ip(request) == "203.0.113.99"


def test_external_client_cannot_override_its_ip_with_internal_header():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/auth/login",
            "query_string": b"",
            "headers": [(b"x-dashboard-client-ip", b"203.0.113.99")],
            "client": ("198.51.100.10", 54321),
            "server": ("testserver", 443),
        }
    )

    assert get_login_client_ip(request) == "198.51.100.10"
