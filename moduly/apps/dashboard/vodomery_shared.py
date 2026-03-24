from __future__ import annotations

from dataclasses import dataclass
import datetime
from pathlib import Path
import sys
from collections.abc import Callable, Iterable

import pandas as pd
import streamlit as st
from sqlalchemy import bindparam, func, text


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connect import ENGINE_PG, get_session_pg
from moduly.apps.dashboard.auth import get_allowed_devices, is_admin
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
    Vodomer_areal_Zarizeni_QGIS,
    VodomeryAnomalyEvent,
    VodomeryAnomalyScore,
    VodomeryProfilesAnomaly,
)


MAX_IDENT_OPTIONS = 500
FILTER_SOURCE_KEY = "vodomery_source_filter"
FILTER_DEVICE_KEY = "vodomery_identifikace"
FILTER_DATE_RANGE_KEY = "vodomery_date_range"
WATER_PAGES = {"Přehled", "Přehled větve", "Anomalie a eventy", "Detail"}
MIN_VISIBLE_EVENT_DURATION_MINUTES = 120
DEFAULT_CONSUMPTION_COLUMNS = (
    "objem",
    "delta",
    "spotreba",
    "kumulovana_spotreba",
    "ocekavana_spotreba",
    "ocekavana_kumulovana_spotreba",
    "actual_value",
    "expected_mean",
    "nocni_spotreba",
    "nocni_odber_m3",
    "prumerny_denni_odber",
    "Objem",
    "Delta",
    "Spotreba",
    "Kumulovana spotreba",
    "Ocekavana spotreba",
    "Ocekavana kumulovana spotreba",
    "Actual value",
    "Expected mean",
    "Noční odběr [m³]",
    "Průměrný měsíční odběr",
    "Očekávaný denní odběr",
)


@dataclass(frozen=True)
class BranchDashboardConfig:
    key: str
    title: str
    billing_ident: str
    daily_limit: float | None
    intervals: tuple[tuple[datetime.datetime, datetime.datetime, list[str]], ...]
    membership_resolver: Callable[[datetime.datetime], list[str]]


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


