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
from moduly.mereni.vodomery.database.model_validation import get_active_vodomery_model_version
from moduly.mereni.vodomery.database.models import (
    Mereni_vodomery,
    Vodomer_areal_Zarizeni,
    VodomeryAnomalyEvent,
    VodomeryProfilesAnomaly,
    VodomeryAnomalyScore,
)
from services.api.services.dashboard_auth import (
    AuthorizationError,
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

BRANCH_DASHBOARD_CONFIG_BY_BILLING_IDENT = {
    config_item.billing_ident: config_item for config_item in BRANCH_DASHBOARD_CONFIGS
}


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


def _build_exclusive_datetime_range(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.min) + timedelta(days=1)
    return start_dt, end_dt


def _to_rounded_float(value: object) -> float | None:
    if value is None:
        return None
    numeric_value = float(value)
    if pd.isna(numeric_value):
        return None
    return round(numeric_value, 3)


def _compute_consumption_between_values(start_value: float | None, end_value: float | None) -> float | None:
    if start_value is None or end_value is None or end_value < start_value:
        return None
    return round(end_value - start_value, 3)


def _normalize_branch_billing_ident(billing_ident: str) -> BranchDashboardConfig:
    normalized = (billing_ident or "").strip().upper()
    config_item = BRANCH_DASHBOARD_CONFIG_BY_BILLING_IDENT.get(normalized)
    if config_item is None:
        allowed_values = ", ".join(sorted(BRANCH_DASHBOARD_CONFIG_BY_BILLING_IDENT))
        raise ValueError(
            f"Neznamy fakturacni vodomer '{billing_ident}'. Povolené hodnoty: {allowed_values}."
        )
    return config_item


def _source_ident_subquery(session, source_filter: str):
    return (
        session.query(Mereni_vodomery.identifikace)
        .filter(Mereni_vodomery.zdroj == source_filter)
        .distinct()
    )


def _get_active_model_version(session) -> int:
    return get_active_vodomery_model_version(session=session, default=1)


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
        if "platne" in item.columns:
            item.loc[~item["platne"].fillna(True), "spotreba"] = 0.0
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


def _load_last_valid_measurements_at_or_before(
    conn,
    identifiers: Iterable[str],
    cutoff: datetime,
) -> dict[str, float | None]:
    unique_identifiers = list(dict.fromkeys(str(identifier) for identifier in identifiers if identifier))
    if not unique_identifiers:
        return {}

    statement = text(
        """
        WITH ranked_measurements AS (
            SELECT
                identifikace,
                objem,
                ROW_NUMBER() OVER (
                    PARTITION BY identifikace
                    ORDER BY date DESC, id DESC
                ) AS row_num
            FROM monitoring."Mereni_vodomery_vse"
            WHERE identifikace IN :identifiers
              AND date <= :cutoff
              AND platne = TRUE
              AND objem IS NOT NULL
        )
        SELECT identifikace, objem
        FROM ranked_measurements
        WHERE row_num = 1
        """
    ).bindparams(bindparam("identifiers", expanding=True))

    rows = conn.execute(
        statement,
        {
            "identifiers": unique_identifiers,
            "cutoff": cutoff,
        },
    ).all()
    return {str(identifikace): _to_rounded_float(objem) for identifikace, objem in rows}


def _to_display_end(exclusive_end: datetime) -> datetime:
    return exclusive_end - timedelta(seconds=1)


def _collect_device_assignment_intervals(
    effective_segments: Iterable[tuple[datetime, datetime, tuple[str, ...]]],
) -> dict[str, list[tuple[datetime, datetime]]]:
    device_intervals: dict[str, list[tuple[datetime, datetime]]] = {}
    for segment_start, segment_end, identifiers in effective_segments:
        for identifier in identifiers:
            intervals = device_intervals.setdefault(identifier, [])
            if intervals and intervals[-1][1] == segment_start:
                intervals[-1] = (intervals[-1][0], segment_end)
            else:
                intervals.append((segment_start, segment_end))
    return device_intervals


def _build_branch_billing_payload(
    *,
    config_item: BranchDashboardConfig,
    start_date: date,
    end_date: date,
    period_start: datetime,
    period_end: datetime,
    effective_segments: list[tuple[datetime, datetime, tuple[str, ...]]],
    snapshot_cache: dict[datetime, dict[str, float | None]],
) -> dict[str, object]:
    all_active_devices = tuple(
        dict.fromkeys(
            identifier
            for _, _, segment_identifiers in effective_segments
            for identifier in segment_identifiers
        )
    )
    device_totals = {identifier: 0.0 for identifier in all_active_devices}
    device_active_segment_counts = {identifier: 0 for identifier in all_active_devices}
    device_segments_with_data_counts = {identifier: 0 for identifier in all_active_devices}

    segment_rows: list[dict[str, object]] = []
    for segment_start, segment_end, active_devices in effective_segments:
        segment_consumptions: list[float] = []
        devices_with_data_count = 0
        for identifier in active_devices:
            device_active_segment_counts[identifier] = device_active_segment_counts.get(identifier, 0) + 1
            consumption = _compute_consumption_between_values(
                snapshot_cache.get(segment_start, {}).get(identifier),
                snapshot_cache.get(segment_end, {}).get(identifier),
            )
            if consumption is None:
                continue
            device_totals[identifier] = round(device_totals.get(identifier, 0.0) + consumption, 3)
            device_segments_with_data_counts[identifier] = device_segments_with_data_counts.get(identifier, 0) + 1
            devices_with_data_count += 1
            segment_consumptions.append(consumption)

        billing_consumption = _compute_consumption_between_values(
            snapshot_cache.get(segment_start, {}).get(config_item.billing_ident),
            snapshot_cache.get(segment_end, {}).get(config_item.billing_ident),
        )
        submeter_consumption = round(sum(segment_consumptions), 3) if segment_consumptions else 0.0
        difference = None
        if billing_consumption is not None:
            difference = round(billing_consumption - submeter_consumption, 3)

        segment_rows.append(
            {
                "start_time": segment_start,
                "end_time": _to_display_end(segment_end),
                "active_devices": list(active_devices),
                "device_count": len(active_devices),
                "devices_with_data_count": devices_with_data_count,
                "devices_without_data_count": len(active_devices) - devices_with_data_count,
                "submeter_consumption": submeter_consumption,
                "billing_consumption": billing_consumption,
                "difference": difference,
            }
        )

    device_interval_map = _collect_device_assignment_intervals(effective_segments)
    assignment_rows: list[dict[str, object]] = []
    for identifier, intervals in sorted(device_interval_map.items()):
        for interval_start, interval_end in intervals:
            assignment_rows.append(
                {
                    "identifikace": identifier,
                    "start_time": interval_start,
                    "end_time": _to_display_end(interval_end),
                    "duration_hours": round((interval_end - interval_start).total_seconds() / 3600, 2),
                }
            )

    billing_start_value = snapshot_cache.get(period_start, {}).get(config_item.billing_ident)
    billing_end_value = snapshot_cache.get(period_end, {}).get(config_item.billing_ident)
    billing_consumption = _compute_consumption_between_values(billing_start_value, billing_end_value)
    if billing_consumption is None and segment_rows:
        candidate_values = [row["billing_consumption"] for row in segment_rows if row["billing_consumption"] is not None]
        if candidate_values:
            billing_consumption = round(sum(candidate_values), 3)

    submeter_consumption_total = round(sum(device_totals.values()), 3) if device_totals else 0.0
    difference = None
    coverage_percent = None
    if billing_consumption is not None:
        difference = round(billing_consumption - submeter_consumption_total, 3)
        if billing_consumption > 0:
            coverage_percent = round(submeter_consumption_total / billing_consumption * 100, 1)

    device_rows: list[dict[str, object]] = []
    for identifier in all_active_devices:
        device_consumption = round(device_totals.get(identifier, 0.0), 3)
        share_of_submeters = (
            round(device_consumption / submeter_consumption_total * 100, 1)
            if submeter_consumption_total > 0
            else 0.0
        )
        share_of_billing = (
            round(device_consumption / billing_consumption * 100, 1)
            if billing_consumption is not None and billing_consumption > 0
            else None
        )
        allocated_billing_consumption = (
            round(billing_consumption * device_consumption / submeter_consumption_total, 3)
            if billing_consumption is not None and submeter_consumption_total > 0
            else None
        )
        intervals = device_interval_map.get(identifier, [])
        device_rows.append(
            {
                "identifikace": identifier,
                "spotreba": device_consumption,
                "podil_na_podruznych_procent": share_of_submeters,
                "podil_na_fakturacnim_procent": share_of_billing,
                "rozpoctena_fakturacni_spotreba": allocated_billing_consumption,
                "active_segment_count": device_active_segment_counts.get(identifier, 0),
                "segments_with_data_count": device_segments_with_data_counts.get(identifier, 0),
                "segments_without_data_count": (
                    device_active_segment_counts.get(identifier, 0)
                    - device_segments_with_data_counts.get(identifier, 0)
                ),
                "active_from": intervals[0][0] if intervals else None,
                "active_to": _to_display_end(intervals[-1][1]) if intervals else None,
            }
        )

    device_rows.sort(key=lambda row: (-float(row["spotreba"]), str(row["identifikace"])))

    return {
        "branch_key": config_item.key,
        "branch_title": config_item.title,
        "billing_ident": config_item.billing_ident,
        "start_date": start_date,
        "end_date": end_date,
        "billing_start_value": billing_start_value,
        "billing_end_value": billing_end_value,
        "billing_consumption": billing_consumption,
        "submeter_consumption_total": submeter_consumption_total,
        "difference": difference,
        "coverage_percent": coverage_percent,
        "active_device_count": len(all_active_devices),
        "active_segment_count": len(effective_segments),
        "device_rows": device_rows,
        "assignment_rows": assignment_rows,
        "segment_rows": segment_rows,
    }


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


def list_branch_billing_options(user_context: DashboardUserContext) -> list[dict[str, object]]:
    require_section_access(user_context, "vodomery")
    return [
        {
            "key": config_item.key,
            "title": config_item.title,
            "billing_ident": config_item.billing_ident,
        }
        for config_item in BRANCH_DASHBOARD_CONFIGS
    ]


def load_branch_billing_period(
    user_context: DashboardUserContext,
    *,
    billing_ident: str,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    require_section_access(user_context, "vodomery")
    config_item = _normalize_branch_billing_ident(billing_ident)
    period_start, period_end = _build_exclusive_datetime_range(start_date, end_date)
    effective_segments = _resolve_branch_segments(
        config_item,
        period_start,
        period_end,
        merge_adjacent=True,
    )

    required_identifiers = tuple(
        dict.fromkeys(
            [
                config_item.billing_ident,
                *(
                    identifier
                    for _, _, segment_identifiers in effective_segments
                    for identifier in segment_identifiers
                ),
            ]
        )
    )
    if not user_context.is_admin and required_identifiers:
        missing_devices = [identifier for identifier in required_identifiers if identifier not in user_context.allowed_devices]
        if missing_devices:
            raise AuthorizationError("Na zvolenou fakturacni vetev nemate opravneni.")

    snapshot_cutoffs = sorted({
        period_start,
        period_end,
        *(segment_start for segment_start, _, _ in effective_segments),
        *(segment_end for _, segment_end, _ in effective_segments),
    })

    with ENGINE_PG.connect() as conn:
        snapshot_cache = {
            cutoff: _load_last_valid_measurements_at_or_before(conn, required_identifiers, cutoff)
            for cutoff in snapshot_cutoffs
        }

    return _build_branch_billing_payload(
        config_item=config_item,
        start_date=min(start_date, end_date),
        end_date=max(start_date, end_date),
        period_start=period_start,
        period_end=period_end,
        effective_segments=effective_segments,
        snapshot_cache=snapshot_cache,
    )


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
        active_model_version = _get_active_model_version(session)
        base_measurements = session.query(Mereni_vodomery).filter(
            Mereni_vodomery.date >= start_dt,
            Mereni_vodomery.date <= end_dt,
        )
        base_scores = session.query(VodomeryAnomalyScore).filter(
            VodomeryAnomalyScore.model_version == active_model_version,
            VodomeryAnomalyScore.date >= start_dt,
            VodomeryAnomalyScore.date <= end_dt,
        )
        base_events = session.query(VodomeryAnomalyEvent).filter(
            VodomeryAnomalyEvent.model_version == active_model_version,
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
            Mereni_vodomery.platne,
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
                "platne": bool(row.platne),
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
        active_model_version = _get_active_model_version(session)

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
            .filter(VodomeryProfilesAnomaly.model_version == active_model_version)
            .order_by(
                VodomeryProfilesAnomaly.day_of_week.asc(),
                VodomeryProfilesAnomaly.slot.asc(),
            )
            .all()
        )
        if not rows:
            return []
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
        active_model_version = _get_active_model_version(session)
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
            .filter(VodomeryAnomalyScore.model_version == active_model_version)
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
        active_model_version = _get_active_model_version(session)
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
            VodomeryAnomalyEvent.model_version == active_model_version,
            VodomeryAnomalyEvent.end_time.is_(None),
        )
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
        active_model_version = _get_active_model_version(session)
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
            VodomeryAnomalyEvent.model_version == active_model_version,
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
        active_model_version = _get_active_model_version(session)
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
                .filter(
                    VodomeryAnomalyEvent.identifikace == identifikace,
                    VodomeryAnomalyEvent.model_version == active_model_version,
                )
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
        SELECT date, identifikace, objem, delta, platne, reset_detected
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
          AND model_version = :model_version
        """
    ).bindparams(bindparam("identifiers", expanding=True))

    with ENGINE_PG.connect() as conn:
        active_model_version = _get_active_model_version(conn)
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
                    columns=["date", "identifikace", "objem", "delta", "platne", "reset_detected"],
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
                        "model_version": active_model_version,
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
