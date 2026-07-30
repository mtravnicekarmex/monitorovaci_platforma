from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import isclose
from types import SimpleNamespace

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_PG
from moduly.mereni.kalorimetry.active_profile import (
    MISSING_PROFILE,
    KalorimetryProfileLookupRequest,
    load_period_valid_active_profiles,
)
from moduly.mereni.kalorimetry.database.models import (
    KalorimetryAnomalyEvent,
    KalorimetryAnomalyScore,
    Mereni_kalorimetry,
)
from moduly.mereni.kalorimetry.events import evaluate_event_transitions
from moduly.mereni.kalorimetry.kalorimetry_anomaly import (
    ACTIVE_SELECTION_SCORE_MODEL_VERSION,
    build_score_row,
)
from moduly.mereni.kalorimetry.observation_quality import (
    KalorimetryObservationPurpose,
    evaluate_kalorimetry_observation,
)
from moduly.mereni.kalorimetry.production_backfill import (
    KALORIMETRY_CONTROLLED_BACKFILL_END,
    KALORIMETRY_CONTROLLED_BACKFILL_START,
)

CONTROLLED_PERIOD_START = KALORIMETRY_CONTROLLED_BACKFILL_START
CONTROLLED_PERIOD_END = KALORIMETRY_CONTROLLED_BACKFILL_END

SCORE_FLOAT_FIELDS = (
    "actual_value",
    "expected_mean",
    "expected_std",
    "expected_median",
    "expected_p10",
    "expected_p90",
    "deviation",
    "z_score",
)


@dataclass(frozen=True)
class KalorimetryReconciliationSummary:
    period_start: datetime
    period_end: datetime
    measurement_count: int
    eligible_measurement_count: int
    ineligible_measurement_count: int
    unavailable_selection_count: int
    intentionally_unscored_count: int
    expected_score_count: int
    persisted_score_count: int
    missing_score_count: int
    unexpected_score_count: int
    mismatched_score_count: int
    anomaly_flag_change_count: int
    severity_change_count: int
    expected_event_created_count: int
    expected_event_resolved_count: int
    persisted_event_count: int
    missing_event_count: int
    unexpected_event_count: int
    mismatched_event_count: int
    score_table_exists: bool
    event_table_exists: bool
    read_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class _Counters:
    measurement_count: int = 0
    eligible_measurement_count: int = 0
    intentionally_unscored_count: int = 0
    expected_score_count: int = 0
    persisted_score_count: int = 0
    missing_score_count: int = 0
    unexpected_score_count: int = 0
    mismatched_score_count: int = 0
    anomaly_flag_change_count: int = 0
    severity_change_count: int = 0


def run_historical_reconciliation_dry_run(
    *,
    batch_size: int = 5000,
) -> KalorimetryReconciliationSummary:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    with ENGINE_PG.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            session = Session(
                bind=connection,
                autoflush=False,
                expire_on_commit=False,
            )
            try:
                return build_historical_reconciliation_dry_run(
                    session,
                    batch_size=batch_size,
                )
            finally:
                session.close()
        finally:
            transaction.rollback()