def render_page_styles() -> None:
    st.markdown(
        """
        <style>
        .vodomery-hero {
            padding: 0.25rem 0 0.75rem 0;
        }

        .vodomery-eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.78rem;
            color: #64748b;
            margin-bottom: 0.35rem;
        }

        .vodomery-subtitle {
            color: #475569;
            font-size: 0.95rem;
            margin-top: 0.35rem;
        }

        .vodomery-filters {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin: 0.25rem 0 1rem 0;
        }

        .vodomery-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: #f1f5f9;
            border: 1px solid #dbe4ee;
            color: #0f172a;
            font-size: 0.85rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_vodomery_header(title: str, subtitle: str) -> None:
    render_page_styles()
    st.markdown(
        f"""
        <div class="vodomery-hero">
            <div class="vodomery-eyebrow">Monitoring</div>
            <h1 style="margin: 0;">{title}</h1>
            <div class="vodomery-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_vodomery_access_context() -> tuple[bool, tuple[str, ...]]:
    user_is_admin = is_admin()
    allowed_devices = get_allowed_devices()
    if not user_is_admin and not allowed_devices:
        st.warning("Prihlasenemu uzivateli nejsou prirazena zadna zarizeni.")
        st.stop()
    return user_is_admin, allowed_devices


def init_filter_state() -> None:
    st.session_state.setdefault(FILTER_SOURCE_KEY, "VSE")
    st.session_state.setdefault(FILTER_DEVICE_KEY, "")
    default_start = datetime.datetime.now() - datetime.timedelta(days=1)
    default_end = datetime.datetime.now()
    st.session_state.setdefault(FILTER_DATE_RANGE_KEY, (default_start.date(), default_end.date()))


def normalize_date_range(value: object) -> tuple[datetime.date, datetime.date]:
    if isinstance(value, tuple) and len(value) == 2:
        start_date, end_date = value
    elif isinstance(value, list) and len(value) == 2:
        start_date, end_date = value
    else:
        start_date = end_date = value

    if not isinstance(start_date, datetime.date):
        start_date = datetime.datetime.now().date()
    if not isinstance(end_date, datetime.date):
        end_date = start_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def build_datetime_range(start_date: datetime.date, end_date: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(end_date, datetime.time.max)
    return start_dt, end_dt


@st.cache_data(ttl=60)
def load_expected_zero_idents() -> tuple[str, ...]:
    return tuple(sorted(get_expected_zero_device_set()))


def filter_expected_zero_events(df: pd.DataFrame, identifikace: str | None = None) -> pd.DataFrame:
    if df.empty or "event_type" not in df.columns:
        return df
    expected_zero_idents = set(load_expected_zero_idents())
    if not expected_zero_idents:
        return df

    filtered = df.copy()
    if "identifikace" in filtered.columns:
        return filtered.loc[
            ~(
                (filtered["event_type"] == "ZERO_FLOW")
                & (filtered["identifikace"].isin(expected_zero_idents))
            )
        ].copy()

    if identifikace and identifikace in expected_zero_idents:
        return filtered.loc[filtered["event_type"] != "ZERO_FLOW"].copy()
    return filtered


def filter_min_duration_events(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "duration_minutes" not in df.columns:
        return df
    filtered = df.copy()
    filtered["duration_minutes"] = pd.to_numeric(filtered["duration_minutes"], errors="coerce")
    return filtered.loc[
        filtered["duration_minutes"].fillna(0) > MIN_VISIBLE_EVENT_DURATION_MINUTES
    ].copy()


@st.cache_data(ttl=60)
def load_overview_metrics(
    source_filter: str,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> dict[str, int]:
    session = get_session_pg()
    try:
        start_dt, end_dt = build_datetime_range(start_date, end_date)
        expected_zero_idents = set(load_expected_zero_idents())
        base_measurements = session.query(Mereni_vodomery)
        base_scores = session.query(VodomeryAnomalyScore)
        base_events = session.query(VodomeryAnomalyEvent)
        base_devices = session.query(Mereni_vodomery.identifikace).distinct()

        base_measurements = base_measurements.filter(Mereni_vodomery.date >= start_dt, Mereni_vodomery.date <= end_dt)
        base_scores = base_scores.filter(VodomeryAnomalyScore.date >= start_dt, VodomeryAnomalyScore.date <= end_dt)
        base_events = base_events.filter(VodomeryAnomalyEvent.start_time >= start_dt, VodomeryAnomalyEvent.start_time <= end_dt)
        base_events = base_events.filter(
            VodomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES
        )

        if not user_is_admin:
            base_measurements = base_measurements.filter(Mereni_vodomery.identifikace.in_(allowed_devices))
            base_scores = base_scores.filter(VodomeryAnomalyScore.identifikace.in_(allowed_devices))
            base_events = base_events.filter(VodomeryAnomalyEvent.identifikace.in_(allowed_devices))
            base_devices = base_devices.filter(Mereni_vodomery.identifikace.in_(allowed_devices))

        if source_filter != "VSE":
            base_measurements = base_measurements.filter(Mereni_vodomery.zdroj == source_filter)
            base_devices = base_devices.filter(Mereni_vodomery.zdroj == source_filter)
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
            hidden_zero_flow_query = base_events.filter(
                VodomeryAnomalyEvent.is_active.is_(True),
                VodomeryAnomalyEvent.event_type == "ZERO_FLOW",
                VodomeryAnomalyEvent.identifikace.in_(tuple(expected_zero_idents)),
            )
            active_events_count = max(active_events_count - hidden_zero_flow_query.count(), 0)

        return {
            "zarizeni": base_devices.count() if source_filter != "VSE" else session.query(func.count(Vodomer_areal_Zarizeni_QGIS.identifikace)).scalar() or 0,
            "mereni": base_measurements.count(),
            "anomalie": base_scores.filter(VodomeryAnomalyScore.is_anomaly.is_(True)).count(),
            "aktivni_eventy": active_events_count,
        }
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_ident_options(source_filter: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> list[str]:
    session = get_session_pg()
    try:
        query = session.query(Mereni_vodomery.identifikace).distinct()
        if not user_is_admin:
            query = query.filter(Mereni_vodomery.identifikace.in_(allowed_devices))
        if source_filter != "VSE":
            query = query.filter(Mereni_vodomery.zdroj == source_filter)

        rows = query.order_by(Mereni_vodomery.identifikace).limit(MAX_IDENT_OPTIONS).all()
        return [row[0] for row in rows]
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_recent_measurements(
    source_filter: str,
    identifikace: str | None,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        start_dt, end_dt = build_datetime_range(start_date, end_date)
        query = session.query(
            Mereni_vodomery.date,
            Mereni_vodomery.identifikace,
            Mereni_vodomery.zdroj,
            Mereni_vodomery.objem,
            Mereni_vodomery.delta,
            Mereni_vodomery.synthetic,
            Mereni_vodomery.nocni_odber,
            Mereni_vodomery.gap_detected,
            Mereni_vodomery.reset_detected,
        ).filter(Mereni_vodomery.date >= start_dt, Mereni_vodomery.date <= end_dt)

        if not user_is_admin:
            query = query.filter(Mereni_vodomery.identifikace.in_(allowed_devices))
        if source_filter != "VSE":
            query = query.filter(Mereni_vodomery.zdroj == source_filter)
        if identifikace:
            query = query.filter(Mereni_vodomery.identifikace == identifikace)

        rows = query.order_by(Mereni_vodomery.date.desc()).limit(1000).all()
        return pd.DataFrame(
            rows,
            columns=[
                "date",
                "identifikace",
                "zdroj",
                "objem",
                "delta",
                "synthetic",
                "nocni_odber",
                "gap_detected",
                "reset_detected",
            ],
        )
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_measurement_series(
    source_filter: str,
    identifikace: str,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        start_dt, end_dt = build_datetime_range(start_date, end_date)
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

        if not user_is_admin:
            query = query.filter(Mereni_vodomery.identifikace.in_(allowed_devices))
        if source_filter != "VSE":
            query = query.filter(Mereni_vodomery.zdroj == source_filter)

        rows = query.order_by(Mereni_vodomery.date.asc()).all()
        return pd.DataFrame(
            rows,
            columns=[
                "date",
                "identifikace",
                "seriove_cislo",
                "zdroj",
                "objem",
                "delta",
                "interval_minutes",
                "day_of_week",
                "slot",
                "synthetic",
                "nocni_odber",
                "gap_detected",
                "reset_detected",
            ],
        )
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_prediction_profiles(
    identifikace: str,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        if not user_is_admin and identifikace not in allowed_devices:
            return pd.DataFrame()

        latest_model_version = (
            session.query(func.max(VodomeryProfilesAnomaly.model_version))
            .filter(VodomeryProfilesAnomaly.identifikace == identifikace)
            .scalar()
        )
        if latest_model_version is None:
            return pd.DataFrame()

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
            .all()
        )
        return pd.DataFrame(
            rows,
            columns=[
                "interval_minutes",
                "day_of_week",
                "slot",
                "expected_mean",
                "expected_median",
                "expected_p10",
                "expected_p90",
                "expected_std",
                "sample_size",
                "model_version",
            ],
        )
    finally:
        session.close()


def _resolve_branch_segments(
    config_item: BranchDashboardConfig,
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
    additional_boundaries: Iterable[datetime.datetime] = (),
    merge_adjacent: bool = True,
) -> list[tuple[datetime.datetime, datetime.datetime, tuple[str, ...]]]:
    boundaries = {start_dt, end_dt}
    one_second = datetime.timedelta(seconds=1)

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
    segments: list[tuple[datetime.datetime, datetime.datetime, tuple[str, ...]]] = []

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


@st.cache_data(ttl=60)
def load_branch_day_overview(
    target_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> list[dict[str, object]]:
    day_start = datetime.datetime.combine(target_date, datetime.time.min)
    day_end = day_start + datetime.timedelta(days=1)
    hour_boundaries = [day_start + datetime.timedelta(hours=hour) for hour in range(25)]
    allowed_set = set(allowed_devices)

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
            if not user_is_admin and not required_devices.issubset(allowed_set):
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
            device_hourly_rows: list[dict[str, object]] = []
            for hour_start in pd.date_range(start=day_start, periods=24, freq="h"):
                midpoint = hour_start.to_pydatetime() + datetime.timedelta(minutes=30)
                active_hour_devices = tuple(dict.fromkeys(config_item.membership_resolver(midpoint)))
                actual_values_by_device = {
                    identifier: round(float(hourly_actual_lookup.get((identifier, hour_start), 0.0)), 3)
                    for identifier in active_hour_devices
                }
                actual_sum = round(
                    sum(actual_values_by_device.values()),
                    3,
                )
                predicted_sum = round(
                    sum(hourly_prediction_lookup.get((identifier, hour_start), 0.0) for identifier in active_hour_devices),
                    3,
                )
                for identifier, actual_value in actual_values_by_device.items():
                    device_actual_totals[identifier] = round(device_actual_totals.get(identifier, 0.0) + actual_value, 3)
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
                expected_end_of_day = round(float(pd.to_numeric(hourly_df["navazna_predikce"], errors="coerce").dropna().iloc[-1]), 3)

            device_consumption_df = pd.DataFrame(
                (
                    {
                        "identifikace": identifier,
                        "spotreba": round(float(device_actual_totals.get(identifier, 0.0)), 3),
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
                    "active_devices": active_devices,
                    "hourly_df": hourly_df,
                    "last_actual_timestamp": last_actual_timestamp.to_pydatetime() if last_actual_timestamp is not None else None,
                    "actual_total": actual_total,
                    "device_consumption_df": device_consumption_df,
                    "device_hourly_df": device_hourly_df,
                    "expected_total": expected_total,
                    "expected_end_of_day": expected_end_of_day,
                    "expected_vs_limit": expected_vs_limit,
                    "remaining_to_limit": remaining_to_limit,
                }
            )

        return branch_payloads


@st.cache_data(ttl=60)
def load_recent_anomalies(
    source_filter: str,
    identifikace: str | None,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    limit: int = 50,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        start_dt, end_dt = build_datetime_range(start_date, end_date)
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

        if not user_is_admin:
            query = query.filter(VodomeryAnomalyScore.identifikace.in_(allowed_devices))
        if identifikace:
            query = query.filter(VodomeryAnomalyScore.identifikace == identifikace)
        elif source_filter != "VSE":
            query = query.filter(
                VodomeryAnomalyScore.identifikace.in_(
                    session.query(Mereni_vodomery.identifikace)
                    .filter(Mereni_vodomery.zdroj == source_filter)
                    .distinct()
                )
            )

        rows = query.order_by(VodomeryAnomalyScore.date.desc()).limit(limit).all()
        return pd.DataFrame(
            rows,
            columns=[
                "date",
                "identifikace",
                "actual_value",
                "expected_mean",
                "z_score",
                "severity",
                "is_anomaly",
            ],
        )
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_active_events(
    source_filter: str,
    identifikace: str | None,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    limit: int = 50,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        start_dt, end_dt = build_datetime_range(start_date, end_date)
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
        query = query.filter(VodomeryAnomalyEvent.start_time >= start_dt, VodomeryAnomalyEvent.start_time <= end_dt)

        if not user_is_admin:
            query = query.filter(VodomeryAnomalyEvent.identifikace.in_(allowed_devices))
        if identifikace:
            query = query.filter(VodomeryAnomalyEvent.identifikace == identifikace)
        elif source_filter != "VSE":
            query = query.filter(
                VodomeryAnomalyEvent.identifikace.in_(
                    session.query(Mereni_vodomery.identifikace)
                    .filter(Mereni_vodomery.zdroj == source_filter)
                    .distinct()
                )
            )

        rows = query.order_by(VodomeryAnomalyEvent.start_time.desc()).limit(limit).all()
        df = pd.DataFrame(
            rows,
            columns=[
                "identifikace",
                "event_type",
                "start_time",
                "end_time",
                "duration_minutes",
                "max_z_score",
                "avg_z_score",
                "severity",
            ],
        )
        return filter_min_duration_events(filter_expected_zero_events(df, identifikace))
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_all_open_events(
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    limit: int = 500,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
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

        if not user_is_admin:
            query = query.filter(VodomeryAnomalyEvent.identifikace.in_(allowed_devices))

        rows = query.order_by(
            VodomeryAnomalyEvent.severity.asc(),
            VodomeryAnomalyEvent.duration_minutes.desc(),
            VodomeryAnomalyEvent.start_time.desc(),
        ).limit(limit).all()
        df = pd.DataFrame(
            rows,
            columns=[
                "identifikace",
                "event_type",
                "start_time",
                "end_time",
                "duration_minutes",
                "max_z_score",
                "avg_z_score",
                "severity",
            ],
        )
        return filter_min_duration_events(filter_expected_zero_events(df))
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_recent_resolved_events(
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    days: int = 7,
    limit: int = 500,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        resolved_since = datetime.datetime.now() - datetime.timedelta(days=days)
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

        if not user_is_admin:
            query = query.filter(VodomeryAnomalyEvent.identifikace.in_(allowed_devices))

        rows = query.order_by(
            VodomeryAnomalyEvent.end_time.desc(),
            VodomeryAnomalyEvent.duration_minutes.desc(),
        ).limit(limit).all()
        df = pd.DataFrame(
            rows,
            columns=[
                "identifikace",
                "event_type",
                "start_time",
                "end_time",
                "duration_minutes",
                "max_z_score",
                "avg_z_score",
                "severity",
            ],
        )
        return filter_min_duration_events(filter_expected_zero_events(df))
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_events_in_period(
    identifikace: str,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    limit: int = 200,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        if not user_is_admin and identifikace not in allowed_devices:
            return pd.DataFrame()

        start_dt, end_dt = build_datetime_range(start_date, end_date)
        rows = (
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
            .filter(VodomeryAnomalyEvent.start_time <= end_dt)
            .filter(VodomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES)
            .filter(
                (VodomeryAnomalyEvent.end_time.is_(None))
                | (VodomeryAnomalyEvent.end_time >= start_dt)
            )
            .order_by(VodomeryAnomalyEvent.start_time.desc())
            .limit(limit)
            .all()
        )
        df = pd.DataFrame(
            rows,
            columns=[
                "event_type",
                "start_time",
                "end_time",
                "duration_minutes",
                "max_z_score",
                "avg_z_score",
                "severity",
                "is_active",
                "resolved",
            ],
        )
        return filter_min_duration_events(filter_expected_zero_events(df, identifikace))
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_device_detail(identifikace: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object] | None:
    session = get_session_pg()
    try:
        if not user_is_admin and identifikace not in allowed_devices:
            return None
        device = (
            session.query(Vodomer_areal_Zarizeni_QGIS)
            .filter(Vodomer_areal_Zarizeni_QGIS.identifikace == identifikace)
            .one_or_none()
        )
        if device is None:
            return None

        return {
            "identifikace": device.identifikace,
            "seriove_cislo": device.seriove_cislo,
            "mbus": device.MBUS,
            "objekt": device.objekt,
            "patro": device.patro,
            "mistnost": device.mistnost,
            "umisteni": device.umisteni,
            "napaji": device.napaji,
            "koncovy_odberatel": device.koncovy_odberatel,
            "platnost_cejchu": device.platnost_cejchu,
            "poznamka": device.poznamka_vodomery,
        }
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_latest_measurement_summary(identifikace: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object] | None:
    session = get_session_pg()
    try:
        if not user_is_admin and identifikace not in allowed_devices:
            return None
        row = (
            session.query(
                Mereni_vodomery.date,
                Mereni_vodomery.zdroj,
                Mereni_vodomery.objem,
                Mereni_vodomery.delta,
                Mereni_vodomery.nocni_odber,
                Mereni_vodomery.synthetic,
                Mereni_vodomery.gap_detected,
                Mereni_vodomery.reset_detected,
            )
            .filter(Mereni_vodomery.identifikace == identifikace)
            .order_by(Mereni_vodomery.date.desc())
            .first()
        )
        if row is None:
            return None
        return {
            "date": row.date,
            "zdroj": row.zdroj,
            "objem": row.objem,
            "delta": row.delta,
            "nocni_odber": row.nocni_odber,
            "synthetic": row.synthetic,
            "gap_detected": row.gap_detected,
            "reset_detected": row.reset_detected,
        }
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_event_history(
    identifikace: str,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    limit: int = 20,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        if not user_is_admin and identifikace not in allowed_devices:
            return pd.DataFrame()
        rows = (
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
            .filter(VodomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES)
            .order_by(VodomeryAnomalyEvent.start_time.desc())
            .limit(limit)
            .all()
        )
        df = pd.DataFrame(
            rows,
            columns=[
                "event_type",
                "start_time",
                "end_time",
                "duration_minutes",
                "max_z_score",
                "avg_z_score",
                "severity",
                "is_active",
                "resolved",
            ],
        )
        return filter_min_duration_events(filter_expected_zero_events(df, identifikace))
    finally:
        session.close()


def render_sidebar_filters(
    user_is_admin: bool,
    allowed_devices: tuple[str, ...],
) -> tuple[str, str | None, datetime.date, datetime.date]:
    init_filter_state()

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        source_filter = st.selectbox("Zdroj", ["VSE", "AREAL", "SCVK"], key=FILTER_SOURCE_KEY)

    ident_options = load_ident_options(source_filter, allowed_devices, user_is_admin)
    current_ident = st.session_state.get(FILTER_DEVICE_KEY, "")
    if current_ident and current_ident not in ident_options:
        st.session_state[FILTER_DEVICE_KEY] = ""

    with st.sidebar:
        identifikace = st.selectbox(
            "Vodomer",
            options=[""] + ident_options,
            key=FILTER_DEVICE_KEY,
            format_func=lambda value: "Vsechny vodomery" if value == "" else value,
        )

    with st.sidebar:
        date_range = st.date_input(
            "Vybrat obdobi:",
            key=FILTER_DATE_RANGE_KEY,
            value=st.session_state[FILTER_DATE_RANGE_KEY],
        )

    start_date, end_date = normalize_date_range(date_range)
    return source_filter, identifikace or None, start_date, end_date


def format_value(value: object) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, datetime.datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, bool):
        return "ANO" if value else "NE"
    return str(value)


def format_metric_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:,}".replace(",", " ")
    return format_value(value)


def format_consumption_number(value: object, signed: bool = False) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return format_value(value)
    if pd.isna(numeric_value):
        return "-"
    if abs(numeric_value) < 0.0005:
        numeric_value = 0.0
    return f"{numeric_value:+.3f}" if signed else f"{numeric_value:.3f}"


def format_consumption_with_unit(value: object, unit: str = "m³", signed: bool = False) -> str:
    formatted = format_consumption_number(value, signed=signed)
    if formatted == "-":
        return formatted
    return f"{formatted} {unit}"


def round_consumption_columns(df: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    rounded = df.copy()
    target_columns = tuple(columns or DEFAULT_CONSUMPTION_COLUMNS)
    for column in target_columns:
        if column in rounded.columns:
            rounded[column] = pd.to_numeric(rounded[column], errors="coerce").round(3)
    return rounded


def format_consumption_dataframe(df: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    formatted = df.copy()
    target_columns = tuple(columns or DEFAULT_CONSUMPTION_COLUMNS)
    for column in target_columns:
        if column in formatted.columns:
            formatted[column] = pd.to_numeric(formatted[column], errors="coerce").map(format_consumption_number)
    return formatted


def prepare_event_display_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return df.drop(columns=["max_z_score", "avg_z_score", "Max Z-score", "Avg Z-score"], errors="ignore")


def render_filter_summary(
    source_filter: str,
    selected_ident: str | None,
    start_date: datetime.date,
    end_date: datetime.date,
    user_is_admin: bool,
    allowed_devices: tuple[str, ...],
) -> None:
    access_label = "vsechna zarizeni" if user_is_admin else f"{len(allowed_devices)} povolenych zarizeni"
    ident_label = selected_ident or "vsechny vodomery"
    range_label = f"{format_value(start_date)} - {format_value(end_date)}"
    st.markdown(
        (
            '<div class="vodomery-filters">'
            f'<span class="vodomery-pill">Zdroj: {source_filter}</span>'
            f'<span class="vodomery-pill">Vodomer: {ident_label}</span>'
            f'<span class="vodomery-pill">Obdobi: {range_label}</span>'
            f'<span class="vodomery-pill">Pristup: {access_label}</span>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_metric_cards(metrics: dict[str, int]) -> None:
    cards = [
        ("Zarizeni", metrics["zarizeni"], "Aktualne viditelna zarizeni v zadanem filtru."),
        ("Mereni", metrics["mereni"], "Pocet nactenych mereni v pracovnim vyberu."),
        ("Anomalie", metrics["anomalie"], "Detekovana anomali mereni v aktualnim vyberu."),
        ("Aktivni eventy", metrics["aktivni_eventy"], "Prave otevrene udalosti bez uzavreni."),
    ]
    metric_cols = st.columns(4)
    for col, (label, value, help_text) in zip(metric_cols, cards):
        with col:
            with st.container(border=True):
                st.metric(label, format_metric_value(value))
                st.caption(help_text)
