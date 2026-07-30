from __future__ import annotations

import datetime

import pytest

from moduly.mereni.kalorimetry.calendar_baseline import (
    KALORIMETRY_BASELINE_MODEL_KEY,
    KALORIMETRY_BASELINE_PROFILE_POINTS,
    KalorimetryCalendarBaselineCandidate,
    build_kalorimetry_calendar_profile_catalog,
    ensure_kalorimetry_prediction_tables,
)
from moduly.mereni.prediction import (
    CandidateProfileBuildResult,
    PredictionObservation,
    PredictionRebuildWindows,
    PredictionTimeWindow,
)


def observation(
    identifier: str,
    *,
    day_of_week: int,
    slot: int,
    value: float,
    interval_minutes: int = 15,
) -> PredictionObservation:
    return PredictionObservation(
        identifier=identifier,
        timestamp=datetime.datetime(2026, 1, 5)
        + datetime.timedelta(days=day_of_week, minutes=slot * 15),
        actual_value=value,
        interval_minutes=interval_minutes,
        day_of_week=day_of_week,
        slot=slot,
    )


def complete_observations(
    identifier: str,
    *,
    samples_per_slot: int,
) -> tuple[PredictionObservation, ...]:
    return tuple(
        observation(
            identifier,
            day_of_week=day_of_week,
            slot=slot,
            value=float(sample_index),
        )
        for day_of_week in range(7)
        for slot in range(96)
        for sample_index in range(samples_per_slot)
    )


def test_calendar_baseline_builds_complete_15_minute_week_profile():
    catalog = build_kalorimetry_calendar_profile_catalog(
        complete_observations("KAL-01", samples_per_slot=2),
        minimum_slot_samples=2,
    )

    assert catalog.eligible_identifiers == ("KAL-01",)
    assert catalog.insufficient_history_identifiers == ()
    assert len(catalog.profiles) == KALORIMETRY_BASELINE_PROFILE_POINTS
    first = catalog.profiles[0]
    assert first.identifier == "KAL-01"
    assert first.interval_minutes == 15
    assert first.day_of_week == 0
    assert first.slot == 0
    assert first.expected_mean == 0.5
    assert first.expected_median == 0.5
    assert first.expected_p10 == pytest.approx(0.1)
    assert first.expected_p90 == pytest.approx(0.9)
    assert first.sample_size == 2
    assert first.features["strategy"] == KALORIMETRY_BASELINE_MODEL_KEY


def test_incomplete_identifier_publishes_no_partial_profile():
    rows = list(complete_observations("KAL-01", samples_per_slot=2))
    rows = [
        row
        for row in rows
        if not (row.day_of_week == 6 and row.slot == 95)
    ]

    catalog = build_kalorimetry_calendar_profile_catalog(
        rows,
        minimum_slot_samples=2,
    )

    assert catalog.profiles == ()
    assert catalog.eligible_identifiers == ()
    assert catalog.insufficient_history_identifiers == ("KAL-01",)


def test_catalog_keeps_eligible_identifiers_when_another_is_insufficient():
    rows = [
        *complete_observations("KAL-OK", samples_per_slot=1),
        observation("KAL-NEW", day_of_week=0, slot=0, value=1.0),
    ]

    catalog = build_kalorimetry_calendar_profile_catalog(
        rows,
        minimum_slot_samples=1,
    )

    assert catalog.eligible_identifiers == ("KAL-OK",)
    assert catalog.insufficient_history_identifiers == ("KAL-NEW",)
    assert len(catalog.profiles) == KALORIMETRY_BASELINE_PROFILE_POINTS


def test_zero_values_are_retained_and_negative_or_nonfinite_values_do_not_count():
    rows = [
        observation("KAL-01", day_of_week=0, slot=0, value=0.0),
        observation("KAL-01", day_of_week=0, slot=0, value=-1.0),
        observation("KAL-01", day_of_week=0, slot=0, value=float("inf")),
    ]

    catalog = build_kalorimetry_calendar_profile_catalog(
        rows,
        minimum_slot_samples=1,
    )

    assert catalog.eligible_identifiers == ()
    assert catalog.insufficient_history_identifiers == ("KAL-01",)


