import logging
from datetime import datetime, timedelta
from time import perf_counter
from sqlalchemy import select, func, inspect, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from moduly.mereni.vodomery.database.models import (
    Mereni_vodomery,
    Vodomer_areal_Mereni,
    Vodomer_areal_Zarizeni,
    Vodomer_SCVK_Mereni,
)
from moduly.mereni.vodomery.alerting.outlier_notifications import process_new_outlier_review_notifications
from moduly.mereni.vodomery.database.outlier_reviews import (
    build_outlier_review_key,
    load_outlier_review_ids_by_keys,
    upsert_outlier_review_candidates,
)
from moduly.mereni.vodomery.database.runtime_schema import drop_legacy_identifikace_fk
from moduly.mereni.time_semantics import build_time_columns
from core.db.connect import ENGINE_MS, ENGINE_PG
from app.time_utils import utc_now_naive


engine = ENGINE_PG
engine_ms = ENGINE_MS
logger = logging.getLogger(__name__)


CHUNK_SIZE = 5000
OUTLIER_LOOKBACK_DAYS = 90
OUTLIER_MIN_HISTORY = 48
OUTLIER_ABSOLUTE_MIN_DELTA = 10.0
OUTLIER_P90_SPREAD_MULTIPLIER = 25.0
OUTLIER_STD_MULTIPLIER = 12.0
OUTLIER_P99_MULTIPLIER = 8.0


def chunked(items, size=CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def ensure_destination_table():
    # Ensure target schema exists before checking/creating the table.
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))

    inspector = inspect(engine)
    monitoring_tables = inspector.get_table_names(schema="monitoring")
    expected_table = Mereni_vodomery.__tablename__

    # Protect against subtle case-only mismatches in PostgreSQL identifiers.
    case_mismatch = next(
        (t for t in monitoring_tables if t.lower() == expected_table.lower() and t != expected_table),
        None
    )
    if case_mismatch:
        raise RuntimeError(
            f"Case mismatch in monitoring schema: model expects '{expected_table}', "
            f"but database has '{case_mismatch}'. Unify table naming first."
        )

    if expected_table not in monitoring_tables:
        Mereni_vodomery.__table__.create(bind=engine, checkfirst=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_vodomery_vse_time_utc
                    ON monitoring."Mereni_vodomery_vse" (time_utc)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_vodomery_vse_ident_time_utc
                    ON monitoring."Mereni_vodomery_vse" (identifikace, time_utc)
                    """
                )
            )
        logger.info('Created missing table monitoring."%s"', expected_table)

    drop_legacy_identifikace_fk(expected_table)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE monitoring."Mereni_vodomery_vse"
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
                CREATE INDEX IF NOT EXISTS ix_vodomery_vse_time_utc
                ON monitoring."Mereni_vodomery_vse" (time_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_vodomery_vse_ident_time_utc
                ON monitoring."Mereni_vodomery_vse" (identifikace, time_utc)
                """
            )
        )



def get_last_imported_recid(session, source_name):

    q = (
        select(func.max(Mereni_vodomery.source_recid))
        .where(Mereni_vodomery.zdroj == source_name)
    )

    return session.execute(q).scalar()



def fetch_from_ms_areal():

    t0 = perf_counter()
    with Session(engine) as pg_session:
        last_recid = get_last_imported_recid(pg_session, "AREAL")
    logger.info("AREAL last_recid: %s", last_recid)

    with Session(engine_ms) as ms_session:

        q = select(
            Vodomer_areal_Mereni.recid,
            Vodomer_areal_Mereni.identifikace,
            Vodomer_areal_Mereni.seriove_cislo,
            Vodomer_areal_Mereni.date,
            Vodomer_areal_Mereni.objem
        )

        if last_recid is not None:
            q = q.where(Vodomer_areal_Mereni.recid > last_recid)

        q = q.order_by(Vodomer_areal_Mereni.recid)

        rows = ms_session.execute(q).all()
        logger.info("AREAL rows fetched: %s in %.1fs", len(rows), perf_counter() - t0)

        result = []

        for r in rows:
            result.append({
                "recid": r.recid,
                "identifikace": r.identifikace,
                "seriove_cislo": r.seriove_cislo,
                "date": r.date,
                "objem": r.objem,
                "interval_minutes": 15,
            })

        return result



