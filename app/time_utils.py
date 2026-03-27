import datetime
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("Europe/Prague")

# ==============================
# Helper function: UTC naive datetime
# ==============================

def utc_now_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def utc_today() -> datetime.date:
    return utc_now_naive().date()


def prague_now_naive() -> datetime.datetime:
    return datetime.datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def prague_today() -> datetime.date:
    return prague_now_naive().date()
