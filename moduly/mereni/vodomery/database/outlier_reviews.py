from __future__ import annotations

from sqlalchemy import select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.vodomery.database.models import VodomeryOutlierReview


REVIEW_STATUS_OPTIONS = ("PENDING", "CONFIRMED_OUTLIER", "CONFIRMED_CONSUMPTION")
DETECTION_KIND_OPTIONS = ("NORMAL_DELTA", "GAP_MEAN")


def ensure_vodomery_outlier_review_table() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        VodomeryOutlierReview.__table__.create(bind=conn, checkfirst=True)


def normalize_source_filter(source_filter: str) -> str:
    resolved = str(source_filter or "VSE").strip().upper()
    if resolved not in {"VSE", "AREAL", "SCVK"}:
        raise ValueError("Neznamy source filter pro outlier review.")
    return resolved


def normalize_review_status(review_status: str) -> str:
    resolved = str(review_status or "").strip().upper()
    if resolved not in REVIEW_STATUS_OPTIONS:
        raise ValueError("Neznamy review status outlieru.")
    return resolved


def normalize_review_note(review_note: str | None) -> str | None:
    if review_note is None:
        return None
    resolved = str(review_note).strip()
    return resolved or None


def build_outlier_review_key(row: dict[str, object] | VodomeryOutlierReview) -> tuple[str, object, str]:
    if isinstance(row, VodomeryOutlierReview):
        return (
            str(row.identifikace),
            row.date,
            str(row.zdroj),
        )
    return (
        str(row["identifikace"]),
        row["date"],
        str(row["zdroj"]),
    )


def serialize_review_row(row: VodomeryOutlierReview) -> dict[str, object]:
    return {
        "id": row.id,
        "identifikace": row.identifikace,
        "date": row.date,
        "zdroj": row.zdroj,
        "source_recid": row.source_recid,
        "seriove_cislo": row.seriove_cislo,
        "interval_minutes": row.interval_minutes,
        "detection_kind": row.detection_kind,
        "current_objem": row.current_objem,
        "baseline_objem": row.baseline_objem,
        "baseline_date": row.baseline_date,
        "candidate_delta": row.candidate_delta,
        "threshold_delta": row.threshold_delta,
        "sample_size": row.sample_size,
        "median_delta": row.median_delta,
        "p90_delta": row.p90_delta,
        "p99_delta": row.p99_delta,
        "std_delta": row.std_delta,
        "review_status": row.review_status,
        "review_note": row.review_note,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
    }


def load_outlier_review_ids_by_keys(
    keys: list[tuple[str, object, str]],
    *,
    session: Session | None = None,
) -> dict[tuple[str, object, str], int]:
    ensure_vodomery_outlier_review_table()
    if not keys:
        return {}

    unique_keys = list(dict.fromkeys(keys))
    owns_session = session is None
    db_session = session or Session(ENGINE_PG, autoflush=False, expire_on_commit=False)
    try:
        rows = db_session.execute(
            select(VodomeryOutlierReview).where(
                tuple_(
                    VodomeryOutlierReview.identifikace,
                    VodomeryOutlierReview.date,
                    VodomeryOutlierReview.zdroj,
                ).in_(unique_keys)
            )
        ).scalars().all()
        return {
            build_outlier_review_key(row): int(row.id)
            for row in rows
        }
    finally:
        if owns_session:
            db_session.close()


def upsert_outlier_review_candidates(
    rows: list[dict[str, object]],
    *,
    session: Session | None = None,
) -> int:
    ensure_vodomery_outlier_review_table()
    if not rows:
        return 0

    owns_session = session is None
    db_session = session or Session(ENGINE_PG, autoflush=False, expire_on_commit=False)
    try:
        insert_stmt = insert(VodomeryOutlierReview).values(rows)
        excluded = insert_stmt.excluded
        db_session.execute(
            insert_stmt.on_conflict_do_update(
                index_elements=["identifikace", "date", "zdroj"],
                set_={
                    "source_recid": excluded.source_recid,
                    "seriove_cislo": excluded.seriove_cislo,
                    "interval_minutes": excluded.interval_minutes,
                    "detection_kind": excluded.detection_kind,
                    "current_objem": excluded.current_objem,
                    "baseline_objem": excluded.baseline_objem,
                    "baseline_date": excluded.baseline_date,
                    "candidate_delta": excluded.candidate_delta,
                    "threshold_delta": excluded.threshold_delta,
                    "sample_size": excluded.sample_size,
                    "median_delta": excluded.median_delta,
                    "p90_delta": excluded.p90_delta,
                    "p99_delta": excluded.p99_delta,
                    "std_delta": excluded.std_delta,
                },
            )
        )
        if owns_session:
            db_session.commit()
        return len(rows)
    finally:
        if owns_session:
            db_session.close()


def list_outlier_reviews(
    *,
    review_status: str | None = None,
    identifikace: str | None = None,
    source_filter: str = "VSE",
    limit: int = 200,
) -> list[dict[str, object]]:
    ensure_vodomery_outlier_review_table()
    resolved_source = normalize_source_filter(source_filter)
    resolved_ident = str(identifikace or "").strip() or None
    resolved_limit = max(1, min(int(limit), 1000))

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        query = select(VodomeryOutlierReview)

        if review_status:
            query = query.where(
                VodomeryOutlierReview.review_status == normalize_review_status(review_status)
            )
        if resolved_ident:
            query = query.where(VodomeryOutlierReview.identifikace == resolved_ident)
        if resolved_source != "VSE":
            query = query.where(VodomeryOutlierReview.zdroj == resolved_source)

        rows = session.execute(
            query.order_by(
                VodomeryOutlierReview.date.desc(),
                VodomeryOutlierReview.id.desc(),
            ).limit(resolved_limit)
        ).scalars().all()
        return [serialize_review_row(row) for row in rows]


def update_outlier_review(
    review_id: int,
    *,
    review_status: str,
    review_note: str | None = None,
    actor: str | None = None,
) -> dict[str, object]:
    ensure_vodomery_outlier_review_table()
    resolved_status = normalize_review_status(review_status)
    resolved_note = normalize_review_note(review_note)

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        row = session.get(VodomeryOutlierReview, int(review_id))
        if row is None:
            raise ValueError("Outlier review zaznam neexistuje.")

        row.review_status = resolved_status
        row.review_note = resolved_note
        if resolved_status == "PENDING":
            row.reviewed_by = None
            row.reviewed_at = None
        else:
            row.reviewed_by = actor
            row.reviewed_at = utc_now_naive()

        session.commit()
        session.refresh(row)
        return serialize_review_row(row)
