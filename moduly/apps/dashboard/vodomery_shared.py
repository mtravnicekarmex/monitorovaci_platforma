from __future__ import annotations

import datetime
from pathlib import Path
import sys
from collections.abc import Iterable

import pandas as pd
import streamlit as st

from app.time_utils import prague_today

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    get_vodomery_billing_options as api_get_vodomery_billing_options,
    get_vodomery_billing_period as api_get_vodomery_billing_period,
    get_vodomery_branch_day_overview as api_get_vodomery_branch_day_overview,
    get_vodomery_device_detail as api_get_vodomery_device_detail,
    get_vodomery_devices as api_get_vodomery_devices,
    get_vodomery_event_history as api_get_vodomery_event_history,
    get_vodomery_measurement_series as api_get_vodomery_measurement_series,
    get_vodomery_open_events as api_get_vodomery_open_events,
    get_vodomery_overview_metrics as api_get_vodomery_overview_metrics,
    get_vodomery_prediction_profiles as api_get_vodomery_prediction_profiles,
    get_vodomery_recent_anomalies as api_get_vodomery_recent_anomalies,
    get_vodomery_resolved_events as api_get_vodomery_resolved_events,
)
from moduly.apps.dashboard.auth import get_allowed_devices, get_auth_token, is_admin
from moduly.apps.dashboard.device_photo import (
    build_photo_data_uri,
    render_clickable_device_photo,
    resolve_photo_path,
)


MAX_IDENT_OPTIONS = 500
FILTER_SOURCE_KEY = "vodomery_source_filter"
FILTER_DEVICE_KEY = "vodomery_identifikace"
FILTER_DATE_RANGE_KEY = "vodomery_date_range"
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
    default_end = prague_today()
    default_start = default_end - datetime.timedelta(days=1)
    st.session_state.setdefault(FILTER_DATE_RANGE_KEY, (default_start, default_end))


