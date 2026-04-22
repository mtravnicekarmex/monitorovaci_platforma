from __future__ import annotations

from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.plynomery.database.expected_zero import (
    ensure_expected_zero_table,
    get_expected_zero_device_set,
)
from moduly.mereni.plynomery.database.models import (
    PlynomeryAnomalyEvent,
    PlynomeryAnomalyScore,
    PlynomeryEventEngineState,
    PlynomeryEventState,
)


EVENT_CONFIG = {
    "NIGHT_USAGE": {
        "threshold": 3.0,
        "min_consecutive": 2,
    },
    "SPIKE": {
        "threshold": 5.0,
        "min_consecutive": 1,
    },
    "LONG_HIGH_USAGE": {
        "threshold": 2.0,
        "min_consecutive": 8,
    },
    "EXPECTED_ZERO_USAGE": {
        "threshold": None,
        "min_consecutive": 1,
    },
}
EVENT_TYPE_CONSTRAINT_OPTIONS = (
    "NIGHT_USAGE",
    "SPIKE",
    "LONG_HIGH_USAGE",
    "EXPECTED_ZERO_USAGE",
)


def ensure_event_tables() -> None:
    ensure_expected_zero_table()
    with ENGINE_PG.begin() as conn:
        PlynomeryAnomalyEvent.__table__.create(bind=conn, checkfirst=True)
        PlynomeryEventState.__table__.create(bind=conn, checkfirst=True)
        PlynomeryEventEngineState.__table__.create(bind=conn, checkfirst=True)
        _ensure_event_type_constraint(conn)
    _drop_legacy_identifikace_fk(PlynomeryAnomalyEvent.__tablename__)


def _ensure_event_type_constraint(conn) -> None:
    inspector = inspect(conn)
    if "plynomery_anomaly_events" not in inspector.get_table_names(schema="monitoring"):
        return

    allowed_values = ", ".join(f"'{value}'" for value in EVENT_TYPE_CONSTRAINT_OPTIONS)
    conn.execute(
        text(
            "ALTER TABLE monitoring.plynomery_anomaly_events "
            "DROP CONSTRAINT IF EXISTS ck_plynomery_event_type_valid"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE monitoring.plynomery_anomaly_events "
            f"ADD CONSTRAINT ck_plynomery_event_type_valid CHECK (event_type IN ({allowed_values}))"
        )
    )


def _drop_legacy_identifikace_fk(table_name: str) -> None:
    inspector = inspect(ENGINE_PG)
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
            with ENGINE_PG.begin() as conn:
                conn.execute(
                    text(
                        f'ALTER TABLE monitoring."{table_name}" '
                        f'DROP CONSTRAINT IF EXISTS "{escaped_name}"'
                    )
                )


