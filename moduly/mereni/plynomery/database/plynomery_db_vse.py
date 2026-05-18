from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_MS, ENGINE_PG
from moduly.mereni.time_semantics import build_time_columns
from moduly.mereni.plynomery.alerting.outlier_notifications import process_new_outlier_review_notifications
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    Plynomer_areal_Mereni,
    Plynomer_areal_Zarizeni,
)
from moduly.mereni.plynomery.database.outlier_reviews import (
    build_outlier_review_key,
    load_outlier_review_ids_by_keys,
    upsert_outlier_review_candidates,
)


logger = logging.getLogger(__name__)

engine = ENGINE_PG
engine_ms = ENGINE_MS

CHUNK_SIZE = 5000
DEFAULT_INTERVAL_MINUTES = 15
MAX_GAP_MULTIPLIER = 2
MIN_NIGHT_DELTA = 0.01
OUTLIER_LOOKBACK_DAYS = 90
OUTLIER_MIN_HISTORY = 48
OUTLIER_ABSOLUTE_MIN_DELTA = 10.0
OUTLIER_P90_SPREAD_MULTIPLIER = 25.0
OUTLIER_STD_MULTIPLIER = 12.0
OUTLIER_P99_MULTIPLIER = 8.0


def chunked(items, size: int = CHUNK_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _drop_legacy_identifikace_fk(table_name: str) -> None:
    inspector = inspect(engine)
    for foreign_key in inspector.get_foreign_keys(table_name, schema="monitoring"):
        name = foreign_key.get("name")
        constrained_columns = tuple(foreign_key.get("constrained_columns") or ())
        referred_schema = foreign_key.get("referred_schema")
        referred_table = foreign_key.get("referred_table")
        if (
            name
            and constrained_columns == ("identifikace",)
            and referred_schema == "evidence"
            and referred_table == "plynoměry"
        ):
            escaped_name = str(name).replace('"', '""')
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f'ALTER TABLE monitoring."{table_name}" '
                        f'DROP CONSTRAINT IF EXISTS "{escaped_name}"'
                    )
                )
            logger.info(
                'Dropped legacy foreign key "%s" from monitoring."%s"',
                name,
                table_name,
            )


