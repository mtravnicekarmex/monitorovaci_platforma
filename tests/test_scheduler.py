import datetime
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.scheduler import scheduler


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


def test_monthly_job_calls_both_monthly_reports(monkeypatch):
    calls = []

    def fake_vodomery_report():
        return None

    def fake_b1_report():
        return None

    monkeypatch.setattr(scheduler, "send_monthly_vodomery_consumption_report", fake_vodomery_report)
    monkeypatch.setattr(scheduler, "send_monthly_b1_consumption_report", fake_b1_report)
    monkeypatch.setattr(
        scheduler,
        "safe_call",
        lambda fn, *args, **kwargs: calls.append((fn, args, kwargs)),
    )

    scheduler.monthly_job()

    assert [fn for fn, _, _ in calls] == [fake_vodomery_report, fake_b1_report]


def test_main_scheduler_registers_monthly_job(monkeypatch, fake_metrics_store):
    fake_logger = FakeLogger()

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
    monkeypatch.setattr(scheduler, "BackgroundScheduler", lambda *args, **kwargs: fake_scheduler)
    monkeypatch.setattr(
        scheduler.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    scheduler.main_scheduler()

    monthly_job = next(job for job in fake_scheduler.jobs if job["id"] == "monthly_job")

    assert monthly_job["fn"] is scheduler.monthly_job
    assert "day='1'" in str(monthly_job["trigger"])
    assert "minute='20'" in str(monthly_job["trigger"])
    assert "second='5'" in str(monthly_job["trigger"])
    assert fake_metrics_store.started == 1
    assert fake_metrics_store.heartbeat_calls == 1
    assert fake_metrics_store.stopped == 1
