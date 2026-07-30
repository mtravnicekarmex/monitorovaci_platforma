from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from moduly.mereni.kalorimetry.calendar_baseline import (
    KALORIMETRY_BASELINE_INTERVAL_MINUTES,
    KALORIMETRY_BASELINE_MIN_SLOT_SAMPLES,
    KALORIMETRY_BASELINE_PROFILE_POINTS,
    KALORIMETRY_BASELINE_SLOTS_PER_DAY,
    _linear_quantile,
    ensure_kalorimetry_prediction_tables,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_MEDIUM_KEY,
)
from moduly.mereni.prediction import (
    CandidateProfileBuildResult,
    PredictionCandidateSpec,
    PredictionForecastPeriod,
    PredictionObservation,
    PredictionProfilePoint,
    PredictionRebuildWindows,
)


KALORIMETRY_WEATHER_MODEL_VERSION = 2
KALORIMETRY_WEATHER_MODEL_KEY = "calendar_week_slot_hdd"
KALORIMETRY_WEATHER_MODEL_NAME = "Kalorimetry calendar-week slot HDD"
KALORIMETRY_WEATHER_MIN_HDD_VARIANCE = 0.0001
PRAGUE_TIMEZONE = ZoneInfo("Europe/Prague")


@dataclass(frozen=True)
class KalorimetryWeatherProfileCatalog:
    profiles: tuple[PredictionProfilePoint, ...]
    eligible_identifiers: tuple[str, ...]
    insufficient_history_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class KalorimetryWeatherDeployResult:
    available: bool
    profiles: tuple[PredictionProfilePoint, ...]
    missing_weather_hours: tuple[datetime, ...] = ()
    reason: str | None = None


@dataclass(frozen=True)
class KalorimetryWeatherCandidate:
    minimum_slot_samples: int = KALORIMETRY_BASELINE_MIN_SLOT_SAMPLES
    minimum_hdd_variance: float = KALORIMETRY_WEATHER_MIN_HDD_VARIANCE
    bootstrap_fn: Callable[[], None] = ensure_kalorimetry_prediction_tables

    @property
    def spec(self) -> PredictionCandidateSpec:
        return PredictionCandidateSpec(
            medium_key=KALORIMETRY_MEDIUM_KEY,
            model_version=KALORIMETRY_WEATHER_MODEL_VERSION,
            model_key=KALORIMETRY_WEATHER_MODEL_KEY,
            model_name=KALORIMETRY_WEATHER_MODEL_NAME,
            training_window_months=12,
            validation_window_months=1,
            selection_enabled=True,
        )

    def build_profile_catalog(
        self,
        observations: Iterable[PredictionObservation],
    ) -> KalorimetryWeatherProfileCatalog:
        return build_kalorimetry_weather_profile_catalog(
            observations,
            model_version=self.spec.model_version,
            minimum_slot_samples=self.minimum_slot_samples,
            minimum_hdd_variance=self.minimum_hdd_variance,
        )

    def build_profiles(
        self,
        adapter,
        windows: PredictionRebuildWindows,
    ) -> CandidateProfileBuildResult:
        self.bootstrap_fn()
        observations = adapter.load_weather_observations(windows.train)
        catalog = self.build_profile_catalog(observations)
        persisted = adapter.replace_weather_profiles(
            model_version=self.spec.model_version,
            profiles=catalog.profiles,
        )
        return CandidateProfileBuildResult(
            model_version=persisted.model_version,
            profile_count=persisted.profile_count,
            metadata={
                **dict(persisted.metadata),
                "eligible_identifier_count": len(catalog.eligible_identifiers),
                "insufficient_history_identifier_count": len(
                    catalog.insufficient_history_identifiers
                ),
                "expected_profile_points_per_identifier": (
                    KALORIMETRY_BASELINE_PROFILE_POINTS
                ),
                "minimum_slot_samples": self.minimum_slot_samples,
                "minimum_hdd_variance": self.minimum_hdd_variance,
            },
        )

    def predict_validation(
        self,
        adapter,
        *,
        train_window,
        validation_window,
    ):
        from moduly.mereni.prediction import PredictionBacktestPoint

        catalog = self.build_profile_catalog(
            adapter.load_weather_observations(train_window)
        )
        profiles_by_slot = {
            (point.identifier, point.day_of_week, point.slot): point
            for point in catalog.profiles
        }
        weather_validation = adapter.load_weather_observations(
            validation_window
        )
        hdd_by_measurement_id = {
            int(observation.features["measurement_id"]): float(
                observation.features["hdd_24h"]
            )
            for observation in weather_validation
            if observation.features.get("measurement_id") is not None
            and observation.features.get("hdd_24h") is not None
        }
        points = []
        for observation in adapter.load_observations(validation_window):
            profile = profiles_by_slot.get(
                (
                    observation.identifier,
                    observation.day_of_week,
                    observation.slot,
                )
            )
            measurement_id = observation.features.get("measurement_id")
            hdd_24h = (
                hdd_by_measurement_id.get(int(measurement_id))
                if measurement_id is not None
                else None
            )
            predicted_mean = None
            if profile is not None and hdd_24h is not None:
                predicted_mean = max(
                    float(profile.features["base_mean"])
                    + float(profile.features["hdd_slope"]) * hdd_24h,
                    0.0,
                )
            points.append(
                PredictionBacktestPoint(
                    identifier=observation.identifier,
                    timestamp=observation.timestamp,
                    actual_value=observation.actual_value,
                    predicted_mean=predicted_mean,
                )
            )
        return tuple(points)
