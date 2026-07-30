from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

import pandas as pd
from sqlalchemy import text

from app.time_utils import prague_now_naive, utc_now_naive
from core.db.connect import get_session_pg
from moduly.apps.dashboard.time_semantics import local_date_range_to_utc
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    PlynomeryAnomalyEvent,
    PlynomeryAnomalyScore,
)
from moduly.mereni.plynomery.plynomery_prediction import get_runtime_model_version
from moduly.mereni.plynomery.prediction_series import (
    build_plynomery_prediction_series,
)
from services.api.services.dashboard_auth import (
    DashboardUserContext,
    require_device_access,
    require_section_access,
)


MIN_VISIBLE_EVENT_DURATION_MINUTES = 120


def _build_datetime_range(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    return start_dt, end_dt


def _get_active_model_version(*, session=None) -> int:
    return get_runtime_model_version(session=session, default=1)


def list_accessible_devices(
    user_context: DashboardUserContext,
    *,
    limit: int = 500,
) -> list[str]:
    require_section_access(user_context, "plynomery")

    session = get_session_pg()
    try:
        query = session.query(Mereni_plynomery.identifikace).distinct()
        if not user_context.is_admin:
            query = query.filter(Mereni_plynomery.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(Mereni_plynomery.identifikace).limit(limit).all()
        return [str(row[0]) for row in rows if row[0]]
    finally:
        session.close()


def load_measurement_series(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, object]]:
    require_section_access(user_context, "plynomery")
    require_device_access(user_context, identifikace)
    if start_date > end_date:
        raise ValueError("start_date nesmí být později než end_date.")

    start_utc, end_utc = local_date_range_to_utc(start_date, end_date)
    session = get_session_pg()
    try:
        rows = (
            session.query(
                Mereni_plynomery.date,
                Mereni_plynomery.identifikace,
                Mereni_plynomery.seriove_cislo,
                Mereni_plynomery.zdroj,
                Mereni_plynomery.objem,
                Mereni_plynomery.delta,
                Mereni_plynomery.platne,
                Mereni_plynomery.interval_minutes,
                Mereni_plynomery.day_of_week,
                Mereni_plynomery.slot,
                Mereni_plynomery.synthetic,
                Mereni_plynomery.nocni_odber,
                Mereni_plynomery.gap_detected,
                Mereni_plynomery.reset_detected,
                Mereni_plynomery.source_date,
                Mereni_plynomery.time_utc,
                Mereni_plynomery.time_basis,
                Mereni_plynomery.source_timezone,
                Mereni_plynomery.source_utc_offset_minutes,
                Mereni_plynomery.time_fold,
                Mereni_plynomery.timestamp_position,
            )
            .filter(
                Mereni_plynomery.identifikace == identifikace,
                Mereni_plynomery.time_utc >= start_utc,
                Mereni_plynomery.time_utc < end_utc,
            )
            .order_by(
                Mereni_plynomery.time_utc.asc(),
                Mereni_plynomery.id.asc(),
            )
            .all()
        )
        return [
            {
                "date": row.date,
                "identifikace": str(row.identifikace),
                "seriove_cislo": (
                    None
                    if row.seriove_cislo is None
                    else str(row.seriove_cislo)
                ),
                "zdroj": str(row.zdroj),
                "objem": float(row.objem),
                "delta": None if row.delta is None else float(row.delta),
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
            for row in rows
        ]
    finally:
        session.close()


def load_current_prediction_profiles(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
    reference_time: datetime | None = None,
) -> dict[str, object]:
    require_section_access(user_context, "plynomery")
    require_device_access(user_context, identifikace)
    current_time = reference_time or prague_now_naive()

    session = get_session_pg()
    try:
        decision = (
            session.execute(
                text(
                    """
                    /* plynomery:current_prediction_decision */
                    SELECT
                        selection_run_id,
                        selected_model_version,
                        selected_model_name,
                        fallback_reason,
                        forecast_period_start,
                        forecast_period_end
                    FROM monitoring.prediction_selected_model_snapshots
                    WHERE medium_key = 'plynomery'
                      AND selection_mode = 'active'
                      AND identifier = :identifikace
                      AND forecast_period_start <= :current_time
                      AND forecast_period_end > :current_time
                    ORDER BY
                        forecast_period_start DESC,
                        created_at DESC,
                        id DESC
                    LIMIT 1
                    """
                ),
                {
                    "identifikace": identifikace,
                    "current_time": current_time,
                },
            )
            .mappings()
            .first()
        )
        if decision is None:
            return _unavailable_prediction_profile_result(
                identifikace,
                reason="no_selection_snapshot",
            )

        fallback_reason = str(decision["fallback_reason"])
        if fallback_reason == "insufficient_history":
            return _unavailable_prediction_profile_result(
                identifikace,
                reason=fallback_reason,
                decision=decision,
            )

        profile_rows = (
            session.execute(
                text(
                    """
                    /* plynomery:current_prediction_profiles */
                    SELECT
                        interval_minutes,
                        day_of_week,
                        slot,
                        expected_mean,
                        expected_median,
                        expected_p10,
                        expected_p90,
                        expected_std,
                        sample_size,
                        model_version,
                        model_key,
                        metadata_json
                    FROM monitoring.prediction_profile_snapshots
                    WHERE medium_key = 'plynomery'
                      AND selection_mode = 'active'
                      AND identifier = :identifikace
                      AND selection_run_id IS NOT DISTINCT FROM :selection_run_id
                      AND model_version = :model_version
                      AND forecast_period_start = :valid_from
                      AND forecast_period_end = :valid_to
                    ORDER BY day_of_week, slot, interval_minutes, id
                    """
                ),
                {
                    "identifikace": identifikace,
                    "selection_run_id": decision["selection_run_id"],
                    "model_version": decision["selected_model_version"],
                    "valid_from": decision["forecast_period_start"],
                    "valid_to": decision["forecast_period_end"],
                },
            )
            .mappings()
            .all()
        )
        rows = [_serialize_prediction_profile_row(row) for row in profile_rows]
        if not rows:
            return _unavailable_prediction_profile_result(
                identifikace,
                reason="missing_profile",
                decision=decision,
            )
        for row in rows:
            row.update(
                {
                    "selection_run_id": decision["selection_run_id"],
                    "valid_from": decision["forecast_period_start"],
                    "valid_to": decision["forecast_period_end"],
                }
            )
        return {
            "identifikace": identifikace,
            "prediction_available": True,
            "availability_status": "available",
            "availability_reason": None,
            "selection_mode": "active",
            "start_date": None,
            "end_date": None,
            "selection_run_id": decision["selection_run_id"],
            "selected_model_version": int(
                decision["selected_model_version"]
            ),
            "selected_model_name": str(decision["selected_model_name"]),
            "valid_from": decision["forecast_period_start"],
            "valid_to": decision["forecast_period_end"],
            "availability_periods": [
                _serialize_availability_period(
                    decision,
                    prediction_available=True,
                    availability_reason=None,
                )
            ],
            "rows": rows,
        }
    finally:
        session.close()


def _unavailable_prediction_profile_result(
    identifikace: str,
    *,
    reason: str,
    decision=None,
) -> dict[str, object]:
    return {
        "identifikace": identifikace,
        "prediction_available": False,
        "availability_status": "unavailable",
        "availability_reason": reason,
        "selection_mode": "active",
        "start_date": None,
        "end_date": None,
        "selection_run_id": (
            None if decision is None else decision["selection_run_id"]
        ),
        "selected_model_version": (
            None
            if decision is None
            else int(decision["selected_model_version"])
        ),
        "selected_model_name": (
            None if decision is None else str(decision["selected_model_name"])
        ),
        "valid_from": (
            None if decision is None else decision["forecast_period_start"]
        ),
        "valid_to": (
            None if decision is None else decision["forecast_period_end"]
        ),
        "availability_periods": (
            []
            if decision is None
            else [
                _serialize_availability_period(
                    decision,
                    prediction_available=False,
                    availability_reason=reason,
                )
            ]
        ),
        "rows": [],
    }


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
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date nesmí být později než end_date.")
    if start_date is None:
        return load_current_prediction_profiles(
            user_context,
            identifikace=identifikace,
            reference_time=reference_time,
        )

    require_section_access(user_context, "plynomery")
    require_device_access(user_context, identifikace)
    return _load_historical_prediction_profiles(
        identifikace=identifikace,
        start_date=start_date,
        end_date=end_date,
    )


def _load_historical_prediction_profiles(
    *,
    identifikace: str,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    range_start = datetime.combine(start_date, time.min)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min)
    session = get_session_pg()
    try:
        decisions = (
            session.execute(
                text(
                    """
                    /* plynomery:historical_prediction_decisions */
                    SELECT
                        selection_run_id,
                        selected_model_version,
                        selected_model_name,
                        fallback_reason,
                        forecast_period_start,
                        forecast_period_end,
                        created_at,
                        id
                    FROM monitoring.prediction_selected_model_snapshots
                    WHERE medium_key = 'plynomery'
                      AND selection_mode = 'active'
                      AND identifier = :identifikace
                      AND forecast_period_start < :range_end
                      AND forecast_period_end > :range_start
                    ORDER BY
                        forecast_period_start ASC,
                        created_at DESC,
                        id DESC
                    """
                ),
                {
                    "identifikace": identifikace,
                    "range_start": range_start,
                    "range_end": range_end,
                },
            )
            .mappings()
            .all()
        )
        if not decisions:
            return {
                "identifikace": identifikace,
                "prediction_available": False,
                "availability_status": "unavailable",
                "availability_reason": "no_selection_snapshot",
                "selection_mode": "active",
                "start_date": start_date,
                "end_date": end_date,
                "selection_run_id": None,
                "selected_model_version": None,
                "selected_model_name": None,
                "valid_from": None,
                "valid_to": None,
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
                "rows": [],
            }

        profile_rows = (
            session.execute(
                text(
                    """
                    /* plynomery:historical_prediction_profiles */
                    SELECT
                        selection_run_id,
                        forecast_period_start,
                        forecast_period_end,
                        interval_minutes,
                        day_of_week,
                        slot,
                        expected_mean,
                        expected_median,
                        expected_p10,
                        expected_p90,
                        expected_std,
                        sample_size,
                        model_version,
                        model_key,
                        metadata_json
                    FROM monitoring.prediction_profile_snapshots
                    WHERE medium_key = 'plynomery'
                      AND selection_mode = 'active'
                      AND identifier = :identifikace
                      AND forecast_period_start < :range_end
                      AND forecast_period_end > :range_start
                    ORDER BY
                        forecast_period_start ASC,
                        day_of_week,
                        slot,
                        interval_minutes,
                        id
                    """
                ),
                {
                    "identifikace": identifikace,
                    "range_start": range_start,
                    "range_end": range_end,
                },
            )
            .mappings()
            .all()
        )
        profiles_by_decision: dict[tuple[object, ...], list[dict[str, object]]] = {}
        for profile_row in profile_rows:
            key = (
                profile_row["selection_run_id"],
                int(profile_row["model_version"]),
                profile_row["forecast_period_start"],
                profile_row["forecast_period_end"],
            )
            serialized = _serialize_prediction_profile_row(profile_row)
            serialized.update(
                {
                    "selection_run_id": profile_row["selection_run_id"],
                    "valid_from": profile_row["forecast_period_start"],
                    "valid_to": profile_row["forecast_period_end"],
                }
            )
            profiles_by_decision.setdefault(key, []).append(serialized)

        availability_periods = []
        result_rows = []
        for decision in decisions:
            key = (
                decision["selection_run_id"],
                int(decision["selected_model_version"]),
                decision["forecast_period_start"],
                decision["forecast_period_end"],
            )
            decision_profiles = profiles_by_decision.get(key, [])
            reason = str(decision["fallback_reason"])
            if reason == "insufficient_history":
                available = False
                availability_reason = reason
            elif not decision_profiles:
                available = False
                availability_reason = "missing_profile"
            else:
                available = True
                availability_reason = None
                result_rows.extend(decision_profiles)
            availability_periods.append(
                _serialize_availability_period(
                    decision,
                    prediction_available=available,
                    availability_reason=availability_reason,
                )
            )

        available_count = sum(
            1 for period in availability_periods
            if period["prediction_available"]
        )
        if available_count == len(availability_periods):
            availability_status = "available"
            availability_reason = None
        elif available_count:
            availability_status = "partial"
            availability_reason = "partial_unavailable"
        else:
            availability_status = "unavailable"
            reasons = {
                str(period["availability_reason"])
                for period in availability_periods
            }
            availability_reason = (
                next(iter(reasons))
                if len(reasons) == 1
                else "multiple_unavailable_reasons"
            )
        return {
            "identifikace": identifikace,
            "prediction_available": available_count > 0,
            "availability_status": availability_status,
            "availability_reason": availability_reason,
            "selection_mode": "active",
            "start_date": start_date,
            "end_date": end_date,
            "selection_run_id": None,
            "selected_model_version": None,
            "selected_model_name": None,
            "valid_from": range_start,
            "valid_to": range_end,
            "availability_periods": availability_periods,
            "rows": result_rows,
        }
    finally:
        session.close()


def _serialize_availability_period(
    decision,
    *,
    prediction_available: bool,
    availability_reason: str | None,
) -> dict[str, object]:
    return {
        "prediction_available": prediction_available,
        "availability_reason": availability_reason,
        "selection_run_id": decision["selection_run_id"],
        "selected_model_version": int(decision["selected_model_version"]),
        "selected_model_name": str(decision["selected_model_name"]),
        "valid_from": decision["forecast_period_start"],
        "valid_to": decision["forecast_period_end"],
    }


def _serialize_prediction_profile_row(row) -> dict[str, object]:
    metadata = {}
    if row.get("metadata_json"):
        try:
            parsed = json.loads(str(row["metadata_json"]))
            if isinstance(parsed, dict):
                metadata = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
    return {
        "interval_minutes": int(row["interval_minutes"]),
        "day_of_week": int(row["day_of_week"]),
        "slot": int(row["slot"]),
        "expected_mean": float(row["expected_mean"]),
        "expected_median": _optional_float(row.get("expected_median")),
        "expected_p10": _optional_float(row.get("expected_p10")),
        "expected_p90": _optional_float(row.get("expected_p90")),
        "expected_std": _optional_float(row.get("expected_std")),
        "sample_size": (
            None if row.get("sample_size") is None else int(row["sample_size"])
        ),
        "model_version": int(row["model_version"]),
        "model_key": row.get("model_key"),
        "profile_kind": str(metadata.get("profile_kind") or "static"),
        "base_mean": _optional_float(metadata.get("base_mean")),
        "hdd_slope": _optional_float(metadata.get("hdd_slope")),
        "hdd_24h_mean": _optional_float(metadata.get("hdd_24h_mean")),
    }


def _optional_float(value) -> float | None:
    return None if value is None else float(value)


def load_prediction_series(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
    start_date: date,
    end_date: date,
    granularity: str,
) -> dict[str, object]:
    require_section_access(user_context, "plynomery")
    require_device_access(user_context, identifikace)
    if start_date > end_date:
        raise ValueError("start_date nesmĂ­ bĂ˝t pozdÄ›ji neĹľ end_date.")

    profile_result = load_prediction_profiles(
        user_context,
        identifikace=identifikace,
        start_date=start_date,
        end_date=end_date,
    )
    profiles_df = pd.DataFrame(profile_result["rows"])
    weather_df = _load_prediction_weather(
        start_date=start_date,
        end_date=end_date,
    )
    prediction_df = build_plynomery_prediction_series(
        profiles_df,
        weather_df=weather_df,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
    )
    rows = []
    for row in prediction_df.to_dict(orient="records"):
        rows.append(
            {
                **row,
                "date": pd.Timestamp(row["date"]).to_pydatetime(),
                "model_versions": list(row["model_versions"]),
                "profile_kinds": list(row["profile_kinds"]),
            }
        )

    availability_status = str(profile_result["availability_status"])
    availability_reason = profile_result["availability_reason"]
    if profile_result["prediction_available"] and not rows:
        availability_status = "unavailable"
        availability_reason = "missing_weather_or_profile"
    elif rows and any(not row["prediction_complete"] for row in rows):
        availability_status = "partial"
        availability_reason = "partial_missing_weather_or_profile"
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


def _load_prediction_weather(
    *,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    range_start, range_end = local_date_range_to_utc(start_date, end_date)
    weather_start = range_start - timedelta(hours=23)
    session = get_session_pg()
    try:
        forecast_rows = (
            session.execute(
                text(
                    """
                    SELECT DISTINCT ON (datetime_hour)
                           datetime_hour, heating_degree_hours
                    FROM monitoring.meteo_forecast_hourly
                    WHERE datetime_hour >= :weather_start
                      AND datetime_hour < :range_end
                    ORDER BY datetime_hour, forecast_run_at DESC
                    """
                ),
                {
                    "weather_start": weather_start,
                    "range_end": range_end,
                },
            )
            .mappings()
            .all()
        )
        historical_rows = (
            session.execute(
                text(
                    """
                    SELECT datetime_hour, heating_degree_hours
                    FROM monitoring.meteo_hourly
                    WHERE datetime_hour >= :weather_start
                      AND datetime_hour < :range_end
                    ORDER BY datetime_hour
                    """
                ),
                {
                    "weather_start": weather_start,
                    "range_end": range_end,
                },
            )
            .mappings()
            .all()
        )
        return pd.DataFrame([*forecast_rows, *historical_rows])
    finally:
        session.close()


def load_recent_anomalies(
    user_context: DashboardUserContext,
    *,
    identifikace: str | None,
    start_date: date,
    end_date: date,
    limit: int = 50,
) -> list[dict[str, object]]:
    require_section_access(user_context, "plynomery")
    start_dt, end_dt = _build_datetime_range(start_date, end_date)
    if identifikace:
        require_device_access(user_context, identifikace)

    session = get_session_pg()
    try:
        active_model_version = _get_active_model_version(session=session)
        query = (
            session.query(
                PlynomeryAnomalyScore.date,
                PlynomeryAnomalyScore.identifikace,
                PlynomeryAnomalyScore.actual_value,
                PlynomeryAnomalyScore.expected_mean,
                PlynomeryAnomalyScore.z_score,
                PlynomeryAnomalyScore.severity,
                PlynomeryAnomalyScore.is_anomaly,
            )
            .filter(PlynomeryAnomalyScore.model_version == active_model_version)
            .filter(PlynomeryAnomalyScore.is_anomaly.is_(True))
            .filter(PlynomeryAnomalyScore.date >= start_dt, PlynomeryAnomalyScore.date <= end_dt)
        )
        if not user_context.is_admin:
            query = query.filter(PlynomeryAnomalyScore.identifikace.in_(user_context.allowed_devices))
        if identifikace:
            query = query.filter(PlynomeryAnomalyScore.identifikace == identifikace)

        rows = query.order_by(PlynomeryAnomalyScore.date.desc()).limit(limit).all()
        return [
            {
                "date": row.date,
                "identifikace": str(row.identifikace),
                "actual_value": float(row.actual_value),
                "expected_mean": float(row.expected_mean),
                "z_score": float(row.z_score),
                "severity": str(row.severity) if row.severity is not None else None,
                "is_anomaly": bool(row.is_anomaly),
            }
            for row in rows
        ]
    finally:
        session.close()


def load_all_open_events(
    user_context: DashboardUserContext,
    *,
    limit: int = 500,
) -> list[dict[str, object]]:
    require_section_access(user_context, "plynomery")

    session = get_session_pg()
    try:
        active_model_version = _get_active_model_version(session=session)
        query = session.query(
            PlynomeryAnomalyEvent.identifikace,
            PlynomeryAnomalyEvent.event_type,
            PlynomeryAnomalyEvent.start_time,
            PlynomeryAnomalyEvent.end_time,
            PlynomeryAnomalyEvent.duration_minutes,
            PlynomeryAnomalyEvent.max_z_score,
            PlynomeryAnomalyEvent.avg_z_score,
            PlynomeryAnomalyEvent.severity,
        ).filter(
            PlynomeryAnomalyEvent.model_version == active_model_version,
            PlynomeryAnomalyEvent.end_time.is_(None),
            PlynomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES,
        )
        if not user_context.is_admin:
            query = query.filter(PlynomeryAnomalyEvent.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(
            PlynomeryAnomalyEvent.severity.asc(),
            PlynomeryAnomalyEvent.duration_minutes.desc(),
            PlynomeryAnomalyEvent.start_time.desc(),
        ).limit(limit).all()
        return [
            {
                "identifikace": str(row.identifikace),
                "event_type": str(row.event_type),
                "start_time": row.start_time,
                "end_time": row.end_time,
                "duration_minutes": int(row.duration_minutes),
                "max_z_score": float(row.max_z_score),
                "avg_z_score": float(row.avg_z_score),
                "severity": str(row.severity),
            }
            for row in rows
        ]
    finally:
        session.close()


def load_recent_resolved_events(
    user_context: DashboardUserContext,
    *,
    days: int = 7,
    limit: int = 500,
) -> list[dict[str, object]]:
    require_section_access(user_context, "plynomery")
    resolved_since = utc_now_naive() - timedelta(days=days)

    session = get_session_pg()
    try:
        active_model_version = _get_active_model_version(session=session)
        query = session.query(
            PlynomeryAnomalyEvent.identifikace,
            PlynomeryAnomalyEvent.event_type,
            PlynomeryAnomalyEvent.start_time,
            PlynomeryAnomalyEvent.end_time,
            PlynomeryAnomalyEvent.duration_minutes,
            PlynomeryAnomalyEvent.max_z_score,
            PlynomeryAnomalyEvent.avg_z_score,
            PlynomeryAnomalyEvent.severity,
        ).filter(
            PlynomeryAnomalyEvent.model_version == active_model_version,
            PlynomeryAnomalyEvent.resolved.is_(True),
            PlynomeryAnomalyEvent.end_time.is_not(None),
            PlynomeryAnomalyEvent.end_time >= resolved_since,
            PlynomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES,
        )
        if not user_context.is_admin:
            query = query.filter(PlynomeryAnomalyEvent.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(
            PlynomeryAnomalyEvent.end_time.desc(),
            PlynomeryAnomalyEvent.duration_minutes.desc(),
        ).limit(limit).all()
        return [
            {
                "identifikace": str(row.identifikace),
                "event_type": str(row.event_type),
                "start_time": row.start_time,
                "end_time": row.end_time,
                "duration_minutes": int(row.duration_minutes),
                "max_z_score": float(row.max_z_score),
                "avg_z_score": float(row.avg_z_score),
                "severity": str(row.severity),
            }
            for row in rows
        ]
    finally:
        session.close()
