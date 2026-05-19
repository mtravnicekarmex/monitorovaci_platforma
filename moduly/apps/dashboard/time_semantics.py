from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pandas as pd


DASHBOARD_TIMEZONE_NAME = "Europe/Prague"
DASHBOARD_TIMEZONE = ZoneInfo(DASHBOARD_TIMEZONE_NAME)

TIME_SEMANTICS_COLUMNS = (
    "source_date",
    "time_utc",
    "time_basis",
    "source_timezone",
    "source_utc_offset_minutes",
    "time_fold",
    "timestamp_position",
)


def local_date_range_to_utc(
    start_date: datetime.date,
    end_date: datetime.date,
) -> tuple[datetime.datetime, datetime.datetime]:
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    start_local = datetime.datetime.combine(start_date, datetime.time.min).replace(tzinfo=DASHBOARD_TIMEZONE)
    end_exclusive_local = datetime.datetime.combine(
        end_date + datetime.timedelta(days=1),
        datetime.time.min,
    ).replace(tzinfo=DASHBOARD_TIMEZONE)
    return (
        start_local.astimezone(datetime.UTC),
        end_exclusive_local.astimezone(datetime.UTC),
    )


def local_datetime_range_to_utc(
    start_datetime: datetime.datetime,
    end_datetime: datetime.datetime,
) -> tuple[datetime.datetime, datetime.datetime]:
    if start_datetime > end_datetime:
        start_datetime, end_datetime = end_datetime, start_datetime

    if start_datetime.tzinfo is None or start_datetime.utcoffset() is None:
        start_datetime = start_datetime.replace(tzinfo=DASHBOARD_TIMEZONE)
    if end_datetime.tzinfo is None or end_datetime.utcoffset() is None:
        end_datetime = end_datetime.replace(tzinfo=DASHBOARD_TIMEZONE)

    return (
        start_datetime.astimezone(datetime.UTC),
        end_datetime.astimezone(datetime.UTC),
    )


def prague_now_utc() -> datetime.datetime:
    return datetime.datetime.now(DASHBOARD_TIMEZONE).astimezone(datetime.UTC)


def add_chart_time(
    df: pd.DataFrame,
    *,
    time_utc_column: str = "time_utc",
    legacy_column: str = "date",
    chart_column: str = "chart_time",
) -> pd.DataFrame:
    prepared = df.copy()
    if time_utc_column not in prepared.columns:
        prepared[time_utc_column] = pd.NaT

    utc_time = pd.to_datetime(prepared[time_utc_column], utc=True, errors="coerce")
    prepared[time_utc_column] = utc_time
    prepared[chart_column] = utc_time.dt.tz_convert(DASHBOARD_TIMEZONE_NAME).dt.tz_localize(None)

    if legacy_column in prepared.columns:
        legacy_time = pd.to_datetime(prepared[legacy_column], errors="coerce")
        prepared.loc[prepared[chart_column].isna(), chart_column] = legacy_time

    return prepared


def time_axis_column(
    df: pd.DataFrame,
    *,
    chart_column: str = "chart_time",
    legacy_column: str = "date",
) -> str:
    if chart_column in df.columns and df[chart_column].notna().any():
        return chart_column
    return legacy_column


def to_prague_naive(value: object) -> datetime.datetime | None:
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value
        return value.astimezone(DASHBOARD_TIMEZONE).replace(tzinfo=None)

    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp.to_pydatetime()
    return timestamp.tz_convert(DASHBOARD_TIMEZONE_NAME).tz_localize(None).to_pydatetime()