def build_kalorimetry_weather_profile_catalog(
    observations: Iterable[PredictionObservation],
    *,
    model_version: int = KALORIMETRY_WEATHER_MODEL_VERSION,
    minimum_slot_samples: int = KALORIMETRY_BASELINE_MIN_SLOT_SAMPLES,
    minimum_hdd_variance: float = KALORIMETRY_WEATHER_MIN_HDD_VARIANCE,
) -> KalorimetryWeatherProfileCatalog:
    if minimum_slot_samples <= 0:
        raise ValueError("Minimum weather slot sample count must be positive.")
    if minimum_hdd_variance < 0:
        raise ValueError("Minimum HDD variance must not be negative.")

    values_by_slot: dict[
        tuple[str, int, int],
        list[tuple[float, float]],
    ] = defaultdict(list)
    identifiers: set[str] = set()
    for observation in observations:
        identifier = str(observation.identifier).strip()
        if not identifier:
            continue
        identifiers.add(identifier)
        if observation.interval_minutes != KALORIMETRY_BASELINE_INTERVAL_MINUTES:
            continue
        if not 0 <= observation.day_of_week <= 6:
            continue
        if not 0 <= observation.slot < KALORIMETRY_BASELINE_SLOTS_PER_DAY:
            continue
        actual = _finite_non_negative(observation.actual_value)
        hdd_24h = _finite_non_negative(observation.features.get("hdd_24h"))
        if actual is None or hdd_24h is None:
            continue
        values_by_slot[
            (identifier, observation.day_of_week, observation.slot)
        ].append((actual, hdd_24h))

    profiles: list[PredictionProfilePoint] = []
    eligible: list[str] = []
    insufficient: list[str] = []
    for identifier in sorted(identifiers):
        identifier_profiles: list[PredictionProfilePoint] = []
        complete = True
        for day_of_week in range(7):
            for slot in range(KALORIMETRY_BASELINE_SLOTS_PER_DAY):
                pairs = values_by_slot.get((identifier, day_of_week, slot), ())
                if len(pairs) < minimum_slot_samples:
                    complete = False
                    break
                identifier_profiles.append(
                    _fit_weather_profile_point(
                        identifier=identifier,
                        day_of_week=day_of_week,
                        slot=slot,
                        pairs=pairs,
                        model_version=model_version,
                        minimum_hdd_variance=minimum_hdd_variance,
                    )
                )
            if not complete:
                break
        if not complete:
            insufficient.append(identifier)
            continue
        if len(identifier_profiles) != KALORIMETRY_BASELINE_PROFILE_POINTS:
            raise RuntimeError("Complete weather profile has an invalid size.")
        eligible.append(identifier)
        profiles.extend(identifier_profiles)

    return KalorimetryWeatherProfileCatalog(
        profiles=tuple(profiles),
        eligible_identifiers=tuple(eligible),
        insufficient_history_identifiers=tuple(insufficient),
    )