def fetch_from_ms_scvk():

    # 1️⃣ zjistíme poslední importovaný recid pro SCVK
    t0 = perf_counter()
    with Session(engine) as pg_session:
        last_recid = get_last_imported_recid(pg_session, "SCVK")
    logger.info("SCVK last_recid: %s", last_recid)

    # 2️⃣ načteme nová data z PG (SCVK je v PG)
    with Session(engine) as ms_session:

        q = select(
            Vodomer_SCVK_Mereni.recid,
            Vodomer_SCVK_Mereni.identifikace,
            Vodomer_SCVK_Mereni.seriove_cislo,
            Vodomer_SCVK_Mereni.date,
            Vodomer_SCVK_Mereni.objem
        )

        if last_recid is not None:
            q = q.where(Vodomer_SCVK_Mereni.recid > last_recid)

        q = q.order_by(Vodomer_SCVK_Mereni.recid)

        rows = ms_session.execute(q).all()
        logger.info("SCVK rows fetched: %s in %.1fs", len(rows), perf_counter() - t0)

        result = []

        for r in rows:
            result.append({
                "recid": r.recid,
                "identifikace": r.identifikace,
                "seriove_cislo": r.seriove_cislo,
                "date": r.date,
                "objem": r.objem,
                "interval_minutes": 20,
            })

        return result




# -------------------------------------------------
# Pomocné funkce
# -------------------------------------------------

def compute_slot(dt: datetime, interval_minutes: int) -> int:
    minutes_from_midnight = dt.hour * 60 + dt.minute
    return minutes_from_midnight // interval_minutes


def compute_day_of_week(dt: datetime) -> int:
    return dt.weekday()  # 0 = Monday


def is_night_time(dt: datetime) -> bool:
    # noční pásmo 23:00–04:59
    return dt.hour >= 23 or dt.hour < 5


# -------------------------------------------------
# Načtení posledních měření pro dotčené vodoměry
# -------------------------------------------------

def get_last_measurements(session, affected_idents, *, only_valid=False):

    if not affected_idents:
        return {}

    all_rows = {}
    idents_list = list(affected_idents)
    for ident_chunk in chunked(idents_list):
        subq_query = (
            select(
                Mereni_vodomery.identifikace,
                func.max(Mereni_vodomery.date).label("max_date")
            )
            .where(Mereni_vodomery.identifikace.in_(ident_chunk))
        )
        if only_valid:
            subq_query = subq_query.where(Mereni_vodomery.platne.is_(True))

        subq = subq_query.group_by(Mereni_vodomery.identifikace).subquery()

        q = (
            select(Mereni_vodomery)
            .join(
                subq,
                (Mereni_vodomery.identifikace == subq.c.identifikace) &
                (Mereni_vodomery.date == subq.c.max_date)
            )
        )
        if only_valid:
            q = q.where(Mereni_vodomery.platne.is_(True))
        rows = session.execute(q).scalars().all()
        for r in rows:
            all_rows[r.identifikace] = r

    return all_rows


def get_existing_measurement_dates(
    session,
    affected_idents,
    source_name,
    *,
    min_date,
    max_date,
):
    if session is None or not affected_idents:
        return {}

    dates_by_ident = {}
    for ident_chunk in chunked(list(affected_idents)):
        q = (
            select(Mereni_vodomery.identifikace, Mereni_vodomery.date)
            .where(
                Mereni_vodomery.identifikace.in_(ident_chunk),
                Mereni_vodomery.zdroj == source_name,
                Mereni_vodomery.date >= min_date,
                Mereni_vodomery.date <= max_date,
            )
        )
        for ident, measurement_date in session.execute(q).all():
            dates_by_ident.setdefault(str(ident), set()).add(measurement_date)

    return dates_by_ident