def build_historical_reconciliation_dry_run(
    session: Session,
    *,
    batch_size: int = 5000,
) -> KalorimetryReconciliationSummary:
    score_table_exists = _table_exists(
        session,
        "monitoring.kalorimetry_anomaly_scores",
    )
    event_table_exists = _table_exists(
        session,
        "monitoring.kalorimetry_anomaly_events",
    )
    persisted_scores = (
        session.execute(
            select(KalorimetryAnomalyScore).where(
                KalorimetryAnomalyScore.model_version
                == ACTIVE_SELECTION_SCORE_MODEL_VERSION,
                KalorimetryAnomalyScore.date >= CONTROLLED_PERIOD_START,
                KalorimetryAnomalyScore.date < CONTROLLED_PERIOD_END,
            )
        )
        .scalars()
        .all()
        if score_table_exists
        else []
    )
    persisted_by_measurement = {
        int(row.measurement_id): row for row in persisted_scores
    }
    counters = _Counters(persisted_score_count=len(persisted_scores))
    expected_measurement_ids: set[int] = set()
    event_states = ()
    event_transitions = []
    last_id = 0

    while True:
        measurements = (
            session.execute(
                select(Mereni_kalorimetry)
                .where(
                    Mereni_kalorimetry.id > last_id,
                    Mereni_kalorimetry.date >= CONTROLLED_PERIOD_START,
                    Mereni_kalorimetry.date < CONTROLLED_PERIOD_END,
                )
                .order_by(Mereni_kalorimetry.id)
                .limit(batch_size)
            )
            .scalars()
            .all()
        )
        if not measurements:
            break
        last_id = int(measurements[-1].id)
        counters.measurement_count += len(measurements)
        expected_rows = _build_expected_rows(session, measurements, counters)
        expected_measurement_ids.update(
            int(row["measurement_id"]) for row in expected_rows
        )
        compare_score_rows(
            expected_rows,
            persisted_by_measurement,
            counters=counters,
        )
        score_objects = [
            SimpleNamespace(id=row["measurement_id"], **row)
            for row in expected_rows
        ]
        event_states, transitions = evaluate_event_transitions(
            score_objects,
            initial_states=event_states,
        )
        event_transitions.extend(transitions)

    persisted_ids = set(persisted_by_measurement)
    counters.unexpected_score_count = len(
        persisted_ids - expected_measurement_ids
    )
    counters.intentionally_unscored_count = (
        counters.measurement_count - counters.expected_score_count
    )

    expected_created = [
        transition
        for transition in event_transitions
        if transition.transition == "CREATED"
    ]
    expected_resolved_count = sum(
        transition.transition == "RESOLVED"
        for transition in event_transitions
    )
    persisted_events = (
        session.execute(
            select(KalorimetryAnomalyEvent).where(
                KalorimetryAnomalyEvent.model_version
                == ACTIVE_SELECTION_SCORE_MODEL_VERSION,
                KalorimetryAnomalyEvent.start_time >= CONTROLLED_PERIOD_START,
                KalorimetryAnomalyEvent.start_time < CONTROLLED_PERIOD_END,
            )
        )
        .scalars()
        .all()
        if event_table_exists
        else []
    )
    missing_events, unexpected_events, mismatched_events = compare_events(
        event_transitions,
        persisted_events,
    )
    return KalorimetryReconciliationSummary(
        period_start=CONTROLLED_PERIOD_START,
        period_end=CONTROLLED_PERIOD_END,
        measurement_count=counters.measurement_count,
        eligible_measurement_count=counters.eligible_measurement_count,
        ineligible_measurement_count=(
            counters.measurement_count - counters.eligible_measurement_count
        ),
        unavailable_selection_count=(
            counters.eligible_measurement_count
            - counters.expected_score_count
        ),
        intentionally_unscored_count=counters.intentionally_unscored_count,
        expected_score_count=counters.expected_score_count,
        persisted_score_count=counters.persisted_score_count,
        missing_score_count=counters.missing_score_count,
        unexpected_score_count=counters.unexpected_score_count,
        mismatched_score_count=counters.mismatched_score_count,
        anomaly_flag_change_count=counters.anomaly_flag_change_count,
        severity_change_count=counters.severity_change_count,
        expected_event_created_count=len(expected_created),
        expected_event_resolved_count=expected_resolved_count,
        persisted_event_count=len(persisted_events),
        missing_event_count=missing_events,
        unexpected_event_count=unexpected_events,
        mismatched_event_count=mismatched_events,
        score_table_exists=score_table_exists,
        event_table_exists=event_table_exists,
    )


