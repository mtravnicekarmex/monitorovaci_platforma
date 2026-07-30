from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

import pandas as pd
from sqlalchemy import select

from app.time_utils import prague_now_naive
from core.db.connect import get_session_pg
from moduly.apps.dashboard.time_semantics import local_date_range_to_utc
from moduly.mereni.kalorimetry.database.models import Mereni_kalorimetry
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_MEDIUM_KEY,
)
from moduly.mereni.kalorimetry.prediction_series import (
    build_kalorimetry_prediction_series,
)
from moduly.mereni.prediction.storage import (
    PredictionProfileSnapshot,
    PredictionSelectedModelSnapshot,
    SELECTION_MODE_ACTIVE,
)
from services.api.services.dashboard_auth import (
    DashboardUserContext,
    require_device_access,
    require_section_access,
)


def load_measurement_series(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, object]]:
    _require_device_scope(user_context, identifikace)
    if start_date > end_date:
        raise ValueError("start_date nesmí být později než end_date.")
    start_utc, end_utc = local_date_range_to_utc(start_date, end_date)
    session = get_session_pg()
    try:
        rows = (
            session.execute(
                select(Mereni_kalorimetry)
                .where(
                    Mereni_kalorimetry.identifikace == identifikace,
                    Mereni_kalorimetry.time_utc >= start_utc,
                    Mereni_kalorimetry.time_utc < end_utc,
                )
                .order_by(
                    Mereni_kalorimetry.time_utc,
                    Mereni_kalorimetry.id,
                )
            )
            .scalars()
            .all()
        )
        return [_serialize_measurement(row) for row in rows]
    finally:
        session.close()


def load_prediction_profiles(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
    start_date: date | None = None,
    end_date: date | None = None,
    reference_time: datetime | None = None,
) -> dict[str, object]:
    if (start_date is None) != (end_date is None):
        raise ValueError("start_date a end_date musí být zadány společně.")
    if start_date is not None and start_date > end_date:
        raise ValueError("start_date nesmí být později než end_date.")
    _require_device_scope(user_context, identifikace)
    if start_date is None:
        return _load_current_profiles(
            identifikace,
            reference_time=reference_time or prague_now_naive(),
        )
    return _load_historical_profiles(
        identifikace,
        start_date=start_date,
        end_date=end_date,
    )


def load_prediction_series(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
    start_date: date,
    end_date: date,
    granularity: str,
) -> dict[str, object]:
    _require_device_scope(user_context, identifikace)
    if start_date > end_date:
        raise ValueError("start_date nesmí být později než end_date.")
    profile_result = load_prediction_profiles(
        user_context,
        identifikace=identifikace,
        start_date=start_date,
        end_date=end_date,
    )
    prediction_df = build_kalorimetry_prediction_series(
        pd.DataFrame(profile_result["rows"]),
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
    )
    rows = [
        {
            **row,
            "date": pd.Timestamp(row["date"]).to_pydatetime(),
            "model_versions": list(row["model_versions"]),
            "profile_kinds": list(row["profile_kinds"]),
        }
        for row in prediction_df.to_dict(orient="records")
    ]
    availability_status = str(profile_result["availability_status"])
    availability_reason = profile_result["availability_reason"]
    if profile_result["prediction_available"] and not rows:
        availability_status = "unavailable"
        availability_reason = "missing_profile"
    elif rows and any(not row["prediction_complete"] for row in rows):
        availability_status = "partial"
        availability_reason = "partial_missing_profile"
    return {
        "identifikace": identifikace,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
        "prediction_available": bool(rows),
        "availability_status": availability_status,
        "availability_reason": availability_reason,
        "rows": rows,
    }