def build_kalorimetry_weather_deploy_profiles(
    profiles: Sequence[PredictionProfilePoint],
    *,
    forecast_period: PredictionForecastPeriod,
    hdd_24h_by_utc_hour: Mapping[datetime, float],
) -> KalorimetryWeatherDeployResult:
    required_hours = _required_utc_hours(forecast_period)
    normalized_hdd = {
        _normalize_utc_hour(hour): value
        for hour, raw_value in hdd_24h_by_utc_hour.items()
        if (value := _finite_non_negative(raw_value)) is not None
    }
    missing_hours = tuple(
        hour for hour in required_hours if hour not in normalized_hdd
    )
    if missing_hours:
        return KalorimetryWeatherDeployResult(
            available=False,
            profiles=(),
            missing_weather_hours=missing_hours,
            reason="missing_forecast_weather",
        )

    profiles_by_slot = {
        (point.identifier, point.day_of_week, point.slot): point
        for point in profiles
    }
    identifiers = sorted({point.identifier for point in profiles})
    expected_source_count = len(identifiers) * KALORIMETRY_BASELINE_PROFILE_POINTS
    if len(profiles_by_slot) != expected_source_count:
        return KalorimetryWeatherDeployResult(
            available=False,
            profiles=(),
            reason="incomplete_weather_profile",
        )

    deploy_profiles: list[PredictionProfilePoint] = []
    cursor = forecast_period.start
    while cursor < forecast_period.end:
        day_of_week = cursor.weekday()
        slot = (cursor.hour * 60 + cursor.minute) // 15
        weather_hour = _local_prague_to_utc_hour(cursor)
        hdd_24h = normalized_hdd[weather_hour]
        for identifier in identifiers:
            source = profiles_by_slot.get((identifier, day_of_week, slot))
            if source is None:
                return KalorimetryWeatherDeployResult(
                    available=False,
                    profiles=(),
                    reason="incomplete_weather_profile",
                )
            deploy_profiles.append(
                _apply_deploy_hdd(source, hdd_24h)
            )
        cursor += timedelta(minutes=15)

    if len(deploy_profiles) != expected_source_count:
        return KalorimetryWeatherDeployResult(
            available=False,
            profiles=(),
            reason="invalid_forecast_period_shape",
        )
    return KalorimetryWeatherDeployResult(
        available=True,
        profiles=tuple(deploy_profiles),
    )


def weather_profile_point_to_row(
    profile: PredictionProfilePoint,
    *,
    model_version: int = KALORIMETRY_WEATHER_MODEL_VERSION,
) -> dict[str, object]:
    features = profile.features
    required = (
        "base_mean",
        "hdd_slope",
        "hdd_24h_mean",
        "residual_mean",
        "residual_median",
        "residual_p10",
        "residual_p90",
        "residual_std",
    )
    if any(_finite_number(features.get(key)) is None for key in required):
        raise ValueError("Weather profile metadata is incomplete.")
    return {
        "identifikace": profile.identifier,
        "interval_minutes": int(profile.interval_minutes),
        "day_of_week": int(profile.day_of_week),
        "slot": int(profile.slot),
        **{key: float(features[key]) for key in required},
        "model_version": int(model_version),
        "sample_size": int(profile.sample_size),
    }


