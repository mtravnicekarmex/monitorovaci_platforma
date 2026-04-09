from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pandas as pd
from sqlalchemy import bindparam, func, text

from app.metrics_utils import calculate_percentage_deviation
from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG, get_session_ms, get_session_pg
from moduly.mereni.vodomery.SCVK.SCVK_data_z_dotazu import paths as SCVK_PATHS
from moduly.mereni.vodomery.SCVK.historie_vetve import (
    INTERVALY_vetev_L,
    INTERVALY_vetev_dok_poz_voda,
    INTERVALY_vetev_dok_voda,
    INTERVALY_vetev_grobar,
    ziskej_vetev_L,
    ziskej_vetev_dok_poz_voda,
    ziskej_vetev_dok_voda,
    ziskej_vetev_grobar,
)
from moduly.mereni.vodomery.database.expected_zero import get_expected_zero_device_set
from moduly.mereni.vodomery.database.models import (
    Mereni_vodomery,
    Vodomer_areal_Zarizeni,
    VodomeryAnomalyEvent,
    VodomeryProfilesAnomaly,
    VodomeryAnomalyScore,
)
from services.api.services.dashboard_auth import (
    DashboardUserContext,
    require_device_access,
    require_section_access,
)


VALID_SOURCE_FILTERS = {"VSE", "AREAL", "SCVK"}
MIN_VISIBLE_EVENT_DURATION_MINUTES = 120


@dataclass(frozen=True)
class BranchDashboardConfig:
    key: str
    title: str
    billing_ident: str
    daily_limit: float | None
    intervals: tuple[tuple[datetime, datetime, list[str]], ...]
    membership_resolver: Callable[[datetime], list[str]]


BRANCH_DASHBOARD_CONFIGS: tuple[BranchDashboardConfig, ...] = (
    BranchDashboardConfig(
        key="SCVK_HE",
        title="HECHT",
        billing_ident="SCVK_HE",
        daily_limit=float(SCVK_PATHS["SCVK_HE"]["denni limit"]),
        intervals=tuple(INTERVALY_vetev_L),
        membership_resolver=ziskej_vetev_L,
    ),
    BranchDashboardConfig(
        key="SCVK_DV",
        title="DOKTOR voda",
        billing_ident="SCVK_DV",
        daily_limit=float(SCVK_PATHS["SCVK_DV"]["denni limit"]),
        intervals=tuple(INTERVALY_vetev_dok_voda),
        membership_resolver=ziskej_vetev_dok_voda,
    ),
    BranchDashboardConfig(
        key="SCVK_DP",
        title="DOKTOR požární voda",
        billing_ident="SCVK_DP",
        daily_limit=float(SCVK_PATHS["SCVK_DP"]["denni limit"]),
        intervals=tuple(INTERVALY_vetev_dok_poz_voda),
        membership_resolver=ziskej_vetev_dok_poz_voda,
    ),
    BranchDashboardConfig(
        key="SCVK_GR",
        title="GROBÁR",
        billing_ident="SCVK_GR",
        daily_limit=float(SCVK_PATHS["SCVK_GR"]["denni limit"]),
        intervals=tuple(INTERVALY_vetev_grobar),
        membership_resolver=ziskej_vetev_grobar,
    ),
)


def _normalize_source_filter(source_filter: str) -> str:
    normalized = (source_filter or "VSE").strip().upper()
    if normalized not in VALID_SOURCE_FILTERS:
        raise ValueError(
            f"Neznamy source filter '{source_filter}'. Povolené hodnoty: {', '.join(sorted(VALID_SOURCE_FILTERS))}."
        )
    return normalized


