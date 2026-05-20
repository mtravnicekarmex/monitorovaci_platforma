from __future__ import annotations

import logging
from datetime import datetime, timedelta
from time import perf_counter

from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_MS, ENGINE_PG
from moduly.mereni.reset_detection import has_significant_negative_diff
from moduly.mereni.kalorimetry.database.models import (
    Kalorimetr_areal_Mereni,
    Kalorimetr_areal_Zarizeni,
    Mereni_kalorimetry,
)
from moduly.mereni.kalorimetry.database.outlier_reviews import (
    build_outlier_review_key,
    load_outlier_review_ids_by_keys,
    upsert_outlier_review_candidates,
)
from moduly.mereni.time_semantics import build_time_columns


logger = logging.getLogger(__name__)

engine = ENGINE_PG
engine_ms = ENGINE_MS

CHUNK_SIZE = 5000
DEFAULT_INTERVAL_MINUTES = 15
MAX_GAP_MULTIPLIER = 2
MIN_NIGHT_DELTA = 0.01
SOURCE_NAME = "AREAL"
OUTLIER_LOOKBACK_DAYS = 90
OUTLIER_MIN_HISTORY = 48
OUTLIER_ABSOLUTE_MIN_DELTA = 10.0
OUTLIER_P90_SPREAD_MULTIPLIER = 25.0
OUTLIER_STD_MULTIPLIER = 12.0
OUTLIER_P99_MULTIPLIER = 8.0


def chunked(items, size: int = CHUNK_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def ensure_destination_table() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))

    inspector = inspect(engine)
    monitoring_tables = inspector.get_table_names(schema="monitoring")
    expected_table = Mereni_kalorimetry.__tablename__

    case_mismatch = next(
        (
            table_name
            for table_name in monitoring_tables
            if table_name.lower() == expected_table.lower() and table_name != expected_table
        ),
        None,
    )
    if case_mismatch:
        raise RuntimeError(
            f"Case mismatch in monitoring schema: model expects '{expected_table}', "
            f"but database has '{case_mismatch}'. Unify table naming first."
        )

    if expected_table not in monitoring_tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE monitoring."Mereni_kalorimetry_vse" (
                        id BIGSERIAL PRIMARY KEY,
                        source_recid BIGINT,
                        identifikace VARCHAR(250) NOT NULL,
                        seriove_cislo BIGINT,
                        date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                        source_date TIMESTAMP WITHOUT TIME ZONE,
                        time_utc TIMESTAMP WITH TIME ZONE,
                        time_basis VARCHAR(40),
                        source_timezone VARCHAR(64),
                        source_utc_offset_minutes INTEGER,
                        time_fold INTEGER,
                        timestamp_position VARCHAR(20),
                        spotreba_energie DOUBLE PRECISION NOT NULL,
                        objem DOUBLE PRECISION,
                        delta DOUBLE PRECISION,
                        interval_minutes INTEGER NOT NULL,
                        day_of_week INTEGER NOT NULL,
                        slot INTEGER NOT NULL,
                        nocni_odber BOOLEAN NOT NULL DEFAULT FALSE,
                        platne BOOLEAN NOT NULL DEFAULT TRUE,
                        gap_detected BOOLEAN NOT NULL DEFAULT FALSE,
                        synthetic BOOLEAN NOT NULL DEFAULT FALSE,
                        zdroj VARCHAR(20) NOT NULL,
                        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
                        reset_detected BOOLEAN NOT NULL DEFAULT FALSE,
                        CONSTRAINT uq_kalorimetry_ident_date_zdroj UNIQUE (identifikace, date, zdroj),
                        CONSTRAINT uq_kalorimetry_source_recid_zdroj UNIQUE (source_recid, zdroj)
                    )
                    """
                )
            )
        logger.info('Created missing table monitoring."%s"', expected_table)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE monitoring."Mereni_kalorimetry_vse"
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
                CREATE TABLE IF NOT EXISTS monitoring.kalorimetry_import_state (
                    zdroj VARCHAR(20) PRIMARY KEY,
                    last_source_recid BIGINT NOT NULL,
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_Mereni_kalorimetry_vse_source_recid
                ON monitoring."Mereni_kalorimetry_vse" (source_recid)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_kalorimetry_ident_interval_slot
                ON monitoring."Mereni_kalorimetry_vse" (identifikace, interval_minutes, day_of_week, slot)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_kalorimetry_ident_date_desc
                ON monitoring."Mereni_kalorimetry_vse" (identifikace, date)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_kalorimetry_date_desc
                ON monitoring."Mereni_kalorimetry_vse" (date)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_kalorimetry_vse_time_utc
                ON monitoring."Mereni_kalorimetry_vse" (time_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_kalorimetry_vse_ident_time_utc
                ON monitoring."Mereni_kalorimetry_vse" (identifikace, time_utc)
                """
            )
        )


