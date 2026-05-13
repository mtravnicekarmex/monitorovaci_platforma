"""
Scheduler pro automatizované úlohy monitorovací platformy.

Tento modul obsahuje implementace jednotlivých jobů a registraci do APScheduleru.
Časování jobů je centralizované v ``core.scheduler.job_schedule``.
"""

import html
import os
import sys
from datetime import datetime
from dataclasses import dataclass
from functools import wraps
from moduly.mereni.vodomery.SCVK.SCVK_to_database import SCVK_save_to_database_all
from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_to_database import SOFTLINK_to_database_mereni
from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_data_z_dotazu import SOFTLINK_dotaz
from core.db.connect import get_session_pg
from moduly.apps.web_search.service import hledat_nove_vyskyt, notify_new_results_for_monitor
from moduly.apps.web_search.database.models import *
import json
import threading
import time
import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED
from app.channels.email import send_email_outlook
from app.time_utils import utc_now_naive
from core.scheduler.job_schedule import SCHEDULER_TIMEZONE_NAME, get_scheduler_job_specs
from core.scheduler.metrics import SCHEDULER_HEARTBEAT_TTL_SECONDS, get_metrics_store
from decouple import config
from moduly.mereni.vodomery.database.vodomery_db_vse import vodomery_db_import
from moduly.mereni.elektromery.database.elektromery_db_vse import elektromery_db_import
from moduly.mereni.elektromery.database.binary_ts_import import sync_changed_binary_meter_sources
from moduly.mereni.vodomery.vodomery_prediction import (
    get_candidate_model_versions,
    get_runtime_model_version,
    rebuild_profiles,
)
from moduly.mereni.vodomery.vodomery_anomaly import score_new_measurements
from moduly.mereni.vodomery.alerting import process_vodomery_alerts
from moduly.mereni.vodomery.reporting import (
    send_daily_vodomery_branch_report,
    send_daily_vodomery_billing_summary_report,
    send_weekly_vodomery_branch_report,
    send_weekly_vodomery_billing_summary_report,
    send_monthly_vodomery_branch_report,
    send_monthly_vodomery_billing_summary_report,
    send_monthly_b1_consumption_report,
    send_vodomery_model_rebuild_report,
    send_monthly_vodomery_consumption_report,
)
from moduly.mereni.elektromery.reporting import (
    send_monthly_elektromery_branch_report,
    send_weekly_elektromery_branch_report,
)
from moduly.mereni.elektromery.softlink_devices import send_weekly_new_elektromery_report
from moduly.mereni.vodomery.vodomery_events import detect_events_from_scores
from moduly.mereni.plynomery.database.plynomery_db_vse import plynomery_db_import
from moduly.mereni.plynomery.plynomery_anomaly import score_new_measurements as score_new_plynomery_measurements
from moduly.mereni.plynomery.plynomery_prediction import (
    get_candidate_model_versions as get_plynomery_candidate_model_versions,
    get_runtime_model_version as get_plynomery_runtime_model_version,
    rebuild_profiles as rebuild_plynomery_profiles,
)
from moduly.mereni.plynomery.plynomery_events import detect_events_from_scores as detect_plynomery_events_from_scores
from moduly.mereni.plynomery.alerting import process_plynomery_alerts
from moduly.mereni.plynomery.reporting import send_plynomery_model_rebuild_report
from moduly.apps.meteo.meteo_sync import meteo_sync
from moduly.apps.smartfuelpass import send_charge_sessions_report_email, sync_charge_sessions_to_db

if os.name == "nt":
    import msvcrt
else:
    import fcntl


# -------------------------
# Logger
# -------------------------

SCHEDULER_DIR = Path(__file__).resolve().parent
SCHEDULER_LOGS_DIR = SCHEDULER_DIR / "logs"
SCHEDULER_LOCKS_DIR = SCHEDULER_DIR / "locks"
SCHEDULER_LOG_PATH = SCHEDULER_LOGS_DIR / "scheduler.log"
SCHEDULER_MISFIRE_GRACE_SECONDS = config("SCHEDULER_MISFIRE_GRACE_SECONDS", default=900, cast=int)


