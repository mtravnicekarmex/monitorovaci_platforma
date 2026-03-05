import sys
from moduly.mereni.vodomery.SCVK.SCVK_to_database import SCVK_save_to_database_all
from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_to_database import SOFTLINK_to_database_mereni
from moduly.mereni.elektromery.SOFTLINK.SOFTLINK_data_z_dotazu import SOFTLINK_dotaz
from core.db.connect import get_session_pg
from core.db.database_nyni import df_vodomery_vse_join, df_elektromery_vse_join, df_plynomery_vse_join, df_kalorimetry_vse_join, df_manometry_vse_join
from moduly.apps.web_search.web_search import hledat_nove_vyskyt, poslat_email_html_vyraz
from moduly.apps.web_search.database.models import *
import json
import threading
import os
import traceback
import time
import logging
from logging.handlers import TimedRotatingFileHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_EXECUTED
from app.channels.email import send_email_outlook
from app.time_utils import utc_now_naive
from decouple import config
from moduly.mereni.vodomery.database.vodomery_db_vse import vodomery_db_import
from moduly.mereni.vodomery.vodomery_prediction import rebuild_profiles
from moduly.mereni.vodomery.vodomery_anomaly import score_new_measurements
from moduly.mereni.vodomery.vodomery_events import detect_events_from_scores
from moduly.apps.meteo.meteo_sync import meteo_sync


# -------------------------
# Logger
# -------------------------


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # --- Console handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # --- File handler (rotace každý den, uchová 14 dní) ---
    file_handler = TimedRotatingFileHandler(
        "scheduler.log",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # potlačí SQLAlchemy spam
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return logging.getLogger(__name__)




# -------------------------
# Job listeners
# -------------------------


def job_success_listener(event):
    logger.info(
        "JOB SUCCESS | id=%s | scheduled=%s",
        event.job_id,
        event.scheduled_run_time
    )



def job_error_listener(event):
    if event.exception:
        error_text = "".join(
                        traceback.format_exception(
                            type(event.exception),
                            event.exception,
                            event.exception.__traceback__
                        )
                    )

        logger.exception(
            "JOB ERROR | id=%s | scheduled=%s",
            event.job_id,
            event.scheduled_run_time
        )

        send_email_outlook(
            email_receiver='m.travnicek@armex.cz',
            sender_alias=config('O_EMAIL_ALARM'),
            subject=f"[ALERT] Job {event.job_id} spadl",
            body=f"""
Job ID: {event.job_id}
Naplánovaný čas: {event.scheduled_run_time}

Traceback:
{error_text}
"""
        )

    elif event.code == EVENT_JOB_MISSED:
        logger.error(
            "JOB MISSED | id=%s | scheduled=%s",
            event.job_id,
            event.scheduled_run_time
        )

        send_email_outlook(
            email_receiver='m.travnicek@armex.cz',
            sender_alias=config('O_EMAIL_ALARM'),
            subject=f"[ALERT] Job {event.job_id} nebyl spuštěn",
            body=f"""
Job ID: {event.job_id}
Naplánovaný čas: {event.scheduled_run_time}
Důvod: job byl zmeškán (misfire).
"""
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
                    # Připrav seznam pro email
                    vyskyt_list = [
                        (vyraz, snippet, odkaz)
                        for vyraz, snippet, odkaz in nove_vyskyt
                    ]

                    # Odeslání emailu
                    poslat_email_html_vyraz(
                        monitor.email,
                        f"Nový výskyt na {monitor.url}",
                        vyskyt_list
                    )

                    # Označit právě přidané výsledky jako notified=True
                    now = utc_now_naive()
                    session.query(Result).filter(
                        Result.monitor_id == monitor.id,
                        Result.notified == False,
                        Result.datum <= now
                    ).update({"notified": True}, synchronize_session=False)

                    logger.info(f'Nové výskyty na "{monitor.url}": {len(nove_vyskyt)}')

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
def locked_job(fn):
    def wrapper(*args, **kwargs):
        if not lock.acquire(blocking=False):
            msg = f"{fn.__name__} přeskočen – jiný job běží"
            logger.error(msg)
            raise RuntimeError(msg)
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception(f"Chyba v {fn.__name__}")
            raise
        finally:
            lock.release()
    return wrapper






# -------------------------
# Definice jednotlivých jobů
# -------------------------

# každých 15 minut
@locked_job
def quarter_hour_job():
    safe_call(vodomery_db_import)
    safe_call(score_new_measurements, model_version=1)
    safe_call(detect_events_from_scores, model_version=1)


# každou hodinu
@locked_job
def hourly_job():
    safe_call(SCVK_save_to_database_all)


# každou hodinu od 6 do 16 pracovní den
@locked_job
def working_time_hourly_job():
    safe_call(uloz_manometry_parquet)
    safe_call(uloz_kalorimetry_parquet)
    safe_call(uloz_plynomery_parquet)
    safe_call(uloz_vodomery_parquet)


# každý den v 7 a ve 14
@locked_job
def daily_seven_and_two_job():
    safe_call(daily_web_monitor_job)


# každý den o půlnoci
@locked_job
def daily_pulnoc_job():
    safe_call(SOFTLINK_save_to_database_all)
    safe_call(meteo_sync)


# každý týden v pondělí ráno
@locked_job
def weekly_job():
    safe_call(rebuild_profiles, 1)


# každý měsíc prvního ráno
@locked_job
def monthly_job():
    safe_call(SCVK_save_to_database_all)













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

    # každých 15 minut v X:02,17,32,47
    scheduler.add_job(
        quarter_hour_job,
        CronTrigger(minute="5,28,35,50", second=5),
        id="quarter_hour_job",
    )
    #
    # # každou hodinu v X:02
    # scheduler.add_job(
    #     hourly_job,
    #     CronTrigger(minute=2, second=5),
    #     id="hourly_job",
    #     max_instances=1,
    # )
    #
    # # # každou hodinu v X:03 v pracovní dny od 6 do 16
    # # scheduler.add_job(
    # #     working_time_hourly_job,
    # #     CronTrigger(hour="6-16", minute=3, day_of_week="mon-fri"),
    # #     id="working_time_hourly_job",
    # # )
    #
    # # každý den v X:00 7 a 14
    # scheduler.add_job(
    #     daily_seven_and_two_job,
    #     CronTrigger(hour="7,14", minute=0),
    #     id="daily_seven_and_two_job",
    # )
    #
    # # každý den v 0:05
    # scheduler.add_job(
    #     daily_pulnoc_job,
    #     CronTrigger(hour=0, minute=15, second=5),
    #     id="daily_job",
    # )
    #
    # # každý týden v pondělí v 6:10
    # scheduler.add_job(
    #     weekly_job,
    #     CronTrigger(day_of_week="1", hour=0, minute=10, second=5),
    #     id="weekly_job",
    # )

    # # každý první den v měsíci v 0:00
    # scheduler.add_job(
    #     monthly_job,
    #     CronTrigger(
    #         day=1,  # první den v měsíci
    #         hour=0,
    #         minute=0,
    #         second=5,
    #     ),
    #     id="monthly_job",
    # )


    # --- Listeners ---
    scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    scheduler.add_listener(job_success_listener, EVENT_JOB_EXECUTED)

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
lock = threading.Lock()

# -------------------------
# Start
# -------------------------
# if __name__ == "__main__":
#     main_scheduler()


