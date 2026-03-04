from sqlalchemy import select
from moduly.mereni.vodomery.database.models import *
from core.db.connect import ENGINE_PG
from sqlalchemy.orm import Session
from app.time_utils import utc_now_naive
from moduly.mereni.vodomery.database.vodomery_db_vse import is_night_time


EVENT_CONFIG = {
    "NIGHT_USAGE": {
        "threshold": 3.0,
        "min_consecutive": 2,
    },
    "SPIKE": {
        "threshold": 5.0,
        "min_consecutive": 1,
    },
    "LONG_LEAK": {
        "threshold": 2.0,
        "min_consecutive": 8,
    },
    "ZERO_FLOW": {
        "threshold": None,
        "min_consecutive": 12,
    },
}


def detect_events_from_scores(model_version: int, batch_size: int = 50000):

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:

        # =====================================================
        # 1️⃣ Engine state
        # =====================================================
        engine_state = session.execute(
            select(VodomeryEventEngineState)
            .where(VodomeryEventEngineState.model_version == model_version)
            .with_for_update()
        ).scalar_one_or_none()

        if engine_state is None:
            engine_state = VodomeryEventEngineState(
                model_version=model_version,
                last_score_id=0,
            )
            session.add(engine_state)
            session.commit()
            last_id = 0
        else:
            last_id = engine_state.last_score_id

        # =====================================================
        # 2️⃣ Načti nové scores
        # =====================================================
        new_scores = (
            session.query(VodomeryAnomalyScore)
            .filter(
                VodomeryAnomalyScore.model_version == model_version,
                VodomeryAnomalyScore.id > last_id,
            )
            .order_by(VodomeryAnomalyScore.id)
            .limit(batch_size)
            .all()
        )

        if not new_scores:
            return {
                "processed": 0,
                "created": 0,
                "resolved": 0,
            }

        max_processed_id = new_scores[-1].id
        idents = {s.identifikace for s in new_scores}

        # =====================================================
        # 3️⃣ Načti states
        # =====================================================
        states = session.execute(
            select(VodomeryEventState).where(
                VodomeryEventState.model_version == model_version,
                VodomeryEventState.identifikace.in_(idents),
            )
        ).scalars().all()

        state_lookup = {
            (s.identifikace, s.event_type): s for s in states
        }

        # =====================================================
        # 4️⃣ Načti aktivní eventy
        # =====================================================
        active_events = session.execute(
            select(VodomeryAnomalyEvent).where(
                VodomeryAnomalyEvent.model_version == model_version,
                VodomeryAnomalyEvent.identifikace.in_(idents),
                VodomeryAnomalyEvent.is_active.is_(True),
            )
        ).scalars().all()

        active_lookup = {
            (e.identifikace, e.event_type): e for e in active_events
        }

        created_events = 0
        resolved_events = 0

        # =====================================================
        # 5️⃣ Hlavní smyčka
        # =====================================================
        for score in new_scores:

            ident = score.identifikace
            ts = score.date

            for event_type, cfg in EVENT_CONFIG.items():

                key = (ident, event_type)
                state = state_lookup.get(key)

                # vytvoř state pokud neexistuje
                if not state:
                    state = VodomeryEventState(
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

                # -------------------------------------------------
                # TRIGGER LOGIKA
                # -------------------------------------------------
                if event_type == "ZERO_FLOW":
                    triggered = score.actual_value == 0
                elif event_type == "NIGHT_USAGE":
                    triggered = (
                        is_night_time(ts)
                        and score.z_score > cfg["threshold"]
                    )
                else:
                    triggered = score.z_score > cfg["threshold"]

                # =================================================
                # EVENT AKTIVNÍ
                # =================================================
                if triggered:

                    state.consecutive_count += 1
                    state.accumulator += abs(score.z_score)

                    if (
                        not state.is_event_active
                        and state.consecutive_count >= cfg["min_consecutive"]
                    ):

                        # otevři nový event
                        state.is_event_active = True
                        state.event_start_time = ts

                        new_event = VodomeryAnomalyEvent(
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
                        created_events += 1

                    elif state.is_event_active:

                        # update existujícího eventu
                        event = active_lookup.get(key)
                        if event:

                            event.max_z_score = max(
                                event.max_z_score,
                                score.z_score,
                            )

                            event.total_deviation += abs(score.z_score)

                            duration = int(
                                (ts - event.start_time).total_seconds() / 60
                            )

                            event.duration_minutes = duration

                            event.avg_z_score = (
                                event.total_deviation
                                / max(state.consecutive_count, 1)
                            )

                            event.severity = _compute_severity(
                                event.max_z_score,
                                duration,
                            )

                            event.last_score_time = ts

                # =================================================
                # EVENT KONČÍ
                # =================================================
                else:

                    if state.is_event_active:

                        event = active_lookup.get(key)
                        if event:
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

        # =====================================================
        # 6️⃣ Ulož engine state
        # =====================================================
        engine_state.last_score_id = max_processed_id
        engine_state.updated_at = utc_now_naive()

        session.commit()

        return {
            "processed": len(new_scores),
            "created": created_events,
            "resolved": resolved_events,
            "last_score_id": max_processed_id,
        }



def _compute_severity(max_z: float, duration_min: int) -> str:

    if max_z > 8 or duration_min > 720:
        return "CRITICAL"

    if max_z > 5 or duration_min > 240:
        return "HIGH"

    if max_z > 3:
        return "MEDIUM"

    return "LOW"