def ensure_destination_table() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))

    inspector = inspect(engine)
    monitoring_tables = inspector.get_table_names(schema="monitoring")
    expected_table = Mereni_plynomery.__tablename__

    case_mismatch = next(
        (table_name for table_name in monitoring_tables if table_name.lower() == expected_table.lower() and table_name != expected_table),
        None,
    )
    if case_mismatch:
        raise RuntimeError(
            f"Case mismatch in monitoring schema: model expects '{expected_table}', "
            f"but database has '{case_mismatch}'. Unify table naming first."
        )

    if expected_table not in monitoring_tables:
        Mereni_plynomery.__table__.create(bind=engine, checkfirst=True)
        logger.info('Created missing table monitoring."%s"', expected_table)

    _drop_legacy_identifikace_fk(expected_table)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE monitoring."Mereni_plynomery_vse"
                    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
                    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
                    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
                    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
                    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
                    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_plynomery_vse_time_utc
                ON monitoring."Mereni_plynomery_vse" (time_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_plynomery_vse_ident_time_utc
                ON monitoring."Mereni_plynomery_vse" (identifikace, time_utc)
                """
            )
        )


def get_last_imported_recid(session: Session, source_name: str) -> int | None:
    query = select(func.max(Mereni_plynomery.source_recid)).where(Mereni_plynomery.zdroj == source_name)
    return session.execute(query).scalar()


def fetch_from_ms_areal() -> list[dict[str, object]]:
    with Session(engine) as pg_session:
        last_recid = get_last_imported_recid(pg_session, "AREAL")

    with Session(engine_ms) as ms_session:
        query = (
            select(
                Plynomer_areal_Mereni.recid,
                Plynomer_areal_Mereni.identifikace,
                Plynomer_areal_Mereni.seriove_cislo,
                Plynomer_areal_Mereni.date,
                Plynomer_areal_Mereni.objem,
                Plynomer_areal_Mereni.platne,
            )
            .where(
                Plynomer_areal_Mereni.identifikace.is_not(None),
                Plynomer_areal_Mereni.date.is_not(None),
                Plynomer_areal_Mereni.objem.is_not(None),
            )
            .order_by(Plynomer_areal_Mereni.recid)
        )
        if last_recid is not None:
            query = query.where(Plynomer_areal_Mereni.recid > last_recid)

        rows = ms_session.execute(query).all()

    return [
        {
            "recid": row.recid,
            "identifikace": row.identifikace,
            "seriove_cislo": row.seriove_cislo,
            "date": row.date,
            "objem": row.objem,
            "platne": True if row.platne is None else bool(row.platne),
            "interval_minutes": DEFAULT_INTERVAL_MINUTES,
        }
        for row in rows
    ]


def compute_slot(dt: datetime, interval_minutes: int) -> int:
    minutes_from_midnight = dt.hour * 60 + dt.minute
    return minutes_from_midnight // interval_minutes


def compute_day_of_week(dt: datetime) -> int:
    return dt.weekday()


def is_night_time(dt: datetime) -> bool:
    return dt.hour >= 23 or dt.hour < 5


def get_last_measurements(session: Session, affected_idents: set[str], *, only_valid: bool = False) -> dict[str, Mereni_plynomery]:
    if not affected_idents:
        return {}

    rows_by_ident: dict[str, Mereni_plynomery] = {}
    for ident_chunk in chunked(list(affected_idents)):
        subquery = (
            select(
                Mereni_plynomery.identifikace,
                func.max(Mereni_plynomery.date).label("max_date"),
            )
            .where(Mereni_plynomery.identifikace.in_(ident_chunk))
        )
        if only_valid:
            subquery = subquery.where(Mereni_plynomery.platne.is_(True))
        subquery = subquery.group_by(Mereni_plynomery.identifikace).subquery()

        query = (
            select(Mereni_plynomery)
            .join(
                subquery,
                (Mereni_plynomery.identifikace == subquery.c.identifikace)
                & (Mereni_plynomery.date == subquery.c.max_date),
            )
        )
        if only_valid:
            query = query.where(Mereni_plynomery.platne.is_(True))

        for row in session.execute(query).scalars().all():
            rows_by_ident[row.identifikace] = row

    return rows_by_ident


def get_existing_measurement_dates(
    session: Session | None,
    affected_idents: set[str],
    source_name: str,
    *,
    min_date: datetime,
    max_date: datetime,
) -> dict[str, set[datetime]]:
    if session is None or not affected_idents:
        return {}

    dates_by_ident: dict[str, set[datetime]] = {}
    for ident_chunk in chunked(list(affected_idents)):
        query = (
            select(Mereni_plynomery.identifikace, Mereni_plynomery.date)
            .where(
                Mereni_plynomery.identifikace.in_(ident_chunk),
                Mereni_plynomery.zdroj == source_name,
                Mereni_plynomery.date >= min_date,
                Mereni_plynomery.date <= max_date,
            )
        )
        for ident, measurement_date in session.execute(query).all():
            dates_by_ident.setdefault(str(ident), set()).add(measurement_date)

    return dates_by_ident


def get_recent_delta_stats(
    session: Session,
    affected_idents: set[str],
    *,
    reference_time: datetime | None = None,
) -> dict[str, dict[str, float | int]]:
    if not affected_idents:
        return {}

    resolved_reference_time = reference_time or utc_now_naive()
    cutoff = resolved_reference_time - timedelta(days=OUTLIER_LOOKBACK_DAYS)
    stats_by_ident: dict[str, dict[str, float | int]] = {}

    for ident_chunk in chunked(list(affected_idents)):
        query = (
            select(
                Mereni_plynomery.identifikace,
                func.count(Mereni_plynomery.id).label("sample_size"),
                func.percentile_cont(0.5).within_group(Mereni_plynomery.delta).label("median"),
                func.percentile_cont(0.9).within_group(Mereni_plynomery.delta).label("p90"),
                func.percentile_cont(0.99).within_group(Mereni_plynomery.delta).label("p99"),
                func.greatest(
                    func.coalesce(func.stddev_samp(Mereni_plynomery.delta), 0.0),
                    0.0001,
                ).label("std"),
            )
            .where(
                Mereni_plynomery.identifikace.in_(ident_chunk),
                Mereni_plynomery.date >= cutoff,
                Mereni_plynomery.synthetic.is_(False),
                Mereni_plynomery.platne.is_(True),
                Mereni_plynomery.reset_detected.is_(False),
                Mereni_plynomery.delta.is_not(None),
            )
            .group_by(Mereni_plynomery.identifikace)
        )

        for row in session.execute(query).all():
            stats_by_ident[str(row.identifikace)] = {
                "sample_size": int(row.sample_size or 0),
                "median": float(row.median or 0.0),
                "p90": float(row.p90 or 0.0),
                "p99": float(row.p99 or 0.0),
                "std": float(row.std or 0.0),
            }

    return stats_by_ident


def compute_outlier_delta_threshold(stats: dict[str, float | int] | None) -> float | None:
    if not stats:
        return None

    sample_size = int(stats.get("sample_size") or 0)
    if sample_size < OUTLIER_MIN_HISTORY:
        return None

    median = float(stats.get("median") or 0.0)
    p90 = float(stats.get("p90") or median)
    p99 = float(stats.get("p99") or p90)
    std = max(float(stats.get("std") or 0.0), 0.0001)
    spread = max(p90 - median, 0.0)

    return max(
        OUTLIER_ABSOLUTE_MIN_DELTA,
        median + spread * OUTLIER_P90_SPREAD_MULTIPLIER,
        median + std * OUTLIER_STD_MULTIPLIER,
        p99 * OUTLIER_P99_MULTIPLIER,
    )


def is_delta_outlier(delta: float | None, stats: dict[str, float | int] | None) -> bool:
    if delta is None or delta <= 0:
        return False

    threshold = compute_outlier_delta_threshold(stats)
    if threshold is None:
        return False

    return delta > threshold


def format_ident_count_summary(counts: dict[str, int], *, limit: int = 10) -> str:
    if not counts:
        return ""

    ordered_counts = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    summary = ", ".join(
        f"{ident}:{count}"
        for ident, count in ordered_counts[:limit]
    )

    if len(ordered_counts) > limit:
        summary += ", ..."

    return summary


def build_outlier_review_payload(
    *,
    source_name: str,
    row: dict[str, object],
    prev: dict[str, object] | None,
    interval: int,
    candidate_delta: float,
    stats: dict[str, float | int] | None,
    detection_kind: str,
) -> dict[str, object]:
    threshold = compute_outlier_delta_threshold(stats)
    return {
        "identifikace": row["identifikace"],
        "date": row["date"],
        "zdroj": source_name,
        "source_recid": row.get("recid"),
        "seriove_cislo": str(row.get("seriove_cislo") or ""),
        "interval_minutes": interval,
        "detection_kind": detection_kind,
        "current_objem": float(row["objem"]),
        "baseline_objem": None if not prev else float(prev["objem"]),
        "baseline_date": None if not prev else prev["date"],
        "candidate_delta": float(candidate_delta),
        "threshold_delta": None if threshold is None else float(threshold),
        "sample_size": None if not stats else int(stats.get("sample_size") or 0),
        "median_delta": None if not stats else float(stats.get("median") or 0.0),
        "p90_delta": None if not stats else float(stats.get("p90") or 0.0),
        "p99_delta": None if not stats else float(stats.get("p99") or 0.0),
        "std_delta": None if not stats else float(stats.get("std") or 0.0),
    }


def resolve_gap(
    ident: str,
    prev: dict[str, object],
    current_dt: datetime,
    current_objem: float,
    interval: int,
    source_name: str,
    occupied_dates: set[datetime] | None = None,
) -> tuple[list[dict[str, object]], float | None, float | None]:
    prev_dt = prev["date"]
    prev_objem = prev["objem"]

    total_minutes = int((current_dt - prev_dt).total_seconds() // 60)
    num_slots = total_minutes // interval
    if num_slots <= 1:
        return [], None, None

    total_delta = current_objem - prev_objem
    if total_delta <= 0:
        return [], None, None

    mean_delta = round(total_delta / num_slots, 6)
    rows: list[dict[str, object]] = []
    blocked_dates = occupied_dates or set()

    for index in range(1, num_slots):
        slot_time = prev_dt + timedelta(minutes=index * interval)
        if slot_time in blocked_dates:
            continue
        rows.append(
            {
                "source_recid": None,
                "identifikace": ident,
                "seriove_cislo": prev.get("seriove_cislo"),
                "date": slot_time,
                **build_time_columns(slot_time, source_name),
                "objem": round(prev_objem + mean_delta * index, 6),
                "delta": mean_delta,
                "interval_minutes": interval,
                "day_of_week": compute_day_of_week(slot_time),
                "slot": compute_slot(slot_time, interval),
                "nocni_odber": mean_delta > MIN_NIGHT_DELTA and is_night_time(slot_time),
                "platne": True,
                "gap_detected": False,
                "synthetic": True,
                "zdroj": source_name,
                "reset_detected": False,
            }
        )

    terminal_delta = round(total_delta - mean_delta * len(rows), 6)
    return rows, mean_delta, terminal_delta


def build_occupied_dates(
    session: Session | None,
    new_rows: list[dict[str, object]],
    previous_map: dict[str, dict[str, object] | None],
    source_name: str,
) -> dict[str, set[datetime]]:
    affected_idents = set(previous_map.keys())
    min_date = min(
        (
            date_value
            for date_value in (
                [row["date"] for row in new_rows if isinstance(row.get("date"), datetime)]
                + [
                    previous["date"]
                    for previous in previous_map.values()
                    if previous and isinstance(previous.get("date"), datetime)
                ]
            )
        ),
        default=None,
    )
    max_date = max(
        (row["date"] for row in new_rows if isinstance(row.get("date"), datetime)),
        default=None,
    )
    if min_date is None or max_date is None:
        return {}

    occupied_dates = get_existing_measurement_dates(
        session,
        affected_idents,
        source_name,
        min_date=min_date,
        max_date=max_date,
    )
    for row in new_rows:
        ident = str(row["identifikace"])
        row_date = row.get("date")
        if isinstance(row_date, datetime):
            occupied_dates.setdefault(ident, set()).add(row_date)

    return occupied_dates


def filter_valid_rows(session: Session, rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    if not rows:
        return []

    sanitized = []
    dropped_invalid = 0

    for row in rows:
        ident = str(row.get("identifikace") or "").strip()
        dt = row.get("date")
        objem = row.get("objem")

        if not ident or dt is None or objem is None:
            dropped_invalid += 1
            continue

        row["identifikace"] = ident
        row["platne"] = bool(row.get("platne", True))
        row["reset_detected"] = False
        sanitized.append(row)

    if not sanitized:
        logger.warning("%s dropped rows - invalid: %s", source_name, dropped_invalid)
        return []

    valid_idents = set()
    ident_list = list({row["identifikace"] for row in sanitized})
    with Session(engine_ms) as ms_session:
        for ident_chunk in chunked(ident_list):
            valid_idents.update(
                ms_session.execute(
                    select(Plynomer_areal_Zarizeni.identifikace).where(Plynomer_areal_Zarizeni.identifikace.in_(ident_chunk))
                )
                .scalars()
                .all()
            )

    filtered = [row for row in sanitized if row["identifikace"] in valid_idents]
    dropped_fk = len(sanitized) - len(filtered)

    if filtered:
        affected_idents = {row["identifikace"] for row in filtered}
        last_existing = get_last_measurements(session, affected_idents, only_valid=True)
        previous_by_ident = {
            ident: {
                "objem": last.objem,
                "date": last.date,
                "seriove_cislo": last.seriove_cislo,
            }
            for ident, last in last_existing.items()
            if last is not None
        }

        for row in sorted(filtered, key=lambda item: (item["identifikace"], item["date"])):
            ident = row["identifikace"]
            previous = previous_by_ident.get(ident)
            serial_changed = (
                previous is not None
                and previous.get("seriove_cislo") is not None
                and row.get("seriove_cislo") is not None
                and row["seriove_cislo"] != previous["seriove_cislo"]
            )
            volume_reset = previous is not None and row["objem"] < previous["objem"]
            if serial_changed or volume_reset:
                row["reset_detected"] = True

            if row["platne"]:
                previous_by_ident[ident] = {
                    "objem": row["objem"],
                    "date": row["date"],
                    "seriove_cislo": row.get("seriove_cislo"),
                }

    if dropped_invalid or dropped_fk:
        logger.warning(
            "%s dropped rows - invalid: %s, missing_ms_zarizeni_identifikace: %s",
            source_name,
            dropped_invalid,
            dropped_fk,
        )

    return filtered


def prepare_rows(
    session: Session,
    new_rows: list[dict[str, object]],
    source_name: str,
    *,
    include_outlier_reviews: bool = False,
    review_overrides: dict[tuple[str, object, str], str] | None = None,
):
    if not new_rows:
        return ([], []) if include_outlier_reviews else []

    affected_idents = {row["identifikace"] for row in new_rows}
    last_existing = get_last_measurements(session, affected_idents, only_valid=True)
    reference_time = max(
        (row["date"] for row in new_rows if isinstance(row.get("date"), datetime)),
        default=utc_now_naive(),
    )
    recent_delta_stats = get_recent_delta_stats(
        session,
        affected_idents,
        reference_time=reference_time,
    )
    previous_map: dict[str, dict[str, object] | None] = {}

    for ident in affected_idents:
        last = last_existing.get(ident)
        previous_map[ident] = None
        if last is not None:
            previous_map[ident] = {
                "objem": last.objem,
                "date": last.date,
                "seriove_cislo": last.seriove_cislo,
            }

    occupied_dates = build_occupied_dates(session, new_rows, previous_map, source_name)
    rows_to_insert: list[dict[str, object]] = []
    outlier_reviews: list[dict[str, object]] = []
    outlier_count = 0
    outlier_by_ident: dict[str, int] = {}
    overrides_by_key = review_overrides or {}

    for row in sorted(new_rows, key=lambda item: (item["identifikace"], item["date"])):
        ident = row["identifikace"]
        dt = row["date"]
        interval = int(row["interval_minutes"])
        objem = float(row["objem"])
        prev = previous_map.get(ident)
        ident_stats = recent_delta_stats.get(ident)
        review_override = overrides_by_key.get((ident, dt, source_name))

        delta = None
        gap_detected = False
        is_valid_row = bool(row.get("platne", True))
        reset_detected = bool(row.get("reset_detected", False))

        if is_valid_row and not reset_detected and prev and prev.get("date") is not None:
            expected_interval = timedelta(minutes=interval)
            actual_diff = dt - prev["date"]

            if actual_diff > expected_interval * MAX_GAP_MULTIPLIER and objem >= prev["objem"]:
                synthetic_rows, mean_gap_delta, terminal_gap_delta = resolve_gap(
                    ident,
                    prev,
                    dt,
                    objem,
                    interval,
                    source_name,
                    occupied_dates.get(ident),
                )
                is_gap_outlier = (
                    mean_gap_delta is not None
                    and (
                        review_override == "CONFIRMED_OUTLIER"
                        or is_delta_outlier(mean_gap_delta, ident_stats)
                    )
                )
                if is_gap_outlier:
                    if review_override == "CONFIRMED_CONSUMPTION":
                        rows_to_insert.extend(synthetic_rows)
                        if mean_gap_delta is not None:
                            gap_detected = True
                            delta = terminal_gap_delta
                    else:
                        is_valid_row = False
                        outlier_count += 1
                        outlier_by_ident[ident] = outlier_by_ident.get(ident, 0) + 1
                        if include_outlier_reviews and review_override != "CONFIRMED_OUTLIER" and mean_gap_delta is not None:
                            outlier_reviews.append(
                                build_outlier_review_payload(
                                    source_name=source_name,
                                    row=row,
                                    prev=prev,
                                    interval=interval,
                                    candidate_delta=mean_gap_delta,
                                    stats=ident_stats,
                                    detection_kind="GAP_MEAN",
                                )
                            )
                else:
                    rows_to_insert.extend(synthetic_rows)
                    if mean_gap_delta is not None:
                        gap_detected = True
                        delta = terminal_gap_delta
            elif objem >= prev["objem"]:
                candidate_delta = objem - prev["objem"]
                is_normal_outlier = (
                    review_override == "CONFIRMED_OUTLIER"
                    or is_delta_outlier(candidate_delta, ident_stats)
                )
                if is_normal_outlier:
                    if review_override == "CONFIRMED_CONSUMPTION":
                        delta = candidate_delta
                    else:
                        is_valid_row = False
                        outlier_count += 1
                        outlier_by_ident[ident] = outlier_by_ident.get(ident, 0) + 1
                        if include_outlier_reviews and review_override != "CONFIRMED_OUTLIER":
                            outlier_reviews.append(
                                build_outlier_review_payload(
                                    source_name=source_name,
                                    row=row,
                                    prev=prev,
                                    interval=interval,
                                    candidate_delta=candidate_delta,
                                    stats=ident_stats,
                                    detection_kind="NORMAL_DELTA",
                                )
                            )
                else:
                    delta = candidate_delta

        if delta is not None:
            delta = round(delta, 6)

        if reset_detected:
            delta = None

        nocni_odber = (
            is_valid_row
            and not reset_detected
            and delta is not None
            and delta > MIN_NIGHT_DELTA
            and is_night_time(dt)
        )

        rows_to_insert.append(
            {
                "source_recid": row["recid"],
                "identifikace": ident,
                "seriove_cislo": row.get("seriove_cislo"),
                "date": dt,
                **build_time_columns(dt, source_name, row),
                "objem": objem,
                "delta": delta,
                "interval_minutes": interval,
                "day_of_week": compute_day_of_week(dt),
                "slot": compute_slot(dt, interval),
                "nocni_odber": nocni_odber,
                "platne": is_valid_row,
                "gap_detected": gap_detected,
                "synthetic": False,
                "zdroj": source_name,
                "reset_detected": reset_detected,
            }
        )

        if is_valid_row:
            previous_map[ident] = {
                "objem": objem,
                "date": dt,
                "seriove_cislo": row.get("seriove_cislo"),
            }

    if outlier_count:
        ident_summary = format_ident_count_summary(outlier_by_ident)
        if ident_summary:
            logger.warning(
                "%s detected invalid outlier rows: %s (%s)",
                source_name,
                outlier_count,
                ident_summary,
            )
        else:
            logger.warning(
                "%s detected invalid outlier rows: %s",
                source_name,
                outlier_count,
            )

    if include_outlier_reviews:
        return rows_to_insert, outlier_reviews

    return rows_to_insert


def import_measurements(session: Session, source_name: str, ms_rows: list[dict[str, object]]) -> dict[str, object]:
    if not ms_rows:
        return {
            "rows": [],
            "new_outlier_review_ids": [],
        }

    new_rows = filter_valid_rows(session, ms_rows, source_name)
    if not new_rows:
        return {
            "rows": [],
            "new_outlier_review_ids": [],
        }

    rows_to_insert, outlier_reviews = prepare_rows(
        session,
        new_rows,
        source_name,
        include_outlier_reviews=True,
    )
    if not rows_to_insert:
        return {
            "rows": [],
            "new_outlier_review_ids": [],
        }

    for batch in chunked(rows_to_insert):
        statement = insert(Mereni_plynomery).on_conflict_do_nothing(index_elements=["identifikace", "date", "zdroj"])
        session.execute(statement, batch)

    new_outlier_review_ids = []
    if outlier_reviews:
        review_keys = [build_outlier_review_key(row) for row in outlier_reviews]
        existing_review_ids = load_outlier_review_ids_by_keys(review_keys, session=session)
        upsert_outlier_review_candidates(outlier_reviews, session=session)
        inserted_review_keys = [key for key in review_keys if key not in existing_review_ids]
        if inserted_review_keys:
            inserted_review_id_map = load_outlier_review_ids_by_keys(inserted_review_keys, session=session)
            new_outlier_review_ids = [
                inserted_review_id_map[key]
                for key in inserted_review_keys
                if key in inserted_review_id_map
            ]

    logger.info("%s prepared for insert: %s", source_name, len(rows_to_insert))
    return {
        "rows": rows_to_insert,
        "new_outlier_review_ids": new_outlier_review_ids,
    }


def plynomery_db_import() -> dict[str, object]:
    ensure_destination_table()

    with Session(engine) as session:
        with session.begin():
            rows_areal = fetch_from_ms_areal()
            inserted_areal = import_measurements(session, "AREAL", rows_areal)
            logger.info("AREAL inserted: %s", len(inserted_areal["rows"]))

        new_outlier_review_ids = list(inserted_areal["new_outlier_review_ids"])
        notification_result = {
            "matched": 0,
            "emails_sent": 0,
            "deliveries_sent": 0,
            "deliveries_failed": 0,
        }
        if new_outlier_review_ids:
            try:
                notification_result = process_new_outlier_review_notifications(new_outlier_review_ids)
            except Exception:
                logger.exception(
                    "Failed to process new plynomery outlier review notifications for review IDs: %s",
                    new_outlier_review_ids,
                )
            else:
                logger.info(
                    "Plynomery outlier review notifications processed: matched=%s, emails_sent=%s, deliveries_sent=%s, deliveries_failed=%s",
                    notification_result["matched"],
                    notification_result["emails_sent"],
                    notification_result["deliveries_sent"],
                    notification_result["deliveries_failed"],
                )

        return {
            "inserted_areal": len(inserted_areal["rows"]),
            "new_outlier_review_ids": new_outlier_review_ids,
            "notification_result": notification_result,
        }