def get_last_imported_recid(session: Session, source_name: str) -> int | None:
    state_query = text(
        """
        SELECT last_source_recid
        FROM monitoring.kalorimetry_import_state
        WHERE zdroj = :source_name
        """
    )
    state_value = session.execute(state_query, {"source_name": source_name}).scalar()
    if state_value is not None:
        return int(state_value)

    query = select(func.max(Mereni_kalorimetry.source_recid)).where(Mereni_kalorimetry.zdroj == source_name)
    return session.execute(query).scalar()


def update_import_state(session: Session, source_name: str, ms_rows: list[dict[str, object]]) -> None:
    source_recids = [int(row["recid"]) for row in ms_rows if row.get("recid") is not None]
    if not source_recids:
        return

    session.execute(
        text(
            """
            INSERT INTO monitoring.kalorimetry_import_state (zdroj, last_source_recid, updated_at)
            VALUES (:source_name, :last_source_recid, now())
            ON CONFLICT (zdroj) DO UPDATE
            SET last_source_recid = GREATEST(
                    monitoring.kalorimetry_import_state.last_source_recid,
                    EXCLUDED.last_source_recid
                ),
                updated_at = now()
            """
        ),
        {
            "source_name": source_name,
            "last_source_recid": max(source_recids),
        },
    )


