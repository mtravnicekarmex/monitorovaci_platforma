import datetime

# ==============================
# Helper function: UTC naive datetime
# ==============================

def utc_now_naive() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

def utc_today() -> datetime.date:
    return utc_now_naive().date()
