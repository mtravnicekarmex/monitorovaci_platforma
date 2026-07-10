import datetime

from moduly.mereni.elektromery.elektromery_prediction import (
    MODEL_VERSION_RECENT_AVERAGE,
    MODEL_VERSION_SAME_MONTH_LAST_YEAR,
    MODEL_VERSION_TWELVE_MONTH_MEDIAN,
    build_monthly_rebuild_windows,
    build_next_month_forecast_period,
    get_candidate_model_specs,
    get_candidate_model_versions,
    run_monthly_candidate_backtests,
    select_best_backtested_candidate,
)
from moduly.mereni.elektromery.prediction_adapter import ElektromeryMonthlyConsumption
from moduly.mereni.prediction import PredictionTimeWindow


def test_elektromery_candidate_model_specs_use_monthly_next_month_contract():
    specs = get_candidate_model_specs()

    assert get_candidate_model_versions() == (
        MODEL_VERSION_RECENT_AVERAGE,
        MODEL_VERSION_TWELVE_MONTH_MEDIAN,
        MODEL_VERSION_SAME_MONTH_LAST_YEAR,
    )
    assert [spec.medium_key for spec in specs] == ["elektromery", "elektromery", "elektromery"]
    assert [spec.model_key for spec in specs] == [
        "recent_3_month_average",
        "twelve_month_median",
        "same_month_last_year",
    ]
    assert [spec.training_window_months for spec in specs] == [3, 12, 12]
    assert all(spec.validation_window_months == 1 for spec in specs)
    assert all(spec.selection_enabled for spec in specs)


def test_build_next_month_forecast_period_uses_calendar_month_after_reference():
    period = build_next_month_forecast_period(
        reference_time=datetime.datetime(2026, 7, 15, 9, 30),
    )

    assert period.start == datetime.datetime(2026, 8, 1)
    assert period.end == datetime.datetime(2026, 9, 1)
    assert period.label == "2026-08"


def test_build_monthly_rebuild_windows_uses_previous_completed_calendar_month():
    spec = get_candidate_model_specs()[0]

    windows = build_monthly_rebuild_windows(
        reference_time=datetime.datetime(2026, 7, 15, 9, 30),
        spec=spec,
    )

    assert windows.validation.start == datetime.datetime(2026, 6, 1)
    assert windows.validation.end == datetime.datetime(2026, 7, 1)
    assert windows.train.end == datetime.datetime(2026, 6, 1)
    assert windows.train.start == datetime.datetime(2026, 3, 1)
    assert windows.deploy.end == datetime.datetime(2026, 7, 1)


def test_elektromery_monthly_backtests_run_candidates_on_synthetic_data():
    adapter = SyntheticMonthlyAdapter(
        rows=(
            _row("E1", 2025, 6, 80.0),
            _row("E1", 2026, 1, 10.0),
            _row("E1", 2026, 2, 20.0),
            _row("E1", 2026, 3, 30.0),
            _row("E1", 2026, 4, 25.0),
            _row("E1", 2026, 5, 35.0),
            _row("E1", 2026, 6, 40.0),
        )
    )

    results = run_monthly_candidate_backtests(
        adapter=adapter,
        reference_time=datetime.datetime(2026, 7, 15, 9, 30),
        fold_count=2,
    )

    assert [result.spec.model_version for result in results] == [1, 2, 3]
    recent_average = results[0]
    assert recent_average.metrics.validation_total_count == 2
    assert recent_average.metrics.matched_validation_count == 2
    assert recent_average.metrics.coverage == 1.0
    selected = select_best_backtested_candidate(results)
    assert selected is not None
    assert selected.spec.model_version in {1, 2, 3}


class SyntheticMonthlyAdapter:
    medium_key = "elektromery"

    def __init__(self, rows: tuple[ElektromeryMonthlyConsumption, ...]) -> None:
        self._rows = rows

    def load_monthly_consumption(
        self,
        window: PredictionTimeWindow,
        *,
        identifiers=None,
    ) -> tuple[ElektromeryMonthlyConsumption, ...]:
        del identifiers
        return tuple(
            row for row in self._rows if window.start <= row.month_start < window.end
        )


def _row(
    identifier: str,
    year: int,
    month: int,
    consumption_kwh: float,
) -> ElektromeryMonthlyConsumption:
    return ElektromeryMonthlyConsumption(
        identifier=identifier,
        month_start=datetime.datetime(year, month, 1),
        consumption_kwh=consumption_kwh,
        measurement_count=1,
        selected_source_kind="detailed",
        source_names=("BINARY_TEST",),
    )
