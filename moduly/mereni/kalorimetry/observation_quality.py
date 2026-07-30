from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class KalorimetryObservationPurpose(str, Enum):
    METER_STATE_DISPLAY = "meter_state_display"
    CONSUMPTION_DISPLAY = "consumption_display"
    MODEL_INPUT = "model_input"
    SCORING = "scoring"


class KalorimetryObservationExclusionReason(str, Enum):
    MISSING_IDENTIFIER = "missing_identifier"
    MISSING_TIMESTAMP = "missing_timestamp"
    INVALID_INTERVAL = "invalid_interval"
    MISSING_OR_NONFINITE_METER_STATE = "missing_or_nonfinite_meter_state"
    INVALID_MEASUREMENT = "invalid_measurement"
    RESET_MEASUREMENT = "reset_measurement"
    MISSING_OR_NONFINITE_DELTA = "missing_or_nonfinite_delta"
    NEGATIVE_DELTA = "negative_delta"
    SYNTHETIC_GAP_ROW = "synthetic_gap_row"
    GAP_AFFECTED_ROW = "gap_affected_row"


@dataclass(frozen=True)
class KalorimetryObservationEligibility:
    purpose: KalorimetryObservationPurpose
    eligible: bool
    reason: KalorimetryObservationExclusionReason | None = None


def evaluate_kalorimetry_observation(
    row: Mapping[str, object],
    *,
    purpose: KalorimetryObservationPurpose | str,
) -> KalorimetryObservationEligibility:
    resolved_purpose = KalorimetryObservationPurpose(purpose)

    if not str(row.get("identifikace") or "").strip():
        return _excluded(
            resolved_purpose,
            KalorimetryObservationExclusionReason.MISSING_IDENTIFIER,
        )
    if row.get("date") is None:
        return _excluded(
            resolved_purpose,
            KalorimetryObservationExclusionReason.MISSING_TIMESTAMP,
        )

    interval_minutes = _finite_number(row.get("interval_minutes"))
    if interval_minutes is None or interval_minutes <= 0:
        return _excluded(
            resolved_purpose,
            KalorimetryObservationExclusionReason.INVALID_INTERVAL,
        )

    meter_state = _finite_number(row.get("spotreba_energie"))
    if meter_state is None:
        return _excluded(
            resolved_purpose,
            KalorimetryObservationExclusionReason.MISSING_OR_NONFINITE_METER_STATE,
        )

    if resolved_purpose is KalorimetryObservationPurpose.METER_STATE_DISPLAY:
        return KalorimetryObservationEligibility(
            purpose=resolved_purpose,
            eligible=True,
        )

    if not bool(row.get("platne", False)):
        return _excluded(
            resolved_purpose,
            KalorimetryObservationExclusionReason.INVALID_MEASUREMENT,
        )
    if bool(row.get("reset_detected", False)):
        return _excluded(
            resolved_purpose,
            KalorimetryObservationExclusionReason.RESET_MEASUREMENT,
        )

    delta = _finite_number(row.get("delta"))
    if delta is None:
        return _excluded(
            resolved_purpose,
            KalorimetryObservationExclusionReason.MISSING_OR_NONFINITE_DELTA,
        )
    if delta < 0:
        return _excluded(
            resolved_purpose,
            KalorimetryObservationExclusionReason.NEGATIVE_DELTA,
        )

    if resolved_purpose in {
        KalorimetryObservationPurpose.MODEL_INPUT,
        KalorimetryObservationPurpose.SCORING,
    }:
        if bool(row.get("synthetic", False)):
            return _excluded(
                resolved_purpose,
                KalorimetryObservationExclusionReason.SYNTHETIC_GAP_ROW,
            )
        if bool(row.get("gap_detected", False)):
            return _excluded(
                resolved_purpose,
                KalorimetryObservationExclusionReason.GAP_AFFECTED_ROW,
            )

    return KalorimetryObservationEligibility(
        purpose=resolved_purpose,
        eligible=True,
    )


def is_kalorimetry_observation_eligible(
    row: Mapping[str, object],
    *,
    purpose: KalorimetryObservationPurpose | str,
) -> bool:
    return evaluate_kalorimetry_observation(
        row,
        purpose=purpose,
    ).eligible


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def _excluded(
    purpose: KalorimetryObservationPurpose,
    reason: KalorimetryObservationExclusionReason,
) -> KalorimetryObservationEligibility:
    return KalorimetryObservationEligibility(
        purpose=purpose,
        eligible=False,
        reason=reason,
    )