def fetch_from_ms_areal() -> list[dict[str, object]]:
    t0 = perf_counter()
    with Session(engine) as pg_session:
        last_recid = get_last_imported_recid(pg_session, SOURCE_NAME)
    logger.info("%s last_recid: %s", SOURCE_NAME, last_recid)

    with Session(engine_ms) as ms_session:
        query = (
            select(
                Kalorimetr_areal_Mereni.recid,
                Kalorimetr_areal_Mereni.identifikace,
                Kalorimetr_areal_Mereni.seriove_cislo,
                Kalorimetr_areal_Mereni.date,
                Kalorimetr_areal_Mereni.spotreba_energie,
                Kalorimetr_areal_Mereni.objem,
                Kalorimetr_areal_Mereni.platne,
            )
            .where(
                Kalorimetr_areal_Mereni.identifikace.is_not(None),
                Kalorimetr_areal_Mereni.date.is_not(None),
                Kalorimetr_areal_Mereni.spotreba_energie.is_not(None),
            )
            .order_by(Kalorimetr_areal_Mereni.recid)
        )
        if last_recid is not None:
            query = query.where(Kalorimetr_areal_Mereni.recid > last_recid)

        rows = ms_session.execute(query).all()
        logger.info("%s rows fetched: %s in %.1fs", SOURCE_NAME, len(rows), perf_counter() - t0)

    return [
        {
            "recid": row.recid,
            "identifikace": row.identifikace,
            "seriove_cislo": row.seriove_cislo,
            "date": row.date,
            "spotreba_energie": row.spotreba_energie,
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


def get_last_measurements(
    session: Session,
    affected_idents: set[str],
    *,
    only_valid: bool = False,
) -> dict[str, Mereni_kalorimetry]:
    if session is None or not affected_idents:
        return {}

    rows_by_ident: dict[str, Mereni_kalorimetry] = {}
    for ident_chunk in chunked(list(affected_idents)):
        subquery = (
            select(
                Mereni_kalorimetry.identifikace,
                func.max(Mereni_kalorimetry.date).label("max_date"),
            )
            .where(Mereni_kalorimetry.identifikace.in_(ident_chunk))
        )
        if only_valid:
            subquery = subquery.where(Mereni_kalorimetry.platne.is_(True))
        subquery = subquery.group_by(Mereni_kalorimetry.identifikace).subquery()

        query = (
            select(Mereni_kalorimetry)
            .join(
                subquery,
                (Mereni_kalorimetry.identifikace == subquery.c.identifikace)
                & (Mereni_kalorimetry.date == subquery.c.max_date),
            )
        )
        if only_valid:
            query = query.where(Mereni_kalorimetry.platne.is_(True))

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
            select(Mereni_kalorimetry.identifikace, Mereni_kalorimetry.date)
            .where(
                Mereni_kalorimetry.identifikace.in_(ident_chunk),
                Mereni_kalorimetry.zdroj == source_name,
                Mereni_kalorimetry.date >= min_date,
                Mereni_kalorimetry.date <= max_date,
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
    if session is None or not hasattr(session, "execute") or not affected_idents:
        return {}

    resolved_reference_time = reference_time or utc_now_naive()
    cutoff = resolved_reference_time - timedelta(days=OUTLIER_LOOKBACK_DAYS)
    stats_by_ident: dict[str, dict[str, float | int]] = {}

    for ident_chunk in chunked(list(affected_idents)):
        query = (
            select(
                Mereni_kalorimetry.identifikace,
                func.count(Mereni_kalorimetry.id).label("sample_size"),
                func.percentile_cont(0.5).within_group(Mereni_kalorimetry.delta).label("median"),
                func.percentile_cont(0.9).within_group(Mereni_kalorimetry.delta).label("p90"),
                func.percentile_cont(0.99).within_group(Mereni_kalorimetry.delta).label("p99"),
                func.greatest(
                    func.coalesce(func.stddev_samp(Mereni_kalorimetry.delta), 0.0),
                    0.0001,
                ).label("std"),
            )
            .where(
                Mereni_kalorimetry.identifikace.in_(ident_chunk),
                Mereni_kalorimetry.date >= cutoff,
                Mereni_kalorimetry.synthetic.is_(False),
                Mereni_kalorimetry.platne.is_(True),
                Mereni_kalorimetry.reset_detected.is_(False),
                Mereni_kalorimetry.delta.is_not(None),
            )
            .group_by(Mereni_kalorimetry.identifikace)
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
        "current_objem": float(row["spotreba_energie"]),
        "baseline_objem": None if not prev else float(prev["spotreba_energie"]),
        "baseline_date": None if not prev else prev["date"],
        "candidate_delta": float(candidate_delta),
        "threshold_delta": None if threshold is None else float(threshold),
        "sample_size": None if not stats else int(stats.get("sample_size") or 0),
        "median_delta": None if not stats else float(stats.get("median") or 0.0),
        "p90_delta": None if not stats else float(stats.get("p90") or 0.0),
        "p99_delta": None if not stats else float(stats.get("p99") or 0.0),
        "std_delta": None if not stats else float(stats.get("std") or 0.0),
    }


def build_occupied_dates(
    session: Session | None,
    new_rows: list[dict[str, object]],
    previous_map: dict[str, dict[str, object] | None],
    source_name: str,
) -> dict[str, set[datetime]]:
    affected_idents = set(previous_map.keys())
    candidate_dates = [
        row["date"]
        for row in new_rows
        if isinstance(row.get("date"), datetime)
    ]
    candidate_dates.extend(
        previous["date"]
        for previous in previous_map.values()
        if previous and isinstance(previous.get("date"), datetime)
    )
    min_date = min(candidate_dates, default=None)
    max_date = max(candidate_dates, default=None)
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


def resolve_gap(
    ident: str,
    prev: dict[str, object],
    current_dt: datetime,
    current_spotreba_energie: float,
    current_objem: float | None,
    interval: int,
    source_name: str,
    occupied_dates: set[datetime] | None = None,
) -> tuple[list[dict[str, object]], float | None, float | None]:
    prev_dt = prev["date"]
    prev_spotreba_energie = float(prev["spotreba_energie"])

    total_minutes = int((current_dt - prev_dt).total_seconds() // 60)
    num_slots = total_minutes // interval
    if num_slots <= 1:
        return [], None, None

    total_delta = current_spotreba_energie - prev_spotreba_energie
    if total_delta <= 0:
        return [], None, None

    mean_delta = round(total_delta / num_slots, 6)
    blocked_dates = occupied_dates or set()

    prev_objem = prev.get("objem")
    can_interpolate_objem = (
        prev_objem is not None
        and current_objem is not None
        and current_objem >= float(prev_objem)
    )
    mean_objem_delta = None
    if can_interpolate_objem:
        mean_objem_delta = round((current_objem - float(prev_objem)) / num_slots, 6)

    rows: list[dict[str, object]] = []
    for index in range(1, num_slots):
        slot_time = prev_dt + timedelta(minutes=index * interval)
        if slot_time in blocked_dates:
            continue

        synthetic_objem = None
        if mean_objem_delta is not None:
            synthetic_objem = round(float(prev_objem) + mean_objem_delta * index, 6)

        rows.append(
            {
                "source_recid": None,
                "identifikace": ident,
                "seriove_cislo": prev.get("seriove_cislo"),
                "date": slot_time,
                **build_time_columns(slot_time, source_name),
                "spotreba_energie": round(prev_spotreba_energie + mean_delta * index, 6),
                "objem": synthetic_objem,
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


def filter_valid_rows(session: Session, rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    if not rows:
        return []

    sanitized: list[dict[str, object]] = []
    dropped_invalid = 0

    for row in rows:
        ident = str(row.get("identifikace") or "").strip()
        dt = row.get("date")
        spotreba_energie = row.get("spotreba_energie")

        if not ident or dt is None or spotreba_energie is None:
            dropped_invalid += 1
            continue

        try:
            row["spotreba_energie"] = float(spotreba_energie)
            row["objem"] = None if row.get("objem") is None else float(row["objem"])
        except (TypeError, ValueError):
            dropped_invalid += 1
            continue

        row["identifikace"] = ident
        row["platne"] = bool(row.get("platne", True))
        row["reset_detected"] = False
        sanitized.append(row)

    if not sanitized:
        logger.warning("%s dropped rows - invalid: %s", source_name, dropped_invalid)
        return []

    valid_idents: set[str] = set()
    ident_list = list({row["identifikace"] for row in sanitized})
    with Session(engine_ms) as ms_session:
        for ident_chunk in chunked(ident_list):
            valid_idents.update(
                ms_session.execute(
                    select(Kalorimetr_areal_Zarizeni.identifikace).where(
                        Kalorimetr_areal_Zarizeni.identifikace.in_(ident_chunk)
                    )
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
                "spotreba_energie": last.spotreba_energie,
                "date": last.date,
                "seriove_cislo": last.seriove_cislo,
            }
            for ident, last in last_existing.items()
            if last is not None
        }

        for row in sorted(filtered, key=lambda item: (item["identifikace"], item["date"])):
            ident = row["identifikace"]
            previous = previous_by_ident.get(ident)
            if previous is not None and has_significant_negative_diff(
                row["spotreba_energie"],
                previous["spotreba_energie"],
            ):
                row["reset_detected"] = True

            if row["platne"]:
                previous_by_ident[ident] = {
                    "spotreba_energie": row["spotreba_energie"],
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
                "spotreba_energie": last.spotreba_energie,
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
        spotreba_energie = float(row["spotreba_energie"])
        objem = row.get("objem")
        objem = None if objem is None else float(objem)
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

            if actual_diff > expected_interval * MAX_GAP_MULTIPLIER and spotreba_energie >= prev["spotreba_energie"]:
                synthetic_rows, mean_gap_delta, terminal_gap_delta = resolve_gap(
                    ident,
                    prev,
                    dt,
                    spotreba_energie,
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
            elif spotreba_energie >= prev["spotreba_energie"]:
                candidate_delta = spotreba_energie - float(prev["spotreba_energie"])
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
                "spotreba_energie": spotreba_energie,
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
                "spotreba_energie": spotreba_energie,
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
        update_import_state(session, source_name, ms_rows)
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
        update_import_state(session, source_name, ms_rows)
        return {
            "rows": [],
            "new_outlier_review_ids": [],
        }

    for batch in chunked(rows_to_insert):
        statement = insert(Mereni_kalorimetry).on_conflict_do_nothing()
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

    update_import_state(session, source_name, ms_rows)
    logger.info("%s prepared for insert: %s", source_name, len(rows_to_insert))
    return {
        "rows": rows_to_insert,
        "new_outlier_review_ids": new_outlier_review_ids,
    }


def kalorimetry_db_import() -> dict[str, int]:
    ensure_destination_table()

    with Session(engine) as session:
        with session.begin():
            rows_areal = fetch_from_ms_areal()
            inserted_areal = import_measurements(session, SOURCE_NAME, rows_areal)
            logger.info("%s inserted: %s", SOURCE_NAME, len(inserted_areal["rows"]))

    return {"inserted_areal": len(inserted_areal["rows"])}
