from __future__ import annotations

import datetime

import pytest

from moduly.mereni.kalorimetry.observation_quality import (
    KalorimetryObservationExclusionReason,
    KalorimetryObservationPurpose,
    evaluate_kalorimetry_observation,
    is_kalorimetry_observation_eligible,
)


def valid_row(**overrides):
    row = {
        "identifikace": "KAL-01",
        "date": datetime.datetime(2026, 7, 29, 8, 45),
        "interval_minutes": 15,
        "spotreba_energie": 12345.0,
        "delta": 2.5,
        "platne": True,
        "reset_detected": False,
        "synthetic": False,
        "gap_detected": False,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("purpose", list(KalorimetryObservationPurpose))
def test_normalized_valid_energy_delta_is_eligible_for_every_purpose(purpose):
    result = evaluate_kalorimetry_observation(valid_row(), purpose=purpose)

    assert result.eligible is True
    assert result.reason is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"identifikace": ""}, KalorimetryObservationExclusionReason.MISSING_IDENTIFIER),
        ({"date": None}, KalorimetryObservationExclusionReason.MISSING_TIMESTAMP),
        ({"interval_minutes": 0}, KalorimetryObservationExclusionReason.INVALID_INTERVAL),
        (
            {"spotreba_energie": float("nan")},
            KalorimetryObservationExclusionReason.MISSING_OR_NONFINITE_METER_STATE,
        ),
    ],
)
def test_identity_time_cadence_and_meter_state_are_required_for_every_purpose(
    overrides,
    reason,
):
    for purpose in KalorimetryObservationPurpose:
        result = evaluate_kalorimetry_observation(
            valid_row(**overrides),
            purpose=purpose,
        )
        assert result.eligible is False
        assert result.reason is reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"platne": False}, KalorimetryObservationExclusionReason.INVALID_MEASUREMENT),
        ({"reset_detected": True}, KalorimetryObservationExclusionReason.RESET_MEASUREMENT),
        ({"delta": None}, KalorimetryObservationExclusionReason.MISSING_OR_NONFINITE_DELTA),
        ({"delta": float("inf")}, KalorimetryObservationExclusionReason.MISSING_OR_NONFINITE_DELTA),
        ({"delta": -0.001}, KalorimetryObservationExclusionReason.NEGATIVE_DELTA),
    ],
)
def test_consumption_purposes_require_a_valid_non_negative_energy_delta(
    overrides,
    reason,
):
    for purpose in (
        KalorimetryObservationPurpose.CONSUMPTION_DISPLAY,
        KalorimetryObservationPurpose.MODEL_INPUT,
        KalorimetryObservationPurpose.SCORING,
    ):
        result = evaluate_kalorimetry_observation(
            valid_row(**overrides),
            purpose=purpose,
        )
        assert result.eligible is False
        assert result.reason is reason


def test_meter_state_display_preserves_invalid_reset_and_delta_missing_rows():
    result = evaluate_kalorimetry_observation(
        valid_row(
            platne=False,
            reset_detected=True,
            delta=None,
        ),
        purpose=KalorimetryObservationPurpose.METER_STATE_DISPLAY,
    )

    assert result.eligible is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"synthetic": True, "gap_detected": True},
        {"synthetic": False, "gap_detected": True},
    ],
)
def test_gap_continuity_rows_remain_available_for_consumption_display(overrides):
    assert is_kalorimetry_observation_eligible(
        valid_row(**overrides),
        purpose=KalorimetryObservationPurpose.CONSUMPTION_DISPLAY,
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"synthetic": True, "gap_detected": True},
            KalorimetryObservationExclusionReason.SYNTHETIC_GAP_ROW,
        ),
        (
            {"synthetic": False, "gap_detected": True},
            KalorimetryObservationExclusionReason.GAP_AFFECTED_ROW,
        ),
    ],
)
@pytest.mark.parametrize(
    "purpose",
    [
        KalorimetryObservationPurpose.MODEL_INPUT,
        KalorimetryObservationPurpose.SCORING,
    ],
)
def test_gap_affected_rows_are_excluded_from_models_and_scoring(
    overrides,
    reason,
    purpose,
):
    result = evaluate_kalorimetry_observation(
        valid_row(**overrides),
        purpose=purpose,
    )

    assert result.eligible is False
    assert result.reason is reason


@pytest.mark.parametrize(
    "purpose",
    [
        KalorimetryObservationPurpose.CONSUMPTION_DISPLAY,
        KalorimetryObservationPurpose.MODEL_INPUT,
        KalorimetryObservationPurpose.SCORING,
    ],
)
def test_zero_energy_delta_is_a_real_eligible_observation(purpose):
    assert is_kalorimetry_observation_eligible(
        valid_row(delta=0.0),
        purpose=purpose,
    )


def test_string_purpose_is_normalized_to_enum():
    result = evaluate_kalorimetry_observation(
        valid_row(),
        purpose="model_input",
    )

    assert result.purpose is KalorimetryObservationPurpose.MODEL_INPUT
