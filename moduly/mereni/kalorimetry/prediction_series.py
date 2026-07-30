from __future__ import annotations

import datetime

import pandas as pd


GRANULARITY_FREQUENCIES = {
    "hourly": "h",
    "daily": "D",
    "monthly": "ME",
}


def build_kalorimetry_prediction_series(
    profiles_df: pd.DataFrame,
    *,
    start_date: datetime.date,
    end_date: datetime.date,
    granularity: str,
) -> pd.DataFrame:
    """Build period-valid heat consumption without filling snapshot gaps."""
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date.")
    if granularity not in GRANULARITY_FREQUENCIES:
        raise ValueError("granularity must be one of: hourly, daily, monthly.")

    profiles = _prepare_profiles(profiles_df)
    if profiles.empty:
        return _empty_prediction_frame()

    interval_frames: list[pd.DataFrame] = []
    for target_day in pd.date_range(start=start_date, end=end_date, freq="D"):
        rows = profiles.loc[
            profiles["day_of_week"] == target_day.weekday()
        ].copy()
        if rows.empty:
            continue
        rows["date"] = target_day + pd.to_timedelta(
            rows["slot"] * rows["interval_minutes"],
            unit="m",
        )
        rows = rows.loc[
            (rows["date"] >= rows["valid_from"])
            & (rows["date"] < rows["valid_to"])
        ].copy()
        if rows.empty:
            continue
        rows = (
            rows.sort_values(
                ["date", "valid_from", "selection_run_id", "model_version"],
                ascending=[True, False, False, False],
                na_position="last",
            )
            .drop_duplicates("date", keep="first")
        )
        interval_frames.append(
            rows[["date", "expected_mean", "model_version", "profile_kind"]]
        )

    if not interval_frames:
        return _empty_prediction_frame()
    intervals = pd.concat(interval_frames, ignore_index=True)
    intervals["expected_mean"] = pd.to_numeric(
        intervals["expected_mean"], errors="coerce"
    ).clip(lower=0.0)
    intervals["candidate_interval"] = 1
    intervals["available_interval"] = intervals["expected_mean"].notna().astype(
        int
    )
    prediction = (
        intervals.set_index("date")
        .resample(GRANULARITY_FREQUENCIES[granularity])
        .agg(
            ocekavana_spotreba=(
                "expected_mean",
                lambda values: values.sum(min_count=1),
            ),
            interval_count=("available_interval", "sum"),
            candidate_interval_count=("candidate_interval", "sum"),
            model_versions=(
                "model_version",
                lambda values: tuple(
                    sorted({int(value) for value in values.dropna()})
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
        .dropna(subset=["ocekavana_spotreba"])
    )
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
    ):
        profiles[column] = pd.to_numeric(profiles[column], errors="coerce")
    profiles["profile_kind"] = profiles["profile_kind"].fillna("static").astype(
        str
    )
    profiles["valid_from"] = pd.to_datetime(
        profiles["valid_from"], errors="coerce"
    )
    profiles["valid_to"] = pd.to_datetime(
        profiles["valid_to"], errors="coerce"
    )
    return profiles.dropna(subset=required)


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
