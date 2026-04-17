"""
Scheduler pro automatizované úlohy monitorovací platformy.

Spravuje plánování a spouštění periodických úloh:
- Čtvrtletní job (každých 15 minut)
- Hodinový job (každou hodinu)
- Denní job (7:00 a 14:00)
- Noční job (0:15)
- Týdenní job (každé pondělí)
- Měsíční job (první den v měsíci)
"""

import html
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
from core.scheduler.metrics import get_metrics_store
from decouple import config
from moduly.mereni.vodomery.database.vodomery_db_vse import vodomery_db_import
from moduly.mereni.vodomery.vodomery_prediction import (
    get_candidate_model_versions,
    get_runtime_model_version,
    rebuild_profiles,
)
from moduly.mereni.vodomery.vodomery_anomaly import score_new_measurements
from moduly.mereni.vodomery.alerting import process_vodomery_alerts
from moduly.mereni.vodomery.reporting import (
    send_daily_vodomery_branch_report,
    send_weekly_vodomery_branch_report,
    send_monthly_vodomery_branch_report,
    send_monthly_b1_consumption_report,
    send_vodomery_model_rebuild_report,
    send_monthly_vodomery_consumption_report,
)
from moduly.mereni.vodomery.vodomery_events import detect_events_from_scores
from moduly.apps.meteo.meteo_sync import meteo_sync
from moduly.apps.smartfuelpass import send_charge_sessions_report_email


# -------------------------
# Logger
# -------------------------

SCHEDULER_DIR = Path(__file__).resolve().parent
SCHEDULER_LOGS_DIR = SCHEDULER_DIR / "logs"
SCHEDULER_LOG_PATH = SCHEDULER_LOGS_DIR / "scheduler.log"


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    SCHEDULER_LOGS_DIR.mkdir(parents=True, exist_ok=True)

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
# Logger
# -------------------------

SCHEDULER_DIR = Path(__file__).resolve().parent
SCHEDULER_LOGS_DIR = SCHEDULER_DIR / "logs"
SCHEDULER_LOG_PATH = SCHEDULER_LOGS_DIR / "scheduler.log"


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    SCHEDULER_LOGS_DIR.mkdir(parents=True, exist_ok=True)

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




# -------------------------
# Job listeners
# -------------------------


@dataclass(frozen=True)
class SkippedJobResult:
    reason: str
    lock_names: tuple[str, ...]


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
    detail_rows = [
        ("Job", job_id),
        ("Stav", status_text),
        ("Planovany cas", _format_scheduler_time(scheduled_time)),
        ("Detekovano", _format_scheduler_time(datetime.now().astimezone())),
    ]

    row_html = "".join(
        (
            "<tr>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;background:#f6f8fa;'><strong>{html.escape(label)}</strong></td>"
            f"<td style='padding:6px 10px;border:1px solid #d0d7de;'>{html.escape(value)}</td>"
            "</tr>"
        )
        for label, value in detail_rows
    )

    reason_html = ""
    if reason:
        reason_html = (
            "<p style='margin:16px 0 6px;'><strong>Duvod</strong></p>"
            f"<p style='margin:0;'>{html.escape(reason)}</p>"
        )

    targets_html = ""
    if targets:
        target_items = "".join(
            f"<li>{html.escape(target)}</li>"
            for target in targets
        )
        targets_html = (
            "<p style='margin:16px 0 6px;'><strong>Cile</strong></p>"
            f"<ul style='margin:0 0 0 18px;padding:0;'>{target_items}</ul>"
        )

    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        "<h2 style='margin:0 0 12px;'>Scheduler alert</h2>"
        f"<p style='margin:0 0 16px;'>{html.escape(description)}</p>"
        "<table style='border-collapse:collapse;font-size:14px;'>"
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
def _build_locked_job(fn, decorator_lock_names):
    resolved_lock_names = tuple(dict.fromkeys(decorator_lock_names or (fn.__name__,)))

    @wraps(fn)
    def wrapper(*args, **kwargs):
        resolved_locks = tuple(_get_lock(lock_name) for lock_name in sorted(resolved_lock_names))
        acquired_locks = []
        for job_lock in resolved_locks:
            if not job_lock.acquire(blocking=False):
                for acquired_lock in reversed(acquired_locks):
                    acquired_lock.release()
                return SkippedJobResult(reason="lock_busy", lock_names=resolved_lock_names)
            acquired_locks.append(job_lock)
        try:
            return fn(*args, **kwargs)
        finally:
            for acquired_lock in reversed(acquired_locks):
                acquired_lock.release()
    return wrapper


def locked_job(*decorator_args):
    if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1:
        return _build_locked_job(decorator_args[0], ())
    return lambda fn: _build_locked_job(fn, decorator_args)







# -------------------------
# Definice jednotlivých jobů
# -------------------------

# každých 15 minut v X:05,20,35,50
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


# každou hodinu v X:02:05
@locked_job
def hourly_job():
    safe_call(SCVK_save_to_database_all)


# každý den v 7:00 a 14:00
@locked_job
def daily_seven_and_two_job():
    safe_call(daily_web_monitor_job)


# každý den v 0:15:05
@locked_job
def daily_pulnoc_job():
    safe_call(SOFTLINK_save_to_database_all)
    safe_call(meteo_sync)


# každý den v 6:00:05
@locked_job
def daily_vodomery_branch_report_job():
    safe_call(send_daily_vodomery_branch_report)


# každý týden v pondělí v 6:10:05
@locked_job
def weekly_job():
    rebuild_result = safe_call(rebuild_profiles)
    safe_call(send_vodomery_model_rebuild_report, rebuild_result)
    safe_call(send_weekly_vodomery_branch_report)


# každé úterý v 6:55:05
@locked_job
def smartfuelpass_weekly_report_job():
    safe_call(send_charge_sessions_report_email)


# každý první den v měsíci v 6:20:05
@locked_job
def monthly_job():
    safe_call(send_monthly_vodomery_consumption_report)
    safe_call(send_monthly_vodomery_branch_report)
    safe_call(send_monthly_b1_consumption_report)














# -------------------------
# Hlavní funkce scheduleru
# -------------------------
def main_scheduler():
    scheduler = BackgroundScheduler(
        timezone=SCHEDULER_TIMEZONE_NAME,
        job_defaults={
            "coalesce": True,
            "misfire_grace_time": 60,
            "max_instances": 1
        }
    )


    # -------------------------
    # Naplánování jobů
    # -------------------------
    job_functions = {
        "quarter_hour_job": quarter_hour_job,
        "hourly_job": hourly_job,
        "daily_seven_and_two_job": daily_seven_and_two_job,
        "daily_job": daily_pulnoc_job,
        "daily_vodomery_branch_report_job": daily_vodomery_branch_report_job,
        "weekly_job": weekly_job,
        "smartfuelpass_weekly_report_job": smartfuelpass_weekly_report_job,
        "monthly_job": monthly_job,
    }
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
            time.sleep(300)
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


