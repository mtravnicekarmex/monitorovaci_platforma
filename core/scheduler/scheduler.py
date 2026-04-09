import sys
from dataclasses import dataclass
from functools import wraps
from moduly.mereni.vodomery.SCVK.SCVK_to_database import SCVK_save_to_database_all
from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_to_database import SOFTLINK_to_database_mereni
from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_data_z_dotazu import SOFTLINK_dotaz
from core.db.connect import get_session_pg
from core.db.database_nyni import df_vodomery_vse_join, df_elektromery_vse_join, df_plynomery_vse_join, df_kalorimetry_vse_join, df_manometry_vse_join
from moduly.apps.web_search.service import hledat_nove_vyskyt, notify_new_results_for_monitor
from moduly.apps.web_search.database.models import *
import json
import threading
import os
import time
import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED
from app.channels.email import send_email_outlook
from app.time_utils import utc_now_naive
from decouple import config
from moduly.mereni.vodomery.database.vodomery_db_vse import vodomery_db_import
from moduly.mereni.vodomery.vodomery_prediction import rebuild_profiles
from moduly.mereni.vodomery.vodomery_anomaly import score_new_measurements
from moduly.mereni.vodomery.alerting import process_vodomery_alerts
from moduly.mereni.vodomery.reporting import send_monthly_vodomery_consumption_report
from moduly.mereni.vodomery.vodomery_events import detect_events_from_scores
from moduly.apps.meteo.meteo_sync import meteo_sync


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


def _format_scheduler_reason(error) -> str | None:
    if error is None:
        return None
    reason = str(error).strip()
    if reason:
        return reason
    return type(error).__name__


def _send_scheduler_alert(*, job_id: str, status_text: str, scheduled_time, reason: str | None = None) -> None:
    body_lines = [
        f"Cas: {scheduled_time}",
        f"Job: {job_id}",
        f"Stav: {status_text}",
    ]
    if reason:
        body_lines.append(f"Duvod: {reason}")

    send_email_outlook(
        email_receiver='m.travnicek@armex.cz',
        sender_alias=config('O_EMAIL_ALARM'),
        subject=f"[ALERT] Scheduler | {job_id}",
        body="\n".join(body_lines),
    )


def job_success_listener(event):
    if isinstance(event.retval, SkippedJobResult):
        logger.warning(
            "JOB SKIPPED | id=%s | scheduled=%s | reason=%s | locks=%s",
            event.job_id,
            event.scheduled_run_time,
            event.retval.reason,
            ",".join(event.retval.lock_names),
        )
        return
    logger.info(
        "JOB SUCCESS | id=%s | scheduled=%s",
        event.job_id,
        event.scheduled_run_time
    )



def job_error_listener(event):
    if event.exception:
        logger.exception(
            "JOB ERROR | id=%s | scheduled=%s",
            event.job_id,
            event.scheduled_run_time
        )

        _send_scheduler_alert(
            job_id=event.job_id,
            status_text="spadl",
            scheduled_time=event.scheduled_run_time,
            reason=_format_scheduler_reason(event.exception),
        )

    elif event.code == EVENT_JOB_MISSED:
        logger.error(
            "JOB MISSED | id=%s | scheduled=%s",
            event.job_id,
            event.scheduled_run_time
        )

        _send_scheduler_alert(
            job_id=event.job_id,
            status_text="nebyl spusten",
            scheduled_time=event.scheduled_run_time,
            reason="job byl zmeskan (misfire)",
        )


def job_max_instances_listener(event):
    logger.warning(
        "JOB SKIPPED | id=%s | scheduled=%s | reason=max_instances",
        event.job_id,
        ",".join(str(run_time) for run_time in event.scheduled_run_times),
    )



# -------------------------
# Definice jednotlivých funkc
# -------------------------
def uloz_vodomery_parquet(path1="data/vodomery_latest.parquet",
                          path2=r"\\SERVER1A\Company\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\aktuální stavy\vodomery_latest.parquet"):
    """Uloží výsledek df_vse_join_new() do Parquet souboru."""

    # vytvoření adresáře, pokud neexistuje
    os.makedirs(os.path.dirname(path1), exist_ok=True)
    os.makedirs(os.path.dirname(path2), exist_ok=True)

    # načtení a uložení
    df = df_vodomery_vse_join()
    df.to_parquet(path1, index=False, compression="snappy")
    df.to_parquet(path2, index=False, compression="snappy")
    print(f'Uloženo do {path1} a {path2}')

    return path1, path2



