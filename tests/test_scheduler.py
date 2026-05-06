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

    def fake_monthly_elektromery_report():
        return None

    monkeypatch.setattr(scheduler, "send_monthly_vodomery_consumption_report", fake_vodomery_report)
    monkeypatch.setattr(scheduler, "send_monthly_vodomery_branch_report", fake_monthly_branch_report)
    monkeypatch.setattr(scheduler, "send_monthly_vodomery_billing_summary_report", fake_monthly_billing_summary_report)
    monkeypatch.setattr(scheduler, "send_monthly_b1_consumption_report", fake_b1_report)
    monkeypatch.setattr(scheduler, "send_monthly_elektromery_branch_report", fake_monthly_elektromery_report)
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
        fake_monthly_elektromery_report,
    ]


def test_daily_vodomery_branch_report_job_sends_email_report(monkeypatch):
    calls = []

    def fake_safe_call(fn, *args, **kwargs):
        calls.append((fn.__name__, args, kwargs))
        return fn(*args, **kwargs)

    def fake_send_daily_vodomery_branch_report():
        return {"recipient_count": 1}

    def fake_send_daily_vodomery_billing_summary_report():
        return {"recipient_count": 1}

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

    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
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

    scheduler.quarter_hour_job()

    assert [name for name, _, _ in calls] == [
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
    ]
    assert alert_payloads == [([2], [20])]
    assert plynomery_alert_payloads == [([101], [202])]


def test_daily_job_runs_elektromery_vse_import_after_softlink(monkeypatch):
    calls = []

    def fake_safe_call(fn, *args, **kwargs):
        calls.append(fn.__name__)
        return fn(*args, **kwargs)

    def fake_softlink_import():
        return None

    def fake_elektromery_import():
        return {"inserted_softlink": 1, "inserted_ote": 2}

    def fake_meteo_sync():
        return None

    def fake_sync_charge_sessions_to_db():
        return {"upserted_count": 2}

    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
    monkeypatch.setattr(scheduler, "SOFTLINK_save_to_database_all", fake_softlink_import)
    monkeypatch.setattr(scheduler, "elektromery_db_import", fake_elektromery_import)
    monkeypatch.setattr(scheduler, "meteo_sync", fake_meteo_sync)
    monkeypatch.setattr(scheduler, "sync_charge_sessions_to_db", fake_sync_charge_sessions_to_db)

    scheduler.daily_job.__scheduler_unlocked_fn__()

    assert calls == [
        "fake_softlink_import",
        "fake_elektromery_import",
        "fake_meteo_sync",
        "fake_sync_charge_sessions_to_db",
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

    monkeypatch.setattr(scheduler, "safe_call", fake_safe_call)
    monkeypatch.setattr(scheduler, "send_charge_sessions_report_email", fake_send_charge_sessions_report_email)

    scheduler.smartfuelpass_weekly_report_job()

    assert [name for name, _, _ in calls] == ["fake_send_charge_sessions_report_email"]


def test_scheduler_job_registry_matches_schedule_specs():
    assert set(scheduler._get_job_functions()) == {
        job_spec.id for job_spec in get_scheduler_job_specs()
    }


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
