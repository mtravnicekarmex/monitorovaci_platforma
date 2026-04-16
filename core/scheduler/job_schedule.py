from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger


SCHEDULER_TIMEZONE_NAME = "Europe/Prague"
SCHEDULER_TIMEZONE = ZoneInfo(SCHEDULER_TIMEZONE_NAME)


@dataclass(frozen=True)
class SchedulerJobSpec:
    id: str
    label: str
    description: str
    trigger_kwargs: dict[str, object]
    scheduler_kwargs: dict[str, object] = field(default_factory=dict)

    def build_trigger(self) -> CronTrigger:
        return CronTrigger(timezone=SCHEDULER_TIMEZONE, **self.trigger_kwargs)


@dataclass(frozen=True)
class ScheduledRun:
    job_id: str
    job_label: str
    description: str
    scheduled_at: datetime


SCHEDULER_JOB_SPECS: tuple[SchedulerJobSpec, ...] = (
    SchedulerJobSpec(
        id="quarter_hour_job",
        label="Quarter hour",
        description="Import vodomeru, scoring, eventy a alerting.",
        trigger_kwargs={"minute": "5,16,35,50", "second": 5},
    ),
    SchedulerJobSpec(
        id="hourly_job",
        label="Hourly",
        description="Import SCVK vodomeru.",
        trigger_kwargs={"minute": 2, "second": 5},
        scheduler_kwargs={"max_instances": 1},
    ),
    SchedulerJobSpec(
        id="daily_seven_and_two_job",
        label="Daily 7 and 14",
        description="Web search monitoring.",
        trigger_kwargs={"hour": "7,14", "minute": 0, "second": 5},
    ),
    SchedulerJobSpec(
        id="daily_job",
        label="Daily midnight",
        description="SOFTLINK import a meteo sync.",
        trigger_kwargs={"hour": 0, "minute": 15, "second": 5},
    ),
    SchedulerJobSpec(
        id="daily_vodomery_branch_report_job",
        label="Daily vodomery branch report",
        description="Denni PDF report vetvi vodomeru emailem.",
        trigger_kwargs={"hour": 6, "minute": 0, "second": 5},
    ),
    SchedulerJobSpec(
        id="weekly_job",
        label="Weekly",
        description="Rebuild prediction profilu.",
        trigger_kwargs={"day_of_week": "mon", "hour": 6, "minute": 10, "second": 5},
    ),
    SchedulerJobSpec(
        id="smartfuelpass_weekly_report_job",
        label="SmartFuelPass weekly report",
        description="Tydenni SmartFuelPass PDF report emailem.",
        trigger_kwargs={"day_of_week": "tue", "hour": 6, "minute": 55, "second": 5},
    ),
    SchedulerJobSpec(
        id="monthly_job",
        label="Monthly",
        description="Mesicni reporty spotreb.",
        trigger_kwargs={"day": 1, "hour": 6, "minute": 20, "second": 5},
    ),
)


def get_scheduler_job_specs() -> tuple[SchedulerJobSpec, ...]:
    return SCHEDULER_JOB_SPECS


def build_schedule_runs(
    *,
    window_start: datetime | None = None,
    hours: int = 24,
) -> list[ScheduledRun]:
    resolved_start = window_start or datetime.now(SCHEDULER_TIMEZONE)
    if resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=SCHEDULER_TIMEZONE)
    else:
        resolved_start = resolved_start.astimezone(SCHEDULER_TIMEZONE)

    window_end = resolved_start + timedelta(hours=hours)
    runs: list[ScheduledRun] = []

    for job_spec in get_scheduler_job_specs():
        trigger = job_spec.build_trigger()
        previous_fire_time = None
        current_point = resolved_start

        while True:
            next_fire_time = trigger.get_next_fire_time(previous_fire_time, current_point)
            if next_fire_time is None or next_fire_time > window_end:
                break
            runs.append(
                ScheduledRun(
                    job_id=job_spec.id,
                    job_label=job_spec.label,
                    description=job_spec.description,
                    scheduled_at=next_fire_time,
                )
            )
            previous_fire_time = next_fire_time
            current_point = next_fire_time + timedelta(microseconds=1)

    return sorted(runs, key=lambda item: (item.scheduled_at, item.job_id))