def _load_current_profiles(
    identifikace: str,
    *,
    reference_time: datetime,
) -> dict[str, object]:
    session = get_session_pg()
    try:
        decision = (
            session.execute(
                select(PredictionSelectedModelSnapshot)
                .where(
                    PredictionSelectedModelSnapshot.medium_key
                    == KALORIMETRY_MEDIUM_KEY,
                    PredictionSelectedModelSnapshot.selection_mode
                    == SELECTION_MODE_ACTIVE,
                    PredictionSelectedModelSnapshot.identifier
                    == identifikace,
                    PredictionSelectedModelSnapshot.forecast_period_start
                    <= reference_time,
                    PredictionSelectedModelSnapshot.forecast_period_end
                    > reference_time,
                )
                .order_by(
                    PredictionSelectedModelSnapshot.forecast_period_start.desc(),
                    PredictionSelectedModelSnapshot.created_at.desc(),
                    PredictionSelectedModelSnapshot.id.desc(),
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if decision is None:
            return _unavailable(identifikace, "no_selection_snapshot")
        if str(decision.fallback_reason) == "insufficient_history":
            return _unavailable(
                identifikace,
                "insufficient_history",
                decision=decision,
            )
        profiles = _load_profiles_for_period(session, decision)
        if not profiles:
            return _unavailable(
                identifikace,
                "missing_profile",
                decision=decision,
            )
        return _available_current(identifikace, decision, profiles)
    finally:
        session.close()


def _load_historical_profiles(
    identifikace: str,
    *,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    range_start = datetime.combine(start_date, time.min)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min)
    session = get_session_pg()
    try:
        decisions = (
            session.execute(
                select(PredictionSelectedModelSnapshot)
                .where(
                    PredictionSelectedModelSnapshot.medium_key
                    == KALORIMETRY_MEDIUM_KEY,
                    PredictionSelectedModelSnapshot.selection_mode
                    == SELECTION_MODE_ACTIVE,
                    PredictionSelectedModelSnapshot.identifier
                    == identifikace,
                    PredictionSelectedModelSnapshot.forecast_period_start
                    < range_end,
                    PredictionSelectedModelSnapshot.forecast_period_end
                    > range_start,
                )
                .order_by(
                    PredictionSelectedModelSnapshot.forecast_period_start,
                    PredictionSelectedModelSnapshot.created_at.desc(),
                    PredictionSelectedModelSnapshot.id.desc(),
                )
            )
            .scalars()
            .all()
        )
        decisions = _deduplicate_decisions(decisions)
        if not decisions:
            result = _unavailable(identifikace, "no_selection_snapshot")
            result.update(
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "valid_from": range_start,
                    "valid_to": range_end,
                    "availability_periods": [
                        {
                            "prediction_available": False,
                            "availability_reason": "no_selection_snapshot",
                            "selection_run_id": None,
                            "selected_model_version": None,
                            "selected_model_name": None,
                            "valid_from": range_start,
                            "valid_to": range_end,
                        }
                    ],
                }
            )
            return result

        periods = []
        rows = []
        for decision in decisions:
            reason = str(decision.fallback_reason)
            profiles = (
                []
                if reason == "insufficient_history"
                else _load_profiles_for_period(session, decision)
            )
            available = bool(profiles)
            availability_reason = (
                None
                if available
                else (
                    reason
                    if reason == "insufficient_history"
                    else "missing_profile"
                )
            )
            periods.append(
                _availability_period(
                    decision,
                    available=available,
                    reason=availability_reason,
                )
            )
            rows.extend(profiles)
        available_count = sum(row["prediction_available"] for row in periods)
        if available_count == len(periods):
            status, reason = "available", None
        elif available_count:
            status, reason = "partial", "partial_unavailable"
        else:
            reasons = {row["availability_reason"] for row in periods}
            status = "unavailable"
            reason = (
                next(iter(reasons))
                if len(reasons) == 1
                else "multiple_unavailable_reasons"
            )
        return {
            "identifikace": identifikace,
            "prediction_available": available_count > 0,
            "availability_status": status,
            "availability_reason": reason,
            "selection_mode": SELECTION_MODE_ACTIVE,
            "start_date": start_date,
            "end_date": end_date,
            "selection_run_id": None,
            "selected_model_version": None,
            "selected_model_name": None,
            "valid_from": range_start,
            "valid_to": range_end,
            "availability_periods": periods,
            "rows": rows,
        }
    finally:
        session.close()


def _load_profiles_for_period(session, decision) -> list[dict[str, object]]:
    profile_rows = (
        session.execute(
            select(PredictionProfileSnapshot)
            .where(
                PredictionProfileSnapshot.medium_key
                == KALORIMETRY_MEDIUM_KEY,
                PredictionProfileSnapshot.selection_mode
                == SELECTION_MODE_ACTIVE,
                PredictionProfileSnapshot.identifier == decision.identifier,
                PredictionProfileSnapshot.forecast_period_start
                == decision.forecast_period_start,
                PredictionProfileSnapshot.forecast_period_end
                == decision.forecast_period_end,
                PredictionProfileSnapshot.model_version
                == decision.selected_model_version,
            )
            .order_by(
                PredictionProfileSnapshot.archive_version.desc(),
                PredictionProfileSnapshot.created_at.desc(),
                PredictionProfileSnapshot.id.desc(),
            )
        )
        .scalars()
        .all()
    )
    selected = {}
    for row in profile_rows:
        key = (row.interval_minutes, row.day_of_week, row.slot)
        selected.setdefault(key, row)
    return [
        _serialize_profile(row, decision)
        for _, row in sorted(selected.items())
    ]


def _deduplicate_decisions(rows):
    selected = {}
    for row in rows:
        key = (row.forecast_period_start, row.forecast_period_end)
        selected.setdefault(key, row)
    return list(selected.values())


def _available_current(identifikace, decision, rows):
    return {
        "identifikace": identifikace,
        "prediction_available": True,
        "availability_status": "available",
        "availability_reason": None,
        "selection_mode": SELECTION_MODE_ACTIVE,
        "start_date": None,
        "end_date": None,
        "selection_run_id": decision.selection_run_id,
        "selected_model_version": int(decision.selected_model_version),
        "selected_model_name": str(decision.selected_model_name),
        "valid_from": decision.forecast_period_start,
        "valid_to": decision.forecast_period_end,
        "availability_periods": [
            _availability_period(decision, available=True, reason=None)
        ],
        "rows": rows,
    }


def _unavailable(identifikace, reason, *, decision=None):
    return {
        "identifikace": identifikace,
        "prediction_available": False,
        "availability_status": "unavailable",
        "availability_reason": reason,
        "selection_mode": SELECTION_MODE_ACTIVE,
        "start_date": None,
        "end_date": None,
        "selection_run_id": (
            None if decision is None else decision.selection_run_id
        ),
        "selected_model_version": (
            None if decision is None else int(decision.selected_model_version)
        ),
        "selected_model_name": (
            None if decision is None else str(decision.selected_model_name)
        ),
        "valid_from": (
            None if decision is None else decision.forecast_period_start
        ),
        "valid_to": (
            None if decision is None else decision.forecast_period_end
        ),
        "availability_periods": (
            []
            if decision is None
            else [
                _availability_period(
                    decision,
                    available=False,
                    reason=reason,
                )
            ]
        ),
        "rows": [],
    }


def _availability_period(decision, *, available, reason):
    return {
        "prediction_available": available,
        "availability_reason": reason,
        "selection_run_id": decision.selection_run_id,
        "selected_model_version": int(decision.selected_model_version),
        "selected_model_name": str(decision.selected_model_name),
        "valid_from": decision.forecast_period_start,
        "valid_to": decision.forecast_period_end,
    }


def _serialize_profile(row, decision):
    metadata = {}
    if row.metadata_json:
        try:
            parsed = json.loads(str(row.metadata_json))
            if isinstance(parsed, dict):
                metadata = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return {
        "interval_minutes": int(row.interval_minutes),
        "day_of_week": int(row.day_of_week),
        "slot": int(row.slot),
        "expected_mean": float(row.expected_mean),
        "expected_median": _float_or_none(row.expected_median),
        "expected_p10": _float_or_none(row.expected_p10),
        "expected_p90": _float_or_none(row.expected_p90),
        "expected_std": _float_or_none(row.expected_std),
        "sample_size": (
            None if row.sample_size is None else int(row.sample_size)
        ),
        "model_version": int(row.model_version),
        "model_key": row.model_key,
        "profile_kind": str(metadata.get("profile_kind") or "static"),
        "selection_run_id": decision.selection_run_id,
        "valid_from": decision.forecast_period_start,
        "valid_to": decision.forecast_period_end,
    }


def _serialize_measurement(row):
    return {
        "date": row.date,
        "identifikace": str(row.identifikace),
        "seriove_cislo": (
            None if row.seriove_cislo is None else str(row.seriove_cislo)
        ),
        "zdroj": str(row.zdroj),
        "spotreba_energie": float(row.spotreba_energie),
        "objem": _float_or_none(row.objem),
        "delta": _float_or_none(row.delta),
        "platne": bool(row.platne),
        "interval_minutes": int(row.interval_minutes),
        "day_of_week": int(row.day_of_week),
        "slot": int(row.slot),
        "synthetic": bool(row.synthetic),
        "nocni_odber": bool(row.nocni_odber),
        "gap_detected": bool(row.gap_detected),
        "reset_detected": bool(row.reset_detected),
        "source_date": row.source_date,
        "time_utc": row.time_utc,
        "time_basis": row.time_basis,
        "source_timezone": row.source_timezone,
        "source_utc_offset_minutes": row.source_utc_offset_minutes,
        "time_fold": row.time_fold,
        "timestamp_position": row.timestamp_position,
    }


def _require_device_scope(user_context, identifikace):
    require_section_access(user_context, "kalorimetry")
    require_device_access(user_context, identifikace)


def _float_or_none(value):
    return None if value is None else float(value)