def normalize_date_range(value: object) -> tuple[datetime.date, datetime.date]:
    if isinstance(value, tuple) and len(value) == 2:
        start_date, end_date = value
    elif isinstance(value, list) and len(value) == 2:
        start_date, end_date = value
    else:
        start_date = end_date = value

    if not isinstance(start_date, datetime.date):
        start_date = prague_today()
    if not isinstance(end_date, datetime.date):
        end_date = start_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def build_datetime_range(start_date: datetime.date, end_date: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(end_date, datetime.time.max)
    return start_dt, end_dt


def require_dashboard_api_token() -> str:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return access_token


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
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    return api_get_vodomery_overview_metrics(
        access_token,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        source_filter=source_filter,
    )


@st.cache_data(ttl=60)
def load_ident_options(source_filter: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> list[str]:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    return api_get_vodomery_devices(access_token, source_filter=source_filter, limit=MAX_IDENT_OPTIONS)


@st.cache_data(ttl=60)
def load_measurement_series(
    source_filter: str,
    identifikace: str,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> pd.DataFrame:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_vodomery_measurement_series(
        access_token,
        identifikace=identifikace,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        source_filter=source_filter,
    )
    return pd.DataFrame(
        rows,
        columns=[
            "date",
            "identifikace",
            "seriove_cislo",
            "zdroj",
            "objem",
            "delta",
            "platne",
            "interval_minutes",
            "day_of_week",
            "slot",
            "synthetic",
            "nocni_odber",
            "gap_detected",
            "reset_detected",
        ],
    )


@st.cache_data(ttl=60)
def load_prediction_profiles(
    identifikace: str,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> pd.DataFrame:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_vodomery_prediction_profiles(
        access_token,
        identifikace=identifikace,
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


@st.cache_data(ttl=60)
def load_billing_options() -> list[dict[str, object]]:
    access_token = require_dashboard_api_token()
    return api_get_vodomery_billing_options(access_token)


@st.cache_data(ttl=60)
def load_billing_period(
    billing_ident: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> dict[str, object]:
    access_token = require_dashboard_api_token()
    payload = api_get_vodomery_billing_period(
        access_token,
        billing_ident=billing_ident,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    for row in payload.get("device_rows", []):
        row["active_from"] = pd.to_datetime(row.get("active_from"), errors="coerce")
        row["active_to"] = pd.to_datetime(row.get("active_to"), errors="coerce")
    for row in payload.get("assignment_rows", []):
        row["start_time"] = pd.to_datetime(row.get("start_time"), errors="coerce")
        row["end_time"] = pd.to_datetime(row.get("end_time"), errors="coerce")
    for row in payload.get("segment_rows", []):
        row["start_time"] = pd.to_datetime(row.get("start_time"), errors="coerce")
        row["end_time"] = pd.to_datetime(row.get("end_time"), errors="coerce")
    return payload


@st.cache_data(ttl=60)
def load_branch_day_overview(
    target_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> list[dict[str, object]]:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_vodomery_branch_day_overview(
        access_token,
        target_date=target_date.isoformat(),
    )
    branch_payloads: list[dict[str, object]] = []
    for row in rows:
        hourly_df = pd.DataFrame(row.get("hourly_rows", []))
        if "date" in hourly_df.columns:
            hourly_df["date"] = pd.to_datetime(hourly_df["date"], errors="coerce")

        device_consumption_df = pd.DataFrame(row.get("device_consumption_rows", []))

        device_hourly_df = pd.DataFrame(row.get("device_hourly_rows", []))
        if "date" in device_hourly_df.columns:
            device_hourly_df["date"] = pd.to_datetime(device_hourly_df["date"], errors="coerce")

        branch_payloads.append(
            {
                "key": row["key"],
                "title": row["title"],
                "billing_ident": row["billing_ident"],
                "daily_limit": row.get("daily_limit"),
                "active_devices": tuple(row.get("active_devices", [])),
                "hourly_df": hourly_df,
                "last_actual_timestamp": pd.to_datetime(row["last_actual_timestamp"]).to_pydatetime()
                if row.get("last_actual_timestamp")
                else None,
                "actual_total": row.get("actual_total"),
                "device_consumption_df": device_consumption_df,
                "device_hourly_df": device_hourly_df,
                "expected_total": row.get("expected_total"),
                "expected_end_of_day": row.get("expected_end_of_day"),
                "expected_vs_limit": row.get("expected_vs_limit"),
                "remaining_to_limit": row.get("remaining_to_limit"),
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
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_vodomery_recent_anomalies(
        access_token,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        identifikace=identifikace,
        source_filter=source_filter,
        limit=limit,
    )
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


@st.cache_data(ttl=60)
def load_all_open_events(
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    limit: int = 500,
) -> pd.DataFrame:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_vodomery_open_events(
        access_token,
        limit=limit,
    )
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
    return filter_min_duration_events(df)


@st.cache_data(ttl=60)
def load_recent_resolved_events(
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    days: int = 7,
    limit: int = 500,
) -> pd.DataFrame:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_vodomery_resolved_events(
        access_token,
        days=days,
        limit=limit,
    )
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
    return filter_min_duration_events(df)


@st.cache_data(ttl=60)
def load_device_detail(identifikace: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object] | None:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    return api_get_vodomery_device_detail(
        access_token,
        identifikace=identifikace,
    )


@st.cache_data(ttl=60)
def load_event_history(
    identifikace: str,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    limit: int = 20,
) -> pd.DataFrame:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_vodomery_event_history(
        access_token,
        identifikace=identifikace,
        limit=limit,
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
    return filter_min_duration_events(df)


def resolve_device_photo_path(photo_value: object) -> Path | None:
    return resolve_photo_path(photo_value, project_root=PROJECT_ROOT)


def build_device_photo_data_uri(photo_path: Path | None) -> str | None:
    return build_photo_data_uri(photo_path)


def render_device_photo(device_detail: dict[str, object] | None) -> bool:
    return render_clickable_device_photo(
        device_detail,
        project_root=PROJECT_ROOT,
        aria_label="Zvětšit fotografii vodoměru",
    )


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
    formatted = df.drop(
        columns=["max_z_score", "avg_z_score", "Max Z-score", "Avg Z-score"],
        errors="ignore",
    ).copy()
    for column in ("start_time", "end_time", "Zacatek", "Konec"):
        if column not in formatted.columns:
            continue
        datetimes = pd.to_datetime(formatted[column], errors="coerce")
        formatted[column] = datetimes.dt.strftime("%d.%m.%Y %H:%M").where(datetimes.notna(), None)
    return formatted


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
