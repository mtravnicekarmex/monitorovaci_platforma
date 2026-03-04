from datetime import datetime, timedelta
from time import perf_counter
from sqlalchemy import select, func, inspect, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from moduly.mereni.vodomery.database.models import (
    Mereni_vodomery,
    Vodomer_areal_Mereni,
    Vodomer_SCVK_Mereni,
    Vodomer_areal_Zarizeni_QGIS,
)
from core.db.connect import ENGINE_MS, ENGINE_PG
from app.time_utils import utc_now_naive


engine = ENGINE_PG
engine_ms = ENGINE_MS


CHUNK_SIZE = 5000


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
        print(f'Created missing table monitoring."{expected_table}"')



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
    print(f"AREAL last_recid: {last_recid}")

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
        print(f"AREAL rows fetched: {len(rows)} in {perf_counter() - t0:.1f}s")

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
    print(f"SCVK last_recid: {last_recid}")

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
        print(f"SCVK rows fetched: {len(rows)} in {perf_counter() - t0:.1f}s")

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

def get_last_measurements(session, affected_idents):

    if not affected_idents:
        return {}

    all_rows = {}
    idents_list = list(affected_idents)
    for ident_chunk in chunked(idents_list):
        subq = (
            select(
                Mereni_vodomery.identifikace,
                func.max(Mereni_vodomery.date).label("max_date")
            )
            .where(Mereni_vodomery.identifikace.in_(ident_chunk))
            .group_by(Mereni_vodomery.identifikace)
            .subquery()
        )

        q = (
            select(Mereni_vodomery)
            .join(
                subq,
                (Mereni_vodomery.identifikace == subq.c.identifikace) &
                (Mereni_vodomery.date == subq.c.max_date)
            )
        )
        rows = session.execute(q).scalars().all()
        for r in rows:
            all_rows[r.identifikace] = r

    return all_rows


# -------------------------------------------------
# Vypořádává se s výpadky měření
# -------------------------------------------------
def resolve_gap(ident, prev, current_dt, current_objem, interval, source_name):
    prev_dt = prev["date"]
    prev_objem = prev["objem"]
    seriove = prev["seriove_cislo"]

    total_minutes = int((current_dt - prev_dt).total_seconds() // 60)
    num_slots = total_minutes // interval

    # rychlý exit
    if num_slots <= 1:
        return []

    total_delta = current_objem - prev_objem
    if total_delta <= 0:
        return []

    mean_delta = round(total_delta / num_slots, 6)

    rows = []
    base_timestamp = int(prev_dt.timestamp())

    for i in range(1, num_slots):
        slot_time = prev_dt + timedelta(minutes=i * interval)

        # žádné postupné sčítání → žádný drift
        objem = round(prev_objem + mean_delta * i, 6)

        rows.append({
            "source_recid": None,
            "identifikace": ident,
            "seriove_cislo": seriove,
            "date": slot_time,
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

    return rows


# -------------------------------------------------
# Příprava řádků k insertu (včetně delta)
# -------------------------------------------------
def prepare_rows(session, new_rows, source_name):

    if not new_rows:
        return []

    MAX_GAP_MULTIPLIER = 2
    MIN_NIGHT_DELTA = 0.01

    affected_idents = {r["identifikace"] for r in new_rows}
    last_existing = get_last_measurements(session, affected_idents)

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

    rows_to_insert = []

    for r in new_rows:

        reset_detected = r.get("reset_detected", False)
        ident = r["identifikace"]
        dt = r["date"]
        interval = r["interval_minutes"]
        objem = r["objem"]

        prev = previous_map.get(ident)

        delta = None
        gap_detected = False

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

                    synthetic_rows = resolve_gap(
                        ident,
                        prev,
                        dt,
                        objem,
                        interval,
                        source_name
                    )

                    rows_to_insert.extend(synthetic_rows)
                    gap_detected = True

            else:
                # ----------------------------
                # Normální interval
                # ----------------------------
                if objem >= prev["objem"]:
                    delta = objem - prev["objem"]

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
            "objem": objem,
            "delta": delta,
            "interval_minutes": interval,
            "day_of_week": compute_day_of_week(dt),
            "slot": compute_slot(dt, interval),
            "nocni_odber": nocni_odber,
            "platne": True,
            "gap_detected": gap_detected,
            "synthetic": False,
            "zdroj": source_name,
            "reset_detected": reset_detected,
        })

        # -------------------------------------------------
        # Aktualizace previous_map
        # -------------------------------------------------
        previous_map[ident] = {
            "objem": objem,
            "date": dt,
            "seriove_cislo": r["seriove_cislo"],
        }

    return rows_to_insert




# -------------------------------------------------
# Import měření z jednoho zdroje
# -------------------------------------------------

def import_measurements(session, source_name, ms_rows):

    if not ms_rows:
        return []

    # new_rows = filter_new_rows(session, source_name, ms_rows)
    new_rows = filter_valid_rows(session, ms_rows, source_name)

    if not new_rows:
        return []

    rows_to_insert = prepare_rows(session, new_rows, source_name)

    if not rows_to_insert:
        return []

    inserted_rows = 0
    for batch in chunked(rows_to_insert):
        stmt = insert(Mereni_vodomery).on_conflict_do_nothing(
            index_elements=["identifikace", "date", "zdroj"]
        )

        session.execute(stmt, batch)

        inserted_rows += len(batch)
    print(f"{source_name} prepared for insert: {inserted_rows}")

    return rows_to_insert






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
        print(
            f"{source_name} dropped rows - invalid: {dropped_invalid}, "
            f"future_ts: {dropped_future}"
        )
        return []

    # -------------------------------------------------
    # 2️⃣ validace proti QGIS tabulce (FK logika)
    # -------------------------------------------------
    valid_idents = set()
    ident_list = list(set(r["identifikace"] for r in sanitized))

    for ident_chunk in chunked(ident_list):
        valid_idents.update(
            session.execute(
                select(Vodomer_areal_Zarizeni_QGIS.identifikace)
                .where(Vodomer_areal_Zarizeni_QGIS.identifikace.in_(ident_chunk))
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
        last_existing = get_last_measurements(session, affected_idents)

        for r in filtered:
            ident = r["identifikace"]
            last = last_existing.get(ident)

            if last and r["objem"] < last.objem:
                r["reset_detected"] = True

    # -------------------------------------------------
    # Logování
    # -------------------------------------------------
    if dropped_invalid or dropped_future or dropped_fk:
        print(
            f"{source_name} dropped rows - "
            f"invalid: {dropped_invalid}, "
            f"future_ts: {dropped_future}, "
            f"missing_qgis_identifikace: {dropped_fk}"
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
            print(f"AREAL inserted: {len(inserted_areal)}")

            rows_scvk = fetch_from_ms_scvk()
            inserted_scvk = import_measurements(session, "SCVK", rows_scvk)
            print(f"SCVK inserted: {len(inserted_scvk)}")