def get_recent_delta_stats(session, affected_idents, *, reference_time=None):

    if not affected_idents:
        return {}

    reference_time = reference_time or utc_now_naive()
    cutoff = reference_time - timedelta(days=OUTLIER_LOOKBACK_DAYS)
    all_stats = {}
    idents_list = list(affected_idents)

    for ident_chunk in chunked(idents_list):
        q = (
            select(
                Mereni_vodomery.identifikace,
                func.count(Mereni_vodomery.id).label("sample_size"),
                func.percentile_cont(0.5).within_group(Mereni_vodomery.delta).label("median"),
                func.percentile_cont(0.9).within_group(Mereni_vodomery.delta).label("p90"),
                func.percentile_cont(0.99).within_group(Mereni_vodomery.delta).label("p99"),
                func.greatest(
                    func.coalesce(func.stddev_samp(Mereni_vodomery.delta), 0.0),
                    0.0001,
                ).label("std"),
            )
            .where(
                Mereni_vodomery.identifikace.in_(ident_chunk),
                Mereni_vodomery.date >= cutoff,
                Mereni_vodomery.synthetic.is_(False),
                Mereni_vodomery.platne.is_(True),
                Mereni_vodomery.reset_detected.is_(False),
                Mereni_vodomery.delta.is_not(None),
            )
            .group_by(Mereni_vodomery.identifikace)
        )

        for row in session.execute(q).all():
            all_stats[str(row.identifikace)] = {
                "sample_size": int(row.sample_size or 0),
                "median": float(row.median or 0.0),
                "p90": float(row.p90 or 0.0),
                "p99": float(row.p99 or 0.0),
                "std": float(row.std or 0.0),
            }

    return all_stats


def compute_outlier_delta_threshold(stats):
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


def is_delta_outlier(delta, stats):
    if delta is None or delta <= 0:
        return False

    threshold = compute_outlier_delta_threshold(stats)
    if threshold is None:
        return False

    return delta > threshold


def format_ident_count_summary(counts, *, limit=10):
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
    source_name,
    row,
    prev,
    interval,
    candidate_delta,
    stats,
    detection_kind,
):
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