def uloz_elektromery_parquet(path1="data/elektromery_latest.parquet",
                          path2=r"\\SERVER1A\Company\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\aktuální stavy\elektromery_latest.parquet"):
    """Uloží výsledek df_vse_join_new() do Parquet souboru."""

    # vytvoření adresáře, pokud neexistuje
    os.makedirs(os.path.dirname(path1), exist_ok=True)
    os.makedirs(os.path.dirname(path2), exist_ok=True)

    # načtení a uložení
    df = df_elektromery_vse_join()
    df.to_parquet(path1, index=False, compression="snappy")
    df.to_parquet(path2, index=False, compression="snappy")
    print(f'Uloženo do {path1} a {path2}')

    return path1, path2



def uloz_plynomery_parquet(path1="data/plynomery_latest.parquet",
                          path2=r"\\SERVER1A\Company\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\aktuální stavy\plynomery_latest.parquet"):
    """Uloží výsledek df_vse_join_new() do Parquet souboru."""

    # vytvoření adresáře, pokud neexistuje
    os.makedirs(os.path.dirname(path1), exist_ok=True)
    os.makedirs(os.path.dirname(path2), exist_ok=True)

    # načtení a uložení
    df = df_plynomery_vse_join()
    df.to_parquet(path1, index=False, compression="snappy")
    df.to_parquet(path2, index=False, compression="snappy")
    print(f'Uloženo do {path1} a {path2}')

    return path1, path2



def uloz_kalorimetry_parquet(path1="data/kalorimetry_latest.parquet",
                          path2=r"\\SERVER1A\Company\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\aktuální stavy\kalorimetry_latest.parquet"):
    """Uloží výsledek df_vse_join_new() do Parquet souboru."""

    # vytvoření adresáře, pokud neexistuje
    os.makedirs(os.path.dirname(path1), exist_ok=True)
    os.makedirs(os.path.dirname(path2), exist_ok=True)

    # načtení a uložení
    df = df_kalorimetry_vse_join()
    df.to_parquet(path1, index=False, compression="snappy")
    df.to_parquet(path2, index=False, compression="snappy")
    print(f'Uloženo do {path1} a {path2}')

    return path1, path2


def uloz_manometry_parquet(path1="data/manometry_latest.parquet",
                          path2=r"\\SERVER1A\Company\Holding\Správa Majetku\Budovy\xEvidence\Měření v areálu\aktuální stavy\manometry_latest.parquet"):
    """Uloží výsledek df_vse_join_new() do Parquet souboru."""

    # vytvoření adresáře, pokud neexistuje
    os.makedirs(os.path.dirname(path1), exist_ok=True)
    os.makedirs(os.path.dirname(path2), exist_ok=True)

    # načtení a uložení
    df = df_manometry_vse_join()
    df.to_parquet(path1, index=False, compression="snappy")
    df.to_parquet(path2, index=False, compression="snappy")
    print(f'Uloženo do {path1} a {path2}')

    return path1, path2



def SOFTLINK_save_to_database_all():
    SOFTLINK_to_database_mereni(SOFTLINK_dotaz())


def daily_web_monitor_job():
    session = get_session_pg()
    monitory = session.query(Monitor).all()
    had_error = False

    try:
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

            except Exception:
                had_error = True
                session.rollback()  # reset session po chybě v transakci
                logger.exception(f"Monitor selhal: {monitor.url}")

    finally:
        session.close()

    if had_error:
        raise RuntimeError("Některé monitory selhaly")

    logger.info("Web monitor job dokončen")







def safe_call(fn, *args, **kwargs):
    start = time.time()
    try:
        logger.info("START %s", fn.__name__)
        return fn(*args, **kwargs)
    except Exception:
        logger.exception("FAIL %s", fn.__name__)
        raise
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
        except Exception:
            logger.exception(f"Chyba v {fn.__name__}")
            raise
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
    # safe_call(vodomery_db_import)
    # safe_call(score_new_measurements, model_version=1)
    # event_result = safe_call(detect_events_from_scores, model_version=1)
    # safe_call(process_vodomery_alerts, active_event_ids=event_result.get("active_event_ids", []), resolved_event_ids=event_result.get("resolved_event_ids", []),)
    safe_call(daily_web_monitor_job)

