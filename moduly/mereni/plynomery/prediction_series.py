from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pandas as pd


PRAGUE_TIMEZONE = ZoneInfo("Europe/Prague")
GRANULARITY_FREQUENCIES = {
    "hourly": "h",
    "daily": "D",
    "monthly": "ME",
}


def build_plynomery_prediction_series(
    profiles_df: pd.DataFrame,
    *,
    start_date: datetime.date,
    end_date: datetime.date,
    granularity: str,
    weather_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a period-valid gas prediction without inventing missing values."""
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")
    if granularity not in GRANULARITY_FREQUENCIES:
        raise ValueError(
            "granularity must be one of: hourly, daily, monthly."
        )

    empty_result = _empty_prediction_frame()
    profiles = _prepare_profiles(profiles_df)
    if profiles.empty:
        return empty_result

    hdd_24h_by_hour = _build_hdd_24h_lookup(weather_df)
    interval_frames: list[pd.DataFrame] = []
    for target_day in pd.date_range(start=start_date, end=end_date, freq="D"):
        day_profiles = profiles.loc[
            profiles["day_of_week"] == target_day.weekday()
        ].copy()
        if day_profiles.empty:
            continue
        day_profiles["date"] = target_day + pd.to_timedelta(
            day_profiles["slot"] * day_profiles["interval_minutes"],
            unit="m",
        )
        day_profiles = day_profiles.loc[
            (day_profiles["date"] >= day_profiles["valid_from"])
            & (day_profiles["date"] < day_profiles["valid_to"])
        ].copy()
        if day_profiles.empty:
            continue

        day_profiles = (
            day_profiles.sort_values(
                [
                    "date",
                    "valid_from",
                    "selection_run_id",
                    "valid_to",
                    "model_version",
                ],
                ascending=[True, False, False, False, False],
                na_position="last",
            )
            .drop_duplicates("date", keep="first")
        )
        day_profiles["hdd_24h"] = day_profiles["date"].map(
            lambda value: hdd_24h_by_hour.get(
                _local_prague_to_utc_hour(value)
            )
        )
        static_mask = day_profiles["profile_kind"] != "weather_adjusted"
        weather_mask = (
            ~static_mask
            & day_profiles["base_mean"].notna()
            & day_profiles["hdd_slope"].notna()
            & day_profiles["hdd_24h"].notna()
        )
        day_profiles["expected_value"] = pd.NA
        day_profiles.loc[static_mask, "expected_value"] = day_profiles.loc[
            static_mask, "expected_mean"
        ]
        day_profiles.loc[weather_mask, "expected_value"] = (
            day_profiles.loc[weather_mask, "base_mean"]
            + day_profiles.loc[weather_mask, "hdd_slope"]
            * day_profiles.loc[weather_mask, "hdd_24h"]
        )
        interval_frames.append(
            day_profiles[
                [
                    "date",
                    "expected_value",
                    "model_version",
                    "profile_kind",
                ]
            ]
        )

    if not interval_frames:
        return empty_result

    intervals = pd.concat(interval_frames, ignore_index=True)
    intervals["expected_value"] = pd.to_numeric(
        intervals["expected_value"], errors="coerce"
    )
    intervals["expected_value"] = intervals["expected_value"].clip(lower=0.0)
    intervals = intervals.dropna(subset=["date"])
    if intervals.empty:
        return empty_result
    intervals["candidate_interval"] = 1
    intervals["available_interval"] = intervals["expected_value"].notna().astype(
        int
    )

    frequency = GRANULARITY_FREQUENCIES[granularity]
    prediction = (
        intervals.set_index("date")
        .resample(frequency)
        .agg(
            ocekavana_spotreba=(
                "expected_value",
                lambda values: values.sum(min_count=1),
            ),
            interval_count=("available_interval", "sum"),
            candidate_interval_count=("candidate_interval", "sum"),
            model_versions=(
                "model_version",
                lambda values: tuple(
                    sorted(
                        {
                            int(value)
                            for value in values.dropna()
                        }
                    )
                ),
            ),
            profile_kinds=(
                "profile_kind",
                lambda values: tuple(
                    sorted({str(value) for value in values.dropna()})
                ),
            ),
        )
        .reset_index()
    )
    prediction = prediction.dropna(subset=["ocekavana_spotreba"]).copy()
    prediction["prediction_complete"] = (
        prediction["interval_count"]
        == prediction["candidate_interval_count"]
    )
    prediction["ocekavana_spotreba"] = prediction[
        "ocekavana_spotreba"
    ].round(3)
    prediction["ocekavana_kumulovana_spotreba"] = prediction[
        "ocekavana_spotreba"
    ].cumsum().round(3)
    return prediction.reset_index(drop=True)


def _prepare_profiles(profiles_df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "interval_minutes",
        "day_of_week",
        "slot",
        "expected_mean",
        "model_version",
        "profile_kind",
        "valid_from",
        "valid_to",
    }
    if profiles_df.empty or not required.issubset(profiles_df.columns):
        return pd.DataFrame()

    profiles = profiles_df.copy()
    profiles["selection_run_id"] = pd.to_numeric(
        profiles.get("selection_run_id"), errors="coerce"
    )
    for column in (
        "interval_minutes",
        "day_of_week",
        "slot",
        "expected_mean",
        "model_version",
        "base_mean",
        "hdd_slope",
    ):
        if column not in profiles:
            profiles[column] = pd.NA
        profiles[column] = pd.to_numeric(profiles[column], errors="coerce")
    profiles["profile_kind"] = (
        profiles["profile_kind"].fillna("static").astype(str)
    )
    profiles["valid_from"] = pd.to_datetime(
        profiles["valid_from"], errors="coerce"
    )
    profiles["valid_to"] = pd.to_datetime(
        profiles["valid_to"], errors="coerce"
    )
    return profiles.dropna(
        subset=[
            "interval_minutes",
            "day_of_week",
            "slot",
            "expected_mean",
            "model_version",
            "valid_from",
            "valid_to",
        ]
    )


def _build_hdd_24h_lookup(
    weather_df: pd.DataFrame | None,
) -> dict[datetime.datetime, float]:
    if weather_df is None or weather_df.empty:
        return {}
    if "datetime_hour" not in weather_df.columns:
        return {}

    weather = weather_df.copy()
    weather["datetime_hour"] = pd.to_datetime(
        weather["datetime_hour"], errors="coerce", utc=True
    ).dt.tz_localize(None).dt.floor("h")
    weather = weather.dropna(subset=["datetime_hour"])
    if weather.empty:
        return {}

    if "hdd_24h" in weather.columns:
        weather["hdd_24h"] = pd.to_numeric(
            weather["hdd_24h"], errors="coerce"
        )
    elif "heating_degree_hours" in weather.columns:
        weather["heating_degree_hours"] = pd.to_numeric(
            weather["heating_degree_hours"], errors="coerce"
        )
        weather = weather.drop_duplicates(
            "datetime_hour", keep="last"
        ).sort_values("datetime_hour")
        indexed = weather.set_index("datetime_hour")
        weather["hdd_24h"] = indexed["heating_degree_hours"].rolling(
            "24h", min_periods=1
        ).mean().to_numpy()
    else:
        return {}

    return {
        timestamp.to_pydatetime(): float(hdd_24h)
        for timestamp, hdd_24h in weather[
            ["datetime_hour", "hdd_24h"]
        ].itertuples(index=False, name=None)
        if pd.notna(hdd_24h)
    }


def _local_prague_to_utc_hour(value: object) -> datetime.datetime:
    timestamp = pd.Timestamp(value)
    local_value = timestamp.to_pydatetime()
    if local_value.tzinfo is None:
        local_value = local_value.replace(tzinfo=PRAGUE_TIMEZONE)
    else:
        local_value = local_value.astimezone(PRAGUE_TIMEZONE)
    return (
        local_value.astimezone(datetime.UTC)
        .replace(tzinfo=None, minute=0, second=0, microsecond=0)
    )


def _empty_prediction_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "date",
            "ocekavana_spotreba",
            "interval_count",
            "candidate_interval_count",
            "prediction_complete",
            "model_versions",
            "profile_kinds",
            "ocekavana_kumulovana_spotreba",
        ]
    )