def detect_events_from_scores(
    model_version: int,
    batch_size: int = 50000,
    *,
    bootstrap_to_latest_if_missing: bool = False,
):
    ensure_event_tables()

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        engine_state = session.execute(
            select(PlynomeryEventEngineState)
            .where(PlynomeryEventEngineState.model_version == model_version)
            .with_for_update()
        ).scalar_one_or_none()

        if engine_state is None:
            initial_checkpoint = 0
            if bootstrap_to_latest_if_missing:
                initial_checkpoint = int(
                    session.query(func.max(PlynomeryAnomalyScore.id))
                    .filter(PlynomeryAnomalyScore.model_version == model_version)
                    .scalar()
                    or 0
                )
            engine_state = PlynomeryEventEngineState(
                model_version=model_version,
                last_score_id=initial_checkpoint,
            )
            session.add(engine_state)
            session.commit()
            last_id = initial_checkpoint
        else:
            last_id = int(engine_state.last_score_id or 0)

        if last_id > 0:
            session.execute(
                update(PlynomeryAnomalyScore)
                .where(
                    PlynomeryAnomalyScore.model_version == model_version,
                    PlynomeryAnomalyScore.id <= last_id,
                    PlynomeryAnomalyScore.processed.is_(False),
                )
                .values(processed=True)
            )

        new_scores = (
            session.query(PlynomeryAnomalyScore)
            .filter(
                PlynomeryAnomalyScore.model_version == model_version,
                PlynomeryAnomalyScore.processed.is_(False),
            )
            .order_by(PlynomeryAnomalyScore.id)
            .limit(batch_size)
            .all()
        )
        if not new_scores:
            return {
                "processed": 0,
                "created": 0,
                "resolved": 0,
                "last_score_id": last_id,
                "created_event_ids": [],
                "active_event_ids": [],
                "resolved_event_ids": [],
            }

        max_processed_id = int(new_scores[-1].id)
        idents = {score.identifikace for score in new_scores}
        expected_zero_idents = get_expected_zero_device_set(session=session) & idents

        states = session.execute(
            select(PlynomeryEventState).where(
                PlynomeryEventState.model_version == model_version,
                PlynomeryEventState.identifikace.in_(idents),
            )
        ).scalars().all()
        state_lookup = {(state.identifikace, state.event_type): state for state in states}

        active_events = session.execute(
            select(PlynomeryAnomalyEvent).where(
                PlynomeryAnomalyEvent.model_version == model_version,
                PlynomeryAnomalyEvent.identifikace.in_(idents),
                PlynomeryAnomalyEvent.is_active.is_(True),
            )
        ).scalars().all()
        active_lookup = {(event.identifikace, event.event_type): event for event in active_events}

        created_events = 0
        resolved_events = 0
        created_event_objects = []
        active_event_candidates = {}
        resolved_event_candidates = {}

        for score in new_scores:
            ident = score.identifikace
            ts = score.date

            for event_type, cfg in EVENT_CONFIG.items():
                key = (ident, event_type)
                state = state_lookup.get(key)
                if state is None:
                    state = PlynomeryEventState(
                        identifikace=ident,
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
                    triggered = ident in expected_zero_idents and score.actual_value > 0
                elif event_type == "NIGHT_USAGE":
                    triggered = (ts.hour >= 23 or ts.hour < 5) and score.z_score > cfg["threshold"]
                else:
                    triggered = score.z_score > cfg["threshold"]

                if triggered:
                    state.consecutive_count += 1
                    state.accumulator += abs(score.z_score)

                    if not state.is_event_active and state.consecutive_count >= cfg["min_consecutive"]:
                        state.is_event_active = True
                        state.event_start_time = ts

                        new_event = PlynomeryAnomalyEvent(
                            identifikace=ident,
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
                        session.add(new_event)
                        active_lookup[key] = new_event
                        created_event_objects.append(new_event)
                        active_event_candidates[key] = new_event
                        created_events += 1
                    elif state.is_event_active:
                        event = active_lookup.get(key)
                        if event is not None:
                            event.max_z_score = max(event.max_z_score, score.z_score)
                            event.total_deviation += abs(score.z_score)
                            duration = int((ts - event.start_time).total_seconds() / 60)
                            event.duration_minutes = duration
                            event.avg_z_score = event.total_deviation / max(state.consecutive_count, 1)
                            event.severity = _compute_severity(event.max_z_score, duration)
                            event.last_score_time = ts
                            active_event_candidates[key] = event
                else:
                    if state.is_event_active:
                        event = active_lookup.get(key)
                        if event is not None:
                            event.is_active = False
                            event.resolved = True
                            event.resolved_at = ts
                            event.end_time = ts
                            resolved_event_candidates[key] = event
                            resolved_events += 1
                        state.is_event_active = False

                    state.consecutive_count = 0
                    state.accumulator = 0.0
                    state.event_start_time = None

                state.last_score_time = ts

        processed_score_ids = [score.id for score in new_scores if score.id is not None]
        if processed_score_ids:
            session.execute(
                update(PlynomeryAnomalyScore)
                .where(PlynomeryAnomalyScore.id.in_(processed_score_ids))
                .values(processed=True)
            )

        engine_state.last_score_id = max_processed_id
        engine_state.updated_at = utc_now_naive()
        session.commit()

        created_event_ids = [event.id for event in created_event_objects if event.id is not None]
        active_event_ids = [event.id for event in active_event_candidates.values() if event.id is not None]
        resolved_event_ids = [event.id for event in resolved_event_candidates.values() if event.id is not None]

        return {
            "processed": len(new_scores),
            "created": created_events,
            "resolved": resolved_events,
            "last_score_id": max_processed_id,
            "created_event_ids": created_event_ids,
            "active_event_ids": active_event_ids,
            "resolved_event_ids": resolved_event_ids,
        }


def _compute_severity(max_z: float, duration_min: int) -> str:
    if max_z > 8 or duration_min > 720:
        return "CRITICAL"
    if max_z > 5 or duration_min > 240:
        return "HIGH"
    if max_z > 3:
        return "MEDIUM"
    return "LOW"
