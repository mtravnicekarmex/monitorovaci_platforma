import datetime
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.scheduler import scheduler
from core.scheduler.job_schedule import get_scheduler_job_specs


class FakeLogger:
    def __init__(self):
        self.records = []

    def _record(self, level, message, *args, **kwargs):
        if args:
            message = message % args
        if kwargs.get("exc_info"):
            message = f"{message}\n<exc_info>"
        self.records.append((level, message))

    def info(self, message, *args, **kwargs):
        self._record("info", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._record("warning", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._record("error", message, *args, **kwargs)


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False

    def query(self, model):
        return FakeQuery(self.rows)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.closed = True


class FakeMetricsStore:
    def __init__(self):
        self.success_calls = []
        self.error_calls = []
        self.skipped_calls = []
        self.next_run_updates = []
        self.scheduler_running = False
        self.started = 0
        self.stopped = 0
        self.heartbeat_calls = 0

    def record_job_success(self, job_id, duration_seconds=None):
        self.success_calls.append((job_id, duration_seconds))

    def record_job_error(self, job_id, duration_seconds=None):
        self.error_calls.append((job_id, duration_seconds))

    def record_job_skipped(self, job_id, reason):
        self.skipped_calls.append((job_id, reason))

    def set_job_next_run(self, job_id, next_run):
        self.next_run_updates.append((job_id, next_run))

    def update_job_next_runs(self, next_runs):
        self.next_run_updates.append(dict(next_runs))

    def mark_scheduler_started(self):
        self.started += 1
        self.scheduler_running = True

    def heartbeat(self):
        self.heartbeat_calls += 1
        self.scheduler_running = True

    def mark_scheduler_stopped(self):
        self.stopped += 1
        self.scheduler_running = False


@pytest.fixture
def fake_metrics_store(monkeypatch):
    store = FakeMetricsStore()
    monkeypatch.setattr(scheduler, "get_metrics_store", lambda *args, **kwargs: store)
    return store


def test_safe_call_wraps_exception_without_error_logging(monkeypatch, fake_metrics_store):
    fake_logger = FakeLogger()
    monkeypatch.setattr(scheduler, "logger", fake_logger)

    def boom():
        raise ValueError("db timeout")

    with pytest.raises(scheduler.SchedulerContextError) as exc_info:
        scheduler.safe_call(boom)

    assert exc_info.value.alert_targets == ("boom",)
    assert exc_info.value.alert_reason == "db timeout"
    assert exc_info.value.__cause__.__class__ is ValueError
    assert [job_id for job_id, _ in fake_metrics_store.error_calls] == ["boom"]
    assert not [record for record in fake_logger.records if record[0] == "error"]


def test_safe_call_records_success_metrics(monkeypatch, fake_metrics_store):
    fake_logger = FakeLogger()
    monkeypatch.setattr(scheduler, "logger", fake_logger)

    def ok():
        return "done"

    assert scheduler.safe_call(ok) == "done"
    assert [job_id for job_id, _ in fake_metrics_store.success_calls] == ["ok"]


def test_alert_technical_text_redacts_common_secret_forms():
    source = (
        "postgresql://user:password@server/db "
        "password=hunter2 token:abc123 secret=value"
    )

    sanitized = scheduler._sanitize_alert_technical_text(source)

    assert "user:password" not in sanitized
    assert "hunter2" not in sanitized
    assert "abc123" not in sanitized
    assert "secret=value" not in sanitized
    assert "postgresql://***@server/db" in sanitized
    assert "password=***" in sanitized
    assert "token:***" in sanitized


def test_job_error_listener_sends_readable_alert(monkeypatch, fake_metrics_store):
    fake_logger = FakeLogger()
    sent_email = {}

    monkeypatch.setattr(scheduler, "logger", fake_logger)
    monkeypatch.setattr(scheduler, "config", lambda key: "alarm@example.com")
    monkeypatch.setattr(
        scheduler,
        "send_email_outlook",
        lambda **kwargs: sent_email.update(kwargs),
    )
    monkeypatch.setattr(
        scheduler,
        "_load_cached_active_admin_email_hashes",
        lambda: frozenset({scheduler._hash_alert_email("alarm@example.com")}),
    )

    event = SimpleNamespace(
        job_id="daily_seven_and_two_job",
        scheduled_run_time=datetime.datetime(2026, 4, 9, 7, 0, tzinfo=datetime.timezone.utc),
        exception=scheduler.SchedulerContextError(
            "Web monitor selhal",
            alert_targets=("https://a.example", "https://b.example"),
            alert_reason="https://a.example (timeout); https://b.example (HTTP 500)",
        ),
        traceback="Traceback line 1\nTraceback line 2",
        code=None,
    )

    scheduler.job_error_listener(event)

    assert [job_id for job_id, _ in fake_metrics_store.error_calls] == ["daily_seven_and_two_job"]

    error_messages = [message for level, message in fake_logger.records if level == "error"]
    assert any("JOB ERROR | id=daily_seven_and_two_job" in message for message in error_messages)
    assert any("targets=https://a.example,https://b.example" in message for message in error_messages)
    assert any("Traceback line 1" in message for message in error_messages)

    assert sent_email["subject"] == "[ALERT] Scheduler | daily_seven_and_two_job | SPADL"
    assert sent_email["is_html"] is True
    assert "Naplanovany job scheduleru skoncil chybou" in sent_email["body"]
    assert "https://a.example" in sent_email["body"]
    assert "Duvod" in sent_email["body"]
    assert "Cile" in sent_email["body"]
    assert "background:#ffffff" in sent_email["body"]
    assert "color:#1f2328" in sent_email["body"]


def test_scheduler_alert_uses_brief_body_for_non_admin_recipient(monkeypatch):
    sent_email = {}

    monkeypatch.setattr(
        scheduler,
        "config",
        lambda key: {
            "MY_EMAIL": "operator@example.com",
            "O_EMAIL_ALARM": "alarm@example.com",
        }[key],
    )
    monkeypatch.setattr(
        scheduler,
        "_load_cached_active_admin_email_hashes",
        lambda: frozenset(),
    )
    monkeypatch.setattr(
        scheduler,
        "send_email_outlook",
        lambda **kwargs: sent_email.update(kwargs),
    )

    scheduler._send_scheduler_alert(
        job_id="daily_job",
        status_text="spadl",
        description="Job scheduleru skoncil chybou.",
        scheduled_time=datetime.datetime(2026, 6, 13, 12, 0),
        reason="database password leaked",
        targets=("sensitive-target",),
    )

    assert sent_email["body"] == "Job scheduleru skoncil chybou."
    assert sent_email["is_html"] is False
    assert "database password leaked" not in sent_email["body"]
    assert "sensitive-target" not in sent_email["body"]


def test_job_success_listener_records_skipped_and_success(monkeypatch, fake_metrics_store):
    fake_logger = FakeLogger()
    monkeypatch.setattr(scheduler, "logger", fake_logger)

    skipped_event = SimpleNamespace(
        job_id="hourly_job",
        scheduled_run_time=datetime.datetime(2026, 4, 9, 8, 0, tzinfo=datetime.timezone.utc),
        retval=scheduler.SkippedJobResult(reason="lock_busy", lock_names=("hourly_job",)),
    )
    success_event = SimpleNamespace(
        job_id="weekly_job",
        scheduled_run_time=datetime.datetime(2026, 4, 9, 8, 0, tzinfo=datetime.timezone.utc),
        retval=None,
    )

    scheduler.job_success_listener(skipped_event)
    scheduler.job_success_listener(success_event)

    assert fake_metrics_store.skipped_calls == [("hourly_job", "lock_busy")]
    assert [job_id for job_id, _ in fake_metrics_store.success_calls] == ["weekly_job"]


def test_job_error_listener_handles_alert_delivery_failure(monkeypatch, fake_metrics_store):
    fake_logger = FakeLogger()

    monkeypatch.setattr(scheduler, "logger", fake_logger)
    monkeypatch.setattr(scheduler, "config", lambda key: "alarm@example.com")

    def fail_send(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(scheduler, "send_email_outlook", fail_send)

    event = SimpleNamespace(
        job_id="hourly_job",
        scheduled_run_time=datetime.datetime(2026, 4, 9, 8, 0, tzinfo=datetime.timezone.utc),
        exception=RuntimeError("source failed"),
        traceback="Traceback line",
        code=None,
    )

    scheduler.job_error_listener(event)

    assert [job_id for job_id, _ in fake_metrics_store.error_calls] == ["hourly_job"]

    error_messages = [message for level, message in fake_logger.records if level == "error"]
    assert any("JOB ERROR | id=hourly_job" in message for message in error_messages)
    assert any("SCHEDULER ALERT FAILED | id=hourly_job" in message for message in error_messages)


def test_daily_web_monitor_job_aggregates_failed_targets(monkeypatch):
    fake_logger = FakeLogger()
    monitors = [
        SimpleNamespace(url="https://ok.example", vyrazy=json.dumps(["alpha"]), last_run=None),
        SimpleNamespace(url="https://bad.example", vyrazy=json.dumps(["beta"]), last_run=None),
    ]
    session = FakeSession(monitors)

    monkeypatch.setattr(scheduler, "logger", fake_logger)
    monkeypatch.setattr(scheduler, "get_session_pg", lambda: session)
    monkeypatch.setattr(scheduler, "notify_new_results_for_monitor", lambda *args, **kwargs: 0)

    def fake_hledat(monitor, vyrazy, db_session):
        if monitor.url == "https://bad.example":
            raise RuntimeError("timeout")
        return []

    monkeypatch.setattr(scheduler, "hledat_nove_vyskyt", fake_hledat)

    with pytest.raises(scheduler.SchedulerContextError) as exc_info:
        scheduler.daily_web_monitor_job()

    assert exc_info.value.alert_targets == ("https://bad.example",)
    assert exc_info.value.alert_reason == "https://bad.example (timeout)"
    assert exc_info.value.__cause__.__class__ is RuntimeError
    assert session.rollback_calls == 1
    assert session.closed is True


def test_check_database_availability_raises_for_unavailable_database(monkeypatch):
    fake_logger = FakeLogger()
    executed_queries = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def execute(self, query):
            executed_queries.append(query)

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    class FailingEngine:
        def connect(self):
            raise RuntimeError("login timeout")

    monkeypatch.setattr(scheduler, "logger", fake_logger)
    monkeypatch.setattr(
        scheduler,
        "_refresh_active_admin_email_cache",
        lambda _connection: frozenset(),
    )
    monkeypatch.setattr(
        scheduler,
        "DATABASE_AVAILABILITY_CHECKS",
        (
            ("postgres", "PostgreSQL", FakeEngine()),
            ("mssql", "MS SQL", FailingEngine()),
        ),
    )

    with pytest.raises(scheduler.DatabaseAvailabilityError) as exc_info:
        scheduler.check_database_availability()

    assert executed_queries == [scheduler.DATABASE_AVAILABILITY_QUERY]
    assert [(failure.key, failure.label, failure.reason) for failure in exc_info.value.failures] == [
        ("mssql", "MS SQL", "login timeout")
    ]
    assert exc_info.value.alert_targets == ("MS SQL",)
    assert exc_info.value.alert_reason == "MS SQL: login timeout"
    assert any(
        "DATABASE CHECK FAILED | db=mssql | reason=login timeout" in message
        for level, message in fake_logger.records
        if level == "error"
    )


def test_admin_email_cache_refresh_failure_does_not_fail_database_preflight(monkeypatch):
    fake_logger = FakeLogger()

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def execute(self, query):
            assert query is scheduler.DATABASE_AVAILABILITY_QUERY

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(scheduler, "logger", fake_logger)
    monkeypatch.setattr(
        scheduler,
        "DATABASE_AVAILABILITY_CHECKS",
        (
            ("postgres", "PostgreSQL", FakeEngine()),
            ("mssql", "MS SQL", FakeEngine()),
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "_refresh_active_admin_email_cache",
        lambda _connection: (_ for _ in ()).throw(OSError("cache unavailable")),
    )

    scheduler.check_database_availability()

    assert any(
        "ADMIN ALERT RECIPIENT CACHE REFRESH FAILED" in message
        for level, message in fake_logger.records
        if level == "warning"
    )
    assert any(
        "DATABASE CHECK OK" in message
        for level, message in fake_logger.records
        if level == "info"
    )


def test_database_availability_alert_uses_database_error_recipients(monkeypatch):
    sent_messages = []
    failures = (
        scheduler.DatabaseCheckFailure(
            key="postgres",
            label="PostgreSQL",
            reason="connection refused",
        ),
    )

    values = {
        "DATABASE_ERROR_RECIPIENTS": "first@armex.cz, second@armex.cz",
        "O_EMAIL_ALARM": "alarm@armex.cz",
    }

    monkeypatch.setattr(scheduler, "config", lambda key, default="": values.get(key, default))
    monkeypatch.setattr(
        scheduler,
        "send_email_outlook",
        lambda **kwargs: sent_messages.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler,
        "_load_cached_active_admin_email_hashes",
        lambda: frozenset(),
    )

    scheduler._send_database_availability_alert(failures, job_id="quarter_hour_job")

    assert [message["email_receiver"] for message in sent_messages] == [
        "first@armex.cz",
        "second@armex.cz",
    ]
    assert all(message["sender_alias"] == "alarm@armex.cz" for message in sent_messages)
    assert sent_messages[0]["subject"] == "[ALERT] Nedostupnost POSTGRES"
    assert sent_messages[0]["body"] == "Nedostupnost POSTGRES"
    assert sent_messages[0]["is_html"] is False
    assert "quarter_hour_job" not in sent_messages[0]["subject"]
    assert "connection refused" not in sent_messages[0]["body"]


def test_database_availability_alert_lists_only_unavailable_databases(monkeypatch):
    sent_messages = []
    failures = (
        scheduler.DatabaseCheckFailure(
            key="postgres",
            label="PostgreSQL",
            reason="connection refused",
        ),
        scheduler.DatabaseCheckFailure(
            key="mssql",
            label="MS SQL",
            reason="login timeout",
        ),
    )
    values = {
        "DATABASE_ERROR_RECIPIENTS": "ops@armex.cz",
        "O_EMAIL_ALARM": "alarm@armex.cz",
    }

    monkeypatch.setattr(scheduler, "config", lambda key, default="": values.get(key, default))
    monkeypatch.setattr(
        scheduler,
        "send_email_outlook",
        lambda **kwargs: sent_messages.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler,
        "_load_cached_active_admin_email_hashes",
        lambda: frozenset(),
    )

    scheduler._send_database_availability_alert(failures, job_id="daily_job")

    assert sent_messages == [
        {
            "email_receiver": "ops@armex.cz",
            "sender_alias": "alarm@armex.cz",
            "subject": "[ALERT] Nedostupnost POSTGRES / Nedostupnost MSSQL",
            "body": "Nedostupnost POSTGRES\nNedostupnost MSSQL",
            "is_html": False,
        }
    ]


def test_database_availability_alert_adds_details_only_for_active_admin(monkeypatch):
    sent_messages = []
    failures = (
        scheduler.DatabaseCheckFailure(
            key="postgres",
            label="PostgreSQL",
            reason="connection refused",
        ),
    )
    values = {
        "DATABASE_ERROR_RECIPIENTS": "ADMIN@ARMEX.CZ, operator@armex.cz",
        "O_EMAIL_ALARM": "alarm@armex.cz",
    }

    monkeypatch.setattr(scheduler, "config", lambda key, default="": values.get(key, default))
    monkeypatch.setattr(
        scheduler,
        "_load_cached_active_admin_email_hashes",
        lambda: frozenset({scheduler._hash_alert_email("admin@armex.cz")}),
    )
    monkeypatch.setattr(
        scheduler,
        "send_email_outlook",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    scheduler._send_database_availability_alert(failures, job_id="daily_job")

    admin_message, operator_message = sent_messages
    assert admin_message["email_receiver"] == "ADMIN@ARMEX.CZ"
    assert "Technicke detaily" in admin_message["body"]
    assert "Job: daily_job" in admin_message["body"]
    assert "PostgreSQL: connection refused" in admin_message["body"]
    assert operator_message["body"] == "Nedostupnost POSTGRES"
    assert "connection refused" not in operator_message["body"]


def test_database_recovery_alert_summarizes_outage_for_all_recipients(monkeypatch):
    sent_messages = []
    outage_started_at = datetime.datetime(
        2026,
        6,
        13,
        8,
        5,
        tzinfo=datetime.timezone.utc,
    )
    outage_ended_at = datetime.datetime(
        2026,
        6,
        13,
        10,
        35,
        tzinfo=datetime.timezone.utc,
    )
    events = (
        scheduler.DatabaseAvailabilityEvent(
            id=1,
            service_key="postgres",
            service_label="PostgreSQL",
            event_type="recovered",
            occurred_at=outage_ended_at,
            outage_started_at=outage_started_at,
            outage_ended_at=outage_ended_at,
            reason="connection refused",
            failed_check_count=10,
        ),
    )
    values = {
        "DATABASE_ERROR_RECIPIENTS": "admin@armex.cz, operator@armex.cz",
        "O_EMAIL_ALARM": "alarm@armex.cz",
    }

    monkeypatch.setattr(scheduler, "config", lambda key, default="": values.get(key, default))
    monkeypatch.setattr(
        scheduler,
        "_load_cached_active_admin_email_hashes",
        lambda: frozenset({scheduler._hash_alert_email("admin@armex.cz")}),
    )
    monkeypatch.setattr(
        scheduler,
        "send_email_outlook",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    delivered = scheduler._send_database_recovery_alert(
        events,
        job_id="quarter_hour_job",
    )

    assert delivered is True
    admin_message, operator_message = sent_messages
    assert admin_message["subject"] == "[INFO] Obnovena dostupnost POSTGRES"
    assert "Nedostupnost od: 2026-06-13 10:05:00 CEST" in admin_message["body"]
    assert "Dostupnost od: 2026-06-13 12:35:00 CEST" in admin_message["body"]
    assert "Doba nedostupnosti: 2 h 30 min 0 s" in admin_message["body"]
    assert "Pocet neuspesnych kontrol: 10" in admin_message["body"]
    assert "Posledni duvod: connection refused" in admin_message["body"]
    assert "Job: quarter_hour_job" in admin_message["body"]
    assert "Doba nedostupnosti: 2 h 30 min 0 s" in operator_message["body"]
    assert "Pocet neuspesnych kontrol" not in operator_message["body"]
    assert "connection refused" not in operator_message["body"]


def test_active_admin_email_cache_stores_only_hashes(monkeypatch, tmp_path):
    cache_path = tmp_path / "admin-alert-cache.json"

    class FakeConnection:
        def execute(self, query):
            assert query is scheduler.ACTIVE_ADMIN_EMAIL_QUERY
            return [
                ("Admin@Armex.cz",),
                ("second-admin@armex.cz",),
                (None,),
            ]

    monkeypatch.setattr(scheduler, "ADMIN_ALERT_EMAIL_CACHE_PATH", cache_path)

    refreshed_hashes = scheduler._refresh_active_admin_email_cache(FakeConnection())
    cached_hashes = scheduler._load_cached_active_admin_email_hashes()
    raw_cache = cache_path.read_text(encoding="utf-8")

    assert refreshed_hashes == cached_hashes
    assert scheduler._hash_alert_email("admin@armex.cz") in cached_hashes
    assert scheduler._hash_alert_email("SECOND-ADMIN@ARMEX.CZ") in cached_hashes
    assert "Admin@Armex.cz" not in raw_cache
    assert "second-admin@armex.cz" not in raw_cache


def test_stale_admin_email_cache_fails_closed(monkeypatch, tmp_path):
    cache_path = tmp_path / "admin-alert-cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "version": 1,
                "refreshed_at_epoch": 1,
                "admin_email_hashes": [
                    scheduler._hash_alert_email("admin@armex.cz")
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(scheduler, "ADMIN_ALERT_EMAIL_CACHE_PATH", cache_path)
    monkeypatch.setattr(scheduler.time, "time", lambda: 1000000)

    assert scheduler._load_cached_active_admin_email_hashes() == frozenset()


def test_check_runtime_availability_returns_only_failed_services(monkeypatch):
    http_calls = []
    tcp_calls = []

    def fake_http_check(url):
        http_calls.append(url)
        if "8001" in url:
            raise OSError("connection refused")

    def fake_tcp_check(address):
        tcp_calls.append(address)
        raise OSError("connection refused")

    monkeypatch.setattr(scheduler, "_check_http_endpoint", fake_http_check)
    monkeypatch.setattr(scheduler, "_check_tcp_listener", fake_tcp_check)
    monkeypatch.setattr(scheduler, "RUNTIME_CHECK_ATTEMPTS", 1)

    failures = scheduler.check_runtime_availability()

    assert failures == (
        scheduler.RuntimeCheckFailure(
            key="dashboard",
            alert_text="Nedostupnost DASHBOARD",
            target="http://127.0.0.1:8001/_stcore/health",
            reason="connection refused",
        ),
        scheduler.RuntimeCheckFailure(
            key="caddy",
            alert_text="Nedostupnost CADDY",
            target="127.0.0.1:2019",
            reason="connection refused",
        ),
    )
    assert http_calls == [
        "http://127.0.0.1:8000/health/live",
        "http://127.0.0.1:8001/_stcore/health",
    ]
    assert tcp_calls == [("127.0.0.1", 2019)]


def test_runtime_check_ignores_one_transient_failure(monkeypatch):
    api_attempts = []

    def fake_http_check(url):
        if "8000" not in url:
            return
        api_attempts.append(url)
        if len(api_attempts) == 1:
            raise TimeoutError("temporary reload")

    monkeypatch.setattr(scheduler, "_check_http_endpoint", fake_http_check)
    monkeypatch.setattr(scheduler, "_check_tcp_listener", lambda _address: None)
    monkeypatch.setattr(scheduler, "RUNTIME_CHECK_RETRY_DELAY_SECONDS", 0)

    assert scheduler.check_runtime_availability() == ()
    assert len(api_attempts) == 2


def test_runtime_availability_alert_contains_no_probe_details(monkeypatch):
    sent_messages = []
    failures = (
        scheduler.RuntimeCheckFailure(
            key="api",
            alert_text="Nedostupnost API",
        ),
        scheduler.RuntimeCheckFailure(
            key="caddy",
            alert_text="Nedostupnost CADDY",
        ),
    )
    values = {
        "RUNTIME_ERROR_RECIPIENTS": "ops@armex.cz",
        "DATABASE_ERROR_RECIPIENTS": "database@armex.cz",
        "O_EMAIL_ALARM": "alarm@armex.cz",
    }

    monkeypatch.setattr(scheduler, "config", lambda key, default="": values.get(key, default))
    monkeypatch.setattr(
        scheduler,
        "send_email_outlook",
        lambda **kwargs: sent_messages.append(kwargs),
    )
    monkeypatch.setattr(
        scheduler,
        "_load_cached_active_admin_email_hashes",
        lambda: frozenset(),
    )

    delivered = scheduler._send_runtime_availability_alert(failures)

    assert delivered is True
    assert sent_messages == [
        {
            "email_receiver": "ops@armex.cz",
            "sender_alias": "alarm@armex.cz",
            "subject": "[ALERT] Nedostupnost API / Nedostupnost CADDY",
            "body": "Nedostupnost API\nNedostupnost CADDY",
            "is_html": False,
        }
    ]


def test_runtime_availability_alert_adds_details_only_for_active_admin(monkeypatch):
    sent_messages = []
    failures = (
        scheduler.RuntimeCheckFailure(
            key="api",
            alert_text="Nedostupnost API",
            target="http://127.0.0.1:8000/health/live",
            reason="HTTP 503",
        ),
    )
    values = {
        "RUNTIME_ERROR_RECIPIENTS": "admin@armex.cz, operator@armex.cz",
        "DATABASE_ERROR_RECIPIENTS": "database@armex.cz",
        "O_EMAIL_ALARM": "alarm@armex.cz",
    }

    monkeypatch.setattr(scheduler, "config", lambda key, default="": values.get(key, default))
    monkeypatch.setattr(
        scheduler,
        "_load_cached_active_admin_email_hashes",
        lambda: frozenset({scheduler._hash_alert_email("admin@armex.cz")}),
    )
    monkeypatch.setattr(
        scheduler,
        "send_email_outlook",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    delivered = scheduler._send_runtime_availability_alert(failures)

    assert delivered is True
    admin_message, operator_message = sent_messages
    assert "Technicke detaily" in admin_message["body"]
    assert "cil=http://127.0.0.1:8000/health/live" in admin_message["body"]
    assert "duvod=HTTP 503" in admin_message["body"]
    assert operator_message["body"] == "Nedostupnost API"
    assert "HTTP 503" not in operator_message["body"]


def test_runtime_monitor_alerts_once_until_service_recovers(monkeypatch):
    delivered_alerts = []
    failure = scheduler.RuntimeCheckFailure(
        key="dashboard",
        alert_text="Nedostupnost DASHBOARD",
    )
    check_results = iter(((failure,), (failure,), (), (failure,)))

    monkeypatch.setattr(
        scheduler,
        "check_runtime_availability",
        lambda: next(check_results),
    )
    monkeypatch.setattr(
        scheduler,
        "_deliver_runtime_availability_alert",
        lambda failures: delivered_alerts.append(failures) or True,
    )
    monkeypatch.setattr(scheduler, "_RUNTIME_ALERTED_FAILURE_KEYS", set())

    scheduler._run_runtime_availability_monitor()
    scheduler._run_runtime_availability_monitor()
    scheduler._run_runtime_availability_monitor()
    scheduler._run_runtime_availability_monitor()

    assert delivered_alerts == [(failure,), (failure,)]


def test_database_preflight_checks_runtime_before_databases(monkeypatch):
    calls = []

    monkeypatch.setattr(
        scheduler,
        "_run_runtime_availability_monitor",
        lambda: calls.append("runtime"),
    )
    monkeypatch.setattr(
        scheduler,
        "safe_call",
        lambda fn, *args, **kwargs: calls.append(fn.__name__),
    )
    monkeypatch.setattr(
        scheduler,
        "_record_and_deliver_database_availability_transitions",
        lambda failures, *, job_id: calls.append(
            ("database_state", failures, job_id)
        ),
    )

    assert scheduler._run_database_preflight_or_skip("quarter_hour_job") is None
    assert calls == [
        "runtime",
        "check_database_availability",
        ("database_state", (), "quarter_hour_job"),
    ]


def test_quarter_hour_job_skips_and_alerts_when_database_unavailable(monkeypatch):
    calls = []
    recorded_transitions = []
    failures = (
        scheduler.DatabaseCheckFailure(
            key="mssql",
            label="MS SQL",
            reason="login timeout",
        ),
    )
    database_error = scheduler.DatabaseAvailabilityError(failures)

    def fake_check_database_availability():
        return None

    def fake_safe_call(fn, *args, **kwargs):
        calls.append(fn.__name__)
        if fn is fake_check_database_availability:
            raise database_error
        raise AssertionError(f"Unexpected quarter-hour step: {fn.__name__}")

    monkeypatch.setattr(scheduler, "check_database_availability", fake_check_database_availability)
    monkeypatch.setattr(scheduler, "_run_runtime_availability_monitor", lambda: None)
    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
    monkeypatch.setattr(
        scheduler,
        "_record_and_deliver_database_availability_transitions",
        lambda failures_arg, *, job_id: recorded_transitions.append(
            (failures_arg, job_id)
        ),
    )

    result = scheduler.quarter_hour_job.__scheduler_unlocked_fn__()

    assert calls == ["fake_check_database_availability"]
    assert isinstance(result, scheduler.SkippedJobResult)
    assert result.reason == "database_unavailable"
    assert result.lock_names == ("quarter_hour_job",)
    assert recorded_transitions == [(failures, "quarter_hour_job")]


def test_non_quarter_hour_database_failure_does_not_emit_transition_alert(monkeypatch):
    failures = (
        scheduler.DatabaseCheckFailure(
            key="postgres",
            label="PostgreSQL",
            reason="connection refused",
        ),
    )
    database_error = scheduler.DatabaseAvailabilityError(failures)
    transition_calls = []

    monkeypatch.setattr(scheduler, "_run_runtime_availability_monitor", lambda: None)
    monkeypatch.setattr(
        scheduler,
        "safe_call",
        lambda fn, *args, **kwargs: (_ for _ in ()).throw(database_error),
    )
    monkeypatch.setattr(
        scheduler,
        "_record_and_deliver_database_availability_transitions",
        lambda *args, **kwargs: transition_calls.append((args, kwargs)),
    )

    result = scheduler._run_database_preflight_or_skip("hourly_job")

    assert result == scheduler.SkippedJobResult(
        reason="database_unavailable",
        lock_names=("hourly_job",),
    )
    assert transition_calls == []


def test_database_transition_monitor_alerts_once_and_then_sends_recovery(
    monkeypatch,
    tmp_path,
):
    store = scheduler.DatabaseAvailabilityStore(
        tmp_path / "database-availability.sqlite3"
    )
    outage_deliveries = []
    recovery_deliveries = []
    failures = (
        scheduler.DatabaseCheckFailure(
            key="postgres",
            label="PostgreSQL",
            reason="connection refused",
        ),
    )

    monkeypatch.setattr(scheduler, "DatabaseAvailabilityStore", lambda: store)
    monkeypatch.setattr(
        scheduler,
        "DATABASE_AVAILABILITY_CHECKS",
        (
            ("postgres", "PostgreSQL", object()),
            ("mssql", "MS SQL", object()),
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "_deliver_database_availability_alert",
        lambda failures_arg, *, job_id: (
            outage_deliveries.append((failures_arg, job_id)) or True
        ),
    )
    monkeypatch.setattr(
        scheduler,
        "_deliver_database_recovery_alert",
        lambda events, *, job_id: (
            recovery_deliveries.append((events, job_id)) or True
        ),
    )

    scheduler._record_and_deliver_database_availability_transitions(
        failures,
        job_id="quarter_hour_job",
    )
    scheduler._record_and_deliver_database_availability_transitions(
        failures,
        job_id="quarter_hour_job",
    )
    scheduler._record_and_deliver_database_availability_transitions(
        (),
        job_id="quarter_hour_job",
    )

    assert len(outage_deliveries) == 1
    assert outage_deliveries[0] == (failures, "quarter_hour_job")
    assert len(recovery_deliveries) == 1
    recovery_events, recovery_job_id = recovery_deliveries[0]
    assert recovery_job_id == "quarter_hour_job"
    assert len(recovery_events) == 1
    assert recovery_events[0].service_key == "postgres"
    assert recovery_events[0].event_type == "recovered"
    assert store.load_pending_events() == ()


@pytest.mark.parametrize("job_id", [job_spec.id for job_spec in get_scheduler_job_specs()])
def test_scheduled_db_jobs_skip_before_work_when_database_preflight_fails(monkeypatch, job_id):
    preflight_calls = []
    skipped_result = scheduler.SkippedJobResult(
        reason="database_unavailable",
        lock_names=(job_id,),
    )

    def fake_preflight(actual_job_id):
        preflight_calls.append(actual_job_id)
        return skipped_result

    monkeypatch.setattr(scheduler, "_run_database_preflight_or_skip", fake_preflight)
    monkeypatch.setattr(scheduler, "is_last_czech_business_day", lambda _value: True)
    monkeypatch.setattr(
        scheduler,
        "safe_call",
        lambda *args, **kwargs: pytest.fail("job work should not start after a failed database preflight"),
    )

    job_fn = scheduler._get_job_functions()[job_id]
    result = job_fn.__scheduler_unlocked_fn__()

    assert result is skipped_result
    assert preflight_calls == [job_id]


def test_monthly_job_calls_all_monthly_reports(monkeypatch):
    calls = []

    def fake_vodomery_report():
        return None

    def fake_monthly_branch_report():
        return None

    def fake_monthly_billing_summary_report():
        return None

    def fake_b1_report():
        return None

    def fake_jordan_report():
        return None

    def fake_monthly_elektromery_report():
        return None

    monkeypatch.setattr(scheduler, "send_monthly_vodomery_consumption_report", fake_vodomery_report)
    monkeypatch.setattr(scheduler, "send_monthly_vodomery_branch_report", fake_monthly_branch_report)
    monkeypatch.setattr(scheduler, "send_monthly_vodomery_billing_summary_report", fake_monthly_billing_summary_report)
    monkeypatch.setattr(scheduler, "send_monthly_b1_consumption_report", fake_b1_report)
    monkeypatch.setattr(scheduler, "send_monthly_jordan_consumption_report", fake_jordan_report)
    monkeypatch.setattr(scheduler, "send_monthly_elektromery_branch_report", fake_monthly_elektromery_report)
    monkeypatch.setattr(scheduler, "_run_database_preflight_or_skip", lambda job_id: None)
    monkeypatch.setattr(
        scheduler,
        "safe_call",
        lambda fn, *args, **kwargs: calls.append((fn, args, kwargs)),
    )

    scheduler.monthly_job()

    assert [fn for fn, _, _ in calls] == [
        fake_vodomery_report,
        fake_monthly_branch_report,
        fake_monthly_billing_summary_report,
        fake_b1_report,
        fake_jordan_report,
        fake_monthly_elektromery_report,
    ]


def test_monthly_jordan_report_is_available_for_manual_run():
    manual_specs = scheduler.get_manual_run_specs()

    jordan_spec = manual_specs["send_monthly_jordan_consumption_report"]
    assert jordan_spec.run_fn is scheduler.send_monthly_jordan_consumption_report
    assert jordan_spec.lock_names == ("monthly_job",)


def test_monthly_b1_v1_job_skips_outside_last_czech_business_day(monkeypatch):
    monkeypatch.setattr(scheduler, "prague_today", lambda: datetime.date(2026, 6, 29))
    monkeypatch.setattr(scheduler, "is_last_czech_business_day", lambda _value: False)
    monkeypatch.setattr(
        scheduler,
        "_run_database_preflight_or_skip",
        lambda _job_id: pytest.fail("preflight must not run before the report is due"),
    )
    monkeypatch.setattr(
        scheduler,
        "safe_call",
        lambda *args, **kwargs: pytest.fail("report must not run before the report is due"),
    )

    result = scheduler.monthly_b1_v1_consumption_report_job.__scheduler_unlocked_fn__()

    assert result == scheduler.SkippedJobResult(
        reason="not_last_czech_business_day",
        lock_names=("monthly_b1_v1_consumption_report_job",),
    )


def test_monthly_b1_v1_job_sends_report_on_last_czech_business_day(monkeypatch):
    reference_date = datetime.date(2026, 6, 30)
    calls = []

    monkeypatch.setattr(scheduler, "prague_today", lambda: reference_date)
    monkeypatch.setattr(scheduler, "is_last_czech_business_day", lambda _value: True)
    monkeypatch.setattr(scheduler, "_run_database_preflight_or_skip", lambda _job_id: None)
    monkeypatch.setattr(
        scheduler,
        "safe_call",
        lambda fn, *args, **kwargs: calls.append((fn, args, kwargs)),
    )

    scheduler.monthly_b1_v1_consumption_report_job.__scheduler_unlocked_fn__()

    assert calls == [
        (
            scheduler.vodomery_db_import,
            (),
            {},
        ),
        (
            scheduler.send_monthly_b1_v1_consumption_report,
            (),
            {"reference_date": reference_date},
        )
    ]


def test_monthly_b1_v1_report_is_available_for_manual_run():
    manual_specs = scheduler.get_manual_run_specs()

    report_spec = manual_specs["send_monthly_b1_v1_consumption_report"]
    assert report_spec.run_fn is scheduler.send_monthly_b1_v1_consumption_report
    assert report_spec.lock_names == ("monthly_b1_v1_consumption_report_job",)


def test_daily_vodomery_branch_report_job_sends_email_report(monkeypatch):
    calls = []

    def fake_safe_call(fn, *args, **kwargs):
        calls.append((fn.__name__, args, kwargs))
        return fn(*args, **kwargs)

    def fake_send_daily_vodomery_branch_report():
        return {"recipient_count": 1}

    def fake_send_daily_vodomery_billing_summary_report():
        return {"recipient_count": 1}

    monkeypatch.setattr(scheduler, "_run_database_preflight_or_skip", lambda job_id: None)
    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
    monkeypatch.setattr(scheduler, "send_daily_vodomery_branch_report", fake_send_daily_vodomery_branch_report)
    monkeypatch.setattr(
        scheduler,
        "send_daily_vodomery_billing_summary_report",
        fake_send_daily_vodomery_billing_summary_report,
    )

    scheduler.daily_vodomery_branch_report_job()

    assert [name for name, _, _ in calls] == [
        "fake_send_daily_vodomery_branch_report",
        "fake_send_daily_vodomery_billing_summary_report",
    ]


def test_quarter_hour_job_scores_all_candidate_models_and_alerts_active_only(monkeypatch):
    calls = []
    alert_payloads = []
    plynomery_alert_payloads = []

    def fake_safe_call(fn, *args, **kwargs):
        calls.append((fn.__name__, args, kwargs))
        return fn(*args, **kwargs)

    def fake_check_database_availability():
        return None

    def fake_import():
        return None

    def fake_get_runtime_model_version():
        return 2

    def fake_score_new_measurements(*, model_version, bootstrap_to_latest_if_missing=False):
        assert bootstrap_to_latest_if_missing is True
        return model_version

    def fake_detect_events_from_scores(*, model_version, bootstrap_to_latest_if_missing=False):
        assert bootstrap_to_latest_if_missing is True
        return {
            "active_event_ids": [model_version],
            "resolved_event_ids": [model_version * 10],
        }

    def fake_process_vodomery_alerts(*, active_event_ids, resolved_event_ids):
        alert_payloads.append((active_event_ids, resolved_event_ids))
        return None

    def fake_plynomery_import():
        return None

    def fake_get_plynomery_runtime_model_version():
        return 1

    def fake_score_new_plynomery_measurements(*, model_version, bootstrap_to_latest_if_missing=False):
        assert model_version == 1
        assert bootstrap_to_latest_if_missing is True
        return 3

    def fake_detect_plynomery_events_from_scores(*, model_version, bootstrap_to_latest_if_missing=False):
        assert model_version == 1
        assert bootstrap_to_latest_if_missing is True
        return {
            "active_event_ids": [101],
            "resolved_event_ids": [202],
        }

    def fake_process_plynomery_alerts(*, active_event_ids, resolved_event_ids):
        plynomery_alert_payloads.append((active_event_ids, resolved_event_ids))
        return None

    def fake_manometry_import():
        return None

    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
    monkeypatch.setattr(scheduler, "check_database_availability", fake_check_database_availability)
    monkeypatch.setattr(
        scheduler,
        "_record_and_deliver_database_availability_transitions",
        lambda failures, *, job_id: None,
    )
    monkeypatch.setattr(scheduler, "vodomery_db_import", fake_import)
    monkeypatch.setattr(scheduler, "get_runtime_model_version", fake_get_runtime_model_version)
    monkeypatch.setattr(scheduler, "get_candidate_model_versions", lambda: (1, 2))
    monkeypatch.setattr(scheduler, "score_new_measurements", fake_score_new_measurements)
    monkeypatch.setattr(scheduler, "detect_events_from_scores", fake_detect_events_from_scores)
    monkeypatch.setattr(scheduler, "process_vodomery_alerts", fake_process_vodomery_alerts)
    monkeypatch.setattr(scheduler, "plynomery_db_import", fake_plynomery_import)
    monkeypatch.setattr(scheduler, "get_plynomery_runtime_model_version", fake_get_plynomery_runtime_model_version)
    monkeypatch.setattr(scheduler, "get_plynomery_candidate_model_versions", lambda: (1,))
    monkeypatch.setattr(scheduler, "score_new_plynomery_measurements", fake_score_new_plynomery_measurements)
    monkeypatch.setattr(scheduler, "detect_plynomery_events_from_scores", fake_detect_plynomery_events_from_scores)
    monkeypatch.setattr(scheduler, "process_plynomery_alerts", fake_process_plynomery_alerts)
    monkeypatch.setattr(scheduler, "manometry_db_import", fake_manometry_import)

    scheduler.quarter_hour_job.__scheduler_unlocked_fn__()

    assert [name for name, _, _ in calls] == [
        "fake_check_database_availability",
        "fake_import",
        "fake_get_runtime_model_version",
        "fake_score_new_measurements",
        "fake_detect_events_from_scores",
        "fake_score_new_measurements",
        "fake_detect_events_from_scores",
        "fake_process_vodomery_alerts",
        "fake_plynomery_import",
        "fake_get_plynomery_runtime_model_version",
        "fake_score_new_plynomery_measurements",
        "fake_detect_plynomery_events_from_scores",
        "fake_process_plynomery_alerts",
        "fake_manometry_import",
    ]
    assert alert_payloads == [([2], [20])]
    assert plynomery_alert_payloads == [([101], [202])]


def test_daily_job_runs_meteo_sync_as_last_step(monkeypatch):
    calls = []

    def fake_safe_call(fn, *args, **kwargs):
        calls.append(fn.__name__)
        return fn(*args, **kwargs)

    def fake_softlink_import():
        return None

    def fake_softlink_monitoring_import():
        return {"inserted_softlink": 1}

    def fake_meteo_sync():
        return None

    def fake_sync_charge_sessions_to_db():
        return {"upserted_count": 2}

    monkeypatch.setattr(scheduler, "_run_database_preflight_or_skip", lambda job_id: None)
    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
    monkeypatch.setattr(scheduler, "SOFTLINK_save_to_database_all", fake_softlink_import)
    monkeypatch.setattr(scheduler, "elektromery_softlink_monitoring_import", fake_softlink_monitoring_import)
    monkeypatch.setattr(scheduler, "meteo_sync", fake_meteo_sync)
    monkeypatch.setattr(scheduler, "sync_charge_sessions_to_db", fake_sync_charge_sessions_to_db)

    scheduler.daily_job.__scheduler_unlocked_fn__()

    assert calls == [
        "fake_softlink_import",
        "fake_softlink_monitoring_import",
        "fake_sync_charge_sessions_to_db",
        "fake_meteo_sync",
    ]


def test_weekly_job_rebuilds_profiles_and_sends_report(monkeypatch):
    calls = []
    rebuild_result = {
        "selection_run_id": 7,
        "active_model_version": 2,
        "active_model_name": "Model 2 - adaptive strategy",
        "previous_active_model_version": 1,
        "previous_active_model_name": "Model 1 - baseline MAD",
        "windows": {},
        "candidates": [],
    }

    def fake_safe_call(fn, *args, **kwargs):
        calls.append((fn.__name__, args, kwargs))
        return fn(*args, **kwargs)

    def fake_rebuild_profiles():
        return rebuild_result

    def fake_rebuild_plynomery_profiles():
        return {
            "active_model_version": 1,
            "active_model_name": "Model 1 - exact/fallback baseline",
            "candidates": [],
        }

    def fake_send_vodomery_model_rebuild_report(result):
        assert result is rebuild_result
        return None

    def fake_send_plynomery_model_rebuild_report(result):
        assert result == {
            "active_model_version": 1,
            "active_model_name": "Model 1 - exact/fallback baseline",
            "candidates": [],
        }
        return None

    def fake_send_weekly_vodomery_branch_report():
        return {"recipient_count": 1}

    def fake_send_weekly_vodomery_billing_summary_report():
        return {"recipient_count": 1}

    def fake_send_weekly_elektromery_branch_report():
        return {"recipient_count": 1}

    def fake_send_weekly_new_elektromery_report():
        return {"recipient_count": 1, "new_device_count": 2}

    monkeypatch.setattr(scheduler, "_run_database_preflight_or_skip", lambda job_id: None)
    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
    monkeypatch.setattr(scheduler, "rebuild_profiles", fake_rebuild_profiles)
    monkeypatch.setattr(scheduler, "rebuild_plynomery_profiles", fake_rebuild_plynomery_profiles)
    monkeypatch.setattr(scheduler, "send_vodomery_model_rebuild_report", fake_send_vodomery_model_rebuild_report)
    monkeypatch.setattr(scheduler, "send_plynomery_model_rebuild_report", fake_send_plynomery_model_rebuild_report)
    monkeypatch.setattr(scheduler, "send_weekly_vodomery_branch_report", fake_send_weekly_vodomery_branch_report)
    monkeypatch.setattr(
        scheduler,
        "send_weekly_vodomery_billing_summary_report",
        fake_send_weekly_vodomery_billing_summary_report,
    )
    monkeypatch.setattr(scheduler, "send_weekly_elektromery_branch_report", fake_send_weekly_elektromery_branch_report)
    monkeypatch.setattr(scheduler, "send_weekly_new_elektromery_report", fake_send_weekly_new_elektromery_report)

    scheduler.weekly_job()

    assert [name for name, _, _ in calls] == [
        "fake_rebuild_profiles",
        "fake_rebuild_plynomery_profiles",
        "fake_send_vodomery_model_rebuild_report",
        "fake_send_plynomery_model_rebuild_report",
        "fake_send_weekly_vodomery_branch_report",
        "fake_send_weekly_vodomery_billing_summary_report",
        "fake_send_weekly_elektromery_branch_report",
        "fake_send_weekly_new_elektromery_report",
    ]


def test_smartfuelpass_weekly_report_job_sends_email_report(monkeypatch):
    calls = []

    def fake_safe_call(fn, *args, **kwargs):
        calls.append((fn.__name__, args, kwargs))
        return fn(*args, **kwargs)

    def fake_send_charge_sessions_report_email():
        return {"recipient_count": 1}

    monkeypatch.setattr(scheduler, "_run_database_preflight_or_skip", lambda job_id: None)
    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
    monkeypatch.setattr(scheduler, "send_charge_sessions_report_email", fake_send_charge_sessions_report_email)

    scheduler.smartfuelpass_weekly_report_job()

    assert [name for name, _, _ in calls] == ["fake_send_charge_sessions_report_email"]


def test_scheduler_job_registry_matches_schedule_specs():
    assert set(scheduler._get_job_functions()) == {
        job_spec.id for job_spec in get_scheduler_job_specs()
    }


def test_daily_job_schedule_description_mentions_smartfuelpass_sync():
    daily_job_spec = next(job_spec for job_spec in get_scheduler_job_specs() if job_spec.id == "daily_job")

    assert "SmartFuelPass" in daily_job_spec.description


def test_daily_job_manual_specs_include_smartfuelpass_database_sync():
    manual_specs = scheduler.get_manual_run_specs()

    sync_spec = manual_specs["sync_charge_sessions_to_db"]

    assert sync_spec.run_fn is scheduler.sync_charge_sessions_to_db
    assert sync_spec.lock_names == ("daily_job",)
    assert sync_spec.is_scheduled is False
    assert "databaze" in sync_spec.label


def test_smartfuelpass_report_manual_labels_distinguish_job_and_email_step():
    manual_specs = scheduler.get_manual_run_specs()

    scheduled_job = manual_specs["smartfuelpass_weekly_report_job"]
    email_step = manual_specs["send_charge_sessions_report_email"]

    assert scheduled_job.is_scheduled is True
    assert email_step.is_scheduled is False
    assert scheduled_job.label != email_step.label
    assert "job" in scheduled_job.label.lower()
    assert "email" in email_step.label.lower()


def test_manual_run_worker_enables_scheduler_file_logging(monkeypatch):
    calls = []
    manual_spec = SimpleNamespace(id="demo_manual_job")
    acquired_locks = object()
    requested_at = datetime.datetime(2026, 6, 17, 9, 30)

    def fake_setup_logging(*, enable_file=False):
        calls.append(("setup_logging", enable_file))
        return scheduler.logger

    def fake_run_manual_job(spec, *, requested_at):
        calls.append(("run", spec.id, requested_at))

    def fake_release_job_locks(lock_handle):
        calls.append(("release", lock_handle))

    monkeypatch.setattr(scheduler, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(scheduler, "_run_manual_job", fake_run_manual_job)
    monkeypatch.setattr(scheduler, "_release_job_locks", fake_release_job_locks)

    scheduler._run_manual_job_worker(
        manual_spec,
        acquired_locks,
        requested_at=requested_at,
    )

    assert calls[0] == ("setup_logging", True)
    assert calls[1] == ("run", "demo_manual_job", requested_at)
    assert calls[2] == ("release", acquired_locks)


def test_quarter_hour_schedule_and_manual_specs_include_manometry_import():
    quarter_hour_spec = next(job_spec for job_spec in get_scheduler_job_specs() if job_spec.id == "quarter_hour_job")
    manual_specs = scheduler.get_manual_run_specs()

    assert "manometru" in quarter_hour_spec.description
    assert manual_specs["manometry_db_import"].run_fn is scheduler.manometry_db_import
    assert manual_specs["manometry_db_import"].lock_names == ("quarter_hour_job",)


def test_main_scheduler_registers_monthly_and_daily_report_jobs(monkeypatch, fake_metrics_store):
    fake_logger = FakeLogger()
    fake_process_lock = object()
    released_process_locks = []

    class FakeScheduler:
        def __init__(self, *args, **kwargs):
            self.jobs = []
            self.listeners = []

        def add_job(self, fn, trigger, id=None, **kwargs):
            self.jobs.append({"fn": fn, "trigger": trigger, "id": id, "kwargs": kwargs})

        def add_listener(self, fn, mask):
            self.listeners.append((fn, mask))

        def start(self):
            return None

        def shutdown(self):
            return None

    fake_scheduler = FakeScheduler()

    monkeypatch.setattr(scheduler, "logger", fake_logger)
    monkeypatch.setattr(scheduler, "setup_logging", lambda **kwargs: fake_logger)
    monkeypatch.setattr(scheduler, "_try_acquire_process_lock", lambda lock_name: fake_process_lock)
    monkeypatch.setattr(
        scheduler,
        "_release_process_lock",
        lambda lock_handle: released_process_locks.append(lock_handle),
    )
    monkeypatch.setattr(scheduler, "BackgroundScheduler", lambda *args, **kwargs: fake_scheduler)
    monkeypatch.setattr(
        scheduler.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    scheduler.main_scheduler()

    monthly_job = next(job for job in fake_scheduler.jobs if job["id"] == "monthly_job")
    b1_v1_job = next(
        job
        for job in fake_scheduler.jobs
        if job["id"] == "monthly_b1_v1_consumption_report_job"
    )
    daily_job = next(job for job in fake_scheduler.jobs if job["id"] == "daily_job")
    smartfuelpass_job = next(job for job in fake_scheduler.jobs if job["id"] == "smartfuelpass_weekly_report_job")
    daily_branch_job = next(job for job in fake_scheduler.jobs if job["id"] == "daily_vodomery_branch_report_job")

    assert monthly_job["fn"] is scheduler.monthly_job
    assert daily_job["fn"] is scheduler.daily_job
    assert "hour='0'" in str(daily_job["trigger"])
    assert "minute='15'" in str(daily_job["trigger"])
    assert "second='5'" in str(daily_job["trigger"])
    assert "day='1'" in str(monthly_job["trigger"])
    assert "hour='6'" in str(monthly_job["trigger"])
    assert "minute='20'" in str(monthly_job["trigger"])
    assert "second='5'" in str(monthly_job["trigger"])
    assert b1_v1_job["fn"] is scheduler.monthly_b1_v1_consumption_report_job
    assert "day='25-31'" in str(b1_v1_job["trigger"])
    assert "day_of_week='mon-fri'" in str(b1_v1_job["trigger"])
    assert "hour='13'" in str(b1_v1_job["trigger"])
    assert "minute='3'" in str(b1_v1_job["trigger"])
    assert "second='5'" in str(b1_v1_job["trigger"])
    assert smartfuelpass_job["fn"] is scheduler.smartfuelpass_weekly_report_job
    assert "day_of_week='tue'" in str(smartfuelpass_job["trigger"])
    assert "hour='6'" in str(smartfuelpass_job["trigger"])
    assert "minute='55'" in str(smartfuelpass_job["trigger"])
    assert "second='5'" in str(smartfuelpass_job["trigger"])
    assert daily_branch_job["fn"] is scheduler.daily_vodomery_branch_report_job
    assert "hour='6'" in str(daily_branch_job["trigger"])
    assert "minute='0'" in str(daily_branch_job["trigger"])
    assert "second='5'" in str(daily_branch_job["trigger"])
    assert fake_metrics_store.started == 1
    assert fake_metrics_store.heartbeat_calls == 1
    assert fake_metrics_store.stopped == 1
    assert released_process_locks == [fake_process_lock]


def test_main_scheduler_skips_start_when_process_lock_is_busy(monkeypatch, fake_metrics_store):
    fake_logger = FakeLogger()

    monkeypatch.setattr(scheduler, "logger", fake_logger)
    monkeypatch.setattr(scheduler, "_try_acquire_process_lock", lambda lock_name: None)
    monkeypatch.setattr(
        scheduler,
        "BackgroundScheduler",
        lambda *args, **kwargs: pytest.fail("scheduler should not start without process lock"),
    )

    scheduler.main_scheduler()

    assert fake_metrics_store.started == 0
    assert fake_logger.records == [
        ("warning", "Scheduler uz bezi v jinem procesu; dalsi instance nebude spustena.")
    ]
