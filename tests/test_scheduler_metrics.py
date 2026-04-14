from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from core.scheduler.job_schedule import build_schedule_runs
from core.scheduler.metrics import JobMetrics, SchedulerMetricsStore
from services.api.routes import scheduler_health


def test_scheduler_metrics_store_persists_and_reloads(tmp_path):
    metrics_path = tmp_path / "scheduler_metrics.json"
    store = SchedulerMetricsStore(metrics_path=metrics_path)

    store.mark_scheduler_started()
    store.set_job_next_run("quarter_hour_job", datetime(2026, 4, 10, 10, 15, 5))
    store.record_job_success("quarter_hour_job", 1.25)
    store.record_job_error("daily_job", 2.5)
    store.record_job_skipped("hourly_job", "lock_busy")

    reloaded = SchedulerMetricsStore(metrics_path=metrics_path)

    assert reloaded.is_scheduler_running() is True
    assert reloaded.jobs["quarter_hour_job"].next_run == datetime(2026, 4, 10, 10, 15, 5)
    assert reloaded.jobs["quarter_hour_job"].last_status == "success"
    assert reloaded.jobs["daily_job"].failure_count_24h == 1
    assert reloaded.jobs["hourly_job"].last_status == "skipped (lock_busy)"
    assert reloaded.get_avg_duration("quarter_hour_job") == 1.25


def test_scheduler_metrics_store_marks_stale_heartbeat_as_not_running(tmp_path):
    store = SchedulerMetricsStore(metrics_path=tmp_path / "scheduler_metrics.json")
    store.scheduler_running = True
    store.last_heartbeat = datetime.now() - timedelta(minutes=10)

    assert store.is_scheduler_running(stale_after_seconds=60) is False


def test_build_schedule_runs_returns_expected_next_24h_runs():
    runs = build_schedule_runs(
        window_start=datetime(2026, 4, 10, 10, 0, 0, tzinfo=ZoneInfo("Europe/Prague")),
        hours=24,
    )

    assert len(runs) == 123
    assert runs[0].job_id == "hourly_job"
    assert runs[0].scheduled_at == datetime(2026, 4, 10, 10, 2, 5, tzinfo=ZoneInfo("Europe/Prague"))
    assert any(run.job_id == "daily_job" for run in runs)
    assert any(run.job_id == "daily_seven_and_two_job" for run in runs)
    assert not any(run.job_id == "weekly_job" for run in runs)


def test_scheduler_health_route_returns_degraded_status(monkeypatch):
    class FakeMetricsStore:
        def __init__(self):
            self.jobs = {
                "quarter_hour_job": JobMetrics(
                    last_run=datetime(2026, 4, 10, 8, 0, 0),
                    last_status="success",
                    success_count_24h=9,
                ),
                "daily_job": JobMetrics(
                    last_run=datetime(2026, 4, 10, 9, 0, 0),
                    last_status="error",
                    failure_count_24h=2,
                    success_count_24h=8,
                ),
            }

        def is_scheduler_running(self):
            return True

        def get_failure_rate(self, job_id):
            job = self.jobs[job_id]
            total = job.success_count_24h + job.failure_count_24h
            return 0.0 if total == 0 else job.failure_count_24h / total

        def get_avg_duration(self, job_id):
            del job_id
            return None

    fake_store = FakeMetricsStore()
    fake_schedule = [
        SimpleNamespace(
            job_id="hourly_job",
            job_label="Hourly",
            description="Import SCVK vodomeru.",
            scheduled_at=datetime(2026, 4, 10, 10, 2, 5),
        )
    ]
    monkeypatch.setattr(
        scheduler_health,
        "get_metrics_store",
        lambda *args, **kwargs: fake_store,
    )
    monkeypatch.setattr(
        scheduler_health,
        "build_schedule_runs",
        lambda *args, **kwargs: fake_schedule,
    )

    response = scheduler_health.get_scheduler_health(
        current_user=SimpleNamespace(is_admin=True)
    )

    assert response.status == "degraded"
    assert response.scheduler_running is True
    assert [job.id for job in response.jobs] == ["daily_job", "quarter_hour_job"]
    assert [item.job_id for item in response.schedule] == ["hourly_job"]
