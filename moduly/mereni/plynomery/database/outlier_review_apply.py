from __future__ import annotations

import logging

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.plynomery.database.expected_zero import ensure_expected_zero_table
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    PlynomeryAlertDelivery,
    PlynomeryAnomalyEvent,
    PlynomeryAnomalyScore,
    PlynomeryEventState,
    PlynomeryExpectedZero,
    PlynomeryOutlierReview,
    PlynomeryProfilesAnomaly,
)
from moduly.mereni.plynomery.database.outlier_reviews import (
    ensure_plynomery_outlier_review_table,
    normalize_review_note,
    normalize_review_status,
    serialize_review_row,
    upsert_outlier_review_candidates,
)
from moduly.mereni.plynomery.database.plynomery_db_vse import (
    chunked,
    filter_valid_rows,
    is_night_time,
    prepare_rows,
)
from moduly.mereni.plynomery.plynomery_events import EVENT_CONFIG, _compute_severity
from moduly.mereni.plynomery.plynomery_prediction import get_candidate_model_versions


logger = logging.getLogger(__name__)


def apply_outlier_review_update(
    review_id: int,
    *,
    review_status: str,
    review_note: str | None = None,
    actor: str | None = None,
) -> dict[str, object]:
    ensure_plynomery_outlier_review_table()

    resolved_status = normalize_review_status(review_status)
    resolved_note = normalize_review_note(review_note)

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        review_row = session.execute(
            select(PlynomeryOutlierReview)
            .where(PlynomeryOutlierReview.id == int(review_id))
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
            rebuild_summary = _rebuild_after_review_update(session, review_row)
            logger.info(
                "Applied plynomery outlier review rebuild | review_id=%s | identifikace=%s | zdroj=%s | status=%s | summary=%s",
                review_row.id,
                review_row.identifikace,
                review_row.zdroj,
                resolved_status,
                rebuild_summary,
            )

        session.commit()
        session.refresh(review_row)
        return serialize_review_row(review_row)


def _rebuild_after_review_update(session: Session, review_row: PlynomeryOutlierReview) -> dict[str, object]:
    measurement_summary = _rebuild_measurements_for_review(session, review_row)
    score_summaries = []
    event_summaries = []

    for model_version in get_candidate_model_versions():
        score_summaries.append(
            _rebuild_scores_for_ident(
                session,
                identifikace=review_row.identifikace,
                model_version=model_version,
                start_date=review_row.date,
            )
        )
        event_summaries.append(
            _rebuild_events_for_ident(
                session,
                identifikace=review_row.identifikace,
                model_version=model_version,
            )
        )

    return {
        "measurements": measurement_summary,
        "scores": score_summaries,
        "events": event_summaries,
    }


def _load_review_overrides(
    session: Session,
    *,
    identifikace: str,
    zdroj: str,
    start_date,
) -> dict[tuple[str, object, str], str]:
    rows = session.execute(
        select(PlynomeryOutlierReview.date, PlynomeryOutlierReview.review_status)
        .where(
            PlynomeryOutlierReview.identifikace == identifikace,
            PlynomeryOutlierReview.zdroj == zdroj,
            PlynomeryOutlierReview.date >= start_date,
            PlynomeryOutlierReview.review_status.in_(
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
) -> list[Mereni_plynomery]:
    return session.execute(
        select(Mereni_plynomery)
        .where(
            Mereni_plynomery.identifikace == identifikace,
            Mereni_plynomery.zdroj == zdroj,
            Mereni_plynomery.synthetic.is_(False),
            Mereni_plynomery.date >= start_date,
        )
        .order_by(Mereni_plynomery.date.asc(), Mereni_plynomery.id.asc())
    ).scalars().all()


def _rebuild_measurements_for_review(session: Session, review_row: PlynomeryOutlierReview) -> dict[str, object]:
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
            "objem": row.objem,
            "interval_minutes": row.interval_minutes,
        }
        for row in actual_rows
    ]

    session.execute(
        delete(Mereni_plynomery).where(
            Mereni_plynomery.identifikace == identifikace,
            Mereni_plynomery.zdroj == zdroj,
            Mereni_plynomery.date >= start_date,
        )
    )
    session.execute(
        delete(PlynomeryOutlierReview).where(
            PlynomeryOutlierReview.identifikace == identifikace,
            PlynomeryOutlierReview.zdroj == zdroj,
            PlynomeryOutlierReview.date >= start_date,
            PlynomeryOutlierReview.review_status == "PENDING",
            PlynomeryOutlierReview.id != review_row.id,
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
        session.execute(insert(Mereni_plynomery), batch)
        inserted_actual_rows += len(batch)

    inserted_synthetic_rows = 0
    for batch in chunked(synthetic_rows):
        stmt = insert(Mereni_plynomery).on_conflict_do_nothing(
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


def _rebuild_scores_for_ident(
    session: Session,
    *,
    identifikace: str,
    model_version: int,
    start_date,
) -> dict[str, object]:
    session.execute(
        delete(PlynomeryAnomalyScore).where(
            PlynomeryAnomalyScore.identifikace == identifikace,
            PlynomeryAnomalyScore.model_version == model_version,
            PlynomeryAnomalyScore.date >= start_date,
        )
    )

    profiles = session.execute(
        select(PlynomeryProfilesAnomaly).where(
            PlynomeryProfilesAnomaly.model_version == model_version,
            PlynomeryProfilesAnomaly.identifikace == identifikace,
        )
    ).scalars().all()
    if not profiles:
        return {
            "model_version": model_version,
            "inserted_scores": 0,
        }

    profile_cache = {
        (
            profile.identifikace,
            profile.interval_minutes,
            profile.day_of_week,
            profile.slot,
        ): profile
        for profile in profiles
    }

    measurements = session.execute(
        select(Mereni_plynomery)
        .where(
            Mereni_plynomery.identifikace == identifikace,
            Mereni_plynomery.date >= start_date,
            Mereni_plynomery.synthetic.is_(False),
            Mereni_plynomery.platne.is_(True),
            Mereni_plynomery.reset_detected.is_(False),
            Mereni_plynomery.delta.is_not(None),
        )
        .order_by(Mereni_plynomery.id.asc())
    ).scalars().all()

    rows_to_insert = []
    for measurement in measurements:
        profile = profile_cache.get(
            (
                measurement.identifikace,
                measurement.interval_minutes,
                measurement.day_of_week,
                measurement.slot,
            )
        )
        if profile is None:
            continue

        expected_std = profile.std if profile.std > 0 else 0.0001
        deviation = measurement.delta - profile.mean
        z_score = deviation / expected_std
        is_anomaly = (
            measurement.delta > profile.p90
            or measurement.delta < profile.p10
            or abs(z_score) >= 3
        )

        if abs(z_score) >= 5:
            severity = "CRITICAL"
        elif abs(z_score) >= 4:
            severity = "HIGH"
        elif abs(z_score) >= 3:
            severity = "MEDIUM"
        else:
            severity = None

        rows_to_insert.append(
            {
                "measurement_id": measurement.id,
                "identifikace": measurement.identifikace,
                "date": measurement.date,
                "actual_value": measurement.delta,
                "expected_mean": profile.mean,
                "expected_std": expected_std,
                "expected_median": profile.median,
                "expected_p10": profile.p10,
                "expected_p90": profile.p90,
                "deviation": deviation,
                "z_score": z_score,
                "is_anomaly": is_anomaly,
                "severity": severity,
                "model_version": model_version,
                "processed": False,
            }
        )

    if rows_to_insert:
        session.execute(insert(PlynomeryAnomalyScore), rows_to_insert)

    return {
        "model_version": model_version,
        "inserted_scores": len(rows_to_insert),
    }


def _rebuild_events_for_ident(
    session: Session,
    *,
    identifikace: str,
    model_version: int,
) -> dict[str, object]:
    ensure_expected_zero_table()

    event_ids = session.execute(
        select(PlynomeryAnomalyEvent.id).where(
            PlynomeryAnomalyEvent.identifikace == identifikace,
            PlynomeryAnomalyEvent.model_version == model_version,
        )
    ).scalars().all()

    if event_ids:
        for event_id_chunk in chunked(event_ids):
            session.execute(
                delete(PlynomeryAlertDelivery).where(
                    PlynomeryAlertDelivery.event_id.in_(event_id_chunk)
                )
            )

    session.execute(
        delete(PlynomeryAnomalyEvent).where(
            PlynomeryAnomalyEvent.identifikace == identifikace,
            PlynomeryAnomalyEvent.model_version == model_version,
        )
    )
    session.execute(
        delete(PlynomeryEventState).where(
            PlynomeryEventState.identifikace == identifikace,
            PlynomeryEventState.model_version == model_version,
        )
    )
    session.execute(
        update(PlynomeryAnomalyScore)
        .where(
            PlynomeryAnomalyScore.identifikace == identifikace,
            PlynomeryAnomalyScore.model_version == model_version,
        )
        .values(processed=False)
    )

    scores = session.execute(
        select(PlynomeryAnomalyScore)
        .where(
            PlynomeryAnomalyScore.identifikace == identifikace,
            PlynomeryAnomalyScore.model_version == model_version,
        )
        .order_by(PlynomeryAnomalyScore.id.asc())
    ).scalars().all()

    expected_zero = bool(
        session.execute(
            select(PlynomeryExpectedZero.identifikace).where(
                PlynomeryExpectedZero.identifikace == identifikace
            )
        ).scalar_one_or_none()
    )

    state_lookup = {}
    active_lookup = {}
    created_events = 0
    resolved_events = 0

    for score in scores:
        ts = score.date

        for event_type, cfg in EVENT_CONFIG.items():
            key = (identifikace, event_type)
            state = state_lookup.get(key)

            if state is None:
                state = PlynomeryEventState(
                    identifikace=identifikace,
                    event_type=event_type,
                    model_version=model_version,
                    consecutive_count=0,
                    accumulator=0.0,
                    is_event_active=False,
                    event_start_time=None,
                    last_score_time=ts,
                )
                session.add(state)
                state_lookup[key] = state

            if event_type == "EXPECTED_ZERO_USAGE":
                triggered = expected_zero and score.actual_value > 0
            elif event_type == "NIGHT_USAGE":
                triggered = is_night_time(ts) and score.z_score > cfg["threshold"]
            else:
                triggered = score.z_score > cfg["threshold"]

            if triggered:
                state.consecutive_count += 1
                state.accumulator += abs(score.z_score)

                if (
                    not state.is_event_active
                    and state.consecutive_count >= cfg["min_consecutive"]
                ):
                    state.is_event_active = True
                    state.event_start_time = ts

                    event = PlynomeryAnomalyEvent(
                        identifikace=identifikace,
                        event_type=event_type,
                        start_time=ts,
                        end_time=None,
                        duration_minutes=0,
                        max_z_score=score.z_score,
                        avg_z_score=score.z_score,
                        total_deviation=abs(score.z_score),
                        severity=_compute_severity(score.z_score, 0),
                        is_active=True,
                        resolved=False,
                        model_version=model_version,
                        last_score_time=ts,
                    )
                    session.add(event)
                    active_lookup[key] = event
                    created_events += 1
                elif state.is_event_active:
                    event = active_lookup.get(key)
                    if event is not None:
                        event.max_z_score = max(event.max_z_score, score.z_score)
                        event.total_deviation += abs(score.z_score)
                        duration = int((ts - event.start_time).total_seconds() / 60)
                        event.duration_minutes = duration
                        event.avg_z_score = event.total_deviation / max(
                            state.consecutive_count,
                            1,
                        )
                        event.severity = _compute_severity(
                            event.max_z_score,
                            duration,
                        )
                        event.last_score_time = ts
            else:
                if state.is_event_active:
                    event = active_lookup.get(key)
                    if event is not None:
                        event.is_active = False
                        event.resolved = True
                        event.resolved_at = ts
                        event.end_time = ts
                        resolved_events += 1
                    state.is_event_active = False

                state.consecutive_count = 0
                state.accumulator = 0.0
                state.event_start_time = None

            state.last_score_time = ts

    session.execute(
        update(PlynomeryAnomalyScore)
        .where(
            PlynomeryAnomalyScore.identifikace == identifikace,
            PlynomeryAnomalyScore.model_version == model_version,
        )
        .values(processed=True)
    )

    return {
        "model_version": model_version,
        "processed_scores": len(scores),
        "created_events": created_events,
        "resolved_events": resolved_events,
    }