# -------------------------------------------------
# Vypořádává se s výpadky měření
# -------------------------------------------------
def resolve_gap(ident, prev, current_dt, current_objem, interval, source_name, occupied_dates=None):
    prev_dt = prev["date"]
    prev_objem = prev["objem"]
    seriove = prev["seriove_cislo"]

    total_minutes = int((current_dt - prev_dt).total_seconds() // 60)
    num_slots = total_minutes // interval

    # rychlý exit
    if num_slots <= 1:
        return [], None, None

    total_delta = current_objem - prev_objem
    if total_delta <= 0:
        return [], None, None

    mean_delta = round(total_delta / num_slots, 6)

    rows = []
    blocked_dates = occupied_dates or set()

    for i in range(1, num_slots):
        slot_time = prev_dt + timedelta(minutes=i * interval)
        if slot_time in blocked_dates:
            continue

        # žádné postupné sčítání → žádný drift
        objem = round(prev_objem + mean_delta * i, 6)

        rows.append({
            "source_recid": None,
            "identifikace": ident,
            "seriove_cislo": seriove,
            "date": slot_time,
            **build_time_columns(slot_time, source_name),
            "objem": objem,
            "delta": mean_delta,
            "interval_minutes": interval,
            "day_of_week": compute_day_of_week(slot_time),
            "slot": compute_slot(slot_time, interval),
            "nocni_odber": mean_delta > 0.01 and is_night_time(slot_time),
            "platne": True,
            "gap_detected": False,
            "synthetic": True,
            "zdroj": source_name,
            "reset_detected": False,
        })

    terminal_delta = round(total_delta - mean_delta * len(rows), 6)
    return rows, mean_delta, terminal_delta


def build_occupied_dates(session, new_rows, previous_map, source_name):
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


# -------------------------------------------------
# Příprava řádků k insertu (včetně delta)
# -------------------------------------------------
def prepare_rows(
    session,
    new_rows,
    source_name,
    *,
    include_outlier_reviews=False,
    review_overrides=None,
):

    if not new_rows:
        return ([], []) if include_outlier_reviews else []

    MAX_GAP_MULTIPLIER = 2
    MIN_NIGHT_DELTA = 0.01

    affected_idents = {r["identifikace"] for r in new_rows}
    last_existing = get_last_measurements(session, affected_idents, only_valid=True)
    reference_time = max(
        (r["date"] for r in new_rows if isinstance(r.get("date"), datetime)),
        default=utc_now_naive(),
    )
    recent_delta_stats = get_recent_delta_stats(
        session,
        affected_idents,
        reference_time=reference_time,
    )

    new_rows.sort(key=lambda x: (x["identifikace"], x["date"]))

    previous_map = {}

    for ident in affected_idents:
        last = last_existing.get(ident)

        if last:
            previous_map[ident] = {
                "objem": last.objem,
                "date": last.date,
                "seriove_cislo": last.seriove_cislo,
            }
        else:
            previous_map[ident] = None

    occupied_dates = build_occupied_dates(session, new_rows, previous_map, source_name)

    rows_to_insert = []
    outlier_reviews = []
    outlier_count = 0
    outlier_by_ident = {}
    overrides_by_key = review_overrides or {}

    for r in new_rows:

        reset_detected = r.get("reset_detected", False)
        ident = r["identifikace"]
        dt = r["date"]
        interval = r["interval_minutes"]
        objem = r["objem"]

        prev = previous_map.get(ident)

        delta = None
        gap_detected = False
        is_valid_row = True
        ident_stats = recent_delta_stats.get(ident)
        review_override = overrides_by_key.get((ident, dt, source_name))

        # -------------------------------------------------
        # RESET má prioritu – nová baseline
        # -------------------------------------------------
        if not reset_detected and prev and prev["date"]:

            expected_interval = timedelta(minutes=interval)
            actual_diff = dt - prev["date"]

            # ----------------------------
            # GAP DETEKCE
            # ----------------------------
            if actual_diff > expected_interval * MAX_GAP_MULTIPLIER:

                if objem >= prev["objem"]:
                    total_minutes = int(actual_diff.total_seconds() // 60)
                    num_slots = total_minutes // interval
                    mean_gap_delta = None
                    if num_slots > 0:
                        mean_gap_delta = round((objem - prev["objem"]) / num_slots, 6)

                    is_gap_outlier = (
                        mean_gap_delta is not None
                        and (
                            review_override == "CONFIRMED_OUTLIER"
                            or is_delta_outlier(mean_gap_delta, ident_stats)
                        )
                    )

                    if is_gap_outlier:
                        if review_override == "CONFIRMED_CONSUMPTION":
                            synthetic_rows, _resolved_mean_gap_delta, terminal_gap_delta = resolve_gap(
                                ident,
                                prev,
                                dt,
                                objem,
                                interval,
                                source_name,
                                occupied_dates.get(ident),
                            )

                            rows_to_insert.extend(synthetic_rows)
                            if mean_gap_delta is not None:
                                gap_detected = True
                                delta = terminal_gap_delta
                        else:
                            is_valid_row = False
                            outlier_count += 1
                            outlier_by_ident[ident] = outlier_by_ident.get(ident, 0) + 1
                            if include_outlier_reviews and review_override != "CONFIRMED_OUTLIER":
                                outlier_reviews.append(
                                    build_outlier_review_payload(
                                        source_name=source_name,
                                        row=r,
                                        prev=prev,
                                        interval=interval,
                                        candidate_delta=mean_gap_delta,
                                        stats=ident_stats,
                                        detection_kind="GAP_MEAN",
                                    )
                                )
                    else:
                        synthetic_rows, _resolved_mean_gap_delta, terminal_gap_delta = resolve_gap(
                            ident,
                            prev,
                            dt,
                            objem,
                            interval,
                            source_name,
                            occupied_dates.get(ident),
                        )

                        rows_to_insert.extend(synthetic_rows)
                        if mean_gap_delta is not None:
                            gap_detected = True
                            delta = terminal_gap_delta

            else:
                # ----------------------------
                # Normální interval
                # ----------------------------
                if objem >= prev["objem"]:
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
                                        row=r,
                                        prev=prev,
                                        interval=interval,
                                        candidate_delta=candidate_delta,
                                        stats=ident_stats,
                                        detection_kind="NORMAL_DELTA",
                                    )
                                )
                    else:
                        delta = candidate_delta

        # -------------------------------------------------
        # Finální úprava delta
        # -------------------------------------------------
        if delta is not None:
            delta = round(delta, 6)

        if reset_detected:
            delta = None

        # -------------------------------------------------
        # Noční odběr (až po finálním delta)
        # -------------------------------------------------
        nocni_odber = (
            is_valid_row
            and not reset_detected
            and
            delta is not None
            and delta > MIN_NIGHT_DELTA
            and is_night_time(dt)
        )

        # -------------------------------------------------
        # Insert aktuálního řádku
        # -------------------------------------------------
        rows_to_insert.append({
            "source_recid": r["recid"],
            "identifikace": ident,
            "seriove_cislo": r["seriove_cislo"],
            "date": dt,
            **build_time_columns(dt, source_name, r),
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
        })

        # -------------------------------------------------
        # Aktualizace previous_map
        # -------------------------------------------------
        if is_valid_row:
            previous_map[ident] = {
                "objem": objem,
                "date": dt,
                "seriove_cislo": r["seriove_cislo"],
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




# -------------------------------------------------
# Import měření z jednoho zdroje
# -------------------------------------------------

def import_measurements(session, source_name, ms_rows):

    if not ms_rows:
        return {
            "rows": [],
            "new_outlier_review_ids": [],
        }

    # new_rows = filter_new_rows(session, source_name, ms_rows)
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

    inserted_rows = 0
    for batch in chunked(rows_to_insert):
        stmt = insert(Mereni_vodomery).on_conflict_do_nothing(
            index_elements=["identifikace", "date", "zdroj"]
        )

        session.execute(stmt, batch)

        inserted_rows += len(batch)

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

    logger.info("%s prepared for insert: %s", source_name, inserted_rows)

    return {
        "rows": rows_to_insert,
        "new_outlier_review_ids": new_outlier_review_ids,
    }






def filter_new_rows(session, source_name, ms_rows):
    if not ms_rows:
        return []

    recids = {r["recid"] for r in ms_rows}
    if not recids:
        return []

    existing_set = set()
    recid_list = list(recids)
    for recid_chunk in chunked(recid_list):
        existing = (
            session.execute(
                select(Mereni_vodomery.source_recid)
                .where(
                    Mereni_vodomery.zdroj == source_name,
                    Mereni_vodomery.source_recid.in_(recid_chunk),
                )
            )
            .scalars()
            .all()
        )
        existing_set.update(existing)

    return [r for r in ms_rows if r["recid"] not in existing_set]





def filter_valid_rows(session, rows, source_name):

    if not rows:
        return []

    now_utc = utc_now_naive()

    sanitized = []
    dropped_invalid = 0
    dropped_future = 0

    # -------------------------------------------------
    # 1️⃣ základní sanitizace + ochrana času
    # -------------------------------------------------
    for r in rows:

        ident = (r.get("identifikace") or "").strip()
        dt = r.get("date")
        objem = r.get("objem")

        if not ident or dt is None or objem is None:
            dropped_invalid += 1
            continue

        # if dt > now_utc:
        #     dropped_future += 1
        #     continue

        r["identifikace"] = ident
        r["seriove_cislo"] = str(r.get("seriove_cislo") or "")
        r["reset_detected"] = False  # default

        sanitized.append(r)

    if not sanitized:
        logger.warning(
            "%s dropped rows - invalid: %s, future_ts: %s",
            source_name,
            dropped_invalid,
            dropped_future,
        )
        return []

    # -------------------------------------------------
    # 2️⃣ validace proti mapové tabulce ve schema evidence (FK logika)
    # -------------------------------------------------
    valid_idents = set()
    ident_list = list(set(r["identifikace"] for r in sanitized))

    with Session(engine_ms) as ms_session:
        for ident_chunk in chunked(ident_list):
            valid_idents.update(
                ms_session.execute(
                    select(Vodomer_areal_Zarizeni.identifikace)
                    .where(Vodomer_areal_Zarizeni.identifikace.in_(ident_chunk))
                )
                .scalars()
                .all()
            )

    filtered = [r for r in sanitized if r["identifikace"] in valid_idents]

    dropped_fk = len(sanitized) - len(filtered)

    # -------------------------------------------------
    # 3️⃣ Reset detekce (pro každý ident)
    # -------------------------------------------------
    if filtered:

        affected_idents = {r["identifikace"] for r in filtered}
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

        for r in sorted(filtered, key=lambda item: (item["identifikace"], item["date"])):
            ident = r["identifikace"]
            last = previous_by_ident.get(ident)

            if last and r["objem"] < last["objem"]:
                r["reset_detected"] = True

            previous_by_ident[ident] = {
                "objem": r["objem"],
                "date": r["date"],
                "seriove_cislo": r["seriove_cislo"],
            }

    # -------------------------------------------------
    # Logování
    # -------------------------------------------------
    if dropped_invalid or dropped_future or dropped_fk:
        logger.warning(
            "%s dropped rows - invalid: %s, future_ts: %s, missing_ms_zarizeni_identifikace: %s",
            source_name,
            dropped_invalid,
            dropped_future,
            dropped_fk,
        )

    return filtered




# -------------------------------------------------
# Hlavní běh importu
# -------------------------------------------------

def vodomery_db_import():
    ensure_destination_table()

    with Session(engine) as session:
        with session.begin():

            rows_areal = fetch_from_ms_areal()
            inserted_areal = import_measurements(session, "AREAL", rows_areal)
            logger.info("AREAL inserted: %s", len(inserted_areal["rows"]))

            rows_scvk = fetch_from_ms_scvk()
            inserted_scvk = import_measurements(session, "SCVK", rows_scvk)
            logger.info("SCVK inserted: %s", len(inserted_scvk["rows"]))

        new_outlier_review_ids = list(
            inserted_areal["new_outlier_review_ids"] + inserted_scvk["new_outlier_review_ids"]
        )
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
                    "Failed to process new outlier review notifications for review IDs: %s",
                    new_outlier_review_ids,
                )
            else:
                logger.info(
                    "Outlier review notifications processed: matched=%s, emails_sent=%s, deliveries_sent=%s, deliveries_failed=%s",
                    notification_result["matched"],
                    notification_result["emails_sent"],
                    notification_result["deliveries_sent"],
                    notification_result["deliveries_failed"],
                )

        return {
            "inserted_areal": len(inserted_areal["rows"]),
            "inserted_scvk": len(inserted_scvk["rows"]),
            "new_outlier_review_ids": new_outlier_review_ids,
            "notification_result": notification_result,
        }