def test_non_15_minute_observations_do_not_satisfy_profile_coverage():
    catalog = build_kalorimetry_calendar_profile_catalog(
        [
            observation(
                "KAL-01",
                day_of_week=0,
                slot=0,
                value=1.0,
                interval_minutes=60,
            )
        ],
        minimum_slot_samples=1,
    )

    assert catalog.insufficient_history_identifiers == ("KAL-01",)
    assert catalog.profiles == ()


def test_minimum_slot_samples_must_be_positive():
    with pytest.raises(ValueError, match="must be positive"):
        build_kalorimetry_calendar_profile_catalog(
            (),
            minimum_slot_samples=0,
        )


def test_candidate_spec_and_build_profiles_use_shared_adapter_contract():
    observations = complete_observations("KAL-01", samples_per_slot=1)
    windows = PredictionRebuildWindows(
        train=PredictionTimeWindow(
            start=datetime.datetime(2025, 7, 1),
            end=datetime.datetime(2026, 7, 1),
        ),
        validation=PredictionTimeWindow(
            start=datetime.datetime(2026, 7, 1),
            end=datetime.datetime(2026, 7, 27),
        ),
        deploy=PredictionTimeWindow(
            start=datetime.datetime(2026, 7, 27),
            end=datetime.datetime(2026, 8, 3),
        ),
    )

    class FakeAdapter:
        def __init__(self):
            self.loaded_window = None
            self.persisted_profiles = None

        def load_observations(self, window):
            self.loaded_window = window
            return observations

        def replace_profiles(self, *, model_version, profiles):
            self.persisted_profiles = tuple(profiles)
            return CandidateProfileBuildResult(
                model_version=model_version,
                profile_count=len(self.persisted_profiles),
            )

    adapter = FakeAdapter()
    bootstrap_calls = []
    candidate = KalorimetryCalendarBaselineCandidate(
        minimum_slot_samples=1,
        bootstrap_fn=lambda: bootstrap_calls.append("bootstrap"),
    )

    result = candidate.build_profiles(adapter, windows)

    assert candidate.spec.medium_key == "kalorimetry"
    assert candidate.spec.training_window_months == 12
    assert candidate.spec.selection_enabled is True
    assert bootstrap_calls == ["bootstrap"]
    assert adapter.loaded_window is windows.train
    assert len(adapter.persisted_profiles) == KALORIMETRY_BASELINE_PROFILE_POINTS
    assert result.profile_count == KALORIMETRY_BASELINE_PROFILE_POINTS
    assert result.metadata["eligible_identifier_count"] == 1
    assert result.metadata["insufficient_history_identifier_count"] == 0


def test_bootstrap_creates_only_reviewed_prediction_tables_with_checkfirst(
    monkeypatch,
):
    calls = []

    class FakeConnection:
        pass

    connection = FakeConnection()

    class BeginContext:
        def __enter__(self):
            return connection

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeEngine:
        def begin(self):
            return BeginContext()

    from moduly.mereni.kalorimetry.database.models import (
        KalorimetryModelSelectionRun,
        KalorimetryModelValidationMetric,
        KalorimetryModelValidationRun,
        KalorimetryProfilesAnomaly,
        KalorimetryWeatherModelProfile,
    )

    monkeypatch.setattr(
        KalorimetryProfilesAnomaly.__table__,
        "create",
        lambda *, bind, checkfirst: calls.append(
            ("profiles", bind, checkfirst)
        ),
    )
    monkeypatch.setattr(
        KalorimetryModelSelectionRun.__table__,
        "create",
        lambda *, bind, checkfirst: calls.append(
            ("selection", bind, checkfirst)
        ),
    )
    monkeypatch.setattr(
        KalorimetryWeatherModelProfile.__table__,
        "create",
        lambda *, bind, checkfirst: calls.append(
            ("weather", bind, checkfirst)
        ),
    )
    monkeypatch.setattr(
        KalorimetryModelValidationRun.__table__,
        "create",
        lambda *, bind, checkfirst: calls.append(
            ("validation_run", bind, checkfirst)
        ),
    )
    monkeypatch.setattr(
        KalorimetryModelValidationMetric.__table__,
        "create",
        lambda *, bind, checkfirst: calls.append(
            ("validation_metric", bind, checkfirst)
        ),
    )

    ensure_kalorimetry_prediction_tables(FakeEngine())

    assert calls == [
        ("profiles", connection, True),
        ("selection", connection, True),
        ("weather", connection, True),
        ("validation_run", connection, True),
        ("validation_metric", connection, True),
    ]
