from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.kalorimetry.database.models import (
    KalorimetryAnomalyEvent,
    KalorimetryAnomalyScore,
    KalorimetryEventEngineState,
    KalorimetryEventState as KalorimetryEventStateRow,
)

EVENT_SPIKE = "SPIKE"
EVENT_SUSTAINED_HIGH_USAGE = "SUSTAINED_HIGH_USAGE"

EVENT_CONFIG = {
    EVENT_SPIKE: {"z_threshold": 5.0, "min_consecutive": 1},
    EVENT_SUSTAINED_HIGH_USAGE: {
        "z_threshold": 3.0,
        "min_consecutive": 8,
    },
}


@dataclass(frozen=True)
class KalorimetryEventState:
    identifier: str
    event_type: str
    consecutive_count: int = 0
    is_active: bool = False
    event_start_time: datetime | None = None
    max_z_score: float = 0.0
    last_score_time: datetime | None = None


@dataclass(frozen=True)
class KalorimetryEventTransition:
    identifier: str
    event_type: str
    transition: str
    transition_time: datetime
    severity: str
    max_z_score: float
    duration_minutes: int


@dataclass(frozen=True)
class KalorimetryAlertPlan:
    transition: KalorimetryEventTransition
    delivery_enabled: bool = False


def ensure_event_tables() -> None:
    with ENGINE_PG.begin() as connection:
        KalorimetryAnomalyEvent.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        KalorimetryEventStateRow.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        KalorimetryEventEngineState.__table__.create(
            bind=connection,
            checkfirst=True,
        )