def compare_score_rows(
    expected_rows: list[dict[str, object]],
    persisted_by_measurement: dict[int, object],
    *,
    counters: _Counters | None = None,
) -> _Counters:
    result = counters or _Counters()
    for expected in expected_rows:
        result.expected_score_count += 1
        measurement_id = int(expected["measurement_id"])
        persisted = persisted_by_measurement.get(measurement_id)
        if persisted is None:
            result.missing_score_count += 1
            continue
        numeric_mismatch = any(
            not _floats_match(expected[field], getattr(persisted, field))
            for field in SCORE_FLOAT_FIELDS
        )
        anomaly_changed = bool(expected["is_anomaly"]) != bool(
            persisted.is_anomaly
        )
        severity_changed = expected["severity"] != persisted.severity
        identity_mismatch = (
            int(expected["selected_model_version"])
            != int(persisted.selected_model_version)
            or int(expected["selection_snapshot_id"])
            != int(persisted.selection_snapshot_id)
            or int(expected["profile_snapshot_id"])
            != int(persisted.profile_snapshot_id)
        )
        if (
            numeric_mismatch
            or anomaly_changed
            or severity_changed
            or identity_mismatch
        ):
            result.mismatched_score_count += 1
        result.anomaly_flag_change_count += int(anomaly_changed)
        result.severity_change_count += int(severity_changed)
    return result


def compare_events(
    expected_transitions: list[object],
    persisted_events: list[object],
) -> tuple[int, int, int]:
    expected_by_key = {}
    active_key_by_type = {}
    for row in expected_transitions:
        type_key = (row.identifier, row.event_type)
        if row.transition == "CREATED":
            key = (
                row.identifier,
                row.event_type,
                row.transition_time,
            )
            expected_by_key[key] = row
            active_key_by_type[type_key] = key
        elif type_key in active_key_by_type:
            expected_by_key[active_key_by_type.pop(type_key)] = row
    persisted_by_key = {
        (
            row.identifikace,
            row.event_type,
            row.start_time,
        ): row
        for row in persisted_events
    }
    expected_keys = set(expected_by_key)
    persisted_keys = set(persisted_by_key)
    mismatched = 0
    for key in expected_keys & persisted_keys:
        expected = expected_by_key[key]
        persisted = persisted_by_key[key]
        if (
            expected.severity != persisted.severity
            or not _floats_match(
                expected.max_z_score,
                persisted.max_z_score,
            )
        ):
            mismatched += 1
    return (
        len(expected_keys - persisted_keys),
        len(persisted_keys - expected_keys),
        mismatched,
    )


def _build_expected_rows(
    session: Session,
    measurements: list[Mereni_kalorimetry],
    counters: _Counters,
) -> list[dict[str, object]]:
    eligible = []
    for measurement in measurements:
        quality = evaluate_kalorimetry_observation(
            {
                "identifikace": measurement.identifikace,
                "date": measurement.date,
                "interval_minutes": measurement.interval_minutes,
                "spotreba_energie": measurement.spotreba_energie,
                "platne": measurement.platne,
                "reset_detected": measurement.reset_detected,
                "delta": measurement.delta,
                "synthetic": measurement.synthetic,
                "gap_detected": measurement.gap_detected,
            },
            purpose=KalorimetryObservationPurpose.SCORING,
        )
        if quality.eligible:
            eligible.append(measurement)
    counters.eligible_measurement_count += len(eligible)
    lookups = load_period_valid_active_profiles(
        session,
        [
            KalorimetryProfileLookupRequest(
                identifier=row.identifikace,
                timestamp=row.date,
                interval_minutes=row.interval_minutes,
            )
            for row in eligible
        ],
    )
    expected_rows = []
    for measurement, lookup in zip(eligible, lookups, strict=True):
        if not lookup.prediction_available:
            if lookup.availability_reason == MISSING_PROFILE:
                raise RuntimeError(
                    "Reconciliation stopped: available decision has no "
                    "exact profile slot."
                )
            continue
        expected_rows.append(build_score_row(measurement, lookup=lookup))
    return expected_rows


def _table_exists(session: Session, qualified_name: str) -> bool:
    return (
        session.execute(
            text("SELECT to_regclass(:qualified_name)"),
            {"qualified_name": qualified_name},
        ).scalar_one()
        is not None
    )


def _floats_match(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return isclose(
            float(left),
            float(right),
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
    except (TypeError, ValueError):
        return False
