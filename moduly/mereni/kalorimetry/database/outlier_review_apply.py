from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.kalorimetry.database.models import (
    KalorimetryOutlierReview,
    Mereni_kalorimetry,
)
from moduly.mereni.kalorimetry.database.outlier_reviews import (
    ensure_kalorimetry_outlier_review_table,
    normalize_review_note,
    normalize_review_status,
    serialize_review_row,
    upsert_outlier_review_candidates,
)
from moduly.mereni.kalorimetry.database.kalorimetry_db_vse import (
    chunked,
    filter_valid_rows,
    prepare_rows,
)


logger = logging.getLogger(__name__)


def apply_outlier_review_update(
    review_id: int,
    *,
    review_status: str,
    review_note: str | None = None,
    actor: str | None = None,
) -> dict[str, object]:
    ensure_kalorimetry_outlier_review_table()

    resolved_status = normalize_review_status(review_status)
    resolved_note = normalize_review_note(review_note)

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        review_row = session.execute(
            select(KalorimetryOutlierReview)
            .where(KalorimetryOutlierReview.id == int(review_id))
            .with_for_update()
        ).scalar_one_or_none()
        if review_row is None:
            raise ValueError("Outlier review zaznam neexistuje.")

        previous_status = str(review_row.review_status)
        review_row.review_status = resolved_status
        review_row.review_note = resolved_note
        if resolved_status == "PENDING":
            review_row.reviewed_by = None
            review_row.reviewed_at = None
        else:
            review_row.reviewed_by = actor
            review_row.reviewed_at = utc_now_naive()

        if previous_status != resolved_status:
            rebuild_summary = _rebuild_measurements_for_review(session, review_row)
            logger.info(
                "Applied kalorimetry outlier review rebuild | review_id=%s | identifikace=%s | zdroj=%s | status=%s | summary=%s",
                review_row.id,
                review_row.identifikace,
                review_row.zdroj,
                resolved_status,
                rebuild_summary,
            )

        session.commit()
        session.refresh(review_row)
        return serialize_review_row(review_row)


def _load_review_overrides(
    session: Session,
    *,
    identifikace: str,
    zdroj: str,
    start_date,
) -> dict[tuple[str, object, str], str]:
    rows = session.execute(
        select(KalorimetryOutlierReview.date, KalorimetryOutlierReview.review_status)
        .where(
            KalorimetryOutlierReview.identifikace == identifikace,
            KalorimetryOutlierReview.zdroj == zdroj,
            KalorimetryOutlierReview.date >= start_date,
            KalorimetryOutlierReview.review_status.in_(
                ("CONFIRMED_OUTLIER", "CONFIRMED_CONSUMPTION")
            ),
        )
    ).all()
    return {
        (identifikace, row.date, zdroj): str(row.review_status)
        for row in rows
    }


def _load_actual_measurements(
    session: Session,
    *,
    identifikace: str,
    zdroj: str,
    start_date,
) -> list[Mereni_kalorimetry]:
    return session.execute(
        select(Mereni_kalorimetry)
        .where(
            Mereni_kalorimetry.identifikace == identifikace,
            Mereni_kalorimetry.zdroj == zdroj,
            Mereni_kalorimetry.synthetic.is_(False),
            Mereni_kalorimetry.date >= start_date,
        )
        .order_by(Mereni_kalorimetry.date.asc(), Mereni_kalorimetry.id.asc())
    ).scalars().all()


def _rebuild_measurements_for_review(session: Session, review_row: KalorimetryOutlierReview) -> dict[str, object]:
    identifikace = str(review_row.identifikace)
    zdroj = str(review_row.zdroj)
    start_date = review_row.date

    actual_rows = _load_actual_measurements(
        session,
        identifikace=identifikace,
        zdroj=zdroj,
        start_date=start_date,
    )
    actual_by_key = {
        (row.date, row.source_recid): row
        for row in actual_rows
    }
    raw_rows = [
        {
            "id": row.id,
            "recid": row.source_recid,
            "identifikace": row.identifikace,
            "seriove_cislo": row.seriove_cislo,
            "date": row.date,
            "spotreba_energie": row.spotreba_energie,
            "objem": row.objem,
            "interval_minutes": row.interval_minutes,
        }
        for row in actual_rows
    ]

    session.execute(
        delete(Mereni_kalorimetry).where(
            Mereni_kalorimetry.identifikace == identifikace,
            Mereni_kalorimetry.zdroj == zdroj,
            Mereni_kalorimetry.date >= start_date,
        )
    )
    session.execute(
        delete(KalorimetryOutlierReview).where(
            KalorimetryOutlierReview.identifikace == identifikace,
            KalorimetryOutlierReview.zdroj == zdroj,
            KalorimetryOutlierReview.date >= start_date,
            KalorimetryOutlierReview.review_status == "PENDING",
            KalorimetryOutlierReview.id != review_row.id,
        )
    )

    if not raw_rows:
        return {
            "identifikace": identifikace,
            "zdroj": zdroj,
            "inserted_actual_rows": 0,
            "inserted_synthetic_rows": 0,
            "recreated_reviews": 0,
        }

    review_overrides = _load_review_overrides(
        session,
        identifikace=identifikace,
        zdroj=zdroj,
        start_date=start_date,
    )
    valid_rows = filter_valid_rows(session, raw_rows, zdroj)
    prepared_rows, outlier_reviews = prepare_rows(
        session,
        valid_rows,
        zdroj,
        include_outlier_reviews=True,
        review_overrides=review_overrides,
    )

    synthetic_rows = []
    actual_rows_to_insert = []
    for prepared_row in prepared_rows:
        if prepared_row["synthetic"]:
            synthetic_rows.append(prepared_row)
            continue

        key = (prepared_row["date"], prepared_row["source_recid"])
        existing_row = actual_by_key.get(key)
        if existing_row is None:
            raise ValueError(
                f"Chybi puvodni measurement row pro rebuild: {identifikace} | {prepared_row['date']} | {zdroj}"
            )

        row_to_insert = dict(prepared_row)
        row_to_insert["id"] = existing_row.id
        actual_rows_to_insert.append(row_to_insert)

    inserted_actual_rows = 0
    for batch in chunked(actual_rows_to_insert):
        session.execute(insert(Mereni_kalorimetry), batch)
        inserted_actual_rows += len(batch)

    inserted_synthetic_rows = 0
    for batch in chunked(synthetic_rows):
        stmt = insert(Mereni_kalorimetry).on_conflict_do_nothing(
            index_elements=["identifikace", "date", "zdroj"]
        )
        session.execute(stmt, batch)
        inserted_synthetic_rows += len(batch)

    recreated_reviews = 0
    if outlier_reviews:
        recreated_reviews = upsert_outlier_review_candidates(
            outlier_reviews,
            session=session,
        )

    return {
        "identifikace": identifikace,
        "zdroj": zdroj,
        "inserted_actual_rows": inserted_actual_rows,
        "inserted_synthetic_rows": inserted_synthetic_rows,
        "recreated_reviews": recreated_reviews,
    }