def detect_events_from_scores(
    *,
    model_version: int = 1,
    batch_size: int = 50000,
    bootstrap_to_latest_if_missing: bool = False,
) -> dict[str, object]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    ensure_event_tables()
    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        engine_state = session.execute(
            select(KalorimetryEventEngineState)
            .where(
                KalorimetryEventEngineState.model_version == model_version
            )
            .with_for_update()
        ).scalar_one_or_none()
        if engine_state is None:
            checkpoint = 0
            if bootstrap_to_latest_if_missing:
                checkpoint = int(
                    session.query(func.max(KalorimetryAnomalyScore.id))
                    .filter(
                        KalorimetryAnomalyScore.model_version == model_version
                    )
                    .scalar()
                    or 0
                )
            engine_state = KalorimetryEventEngineState(
                model_version=model_version,
                last_score_id=checkpoint,
            )
            session.add(engine_state)
            session.commit()

        scores = (
            session.execute(
                select(KalorimetryAnomalyScore)
                .where(
                    KalorimetryAnomalyScore.model_version == model_version,
                    KalorimetryAnomalyScore.id
                    > int(engine_state.last_score_id or 0),
                )
                .order_by(KalorimetryAnomalyScore.id)
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not scores:
            return _event_result(engine_state.last_score_id)

        identifiers = sorted({str(score.identifikace) for score in scores})
        stored_states = (
            session.execute(
                select(KalorimetryEventStateRow).where(
                    KalorimetryEventStateRow.model_version == model_version,
                    KalorimetryEventStateRow.identifikace.in_(identifiers),
                )
            )
            .scalars()
            .all()
        )
        initial_states = [
            KalorimetryEventState(
                identifier=row.identifikace,
                event_type=row.event_type,
                consecutive_count=row.consecutive_count,
                is_active=row.is_event_active,
                event_start_time=row.event_start_time,
                max_z_score=row.max_z_score,
                last_score_time=row.last_score_time,
            )
            for row in stored_states
        ]
        final_states, transitions = evaluate_event_transitions(
            scores,
            initial_states=initial_states,
        )
        _persist_event_states(
            session,
            final_states=final_states,
            stored_states=stored_states,
            model_version=model_version,
        )
        _persist_event_transitions(
            session,
            transitions=transitions,
            model_version=model_version,
        )

        score_ids = [int(score.id) for score in scores]
        session.execute(
            update(KalorimetryAnomalyScore)
            .where(KalorimetryAnomalyScore.id.in_(score_ids))
            .values(processed=True)
        )
        engine_state.last_score_id = max(score_ids)
        engine_state.updated_at = utc_now_naive()
        session.commit()
        return _event_result(
            engine_state.last_score_id,
            processed=len(scores),
            transitions=transitions,
        )


def evaluate_event_transitions(
    scores: Iterable[object],
    *,
    initial_states: Iterable[KalorimetryEventState] = (),
) -> tuple[
    tuple[KalorimetryEventState, ...],
    tuple[KalorimetryEventTransition, ...],
]:
    state_by_key = {
        (state.identifier, state.event_type): state
        for state in initial_states
    }
    transitions: list[KalorimetryEventTransition] = []

    for score in sorted(scores, key=lambda row: (row.date, int(row.id or 0))):
        identifier = str(score.identifikace)
        for event_type, config in EVENT_CONFIG.items():
            key = (identifier, event_type)
            state = state_by_key.get(
                key,
                KalorimetryEventState(
                    identifier=identifier,
                    event_type=event_type,
                ),
            )
            triggered = float(score.z_score) > float(config["z_threshold"])
            if triggered:
                count = state.consecutive_count + 1
                start = state.event_start_time or score.date
                max_z = max(float(state.max_z_score), float(score.z_score))
                became_active = (
                    not state.is_active
                    and count >= int(config["min_consecutive"])
                )
                state = replace(
                    state,
                    consecutive_count=count,
                    is_active=state.is_active or became_active,
                    event_start_time=start,
                    max_z_score=max_z,
                    last_score_time=score.date,
                )
                if became_active:
                    transitions.append(
                        _transition(state, "CREATED", score.date)
                    )
            else:
                if state.is_active:
                    transitions.append(
                        _transition(state, "RESOLVED", score.date)
                    )
                state = replace(
                    state,
                    consecutive_count=0,
                    is_active=False,
                    event_start_time=None,
                    max_z_score=0.0,
                    last_score_time=score.date,
                )
            state_by_key[key] = state

    return (
        tuple(
            state_by_key[key]
            for key in sorted(state_by_key)
        ),
        tuple(transitions),
    )


def build_alert_transition_plan(
    transitions: Iterable[KalorimetryEventTransition],
) -> tuple[KalorimetryAlertPlan, ...]:
    return tuple(
        KalorimetryAlertPlan(
            transition=transition,
            delivery_enabled=False,
        )
        for transition in transitions
    )


def _persist_event_states(
    session: Session,
    *,
    final_states: tuple[KalorimetryEventState, ...],
    stored_states: list[KalorimetryEventStateRow],
    model_version: int,
) -> None:
    stored_by_key = {
        (row.identifikace, row.event_type): row
        for row in stored_states
    }
    for state in final_states:
        key = (state.identifier, state.event_type)
        row = stored_by_key.get(key)
        if row is None:
            row = KalorimetryEventStateRow(
                identifikace=state.identifier,
                event_type=state.event_type,
                model_version=model_version,
            )
            session.add(row)
        row.consecutive_count = state.consecutive_count
        row.is_event_active = state.is_active
        row.event_start_time = state.event_start_time
        row.max_z_score = state.max_z_score
        row.last_score_time = state.last_score_time


def _persist_event_transitions(
    session: Session,
    *,
    transitions: tuple[KalorimetryEventTransition, ...],
    model_version: int,
) -> None:
    for transition in transitions:
        if transition.transition == "CREATED":
            session.add(
                KalorimetryAnomalyEvent(
                    identifikace=transition.identifier,
                    event_type=transition.event_type,
                    model_version=model_version,
                    start_time=(
                        transition.transition_time
                        - timedelta(minutes=transition.duration_minutes)
                    ),
                    end_time=None,
                    duration_minutes=transition.duration_minutes,
                    max_z_score=transition.max_z_score,
                    severity=transition.severity,
                    is_active=True,
                    resolved=False,
                    resolved_at=None,
                    last_score_time=transition.transition_time,
                )
            )
            continue
        active = session.execute(
            select(KalorimetryAnomalyEvent)
            .where(
                KalorimetryAnomalyEvent.identifikace
                == transition.identifier,
                KalorimetryAnomalyEvent.event_type == transition.event_type,
                KalorimetryAnomalyEvent.model_version == model_version,
                KalorimetryAnomalyEvent.is_active.is_(True),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if active is not None:
            active.end_time = transition.transition_time
            active.duration_minutes = transition.duration_minutes
            active.max_z_score = transition.max_z_score
            active.severity = transition.severity
            active.is_active = False
            active.resolved = True
            active.resolved_at = transition.transition_time
            active.last_score_time = transition.transition_time


def _event_result(
    last_score_id: int,
    *,
    processed: int = 0,
    transitions: tuple[KalorimetryEventTransition, ...] = (),
) -> dict[str, object]:
    return {
        "processed": processed,
        "created": sum(
            row.transition == "CREATED" for row in transitions
        ),
        "resolved": sum(
            row.transition == "RESOLVED" for row in transitions
        ),
        "last_score_id": int(last_score_id or 0),
        "alert_plan": build_alert_transition_plan(transitions),
    }


def _transition(
    state: KalorimetryEventState,
    transition: str,
    transition_time: datetime,
) -> KalorimetryEventTransition:
    duration_minutes = 0
    if state.event_start_time is not None:
        duration_minutes = max(
            0,
            int(
                (transition_time - state.event_start_time).total_seconds()
                / 60
            ),
        )
    return KalorimetryEventTransition(
        identifier=state.identifier,
        event_type=state.event_type,
        transition=transition,
        transition_time=transition_time,
        severity=_severity(state.max_z_score, duration_minutes),
        max_z_score=state.max_z_score,
        duration_minutes=duration_minutes,
    )


def _severity(max_z_score: float, duration_minutes: int) -> str:
    if max_z_score >= 8 or duration_minutes >= 720:
        return "CRITICAL"
    if max_z_score >= 5 or duration_minutes >= 240:
        return "HIGH"
    if max_z_score >= 3:
        return "MEDIUM"
    return "LOW"