def _build_datetime_range(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    return start_dt, end_dt


def _source_ident_subquery(session, source_filter: str):
    return (
        session.query(Mereni_vodomery.identifikace)
        .filter(Mereni_vodomery.zdroj == source_filter)
        .distinct()
    )


def _apply_expected_zero_event_filter(query, expected_zero_idents: set[str]):
    if not expected_zero_idents:
        return query
    return query.filter(
        ~(
            (VodomeryAnomalyEvent.event_type == "ZERO_FLOW")
            & (VodomeryAnomalyEvent.identifikace.in_(tuple(sorted(expected_zero_idents))))
        )
    )


def _resolve_branch_segments(
    config_item: BranchDashboardConfig,
    start_dt: datetime,
    end_dt: datetime,
    additional_boundaries: Iterable[datetime] = (),
    merge_adjacent: bool = True,
) -> list[tuple[datetime, datetime, tuple[str, ...]]]:
    boundaries = {start_dt, end_dt}
    one_second = timedelta(seconds=1)

    for interval_start, interval_end, _ in config_item.intervals:
        effective_start = max(start_dt, interval_start)
        effective_end = min(end_dt, interval_end + one_second)
        if effective_start >= effective_end:
            continue
        boundaries.add(effective_start)
        boundaries.add(effective_end)

    for boundary in additional_boundaries:
        if start_dt < boundary < end_dt:
            boundaries.add(boundary)

    sorted_boundaries = sorted(boundaries)
    segments: list[tuple[datetime, datetime, tuple[str, ...]]] = []

    for index in range(len(sorted_boundaries) - 1):
        segment_start = sorted_boundaries[index]
        segment_end = sorted_boundaries[index + 1]
        if segment_start >= segment_end:
            continue

        probe_time = segment_start + (segment_end - segment_start) / 2
        identifiers = tuple(dict.fromkeys(config_item.membership_resolver(probe_time)))
        if not identifiers:
            continue

        if merge_adjacent and segments and segments[-1][2] == identifiers and segments[-1][1] == segment_start:
            previous_start, _, previous_identifiers = segments[-1]
            segments[-1] = (previous_start, segment_end, previous_identifiers)
            continue

        segments.append((segment_start, segment_end, identifiers))

    return segments


def _prepare_branch_measurements(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["objem"] = pd.to_numeric(prepared["objem"], errors="coerce")
    prepared["delta"] = pd.to_numeric(prepared["delta"], errors="coerce")
    prepared = prepared.dropna(subset=["date", "identifikace"]).sort_values(["identifikace", "date"]).reset_index(drop=True)
    if prepared.empty:
        return prepared

    grouped_frames: list[pd.DataFrame] = []
    for _, group in prepared.groupby("identifikace", sort=False):
        item = group.copy()
        diff_from_volume = item["objem"].diff()
        item["spotreba"] = item["delta"].where(item["delta"].notna(), diff_from_volume)
        item["spotreba"] = pd.to_numeric(item["spotreba"], errors="coerce").fillna(0.0)
        item.loc[item["spotreba"] < 0, "spotreba"] = 0.0
        item.loc[item["reset_detected"].fillna(False), "spotreba"] = 0.0
        item["spotreba"] = item["spotreba"].round(3)
        grouped_frames.append(item)

    return pd.concat(grouped_frames, ignore_index=True)


def _serialize_dataframe_rows(df: pd.DataFrame) -> list[dict[str, object]]:
    if df.empty:
        return []
    serialized = df.copy()
    for column in serialized.columns:
        if pd.api.types.is_datetime64_any_dtype(serialized[column]):
            serialized[column] = pd.Series(
                [
                    None
                    if pd.isna(value)
                    else value.to_pydatetime()
                    if isinstance(value, pd.Timestamp)
                    else value
                    for value in serialized[column]
                ],
                index=serialized.index,
                dtype="object",
            )
    serialized = serialized.where(pd.notna(serialized), None)
    records: list[dict[str, object]] = []
    for row in serialized.to_dict(orient="records"):
        normalized_row: dict[str, object] = {}
        for key, value in row.items():
            if hasattr(value, "item"):
                value = value.item()
            normalized_row[key] = value
        records.append(normalized_row)
    return records


def list_accessible_devices(
    user_context: DashboardUserContext,
    *,
    source_filter: str = "VSE",
    limit: int = 500,
) -> list[str]:
    require_section_access(user_context, "vodomery")
    source_filter = _normalize_source_filter(source_filter)

    session = get_session_pg()
    try:
        query = session.query(Mereni_vodomery.identifikace).distinct()
        if not user_context.is_admin:
            query = query.filter(Mereni_vodomery.identifikace.in_(user_context.allowed_devices))
        if source_filter != "VSE":
            query = query.filter(Mereni_vodomery.zdroj == source_filter)

        rows = query.order_by(Mereni_vodomery.identifikace).limit(limit).all()
        return [str(row[0]) for row in rows if row[0]]
    finally:
        session.close()


def load_overview_metrics(
    user_context: DashboardUserContext,
    *,
    source_filter: str,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    require_section_access(user_context, "vodomery")
    source_filter = _normalize_source_filter(source_filter)
    start_dt, end_dt = _build_datetime_range(start_date, end_date)
    expected_zero_idents = set(get_expected_zero_device_set())

    session = get_session_pg()
    try:
        base_measurements = session.query(Mereni_vodomery).filter(
            Mereni_vodomery.date >= start_dt,
            Mereni_vodomery.date <= end_dt,
        )
        base_scores = session.query(VodomeryAnomalyScore).filter(
            VodomeryAnomalyScore.date >= start_dt,
            VodomeryAnomalyScore.date <= end_dt,
        )
        base_events = session.query(VodomeryAnomalyEvent).filter(
            VodomeryAnomalyEvent.start_time >= start_dt,
            VodomeryAnomalyEvent.start_time <= end_dt,
            VodomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES,
        )

        if not user_context.is_admin:
            base_measurements = base_measurements.filter(Mereni_vodomery.identifikace.in_(user_context.allowed_devices))
            base_scores = base_scores.filter(VodomeryAnomalyScore.identifikace.in_(user_context.allowed_devices))
            base_events = base_events.filter(VodomeryAnomalyEvent.identifikace.in_(user_context.allowed_devices))

        if source_filter != "VSE":
            base_measurements = base_measurements.filter(Mereni_vodomery.zdroj == source_filter)
            base_scores = base_scores.filter(
                VodomeryAnomalyScore.measurement_id.in_(
                    session.query(Mereni_vodomery.id).filter(Mereni_vodomery.zdroj == source_filter)
                )
            )
            base_events = base_events.filter(
                VodomeryAnomalyEvent.identifikace.in_(
                    session.query(Mereni_vodomery.identifikace)
                    .filter(Mereni_vodomery.zdroj == source_filter)
                    .distinct()
                )
            )

        active_events_count = base_events.filter(VodomeryAnomalyEvent.is_active.is_(True)).count()
        if expected_zero_idents:
            hidden_zero_flow_count = base_events.filter(
                VodomeryAnomalyEvent.is_active.is_(True),
                VodomeryAnomalyEvent.event_type == "ZERO_FLOW",
                VodomeryAnomalyEvent.identifikace.in_(tuple(expected_zero_idents)),
            ).count()
            active_events_count = max(active_events_count - hidden_zero_flow_count, 0)

        device_count = (
            base_measurements.with_entities(func.count(func.distinct(Mereni_vodomery.identifikace))).scalar() or 0
        )

        return {
            "zarizeni": int(device_count),
            "mereni": int(base_measurements.count()),
            "anomalie": int(base_scores.filter(VodomeryAnomalyScore.is_anomaly.is_(True)).count()),
            "aktivni_eventy": int(active_events_count),
        }
    finally:
        session.close()


def load_measurement_series(
    user_context: DashboardUserContext,
    *,
    source_filter: str,
    identifikace: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, object]]:
    require_section_access(user_context, "vodomery")
    require_device_access(user_context, identifikace)
    source_filter = _normalize_source_filter(source_filter)
    start_dt, end_dt = _build_datetime_range(start_date, end_date)

    session = get_session_pg()
    try:
        query = session.query(
            Mereni_vodomery.date,
            Mereni_vodomery.identifikace,
            Mereni_vodomery.seriove_cislo,
            Mereni_vodomery.zdroj,
            Mereni_vodomery.objem,
            Mereni_vodomery.delta,
            Mereni_vodomery.interval_minutes,
            Mereni_vodomery.day_of_week,
            Mereni_vodomery.slot,
            Mereni_vodomery.synthetic,
            Mereni_vodomery.nocni_odber,
            Mereni_vodomery.gap_detected,
            Mereni_vodomery.reset_detected,
        ).filter(
            Mereni_vodomery.identifikace == identifikace,
            Mereni_vodomery.date >= start_dt,
            Mereni_vodomery.date <= end_dt,
        )

        if source_filter != "VSE":
            query = query.filter(Mereni_vodomery.zdroj == source_filter)

        rows = query.order_by(Mereni_vodomery.date.asc()).all()
        return [
            {
                "date": row.date,
                "identifikace": str(row.identifikace),
                "seriove_cislo": str(row.seriove_cislo) if row.seriove_cislo is not None else None,
                "zdroj": str(row.zdroj) if row.zdroj is not None else None,
                "objem": float(row.objem),
                "delta": float(row.delta) if row.delta is not None else None,
                "interval_minutes": int(row.interval_minutes),
                "day_of_week": int(row.day_of_week),
                "slot": int(row.slot),
                "synthetic": bool(row.synthetic),
                "nocni_odber": bool(row.nocni_odber),
                "gap_detected": bool(row.gap_detected),
                "reset_detected": bool(row.reset_detected),
            }
            for row in rows
        ]
    finally:
        session.close()


def load_prediction_profiles(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
) -> list[dict[str, object]]:
    require_section_access(user_context, "vodomery")
    require_device_access(user_context, identifikace)

    session = get_session_pg()
    try:
        latest_model_version = (
            session.query(func.max(VodomeryProfilesAnomaly.model_version))
            .filter(VodomeryProfilesAnomaly.identifikace == identifikace)
            .scalar()
        )
        if latest_model_version is None:
            return []

        rows = (
            session.query(
                VodomeryProfilesAnomaly.interval_minutes,
                VodomeryProfilesAnomaly.day_of_week,
                VodomeryProfilesAnomaly.slot,
                VodomeryProfilesAnomaly.mean,
                VodomeryProfilesAnomaly.median,
                VodomeryProfilesAnomaly.p10,
                VodomeryProfilesAnomaly.p90,
                VodomeryProfilesAnomaly.std,
                VodomeryProfilesAnomaly.sample_size,
                VodomeryProfilesAnomaly.model_version,
            )
            .filter(VodomeryProfilesAnomaly.identifikace == identifikace)
            .filter(VodomeryProfilesAnomaly.model_version == latest_model_version)
            .order_by(
                VodomeryProfilesAnomaly.day_of_week.asc(),
                VodomeryProfilesAnomaly.slot.asc(),
            )
            .all()
        )
        return [
            {
                "interval_minutes": int(row.interval_minutes),
                "day_of_week": int(row.day_of_week),
                "slot": int(row.slot),
                "expected_mean": float(row.mean),
                "expected_median": float(row.median),
                "expected_p10": float(row.p10),
                "expected_p90": float(row.p90),
                "expected_std": float(row.std),
                "sample_size": int(row.sample_size),
                "model_version": int(row.model_version),
            }
            for row in rows
        ]
    finally:
        session.close()


def load_recent_anomalies(
    user_context: DashboardUserContext,
    *,
    source_filter: str,
    identifikace: str | None,
    start_date: date,
    end_date: date,
    limit: int = 50,
) -> list[dict[str, object]]:
    require_section_access(user_context, "vodomery")
    source_filter = _normalize_source_filter(source_filter)
    start_dt, end_dt = _build_datetime_range(start_date, end_date)
    if identifikace:
        require_device_access(user_context, identifikace)

    session = get_session_pg()
    try:
        query = (
            session.query(
                VodomeryAnomalyScore.date,
                VodomeryAnomalyScore.identifikace,
                VodomeryAnomalyScore.actual_value,
                VodomeryAnomalyScore.expected_mean,
                VodomeryAnomalyScore.z_score,
                VodomeryAnomalyScore.severity,
                VodomeryAnomalyScore.is_anomaly,
            )
            .filter(VodomeryAnomalyScore.is_anomaly.is_(True))
            .filter(VodomeryAnomalyScore.date >= start_dt, VodomeryAnomalyScore.date <= end_dt)
        )

        if not user_context.is_admin:
            query = query.filter(VodomeryAnomalyScore.identifikace.in_(user_context.allowed_devices))
        if identifikace:
            query = query.filter(VodomeryAnomalyScore.identifikace == identifikace)
        elif source_filter != "VSE":
            query = query.filter(VodomeryAnomalyScore.identifikace.in_(_source_ident_subquery(session, source_filter)))

        rows = query.order_by(VodomeryAnomalyScore.date.desc()).limit(limit).all()
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
    require_section_access(user_context, "vodomery")

    session = get_session_pg()
    try:
        expected_zero_idents = get_expected_zero_device_set(session=session)
        query = session.query(
            VodomeryAnomalyEvent.identifikace,
            VodomeryAnomalyEvent.event_type,
            VodomeryAnomalyEvent.start_time,
            VodomeryAnomalyEvent.end_time,
            VodomeryAnomalyEvent.duration_minutes,
            VodomeryAnomalyEvent.max_z_score,
            VodomeryAnomalyEvent.avg_z_score,
            VodomeryAnomalyEvent.severity,
        ).filter(VodomeryAnomalyEvent.end_time.is_(None))
        query = query.filter(VodomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES)
        query = _apply_expected_zero_event_filter(query, expected_zero_idents)

        if not user_context.is_admin:
            query = query.filter(VodomeryAnomalyEvent.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(
            VodomeryAnomalyEvent.severity.asc(),
            VodomeryAnomalyEvent.duration_minutes.desc(),
            VodomeryAnomalyEvent.start_time.desc(),
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
    require_section_access(user_context, "vodomery")
    resolved_since = utc_now_naive() - timedelta(days=days)

    session = get_session_pg()
    try:
        expected_zero_idents = get_expected_zero_device_set(session=session)
        query = session.query(
            VodomeryAnomalyEvent.identifikace,
            VodomeryAnomalyEvent.event_type,
            VodomeryAnomalyEvent.start_time,
            VodomeryAnomalyEvent.end_time,
            VodomeryAnomalyEvent.duration_minutes,
            VodomeryAnomalyEvent.max_z_score,
            VodomeryAnomalyEvent.avg_z_score,
            VodomeryAnomalyEvent.severity,
        ).filter(
            VodomeryAnomalyEvent.resolved.is_(True),
            VodomeryAnomalyEvent.end_time.is_not(None),
            VodomeryAnomalyEvent.end_time >= resolved_since,
            VodomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES,
        )
        query = _apply_expected_zero_event_filter(query, expected_zero_idents)

        if not user_context.is_admin:
            query = query.filter(VodomeryAnomalyEvent.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(
            VodomeryAnomalyEvent.end_time.desc(),
            VodomeryAnomalyEvent.duration_minutes.desc(),
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


def load_event_history(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
    limit: int = 20,
) -> list[dict[str, object]]:
    require_section_access(user_context, "vodomery")
    require_device_access(user_context, identifikace)

    session = get_session_pg()
    try:
        expected_zero_idents = get_expected_zero_device_set(session=session)
        rows = (
            _apply_expected_zero_event_filter(
                session.query(
                    VodomeryAnomalyEvent.event_type,
                    VodomeryAnomalyEvent.start_time,
                    VodomeryAnomalyEvent.end_time,
                    VodomeryAnomalyEvent.duration_minutes,
                    VodomeryAnomalyEvent.max_z_score,
                    VodomeryAnomalyEvent.avg_z_score,
                    VodomeryAnomalyEvent.severity,
                    VodomeryAnomalyEvent.is_active,
                    VodomeryAnomalyEvent.resolved,
                )
                .filter(VodomeryAnomalyEvent.identifikace == identifikace)
                .filter(VodomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES),
                expected_zero_idents,
            )
            .order_by(VodomeryAnomalyEvent.start_time.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "event_type": str(row.event_type),
                "start_time": row.start_time,
                "end_time": row.end_time,
                "duration_minutes": int(row.duration_minutes),
                "max_z_score": float(row.max_z_score),
                "avg_z_score": float(row.avg_z_score),
                "severity": str(row.severity),
                "is_active": bool(row.is_active),
                "resolved": bool(row.resolved),
            }
            for row in rows
        ]
    finally:
        session.close()


def load_device_detail(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
) -> dict[str, object] | None:
    require_section_access(user_context, "vodomery")
    require_device_access(user_context, identifikace)

    session_ms = get_session_ms()
    try:
        device = (
            session_ms.query(Vodomer_areal_Zarizeni)
            .filter(Vodomer_areal_Zarizeni.identifikace == identifikace)
            .one_or_none()
        )
        if device is not None:
            return {
                "identifikace": str(device.identifikace),
                "seriove_cislo": str(device.seriove_cislo) if device.seriove_cislo is not None else None,
                "mbus": str(device.MBUS) if device.MBUS is not None else None,
                "objekt": str(device.objekt) if device.objekt is not None else None,
                "patro": str(device.patro) if device.patro is not None else None,
                "mistnost": str(device.mistnost) if device.mistnost is not None else None,
                "umisteni": str(device.umisteni) if device.umisteni is not None else None,
                "napaji": str(device.napaji) if device.napaji is not None else None,
                "koncovy_odberatel": str(device.koncovy_odberatel) if device.koncovy_odberatel is not None else None,
                "platnost_cejchu": device.platnost_cejchu,
                "poznamka": str(device.poznamka_vodomery) if device.poznamka_vodomery is not None else None,
            }
    finally:
        session_ms.close()
    return None


def load_branch_day_overview(
    user_context: DashboardUserContext,
    *,
    target_date: date,
) -> list[dict[str, object]]:
    require_section_access(user_context, "vodomery")

    day_start = datetime.combine(target_date, time.min)
    day_end = day_start + timedelta(days=1)
    hour_boundaries = [day_start + timedelta(hours=hour) for hour in range(25)]
    allowed_set = set(user_context.allowed_devices)

    measurement_statement = text(
        """
        SELECT date, identifikace, objem, delta, reset_detected
        FROM monitoring."Mereni_vodomery_vse"
        WHERE identifikace IN :identifiers
          AND date >= :day_start
          AND date < :day_end
        ORDER BY identifikace ASC, date ASC
        """
    ).bindparams(bindparam("identifiers", expanding=True))
    prediction_statement = text(
        """
        SELECT identifikace, interval_minutes, day_of_week, slot, mean, model_version
        FROM monitoring."vodomery_anomaly_profiles"
        WHERE identifikace IN :identifiers
        """
    ).bindparams(bindparam("identifiers", expanding=True))

    with ENGINE_PG.connect() as conn:
        branch_payloads: list[dict[str, object]] = []

        for config_item in BRANCH_DASHBOARD_CONFIGS:
            effective_segments = _resolve_branch_segments(
                config_item,
                day_start,
                day_end,
                additional_boundaries=hour_boundaries,
                merge_adjacent=False,
            )
            active_devices = tuple(
                dict.fromkeys(
                    identifier
                    for _, _, segment_identifiers in effective_segments
                    for identifier in segment_identifiers
                )
            )

            required_devices = set(active_devices) | {config_item.billing_ident}
            if not user_context.is_admin and not required_devices.issubset(allowed_set):
                continue

            measurement_identifiers = tuple(dict.fromkeys((*active_devices, config_item.billing_ident)))
            measurement_rows = (
                conn.execute(
                    measurement_statement,
                    {
                        "identifiers": list(measurement_identifiers),
                        "day_start": day_start,
                        "day_end": day_end,
                    },
                ).all()
                if measurement_identifiers
                else []
            )

            measurements_df = _prepare_branch_measurements(
                pd.DataFrame(
                    measurement_rows,
                    columns=["date", "identifikace", "objem", "delta", "reset_detected"],
                )
            )
            last_actual_timestamp = None if measurements_df.empty else pd.to_datetime(measurements_df["date"]).max()
            billing_measurements_df = (
                measurements_df.loc[measurements_df["identifikace"] == config_item.billing_ident].copy()
                if not measurements_df.empty
                else pd.DataFrame()
            )
            last_billing_timestamp = (
                None if billing_measurements_df.empty else pd.to_datetime(billing_measurements_df["date"]).max()
            )

            hourly_actual_lookup: dict[tuple[str, pd.Timestamp], float] = {}
            if not measurements_df.empty:
                measurements_df["hour_bucket"] = measurements_df["date"].dt.floor("h")
                actual_hourly = (
                    measurements_df.groupby(["identifikace", "hour_bucket"], as_index=False)["spotreba"]
                    .sum()
                    .round(3)
                )
                hourly_actual_lookup = {
                    (str(row.identifikace), pd.Timestamp(row.hour_bucket)): round(float(row.spotreba), 3)
                    for row in actual_hourly.itertuples(index=False)
                }

            prediction_rows = (
                conn.execute(
                    prediction_statement,
                    {
                        "identifiers": list(active_devices),
                    },
                ).all()
                if active_devices
                else []
            )

            prediction_df = pd.DataFrame(
                prediction_rows,
                columns=[
                    "identifikace",
                    "interval_minutes",
                    "day_of_week",
                    "slot",
                    "expected_mean",
                    "model_version",
                ],
            )
            hourly_prediction_lookup: dict[tuple[str, pd.Timestamp], float] = {}
            if not prediction_df.empty:
                prediction_df["latest_model_version"] = prediction_df.groupby("identifikace")["model_version"].transform("max")
                prediction_df = prediction_df.loc[
                    prediction_df["model_version"] == prediction_df["latest_model_version"]
                ].copy()
                prediction_df = prediction_df.loc[prediction_df["day_of_week"] == target_date.weekday()].copy()
                if not prediction_df.empty:
                    prediction_df["interval_minutes"] = pd.to_numeric(prediction_df["interval_minutes"], errors="coerce")
                    prediction_df["slot"] = pd.to_numeric(prediction_df["slot"], errors="coerce")
                    prediction_df["expected_mean"] = pd.to_numeric(prediction_df["expected_mean"], errors="coerce")
                    prediction_df = prediction_df.dropna(subset=["interval_minutes", "slot", "expected_mean"])
                    if not prediction_df.empty:
                        prediction_df["date"] = pd.Timestamp(day_start) + pd.to_timedelta(
                            prediction_df["slot"] * prediction_df["interval_minutes"],
                            unit="m",
                        )
                        prediction_df["hour_bucket"] = prediction_df["date"].dt.floor("h")
                        prediction_hourly = (
                            prediction_df.groupby(["identifikace", "hour_bucket"], as_index=False)["expected_mean"]
                            .sum()
                            .round(3)
                        )
                        hourly_prediction_lookup = {
                            (str(row.identifikace), pd.Timestamp(row.hour_bucket)): round(float(row.expected_mean), 3)
                            for row in prediction_hourly.itertuples(index=False)
                        }

            hourly_rows: list[dict[str, object]] = []
            device_actual_totals = {identifier: 0.0 for identifier in active_devices}
            device_expected_totals = {identifier: 0.0 for identifier in active_devices}
            device_hourly_rows: list[dict[str, object]] = []
            last_actual_hour = pd.Timestamp(last_actual_timestamp).floor("h") if last_actual_timestamp is not None else None
            for hour_start in pd.date_range(start=day_start, periods=24, freq="h"):
                midpoint = hour_start.to_pydatetime() + timedelta(minutes=30)
                active_hour_devices = tuple(dict.fromkeys(config_item.membership_resolver(midpoint)))
                actual_values_by_device = {
                    identifier: round(float(hourly_actual_lookup.get((identifier, hour_start), 0.0)), 3)
                    for identifier in active_hour_devices
                }
                predicted_values_by_device = {
                    identifier: round(float(hourly_prediction_lookup.get((identifier, hour_start), 0.0)), 3)
                    for identifier in active_hour_devices
                }
                actual_sum = round(sum(actual_values_by_device.values()), 3)
                predicted_sum = round(sum(predicted_values_by_device.values()), 3)
                for identifier, actual_value in actual_values_by_device.items():
                    device_actual_totals[identifier] = round(device_actual_totals.get(identifier, 0.0) + actual_value, 3)
                if last_actual_hour is not None and hour_start <= last_actual_hour:
                    for identifier, expected_value in predicted_values_by_device.items():
                        device_expected_totals[identifier] = round(
                            device_expected_totals.get(identifier, 0.0) + expected_value,
                            3,
                        )
                for identifier in active_devices:
                    device_hourly_rows.append(
                        {
                            "date": hour_start.to_pydatetime(),
                            "identifikace": identifier,
                            "spotreba": actual_values_by_device.get(identifier, 0.0),
                        }
                    )
                hourly_rows.append(
                    {
                        "date": hour_start.to_pydatetime(),
                        "spotreba": actual_sum,
                        "ocekavana_spotreba": predicted_sum,
                    }
                )

            hourly_df = pd.DataFrame(hourly_rows)
            hourly_df["fakturacni_spotreba"] = [
                round(hourly_actual_lookup.get((config_item.billing_ident, pd.Timestamp(row_date)), 0.0), 3)
                for row_date in hourly_df["date"]
            ]
            hourly_df["kumulovana_spotreba"] = hourly_df["spotreba"].cumsum().round(3)
            hourly_df["fakturacni_kumulovana_spotreba"] = hourly_df["fakturacni_spotreba"].cumsum().round(3)
            hourly_df["ocekavana_kumulovana_spotreba"] = hourly_df["ocekavana_spotreba"].cumsum().round(3)
            hourly_df["kumulovana_spotreba_graf"] = hourly_df["kumulovana_spotreba"]
            hourly_df["fakturacni_kumulovana_spotreba_graf"] = hourly_df["fakturacni_kumulovana_spotreba"]
            hourly_df["navazna_predikce"] = pd.NA
            hourly_df["denni_limit"] = config_item.daily_limit
            if last_actual_timestamp is not None:
                last_actual_hour = pd.Timestamp(last_actual_timestamp).floor("h")
                hourly_df.loc[hourly_df["date"] > last_actual_hour.to_pydatetime(), "kumulovana_spotreba_graf"] = pd.NA
                actual_mask = hourly_df["date"] <= last_actual_hour.to_pydatetime()
                if actual_mask.any():
                    last_actual_cumulative = float(hourly_df.loc[actual_mask, "kumulovana_spotreba"].iloc[-1])
                    future_prediction = (
                        hourly_df.loc[~actual_mask, "ocekavana_spotreba"]
                        .fillna(0)
                        .cumsum()
                        .add(last_actual_cumulative)
                        .round(3)
                    )
                    hourly_df.loc[actual_mask, "navazna_predikce"] = pd.NA
                    hourly_df.loc[hourly_df["date"] == last_actual_hour.to_pydatetime(), "navazna_predikce"] = last_actual_cumulative
                    hourly_df.loc[~actual_mask, "navazna_predikce"] = future_prediction.values
            else:
                hourly_df["kumulovana_spotreba_graf"] = pd.NA
                hourly_df["navazna_predikce"] = pd.NA
            if last_billing_timestamp is not None:
                last_billing_hour = pd.Timestamp(last_billing_timestamp).floor("h")
                hourly_df.loc[
                    hourly_df["date"] > last_billing_hour.to_pydatetime(),
                    "fakturacni_kumulovana_spotreba_graf",
                ] = pd.NA
            else:
                hourly_df["fakturacni_kumulovana_spotreba_graf"] = pd.NA

            actual_total = round(float(hourly_df["spotreba"].sum()), 3) if not hourly_df.empty else 0.0
            expected_total = round(float(hourly_df["ocekavana_spotreba"].sum()), 3) if not hourly_df.empty else 0.0
            expected_end_of_day = expected_total
            if hourly_df["navazna_predikce"].notna().any():
                expected_end_of_day = round(
                    float(pd.to_numeric(hourly_df["navazna_predikce"], errors="coerce").dropna().iloc[-1]),
                    3,
                )

            device_consumption_df = pd.DataFrame(
                (
                    {
                        "identifikace": identifier,
                        "spotreba": round(float(device_actual_totals.get(identifier, 0.0)), 3),
                        "ocekavana_spotreba": round(float(device_expected_totals.get(identifier, 0.0)), 3),
                        "odchylka_od_ocekavani_procent": calculate_percentage_deviation(
                            device_actual_totals.get(identifier, 0.0),
                            device_expected_totals.get(identifier, 0.0),
                        ),
                    }
                    for identifier in active_devices
                )
            )
            device_hourly_df = pd.DataFrame(device_hourly_rows)
            if not device_consumption_df.empty:
                device_consumption_df["podil_procent"] = (
                    device_consumption_df["spotreba"] / actual_total * 100 if actual_total > 0 else 0.0
                )
                device_consumption_df["podil_procent"] = pd.to_numeric(
                    device_consumption_df["podil_procent"],
                    errors="coerce",
                ).fillna(0.0).round(1)
                device_consumption_df = device_consumption_df.sort_values(
                    ["spotreba", "identifikace"],
                    ascending=[False, True],
                ).reset_index(drop=True)

            remaining_to_limit = None
            expected_vs_limit = None
            if config_item.daily_limit is not None:
                remaining_to_limit = round(float(config_item.daily_limit) - expected_total, 3)
                expected_vs_limit = round(float(expected_end_of_day) - float(config_item.daily_limit), 3)

            branch_payloads.append(
                {
                    "key": config_item.key,
                    "title": config_item.title,
                    "billing_ident": config_item.billing_ident,
                    "daily_limit": config_item.daily_limit,
                    "active_devices": list(active_devices),
                    "hourly_rows": _serialize_dataframe_rows(hourly_df),
                    "last_actual_timestamp": last_actual_timestamp.to_pydatetime() if last_actual_timestamp is not None else None,
                    "actual_total": actual_total,
                    "device_consumption_rows": _serialize_dataframe_rows(device_consumption_df),
                    "device_hourly_rows": _serialize_dataframe_rows(device_hourly_df),
                    "expected_total": expected_total,
                    "expected_end_of_day": expected_end_of_day,
                    "expected_vs_limit": expected_vs_limit,
                    "remaining_to_limit": remaining_to_limit,
                }
            )

        return branch_payloads