def _fit_weather_profile_point(
    *,
    identifier: str,
    day_of_week: int,
    slot: int,
    pairs: Sequence[tuple[float, float]],
    model_version: int,
    minimum_hdd_variance: float,
) -> PredictionProfilePoint:
    actual_values = [pair[0] for pair in pairs]
    hdd_values = [pair[1] for pair in pairs]
    actual_mean = statistics.fmean(actual_values)
    hdd_mean = statistics.fmean(hdd_values)
    centered_hdd = [value - hdd_mean for value in hdd_values]
    hdd_sxx = sum(value * value for value in centered_hdd)
    slope = 0.0
    if hdd_sxx >= minimum_hdd_variance:
        slope = max(
            sum(
                centered * (actual - actual_mean)
                for centered, actual in zip(centered_hdd, actual_values)
            )
            / hdd_sxx,
            0.0,
        )
    base_mean = actual_mean - slope * hdd_mean
    residuals = sorted(
        actual - (base_mean + slope * hdd)
        for actual, hdd in pairs
    )
    residual_mean = statistics.fmean(residuals)
    residual_median = statistics.median(residuals)
    residual_p10 = _linear_quantile(residuals, 0.10)
    residual_p90 = _linear_quantile(residuals, 0.90)
    residual_std = max(statistics.pstdev(residuals), 0.0001)
    expected_at_mean = max(base_mean + slope * hdd_mean, 0.0)
    return PredictionProfilePoint(
        identifier=identifier,
        interval_minutes=KALORIMETRY_BASELINE_INTERVAL_MINUTES,
        day_of_week=day_of_week,
        slot=slot,
        expected_mean=expected_at_mean,
        expected_median=max(expected_at_mean + residual_median, 0.0),
        expected_p10=max(expected_at_mean + residual_p10, 0.0),
        expected_p90=max(expected_at_mean + residual_p90, 0.0),
        expected_std=residual_std,
        sample_size=len(pairs),
        model_version=model_version,
        features={
            "profile_kind": "weather_adjusted",
            "base_mean": base_mean,
            "hdd_slope": slope,
            "hdd_24h_mean": hdd_mean,
            "residual_mean": residual_mean,
            "residual_median": residual_median,
            "residual_p10": residual_p10,
            "residual_p90": residual_p90,
            "residual_std": residual_std,
        },
    )


def _apply_deploy_hdd(
    profile: PredictionProfilePoint,
    hdd_24h: float,
) -> PredictionProfilePoint:
    features = dict(profile.features)
    base_mean = float(features["base_mean"])
    slope = float(features["hdd_slope"])
    expected_mean = max(base_mean + slope * hdd_24h, 0.0)
    return PredictionProfilePoint(
        identifier=profile.identifier,
        interval_minutes=profile.interval_minutes,
        day_of_week=profile.day_of_week,
        slot=profile.slot,
        expected_mean=expected_mean,
        expected_median=max(
            expected_mean + float(features["residual_median"]),
            0.0,
        ),
        expected_p10=max(
            expected_mean + float(features["residual_p10"]),
            0.0,
        ),
        expected_p90=max(
            expected_mean + float(features["residual_p90"]),
            0.0,
        ),
        expected_std=max(float(features["residual_std"]), 0.0001),
        sample_size=profile.sample_size,
        model_version=profile.model_version,
        features={**features, "deploy_hdd_24h": hdd_24h},
    )


def _required_utc_hours(
    forecast_period: PredictionForecastPeriod,
) -> tuple[datetime, ...]:
    hours = {
        _local_prague_to_utc_hour(timestamp)
        for timestamp in _iter_quarter_hours(
            forecast_period.start,
            forecast_period.end,
        )
    }
    return tuple(sorted(hours))


def _iter_quarter_hours(start: datetime, end: datetime):
    cursor = start
    while cursor < end:
        yield cursor
        cursor += timedelta(minutes=15)


def _local_prague_to_utc_hour(value: datetime) -> datetime:
    aware = (
        value.replace(tzinfo=PRAGUE_TIMEZONE)
        if value.tzinfo is None
        else value.astimezone(PRAGUE_TIMEZONE)
    )
    return (
        aware.astimezone(UTC)
        .replace(tzinfo=None, minute=0, second=0, microsecond=0)
    )


def _normalize_utc_hour(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(minute=0, second=0, microsecond=0)


def _finite_non_negative(value: object) -> float | None:
    resolved = _finite_number(value)
    return resolved if resolved is not None and resolved >= 0 else None


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None