# každou hodinu v X:02:05
@locked_job
def hourly_job():
    safe_call(SCVK_save_to_database_all)


# každou hodinu v pracovní dny od 6:03 do 16:03
@locked_job
def working_time_hourly_job():
    safe_call(uloz_manometry_parquet)
    safe_call(uloz_kalorimetry_parquet)
    safe_call(uloz_plynomery_parquet)


# každý den v 7:00 a 14:00
@locked_job
def daily_seven_and_two_job():
    safe_call(daily_web_monitor_job)


# každý den v 0:15:05
@locked_job
def daily_pulnoc_job():
    safe_call(SOFTLINK_save_to_database_all)
    safe_call(meteo_sync)


# každý týden v pondělí v 6:10:05
@locked_job
def weekly_job():
    safe_call(rebuild_profiles, 1)


# každý první den v měsíci v 0:20:05
@locked_job
def monthly_job():
    safe_call(send_monthly_vodomery_consumption_report)













# -------------------------
# Hlavní funkce scheduleru
# -------------------------
def main_scheduler():
    scheduler = BackgroundScheduler(
        timezone="Europe/Prague",
        job_defaults={
            "coalesce": True,
            "misfire_grace_time": 60,
            "max_instances": 1
        }
    )


    # -------------------------
    # Naplánování jobů
    # -------------------------

    # každých 15 minut v X:05,20,35,50
    scheduler.add_job(
        quarter_hour_job,
        CronTrigger(minute="5,29,46,50", second=5),
        id="quarter_hour_job",
    )

    # # každou hodinu v X:02:05
    # scheduler.add_job(
    #     hourly_job,
    #     CronTrigger(minute=2, second=5),
    #     id="hourly_job",
    #     max_instances=1,
    # )
    #
    # # každou hodinu v X:03 v pracovní dny od 6 do 16
    # scheduler.add_job(
    #     working_time_hourly_job,
    #     CronTrigger(hour="6-16", minute=3, second=5, day_of_week="mon-fri"),
    #     id="working_time_hourly_job",
    # )
    #
    # # každý den v 7:00 a 14:00
    # scheduler.add_job(
    #     daily_seven_and_two_job,
    #     CronTrigger(hour="7,14", minute=0, second=5),
    #     id="daily_seven_and_two_job",
    # )
    #
    # # každý den v 0:15:05
    # scheduler.add_job(
    #     daily_pulnoc_job,
    #     CronTrigger(hour=0, minute=15, second=5),
    #     id="daily_job",
    # )
    #
    # # každý týden v pondělí v 6:10:05
    # scheduler.add_job(
    #     weekly_job,
    #     CronTrigger(day_of_week="mon", hour=6, minute=10, second=5),
    #     id="weekly_job",
    # )
    #
    # # každý první den v měsíci po noční aktualizaci v 0:20:05
    # scheduler.add_job(
    #     monthly_job,
    #     CronTrigger(
    #         day=1,
    #         hour=0,
    #         minute=20,
    #         second=5,
    #     ),
    #     id="monthly_job",
    # )


    # --- Listeners ---
    scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    scheduler.add_listener(job_success_listener, EVENT_JOB_EXECUTED)
    scheduler.add_listener(job_max_instances_listener, EVENT_JOB_MAX_INSTANCES)

    # --- Start scheduleru ---
    scheduler.start()
    logger.info("Scheduler spuštěn")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Ukončuji scheduler...")
        scheduler.shutdown()





# -------------------------
# Logger
# -------------------------
logger = setup_logging()

# -------------------------
# Lock
# -------------------------
_LOCK_REGISTRY_GUARD = threading.Lock()
_JOB_LOCKS = {}


def _get_lock(lock_name):
    with _LOCK_REGISTRY_GUARD:
        job_lock = _JOB_LOCKS.get(lock_name)
        if job_lock is None:
            job_lock = threading.Lock()
            _JOB_LOCKS[lock_name] = job_lock
        return job_lock

# -------------------------
# Start
# -------------------------
if __name__ == "__main__":
    main_scheduler()