def setup_logging(*, enable_file: bool = False):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    has_console_handler = any(
        isinstance(handler, logging.StreamHandler) and getattr(handler, "stream", None) is sys.stdout
        for handler in logger.handlers
    )
    if not has_console_handler:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if enable_file:
        SCHEDULER_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        has_file_handler = any(
            isinstance(handler, TimedRotatingFileHandler)
            and Path(getattr(handler, "baseFilename", "")).resolve() == SCHEDULER_LOG_PATH.resolve()
            for handler in logger.handlers
        )
        if not has_file_handler:
            file_handler = TimedRotatingFileHandler(
                SCHEDULER_LOG_PATH,
                when="midnight",
                interval=1,
                backupCount=14,
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    # potlačí SQLAlchemy spam
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return logging.getLogger(__name__)


logger = setup_logging()




# -------------------------
# Job listeners
# -------------------------


@dataclass(frozen=True)
class SkippedJobResult:
    reason: str
    lock_names: tuple[str, ...]


@dataclass(frozen=True)
class ManualJobTriggerResult:
    job_id: str
    status: str
    detail: str
    requested_at: datetime


@dataclass(frozen=True)
class ManualRunnableSpec:
    id: str
    label: str
    description: str
    run_fn: object
    lock_names: tuple[str, ...]
    is_scheduled: bool
    kind: str


@dataclass(frozen=True)
class _ProcessLockHandle:
    lock_name: str
    lock_path: Path
    file_handle: object


@dataclass(frozen=True)
class _AcquiredJobLocks:
    lock_names: tuple[str, ...]
    thread_locks: tuple[object, ...]
    process_locks: tuple[_ProcessLockHandle, ...]


class SchedulerContextError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        alert_targets=(),
        alert_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.alert_targets = _normalize_alert_targets(alert_targets)
        self.alert_reason = alert_reason.strip() if isinstance(alert_reason, str) else alert_reason


def _normalize_alert_targets(targets) -> tuple[str, ...]:
    if not targets:
        return ()

    normalized_targets = []
    for target in targets:
        target_text = str(target).strip()
        if target_text and target_text not in normalized_targets:
            normalized_targets.append(target_text)

    return tuple(normalized_targets)


def _format_scheduler_reason(error) -> str | None:
    if error is None:
        return None
    explicit_reason = getattr(error, "alert_reason", None)
    if isinstance(explicit_reason, str):
        explicit_reason = explicit_reason.strip()
        if explicit_reason:
            return explicit_reason
    reason = str(error).strip()
    if reason:
        return reason
    return type(error).__name__


def _format_scheduler_time(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        try:
            value = value.astimezone()
        except ValueError:
            pass
        return value.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    return str(value)


def _extract_scheduler_targets(error) -> tuple[str, ...]:
    return _normalize_alert_targets(getattr(error, "alert_targets", ()))


def _format_monitor_failures(failures, *, max_items: int = 5) -> str:
    if not failures:
        return "-"

    parts = []
    for target, reason in failures[:max_items]:
        if reason:
            parts.append(f"{target} ({reason})")
        else:
            parts.append(target)

    remaining = len(failures) - max_items
    if remaining > 0:
        parts.append(f"... a dalsich {remaining}")

    return "; ".join(parts)


def _build_scheduler_alert_body(
    *,
    job_id: str,
    status_text: str,
    description: str,
    scheduled_time,
    reason: str | None = None,
    targets: tuple[str, ...] = (),
) -> str:
    value_cell_style = (
        "padding:6px 10px;border:1px solid #d0d7de;background:#ffffff;color:#1f2328;"
    )
    label_cell_style = (
        "padding:6px 10px;border:1px solid #d0d7de;background:#f6f8fa;color:#1f2328;"
    )
    detail_rows = [
        ("Job", job_id),
        ("Stav", status_text),
        ("Planovany cas", _format_scheduler_time(scheduled_time)),
        ("Detekovano", _format_scheduler_time(datetime.now().astimezone())),
    ]

    row_html = "".join(
        (
            "<tr>"
            f"<td style='{label_cell_style}'><strong>{html.escape(label)}</strong></td>"
            f"<td style='{value_cell_style}'>{html.escape(value)}</td>"
            "</tr>"
        )
        for label, value in detail_rows
    )

    reason_html = ""
    if reason:
        reason_html = (
            "<div style='margin:16px 0 0;padding:12px;border:1px solid #d0d7de;background:#ffffff;color:#1f2328;'>"
            "<p style='margin:0 0 6px;'><strong>Duvod</strong></p>"
            f"<p style='margin:0;'>{html.escape(reason)}</p>"
            "</div>"
        )

    targets_html = ""
    if targets:
        target_items = "".join(
            f"<li>{html.escape(target)}</li>"
            for target in targets
        )
        targets_html = (
            "<div style='margin:16px 0 0;padding:12px;border:1px solid #d0d7de;background:#ffffff;color:#1f2328;'>"
            "<p style='margin:0 0 6px;'><strong>Cile</strong></p>"
            f"<ul style='margin:0 0 0 18px;padding:0;color:#1f2328;'>{target_items}</ul>"
            "</div>"
        )

    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;background:#ffffff;color:#1f2328;'>"
        "<h2 style='margin:0 0 12px;'>Scheduler alert</h2>"
        f"<p style='margin:0 0 16px;'>{html.escape(description)}</p>"
        "<table style='border-collapse:collapse;font-size:14px;background:#ffffff;color:#1f2328;'>"
        f"{row_html}"
        "</table>"
        f"{reason_html}"
        f"{targets_html}"
        "</body></html>"
    )


def _send_scheduler_alert(
    *,
    job_id: str,
    status_text: str,
    description: str,
    scheduled_time,
    reason: str | None = None,
    targets: tuple[str, ...] = (),
) -> None:
    body = _build_scheduler_alert_body(
        job_id=job_id,
        status_text=status_text,
        description=description,
        scheduled_time=scheduled_time,
        reason=reason,
        targets=targets,
    )

    send_email_outlook(
        email_receiver=config('MY_EMAIL'),
        sender_alias=config('O_EMAIL_ALARM'),
        subject=f"[ALERT] Scheduler | {job_id} | {status_text.upper()}",
        body=body,
        is_html=True,
    )


def _deliver_scheduler_alert(**kwargs) -> None:
    try:
        _send_scheduler_alert(**kwargs)
    except Exception as alert_error:
        logger.error(
            "SCHEDULER ALERT FAILED | id=%s | scheduled=%s | reason=%s",
            kwargs.get("job_id"),
            kwargs.get("scheduled_time"),
            _format_scheduler_reason(alert_error),
            exc_info=True,
        )


def job_success_listener(event):
    metrics = get_metrics_store()
    try:
        if isinstance(event.retval, SkippedJobResult):
            metrics.record_job_skipped(event.job_id, event.retval.reason)
            _sync_job_next_run(event.job_id)
            logger.warning(
                "JOB SKIPPED | id=%s | scheduled=%s | reason=%s | locks=%s",
                event.job_id,
                event.scheduled_run_time,
                event.retval.reason,
                ",".join(event.retval.lock_names),
            )
            return
        metrics.record_job_success(event.job_id)
        _sync_job_next_run(event.job_id)
        logger.info(
            "JOB SUCCESS | id=%s | scheduled=%s",
            event.job_id,
            event.scheduled_run_time
        )
    except Exception as e:
        logger.error("JOB SUCCESS LISTENER FAILED | id=%s | reason=%s", event.job_id, e, exc_info=True)



def job_error_listener(event):
    metrics = get_metrics_store()
    if event.exception:
        metrics.record_job_error(event.job_id)
        _sync_job_next_run(event.job_id)
        reason = _format_scheduler_reason(event.exception)
        targets = _extract_scheduler_targets(event.exception)
        log_message = "JOB ERROR | id=%s | scheduled=%s | reason=%s"
        log_args = [
            event.job_id,
            event.scheduled_run_time,
            reason or "-",
        ]
        if targets:
            log_message += " | targets=%s"
            log_args.append(",".join(targets))

        event_traceback = (getattr(event, "traceback", None) or "").strip()
        if event_traceback:
            log_message = f"{log_message}\n%s"
            log_args.append(event_traceback)

        logger.error(log_message, *log_args)

        _deliver_scheduler_alert(
            job_id=event.job_id,
            status_text="spadl",
            description="Naplanovany job scheduleru skoncil chybou a vyzaduje kontrolu.",
            scheduled_time=event.scheduled_run_time,
            reason=reason,
            targets=targets,
        )

    elif event.code == EVENT_JOB_MISSED:
        metrics.record_job_error(event.job_id)
        _sync_job_next_run(event.job_id)
        logger.error(
            "JOB MISSED | id=%s | scheduled=%s",
            event.job_id,
            event.scheduled_run_time
        )

        _deliver_scheduler_alert(
            job_id=event.job_id,
            status_text="nebyl spusten",
            description="Job scheduleru nebyl spusten v planovanem case.",
            scheduled_time=event.scheduled_run_time,
            reason="job byl zmeskan (misfire)",
        )


def job_max_instances_listener(event):
    get_metrics_store().record_job_skipped(event.job_id, "max_instances")
    _sync_job_next_run(event.job_id)
    logger.warning(
        "JOB SKIPPED | id=%s | scheduled=%s | reason=max_instances",
        event.job_id,
        ",".join(str(run_time) for run_time in event.scheduled_run_times),
    )



def SOFTLINK_save_to_database_all():
    SOFTLINK_to_database_mereni(SOFTLINK_dotaz())


def daily_web_monitor_job():
    session = get_session_pg()
    failures = []
    failure_causes = []

    try:
        monitory = session.query(Monitor).all()
        for monitor in monitory:
            try:
                vyrazy = json.loads(monitor.vyrazy)
                if not vyrazy:
                    monitor.last_run =utc_now_naive()
                    session.commit()
                    continue

                # Hledání nových výskytů
                nove_vyskyt = hledat_nove_vyskyt(monitor, vyrazy, session)

                # Aktualizace last_run vždy
                monitor.last_run = utc_now_naive()

                if nove_vyskyt:
                    notified_count = notify_new_results_for_monitor(session, monitor, nove_vyskyt)
                    logger.info(f'Nové výskyty na "{monitor.url}": {notified_count}')

                session.commit()

            except Exception as exc:
                session.rollback()  # reset session po chybě v transakci
                failures.append((monitor.url, _format_scheduler_reason(exc)))
                failure_causes.append(exc)

        if failures:
            failure_summary = _format_monitor_failures(failures)
            error = SchedulerContextError(
                f"Web monitor selhal pro {len(failures)} cil(e): {failure_summary}",
                alert_targets=tuple(url for url, _ in failures),
                alert_reason=failure_summary,
            )
            if len(failure_causes) == 1:
                raise error from failure_causes[0]
            raise error

    finally:
        session.close()

    logger.info("Web monitor job dokončen")







def safe_call(fn, *args, **kwargs):
    start = time.time()
    try:
        logger.info("START %s", fn.__name__)
        result = fn(*args, **kwargs)
        get_metrics_store().record_job_success(fn.__name__, round(time.time() - start, 2))
        return result
    except SchedulerContextError:
        get_metrics_store().record_job_error(fn.__name__, round(time.time() - start, 2))
        raise
    except Exception as exc:
        get_metrics_store().record_job_error(fn.__name__, round(time.time() - start, 2))
        raise SchedulerContextError(
            f"Selhal krok '{fn.__name__}'",
            alert_targets=(fn.__name__,),
            alert_reason=_format_scheduler_reason(exc),
        ) from exc
    finally:
        duration = round(time.time() - start, 2)
        logger.info("DONE %s | duration=%ss", fn.__name__, duration)




# -------------------------
# Wrapper pro zamezení paralelního běhu
# -------------------------
def _resolve_job_lock_names(fn, decorator_lock_names=()) -> tuple[str, ...]:
    configured_lock_names = tuple(decorator_lock_names or ())
    if configured_lock_names:
        return tuple(dict.fromkeys(configured_lock_names))

    existing_lock_names = tuple(getattr(fn, "__scheduler_lock_names__", ()) or ())
    if existing_lock_names:
        return tuple(dict.fromkeys(existing_lock_names))

    return (fn.__name__,)


def _build_locked_job(fn, decorator_lock_names):
    resolved_lock_names = _resolve_job_lock_names(fn, decorator_lock_names)

    @wraps(fn)
    def wrapper(*args, **kwargs):
        acquired_locks = _try_acquire_job_locks(resolved_lock_names)
        if acquired_locks is None:
            return SkippedJobResult(reason="lock_busy", lock_names=resolved_lock_names)
        try:
            return fn(*args, **kwargs)
        finally:
            _release_job_locks(acquired_locks)

    wrapper.__scheduler_lock_names__ = resolved_lock_names
    wrapper.__scheduler_unlocked_fn__ = fn
    return wrapper


def locked_job(*decorator_args):
    if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1:
        return _build_locked_job(decorator_args[0], ())
    return lambda fn: _build_locked_job(fn, decorator_args)







# -------------------------
# Definice jednotlivých jobů
# -------------------------
#
# Přesné časy běhu jsou definované v `core.scheduler.job_schedule`.

# Import vodomeru, scoring, eventy a alerting.
@locked_job
def quarter_hour_job():
    safe_call(vodomery_db_import)
    active_model_version = safe_call(get_runtime_model_version)
    active_event_result = {
        "active_event_ids": [],
        "resolved_event_ids": [],
    }

    for model_version in get_candidate_model_versions():
        safe_call(
            score_new_measurements,
            model_version=model_version,
            bootstrap_to_latest_if_missing=True,
        )
        event_result = safe_call(
            detect_events_from_scores,
            model_version=model_version,
            bootstrap_to_latest_if_missing=True,
        )
        if model_version == active_model_version:
            active_event_result = event_result

    safe_call(
        process_vodomery_alerts,
        active_event_ids=active_event_result.get("active_event_ids", []),
        resolved_event_ids=active_event_result.get("resolved_event_ids", []),
    )
    safe_call(plynomery_db_import)
    active_plynomery_model_version = safe_call(get_plynomery_runtime_model_version)
    active_plynomery_event_result = {
        "active_event_ids": [],
        "resolved_event_ids": [],
    }
    for model_version in get_plynomery_candidate_model_versions():
        safe_call(
            score_new_plynomery_measurements,
            model_version=model_version,
            bootstrap_to_latest_if_missing=True,
        )
        plynomery_event_result = safe_call(
            detect_plynomery_events_from_scores,
            model_version=model_version,
            bootstrap_to_latest_if_missing=True,
        )
        if model_version == active_plynomery_model_version:
            active_plynomery_event_result = plynomery_event_result
    safe_call(
        process_plynomery_alerts,
        active_event_ids=active_plynomery_event_result.get("active_event_ids", []),
        resolved_event_ids=active_plynomery_event_result.get("resolved_event_ids", []),
    )


# Hodinový import SCVK vodoměrů.
@locked_job
def hourly_job():
    safe_call(SCVK_save_to_database_all)


# Denní web monitoring.
@locked_job
def daily_seven_and_two_job():
    safe_call(daily_web_monitor_job)


# Nocni SOFTLINK import, elektromery import, synchronizace meteo dat a SmartFuelPass relaci.
@locked_job
def daily_job():
    safe_call(SOFTLINK_save_to_database_all)
    safe_call(elektromery_db_import)
    safe_call(sync_changed_binary_meter_sources)
    safe_call(meteo_sync)
    safe_call(sync_charge_sessions_to_db)


# Denní email report větví vodoměrů.
@locked_job
def daily_vodomery_branch_report_job():
    safe_call(send_daily_vodomery_branch_report)
    safe_call(send_daily_vodomery_billing_summary_report)


# Týdenní rebuild profilů vodoměrů i plynoměrů a report větví vodoměrů.
@locked_job
def weekly_job():
    rebuild_result = safe_call(rebuild_profiles)
    plynomery_rebuild_result = safe_call(rebuild_plynomery_profiles)
    safe_call(send_vodomery_model_rebuild_report, rebuild_result)
    safe_call(send_plynomery_model_rebuild_report, plynomery_rebuild_result)
    safe_call(send_weekly_vodomery_branch_report)
    safe_call(send_weekly_vodomery_billing_summary_report)
    safe_call(send_weekly_elektromery_branch_report)
    safe_call(send_weekly_new_elektromery_report)


# Týdenní email report SmartFuelPass.
@locked_job
def smartfuelpass_weekly_report_job():
    safe_call(send_charge_sessions_report_email)


# Měsíční reporty spotřeb.
@locked_job
def monthly_job():
    safe_call(send_monthly_vodomery_consumption_report)
    safe_call(send_monthly_vodomery_branch_report)
    safe_call(send_monthly_vodomery_billing_summary_report)
    safe_call(send_monthly_b1_consumption_report)
    safe_call(send_monthly_elektromery_branch_report)


def _run_vodomery_scoring_step() -> None:
    for model_version in get_candidate_model_versions():
        score_new_measurements(
            model_version=model_version,
            bootstrap_to_latest_if_missing=True,
        )


def _run_vodomery_event_detection_step() -> None:
    for model_version in get_candidate_model_versions():
        detect_events_from_scores(
            model_version=model_version,
            bootstrap_to_latest_if_missing=True,
        )


def _run_vodomery_alerting_step() -> None:
    active_model_version = get_runtime_model_version()
    score_new_measurements(
        model_version=active_model_version,
        bootstrap_to_latest_if_missing=True,
    )
    event_result = detect_events_from_scores(
        model_version=active_model_version,
        bootstrap_to_latest_if_missing=True,
    )
    process_vodomery_alerts(
        active_event_ids=event_result.get("active_event_ids", []),
        resolved_event_ids=event_result.get("resolved_event_ids", []),
    )


def _run_plynomery_scoring_step() -> None:
    for model_version in get_plynomery_candidate_model_versions():
        score_new_plynomery_measurements(
            model_version=model_version,
            bootstrap_to_latest_if_missing=True,
        )


def _run_plynomery_event_detection_step() -> None:
    for model_version in get_plynomery_candidate_model_versions():
        detect_plynomery_events_from_scores(
            model_version=model_version,
            bootstrap_to_latest_if_missing=True,
        )


def _run_plynomery_alerting_step() -> None:
    active_model_version = get_plynomery_runtime_model_version()
    score_new_plynomery_measurements(
        model_version=active_model_version,
        bootstrap_to_latest_if_missing=True,
    )
    event_result = detect_plynomery_events_from_scores(
        model_version=active_model_version,
        bootstrap_to_latest_if_missing=True,
    )
    process_plynomery_alerts(
        active_event_ids=event_result.get("active_event_ids", []),
        resolved_event_ids=event_result.get("resolved_event_ids", []),
    )


def _run_vodomery_model_rebuild_report_step() -> None:
    rebuild_result = rebuild_profiles()
    send_vodomery_model_rebuild_report(rebuild_result)


def _run_plynomery_model_rebuild_report_step() -> None:
    rebuild_result = rebuild_plynomery_profiles()
    send_plynomery_model_rebuild_report(rebuild_result)


def _get_job_functions():
    return {
        "quarter_hour_job": quarter_hour_job,
        "hourly_job": hourly_job,
        "daily_seven_and_two_job": daily_seven_and_two_job,
        "daily_job": daily_job,
        "daily_vodomery_branch_report_job": daily_vodomery_branch_report_job,
        "weekly_job": weekly_job,
        "smartfuelpass_weekly_report_job": smartfuelpass_weekly_report_job,
        "monthly_job": monthly_job,
    }


def _get_manual_run_specs() -> dict[str, ManualRunnableSpec]:
    manual_specs: dict[str, ManualRunnableSpec] = {}

    job_functions = _get_job_functions()
    for job_spec in get_scheduler_job_specs():
        job_fn = job_functions[job_spec.id]
        manual_specs[job_spec.id] = ManualRunnableSpec(
            id=job_spec.id,
            label=job_spec.label,
            description=job_spec.description,
            run_fn=getattr(job_fn, "__scheduler_unlocked_fn__", job_fn),
            lock_names=_resolve_job_lock_names(job_fn),
            is_scheduled=True,
            kind="job",
        )

    internal_step_specs = (
        ManualRunnableSpec(
            id="vodomery_db_import",
            label="Import vodomeru",
            description="Import aktualnich vodomernych mereni do databaze.",
            run_fn=vodomery_db_import,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="get_runtime_model_version",
            label="Aktivni model vodomeru",
            description="Nacteni aktivni runtime verze modelu vodomeru.",
            run_fn=get_runtime_model_version,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="score_new_measurements",
            label="Scoring vodomeru",
            description="Scoring novych vodomernych mereni pro vsechny kandidacni modely.",
            run_fn=_run_vodomery_scoring_step,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="detect_events_from_scores",
            label="Detekce eventu vodomeru",
            description="Detekce eventu z naskorovanych vodomernych mereni pro vsechny kandidacni modely.",
            run_fn=_run_vodomery_event_detection_step,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="process_vodomery_alerts",
            label="Zpracovani alertu vodomeru",
            description="Zpracovani vodomernych alertu pro aktivni model vcetne potrebneho score a event detection.",
            run_fn=_run_vodomery_alerting_step,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="plynomery_db_import",
            label="Import plynomeru",
            description="Import aktualnich plynomernych mereni do databaze.",
            run_fn=plynomery_db_import,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="get_plynomery_runtime_model_version",
            label="Aktivni model plynomeru",
            description="Nacteni aktivni runtime verze modelu plynomeru.",
            run_fn=get_plynomery_runtime_model_version,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="score_new_plynomery_measurements",
            label="Scoring plynomeru",
            description="Scoring novych plynomernych mereni pro vsechny kandidacni modely.",
            run_fn=_run_plynomery_scoring_step,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="detect_plynomery_events_from_scores",
            label="Detekce eventu plynomeru",
            description="Detekce eventu z naskorovanych plynomernych mereni pro vsechny kandidacni modely.",
            run_fn=_run_plynomery_event_detection_step,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="process_plynomery_alerts",
            label="Zpracovani alertu plynomeru",
            description="Zpracovani plynomernych alertu pro aktivni model vcetne potrebneho score a event detection.",
            run_fn=_run_plynomery_alerting_step,
            lock_names=("quarter_hour_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="SCVK_save_to_database_all",
            label="Import SCVK vodomeru",
            description="Hodinovy import SCVK vodomernych dat do databaze.",
            run_fn=SCVK_save_to_database_all,
            lock_names=("hourly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="daily_web_monitor_job",
            label="Web monitoring",
            description="Denni kontrola monitorovanych webu a notifikace novych vyskytu.",
            run_fn=daily_web_monitor_job,
            lock_names=("daily_seven_and_two_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="SOFTLINK_save_to_database_all",
            label="Import SOFTLINK elektromeru",
            description="Nocni import elektromernych dat ze SOFTLINKu do databaze.",
            run_fn=SOFTLINK_save_to_database_all,
            lock_names=("daily_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="elektromery_db_import",
            label="Import elektromeru vse",
            description="Denní import SOFTLINK a OTE elektromernych dat do monitoring.Mereni_elektromery_vse.",
            run_fn=elektromery_db_import,
            lock_names=("daily_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="elektromery_binary_import",
            label="Import binarnich elektromeru",
            description="Kontrola binarnich elektromernych souboru a import zmenenych zdroju do monitoring.Mereni_elektromery_vse.",
            run_fn=sync_changed_binary_meter_sources,
            lock_names=("daily_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="meteo_sync",
            label="Synchronizace meteo dat",
            description="Synchronizace meteorologickych dat pro dalsi vyhodnoceni.",
            run_fn=meteo_sync,
            lock_names=("daily_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_daily_vodomery_branch_report",
            label="Denni report vetvi vodomeru",
            description="Odeslani denniho email reportu vetvi vodomeru.",
            run_fn=send_daily_vodomery_branch_report,
            lock_names=("daily_vodomery_branch_report_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_daily_vodomery_billing_summary_report",
            label="Denni souhrn SCVK vs. odberna mista",
            description="Odeslani denniho souhrnneho reportu SČVK vodomeru proti odbernym mistum.",
            run_fn=send_daily_vodomery_billing_summary_report,
            lock_names=("daily_vodomery_branch_report_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="rebuild_profiles",
            label="Rebuild modelu vodomeru",
            description="Tydenni rebuild profilu a modelovych podkladu pro vodomery.",
            run_fn=rebuild_profiles,
            lock_names=("weekly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="rebuild_plynomery_profiles",
            label="Rebuild modelu plynomeru",
            description="Tydenni rebuild profilu a modelovych podkladu pro plynomery.",
            run_fn=rebuild_plynomery_profiles,
            lock_names=("weekly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_vodomery_model_rebuild_report",
            label="Report rebuildu vodomeru",
            description="Odeslani reportu z rebuildu vodomeru vcetne pripravy potrebnych vystupu.",
            run_fn=_run_vodomery_model_rebuild_report_step,
            lock_names=("weekly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_plynomery_model_rebuild_report",
            label="Report rebuildu plynomeru",
            description="Odeslani reportu z rebuildu plynomeru vcetne pripravy potrebnych vystupu.",
            run_fn=_run_plynomery_model_rebuild_report_step,
            lock_names=("weekly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_weekly_vodomery_branch_report",
            label="Tydenni report vetvi vodomeru",
            description="Odeslani tydenniho email reportu vetvi vodomeru.",
            run_fn=send_weekly_vodomery_branch_report,
            lock_names=("weekly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_weekly_vodomery_billing_summary_report",
            label="Tydenni souhrn SCVK vs. odberna mista",
            description="Odeslani tydenniho souhrnneho reportu SČVK vodomeru proti odbernym mistum.",
            run_fn=send_weekly_vodomery_billing_summary_report,
            lock_names=("weekly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_weekly_elektromery_branch_report",
            label="Tydenni report elektromeru",
            description="Odeslani tydenniho email reportu spotreby elektromeru po trafostanicich.",
            run_fn=send_weekly_elektromery_branch_report,
            lock_names=("weekly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_weekly_new_elektromery_report",
            label="Tydenni kontrola novych elektromeru",
            description="Kontrola novych SOFTLINK zarizeni a odeslani email reportu.",
            run_fn=send_weekly_new_elektromery_report,
            lock_names=("weekly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_charge_sessions_report_email",
            label="Tydenni report SmartFuelPass",
            description="Odeslani tydenniho email reportu SmartFuelPass.",
            run_fn=send_charge_sessions_report_email,
            lock_names=("smartfuelpass_weekly_report_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_monthly_vodomery_consumption_report",
            label="Mesicni report spotreby vodomeru",
            description="Odeslani mesicniho reportu spotreby vodomeru.",
            run_fn=send_monthly_vodomery_consumption_report,
            lock_names=("monthly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_monthly_vodomery_branch_report",
            label="Mesicni report vetvi vodomeru",
            description="Odeslani mesicniho reportu vetvi vodomeru.",
            run_fn=send_monthly_vodomery_branch_report,
            lock_names=("monthly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_monthly_vodomery_billing_summary_report",
            label="Mesicni souhrn SCVK vs. odberna mista",
            description="Odeslani mesicniho souhrnneho reportu SČVK vodomeru proti odbernym mistum.",
            run_fn=send_monthly_vodomery_billing_summary_report,
            lock_names=("monthly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_monthly_b1_consumption_report",
            label="Mesicni report spotreby B1",
            description="Odeslani mesicniho reportu spotreby objektu B1.",
            run_fn=send_monthly_b1_consumption_report,
            lock_names=("monthly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
        ManualRunnableSpec(
            id="send_monthly_elektromery_branch_report",
            label="Mesicni report elektromeru",
            description="Odeslani mesicniho email reportu spotreby elektromeru po trafostanicich.",
            run_fn=send_monthly_elektromery_branch_report,
            lock_names=("monthly_job",),
            is_scheduled=False,
            kind="internal_step",
        ),
    )

    manual_specs.update({spec.id: spec for spec in internal_step_specs})
    return manual_specs


def get_manual_run_specs() -> dict[str, ManualRunnableSpec]:
    return _get_manual_run_specs()


def _run_manual_job(manual_spec: ManualRunnableSpec, *, requested_at: datetime) -> None:
    metrics = get_metrics_store()
    started_at = datetime.now().astimezone()
    start = time.time()
    logger.info(
        "JOB MANUAL START | id=%s | requested=%s | started=%s",
        manual_spec.id,
        requested_at,
        started_at,
    )

    try:
        result = manual_spec.run_fn()
        duration = round(time.time() - start, 2)
        if isinstance(result, SkippedJobResult):
            metrics.record_job_skipped(manual_spec.id, result.reason)
            _sync_job_next_run(manual_spec.id)
            logger.warning(
                "JOB MANUAL SKIPPED | id=%s | reason=%s | locks=%s",
                manual_spec.id,
                result.reason,
                ",".join(result.lock_names),
            )
            return

        metrics.record_job_success(manual_spec.id, duration)
        _sync_job_next_run(manual_spec.id)
        logger.info(
            "JOB MANUAL SUCCESS | id=%s | duration=%ss",
            manual_spec.id,
            duration,
        )
    except Exception as exc:
        duration = round(time.time() - start, 2)
        metrics.record_job_error(manual_spec.id, duration)
        _sync_job_next_run(manual_spec.id)
        reason = _format_scheduler_reason(exc)
        targets = _extract_scheduler_targets(exc)
        logger.error(
            "JOB MANUAL ERROR | id=%s | requested=%s | duration=%ss | reason=%s",
            manual_spec.id,
            requested_at,
            duration,
            reason or "-",
            exc_info=True,
        )
        _deliver_scheduler_alert(
            job_id=manual_spec.id,
            status_text="manual run error",
            description="Rucne spusteny job scheduleru skoncil chybou.",
            scheduled_time=requested_at,
            reason=reason,
            targets=targets,
        )


def _run_manual_job_worker(
    manual_spec: ManualRunnableSpec,
    acquired_locks: _AcquiredJobLocks,
    *,
    requested_at: datetime,
) -> None:
    try:
        _run_manual_job(manual_spec, requested_at=requested_at)
    finally:
        _release_job_locks(acquired_locks)


def trigger_manual_job(job_id: str) -> ManualJobTriggerResult:
    manual_spec = get_manual_run_specs().get(job_id)
    if manual_spec is None:
        raise KeyError(job_id)

    requested_at = datetime.now().astimezone()
    acquired_locks = _try_acquire_job_locks(manual_spec.lock_names)
    if acquired_locks is None:
        return ManualJobTriggerResult(
            job_id=job_id,
            status="busy",
            detail="Job uz prave bezi nebo ceka na uvolneni sdileneho locku.",
            requested_at=requested_at,
        )

    worker = threading.Thread(
        target=_run_manual_job_worker,
        name=f"scheduler-manual-{job_id}",
        args=(manual_spec, acquired_locks),
        kwargs={"requested_at": requested_at},
        daemon=True,
    )

    try:
        worker.start()
    except Exception:
        _release_job_locks(acquired_locks)
        raise

    return ManualJobTriggerResult(
        job_id=job_id,
        status="started",
        detail="Jednorazovy manualni beh byl prijat a spusten na pozadi.",
        requested_at=requested_at,
    )














# -------------------------
# Hlavní funkce scheduleru
# -------------------------
def main_scheduler():
    global logger

    scheduler_process_lock = _try_acquire_process_lock("scheduler_process")
    if scheduler_process_lock is None:
        logger.warning("Scheduler uz bezi v jinem procesu; dalsi instance nebude spustena.")
        return

    try:
        logger = setup_logging(enable_file=True)
        _run_main_scheduler_loop()
    finally:
        _set_scheduler_instance(None)
        _release_process_lock(scheduler_process_lock)


def _run_main_scheduler_loop():
    scheduler = BackgroundScheduler(
        timezone=SCHEDULER_TIMEZONE_NAME,
        job_defaults={
            "coalesce": True,
            "misfire_grace_time": SCHEDULER_MISFIRE_GRACE_SECONDS,
            "max_instances": 1
        }
    )


    # -------------------------
    # Naplánování jobů podle centrální specifikace v core.scheduler.job_schedule
    # -------------------------
    job_functions = _get_job_functions()
    for job_spec in get_scheduler_job_specs():
        scheduler.add_job(
            job_functions[job_spec.id],
            job_spec.build_trigger(),
            id=job_spec.id,
            **job_spec.scheduler_kwargs,
        )



    # --- Listeners ---
    scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    scheduler.add_listener(job_success_listener, EVENT_JOB_EXECUTED)
    scheduler.add_listener(job_max_instances_listener, EVENT_JOB_MAX_INSTANCES)

    # --- Start scheduleru ---
    _set_scheduler_instance(scheduler)
    scheduler.start()
    scheduler_metrics = get_metrics_store()
    scheduler_metrics.mark_scheduler_started()
    _sync_all_job_next_runs()
    logger.info("Scheduler spuštěn")

    try:
        while True:
            scheduler_metrics.heartbeat()
            _sync_all_job_next_runs()
            time.sleep(SCHEDULER_HEARTBEAT_TTL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Ukončuji scheduler...")
        scheduler.shutdown()
        scheduler_metrics.mark_scheduler_stopped()
        _set_scheduler_instance(None)





# -------------------------
# Lock
# -------------------------
_LOCK_REGISTRY_GUARD = threading.Lock()
_JOB_LOCKS = {}
_SCHEDULER_INSTANCE = None


def _sanitize_lock_name(lock_name: str) -> str:
    return "".join(
        character if character.isalnum() or character in ("-", "_") else "_"
        for character in str(lock_name)
    )


def _lock_file_path(lock_name: str) -> Path:
    return SCHEDULER_LOCKS_DIR / f"{_sanitize_lock_name(lock_name)}.lock"


def _try_acquire_process_lock(lock_name: str) -> _ProcessLockHandle | None:
    SCHEDULER_LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_file_path(lock_name)
    file_handle = lock_path.open("a+b")

    try:
        file_handle.seek(0, 2)
        if file_handle.tell() == 0:
            file_handle.write(b"0")
            file_handle.flush()
        file_handle.seek(0)

        if os.name == "nt":
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        file_handle.close()
        return None

    return _ProcessLockHandle(
        lock_name=lock_name,
        lock_path=lock_path,
        file_handle=file_handle,
    )


def _release_process_lock(lock_handle: _ProcessLockHandle) -> None:
    try:
        lock_handle.file_handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(lock_handle.file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(lock_handle.file_handle.fileno(), fcntl.LOCK_UN)
    finally:
        lock_handle.file_handle.close()


def _try_acquire_job_locks(lock_names) -> _AcquiredJobLocks | None:
    resolved_lock_names = tuple(dict.fromkeys(sorted(lock_names or ())))
    acquired_thread_locks = []
    acquired_process_locks = []

    for lock_name in resolved_lock_names:
        thread_lock = _get_lock(lock_name)
        if not thread_lock.acquire(blocking=False):
            if acquired_thread_locks or acquired_process_locks:
                _release_job_locks(
                    _AcquiredJobLocks(
                        lock_names=resolved_lock_names,
                        thread_locks=tuple(acquired_thread_locks),
                        process_locks=tuple(acquired_process_locks),
                    )
                )
            return None
        acquired_thread_locks.append(thread_lock)

        process_lock = _try_acquire_process_lock(lock_name)
        if process_lock is None:
            _release_job_locks(
                _AcquiredJobLocks(
                    lock_names=resolved_lock_names,
                    thread_locks=tuple(acquired_thread_locks),
                    process_locks=tuple(acquired_process_locks),
                )
            )
            return None
        acquired_process_locks.append(process_lock)

    return _AcquiredJobLocks(
        lock_names=resolved_lock_names,
        thread_locks=tuple(acquired_thread_locks),
        process_locks=tuple(acquired_process_locks),
    )


def _release_job_locks(acquired_locks: _AcquiredJobLocks | None) -> None:
    if acquired_locks is None:
        return

    for process_lock in reversed(acquired_locks.process_locks):
        _release_process_lock(process_lock)
    for thread_lock in reversed(acquired_locks.thread_locks):
        thread_lock.release()


def _get_lock(lock_name):
    with _LOCK_REGISTRY_GUARD:
        job_lock = _JOB_LOCKS.get(lock_name)
        if job_lock is None:
            job_lock = threading.Lock()
            _JOB_LOCKS[lock_name] = job_lock
        return job_lock


def _set_scheduler_instance(scheduler_instance):
    global _SCHEDULER_INSTANCE
    _SCHEDULER_INSTANCE = scheduler_instance


def _sync_job_next_run(job_id: str) -> None:
    scheduler_instance = _SCHEDULER_INSTANCE
    if scheduler_instance is None or not hasattr(scheduler_instance, "get_job"):
        return

    job = scheduler_instance.get_job(job_id)
    next_run = None if job is None else getattr(job, "next_run_time", None)
    get_metrics_store().set_job_next_run(job_id, next_run)


def _sync_all_job_next_runs() -> None:
    scheduler_instance = _SCHEDULER_INSTANCE
    if scheduler_instance is None or not hasattr(scheduler_instance, "get_jobs"):
        return

    get_metrics_store().update_job_next_runs(
        {
            job.id: getattr(job, "next_run_time", None)
            for job in scheduler_instance.get_jobs()
        }
    )


# -------------------------
# Start
# -------------------------
if __name__ == "__main__":
    main_scheduler()


