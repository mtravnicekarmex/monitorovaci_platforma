from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


TIME_BASIS_EUROPE_PRAGUE_CIVIL = "EUROPE_PRAGUE_CIVIL"
TIME_BASIS_FIXED_OFFSET = "FIXED_OFFSET"

SOURCE_TIMEZONE_EUROPE_PRAGUE = "Europe/Prague"
SOURCE_TIMEZONE_FIXED_CET = "+01:00"

TIMESTAMP_POSITION_START = "start"
TIMESTAMP_POSITION_INSTANT = "instant"
TIMESTAMP_POSITION_INTERVAL = "interval"

BINARY_FIXED_UTC_OFFSET_MINUTES = 60


@dataclass(frozen=True)
class MeasurementTimeSemantics:
    time_basis: str
    source_timezone: str
    source_utc_offset_minutes: int | None
    timestamp_position: str
    time_fold: int | None = None


BINARY_TIME_SEMANTICS = MeasurementTimeSemantics(
    time_basis=TIME_BASIS_FIXED_OFFSET,
    source_timezone=SOURCE_TIMEZONE_FIXED_CET,
    source_utc_offset_minutes=BINARY_FIXED_UTC_OFFSET_MINUTES,
    timestamp_position=TIMESTAMP_POSITION_START,
)

OTE_TIME_SEMANTICS = MeasurementTimeSemantics(
    time_basis=TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    source_timezone=SOURCE_TIMEZONE_EUROPE_PRAGUE,
    source_utc_offset_minutes=None,
    timestamp_position=TIMESTAMP_POSITION_START,
)

SOFTLINK_TIME_SEMANTICS = MeasurementTimeSemantics(
    time_basis=TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    source_timezone=SOURCE_TIMEZONE_EUROPE_PRAGUE,
    source_utc_offset_minutes=None,
    timestamp_position=TIMESTAMP_POSITION_INSTANT,
)

CUMULATIVE_METER_TIME_SEMANTICS = MeasurementTimeSemantics(
    time_basis=TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    source_timezone=SOURCE_TIMEZONE_EUROPE_PRAGUE,
    source_utc_offset_minutes=None,
    timestamp_position=TIMESTAMP_POSITION_INSTANT,
)

VODOMERY_TIME_SEMANTICS = CUMULATIVE_METER_TIME_SEMANTICS
PLYNOMERY_TIME_SEMANTICS = CUMULATIVE_METER_TIME_SEMANTICS
KALORIMETRY_TIME_SEMANTICS = CUMULATIVE_METER_TIME_SEMANTICS
MANOMETRY_TIME_SEMANTICS = MeasurementTimeSemantics(
    time_basis=TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    source_timezone=SOURCE_TIMEZONE_EUROPE_PRAGUE,
    source_utc_offset_minutes=None,
    timestamp_position=TIMESTAMP_POSITION_INSTANT,
)

SMARTFUELPASS_TIME_SEMANTICS = MeasurementTimeSemantics(
    time_basis=TIME_BASIS_EUROPE_PRAGUE_CIVIL,
    source_timezone=SOURCE_TIMEZONE_EUROPE_PRAGUE,
    source_utc_offset_minutes=None,
    timestamp_position=TIMESTAMP_POSITION_INTERVAL,
)


def get_default_time_semantics(source_name: str) -> MeasurementTimeSemantics:
    if source_name.startswith("BINARY_"):
        return BINARY_TIME_SEMANTICS
    if source_name == "OTE":
        return OTE_TIME_SEMANTICS
    if source_name == "SOFTLINK":
        return SOFTLINK_TIME_SEMANTICS
    if source_name == "SMARTFUELPASS":
        return SMARTFUELPASS_TIME_SEMANTICS
    if source_name == "KALORIMETRY":
        return KALORIMETRY_TIME_SEMANTICS
    if source_name == "MANOMETRY":
        return MANOMETRY_TIME_SEMANTICS
    if source_name in {"AREAL", "SCVK"}:
        return CUMULATIVE_METER_TIME_SEMANTICS
    return CUMULATIVE_METER_TIME_SEMANTICS


def semantics_from_row(row: dict[str, object], source_name: str) -> MeasurementTimeSemantics:
    default = get_default_time_semantics(source_name)
    offset = row.get("source_utc_offset_minutes", default.source_utc_offset_minutes)
    fold = row.get("time_fold", default.time_fold)
    return MeasurementTimeSemantics(
        time_basis=str(row.get("time_basis") or default.time_basis),
        source_timezone=str(row.get("source_timezone") or default.source_timezone),
        source_utc_offset_minutes=None if offset is None else int(offset),
        timestamp_position=str(row.get("timestamp_position") or default.timestamp_position),
        time_fold=None if fold is None else int(fold),
    )


def resolve_time_utc(source_date: datetime, semantics: MeasurementTimeSemantics) -> datetime:
    source_date = source_date.replace(tzinfo=None)
    if semantics.time_basis == TIME_BASIS_FIXED_OFFSET:
        if semantics.source_utc_offset_minutes is None:
            raise ValueError("FIXED_OFFSET time semantics require source_utc_offset_minutes.")
        return (source_date - timedelta(minutes=semantics.source_utc_offset_minutes)).replace(tzinfo=timezone.utc)

    local_zone = ZoneInfo(semantics.source_timezone)
    local_time = source_date.replace(tzinfo=local_zone, fold=semantics.time_fold or 0)
    return local_time.astimezone(timezone.utc)


def resolve_utc_offset_minutes(source_date: datetime, semantics: MeasurementTimeSemantics) -> int | None:
    source_date = source_date.replace(tzinfo=None)
    if semantics.time_basis == TIME_BASIS_FIXED_OFFSET:
        return semantics.source_utc_offset_minutes

    offset = source_date.replace(
        tzinfo=ZoneInfo(semantics.source_timezone),
        fold=semantics.time_fold or 0,
    ).utcoffset()
    if offset is None:
        return None
    return int(offset.total_seconds() // 60)


def build_time_columns(
    source_date: datetime,
    source_name: str,
    row: dict[str, object] | None = None,
) -> dict[str, object]:
    source_date = source_date.replace(tzinfo=None)
    semantics = semantics_from_row(row or {}, source_name)
    return {
        "source_date": source_date,
        "time_utc": resolve_time_utc(source_date, semantics),
        "time_basis": semantics.time_basis,
        "source_timezone": semantics.source_timezone,
        "source_utc_offset_minutes": resolve_utc_offset_minutes(source_date, semantics),
        "time_fold": semantics.time_fold,
        "timestamp_position": semantics.timestamp_position,
    }
