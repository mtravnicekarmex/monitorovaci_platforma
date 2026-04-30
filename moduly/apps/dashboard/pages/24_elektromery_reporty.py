from __future__ import annotations

from pathlib import Path
import sys

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.elektromery_reports import (
    ElektromeryDashboardReportError,
    REPORT_PERIOD_OPTIONS,
    build_consumption_curve,
    build_device_summary,
    build_ote_pdf_report,
    build_ote_report_pdf_filename,
    build_threshold_exceedance,
    describe_selected_identifications,
    ote_records_to_dataframe,
    render_ote_report_pdf,
    resolve_report_period,
    summarize_report,
)
from moduly.apps.dashboard.vodomery_shared import render_page_styles
from core.db.connect import get_session_pg
from moduly.mereni.elektromery.database.models import Elektromer_OTE_Mereni


REPORT_RESULT_KEY = "elektromery_reports_result"


st.set_page_config(
    page_title="Elektroměry - Reporty",
    page_icon="📈",
    layout="wide",
)


require_page_access("elektromery_reports")


def format_datetime(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return "-"
    return timestamp.strftime("%d.%m.%Y %H:%M")


def format_energy(value: object, unit: str = "kWh") -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value):
        return "-"
    if abs(numeric_value) < 0.0005:
        numeric_value = 0.0
    return f"{numeric_value:.3f} {unit}"


@st.cache_data(ttl=60)
def load_ote_data_bounds() -> dict[str, object]:
    session = get_session_pg()
    try:
        row = (
            session.query(
                func.min(Elektromer_OTE_Mereni.date).label("date_min"),
                func.max(Elektromer_OTE_Mereni.date).label("date_max"),
                func.count(Elektromer_OTE_Mereni.recid).label("measurement_count"),
                func.count(func.distinct(Elektromer_OTE_Mereni.identifikace)).label("device_count"),
            )
            .one()
        )
        return {
            "date_min": row.date_min,
            "date_max": row.date_max,
            "measurement_count": int(row.measurement_count or 0),
            "device_count": int(row.device_count or 0),
        }
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_ote_identifikace_options() -> tuple[str, ...]:
    session = get_session_pg()
    try:
        rows = (
            session.query(Elektromer_OTE_Mereni.identifikace)
            .filter(Elektromer_OTE_Mereni.identifikace.is_not(None))
            .distinct()
            .order_by(Elektromer_OTE_Mereni.identifikace.asc())
            .all()
        )
        return tuple(str(row.identifikace).strip() for row in rows if row.identifikace and str(row.identifikace).strip())
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_ote_measurements(period_start, period_end, selected_identifications: tuple[str, ...] | None = None) -> pd.DataFrame:
    if selected_identifications is not None and len(selected_identifications) == 0:
        return pd.DataFrame(columns=["date", "identifikace", "seriove_cislo", "spotreba_kwh", "source_file"])

    session = get_session_pg()
    try:
        query = (
            session.query(
                Elektromer_OTE_Mereni.date,
                Elektromer_OTE_Mereni.identifikace,
                Elektromer_OTE_Mereni.seriove_cislo,
                Elektromer_OTE_Mereni.objem,
                Elektromer_OTE_Mereni.source_file,
            )
            .filter(
                Elektromer_OTE_Mereni.date >= period_start,
                Elektromer_OTE_Mereni.date < period_end,
                Elektromer_OTE_Mereni.objem.is_not(None),
            )
        )
        if selected_identifications:
            query = query.filter(Elektromer_OTE_Mereni.identifikace.in_(selected_identifications))
        rows = (
            query
            .order_by(Elektromer_OTE_Mereni.date.asc(), Elektromer_OTE_Mereni.identifikace.asc())
            .all()
        )
        return ote_records_to_dataframe(
            {
                "date": row.date,
                "identifikace": row.identifikace,
                "seriove_cislo": row.seriove_cislo,
                "objem": row.objem,
                "source_file": row.source_file,
            }
            for row in rows
        )
    finally:
        session.close()


def build_curve_chart(curve_df: pd.DataFrame, reserved_power_kw: float | None) -> alt.Chart:
    chart_source = curve_df.copy()
    chart_source["spotreba_kwh"] = pd.to_numeric(chart_source["spotreba_kwh"], errors="coerce").round(3)
    chart_source["odber_kw"] = pd.to_numeric(chart_source["odber_kw"], errors="coerce").round(3)

    base = alt.Chart(chart_source).encode(
        x=alt.X("date:T", title=None),
        tooltip=[
            alt.Tooltip("date:T", title="Datum"),
            alt.Tooltip("spotreba_kwh:Q", title="Spotřeba [kWh]", format=".3f"),
            alt.Tooltip("odber_kw:Q", title="Odběr [kW]", format=".3f"),
        ],
    )
    line = base.mark_line(color="#dc2626", strokeWidth=2.6).encode(
        y=alt.Y("odber_kw:Q", title="Odběr [kW]"),
    )
    points = base.mark_point(color="#dc2626", size=24, opacity=0.72).encode(
        y=alt.Y("odber_kw:Q", title="Odběr [kW]"),
    )

    chart = line + points
    if reserved_power_kw is not None and reserved_power_kw > 0:
        limit_df = pd.DataFrame({"rezervovana_hladina_kw": [float(reserved_power_kw)]})
        limit = alt.Chart(limit_df).mark_rule(color="#111827", strokeDash=[6, 4], strokeWidth=2).encode(
            y=alt.Y("rezervovana_hladina_kw:Q", title="Odběr [kW]"),
            tooltip=[alt.Tooltip("rezervovana_hladina_kw:Q", title="Rezervovaná hladina [kW]", format=".3f")],
        )
        chart = chart + limit

    return chart.properties(height=360).interactive()


def render_report_result(
    *,
    report_period,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    device_summary_df: pd.DataFrame,
    reserved_power_kw: float | None,
    summary: dict[str, object],
    exceedance_df: pd.DataFrame,
    pdf_bytes: bytes | None,
    pdf_filename: str | None,
    pdf_error: str | None,
    selected_identifications: tuple[str, ...] = (),
    available_identification_count: int = 0,
) -> None:
    metric_cols = st.columns(5)
    metric_cols[0].metric("Spotřeba", format_energy(summary["total_consumption_kwh"]))
    metric_cols[1].metric("Max. odběr", format_energy(summary["max_power_kw"], unit="kW"))
    metric_cols[2].metric("Datum maxima", format_datetime(summary["max_power_at"]))
    metric_cols[3].metric("Měřidla", summary["device_count"])
    metric_cols[4].metric("Překročení", len(exceedance_df))
    st.caption(
        f"Výběr odběrných míst: {describe_selected_identifications(selected_identifications, total_available_count=available_identification_count)}"
    )

    if curve_df.empty:
        st.info("Pro zvolené období a výběr odběrných míst nejsou v databázi žádná OTE data.")
        return

    chart = build_curve_chart(curve_df, reserved_power_kw)
    st.altair_chart(chart, width="stretch")

    table_cols = st.columns(2)
    with table_cols[0]:
        st.subheader("Souhrn měřidel")
        st.dataframe(device_summary_df, width="stretch", hide_index=True)
    with table_cols[1]:
        st.subheader("Překročení hladiny")
        if exceedance_df.empty:
            if reserved_power_kw is None or reserved_power_kw <= 0:
                st.info("Rezervovaná hladina nebyla zadána.")
            else:
                st.info("Bez překročení ve zvoleném období.")
        else:
            st.dataframe(exceedance_df, width="stretch", hide_index=True)


def _build_report_result(
    *,
    report_period,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    device_summary_df: pd.DataFrame,
    reserved_power_kw: float | None,
    selected_identifications: tuple[str, ...],
    available_identification_count: int,
) -> dict[str, object]:
    summary = summarize_report(period_df, curve_df)
    exceedance_df = build_threshold_exceedance(curve_df, reserved_power_kw)
    pdf_bytes = None
    pdf_filename = None
    pdf_error = None

    if not curve_df.empty:
        pdf_report = build_ote_pdf_report(
            period=report_period,
            period_label=period_label,
            period_df=period_df,
            curve_df=curve_df,
            device_summary_df=device_summary_df,
            reserved_power_kw=reserved_power_kw,
            selected_identifications=selected_identifications,
            available_identification_count=available_identification_count,
        )
        try:
            pdf_bytes = render_ote_report_pdf(pdf_report)
            pdf_filename = build_ote_report_pdf_filename(pdf_report)
        except ElektromeryDashboardReportError as exc:
            pdf_error = str(exc)
        except Exception as exc:
            pdf_error = f"PDF report se nepodařilo připravit: {exc.__class__.__name__}."

    return {
        "report_period": report_period,
        "period_label": period_label,
        "period_df": period_df,
        "curve_df": curve_df,
        "device_summary_df": device_summary_df,
        "reserved_power_kw": reserved_power_kw,
        "selected_identifications": selected_identifications,
        "available_identification_count": available_identification_count,
        "summary": summary,
        "exceedance_df": exceedance_df,
        "pdf_bytes": pdf_bytes,
        "pdf_filename": pdf_filename,
        "pdf_error": pdf_error,
    }


def render_dashboard() -> None:
    render_page_styles()
    st.title("Reporty elektroměrů")
    st.caption("Manuální vytvoření reportu z PostgreSQL tabulky `dbo.Mereni_elektromery_OTE`.")

    bounds = load_ote_data_bounds()
    if not bounds["measurement_count"] or bounds["date_min"] is None or bounds["date_max"] is None:
        st.info("V tabulce `dbo.Mereni_elektromery_OTE` zatím nejsou žádná data pro report.")
        return

    identifikace_options = load_ote_identifikace_options()
    if not identifikace_options:
        st.info("V tabulce `dbo.Mereni_elektromery_OTE` nejsou dostupné žádné identifikace odběrných míst.")
        return

    min_date = pd.to_datetime(bounds["date_min"]).date()
    max_date = pd.to_datetime(bounds["date_max"]).date()
    label_to_kind = {label: key for key, label in REPORT_PERIOD_OPTIONS.items()}

    form_cols = st.columns((1.1, 1.1, 1.1, 2.7))
    with form_cols[0]:
        selected_period_label = st.selectbox("Typ reportu", list(label_to_kind.keys()))
    with form_cols[1]:
        selected_date = st.date_input(
            "Datum období",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
        )
    with form_cols[2]:
        reserved_power_kw = st.number_input(
            "Rezervovaná hladina [kW]",
            min_value=0.0,
            value=0.0,
            step=10.0,
        )
    with form_cols[3]:
        selected_identifications = st.multiselect(
            "Zahrnout do reportu",
            options=list(identifikace_options),
            default=list(identifikace_options),
            help="Hodnoty jsou načtené jako unikátní `identifikace` z PostgreSQL tabulky `dbo.Mereni_elektromery_OTE`.",
        )
    st.caption(f"Načteno {len(identifikace_options)} unikátních odběrných míst z databáze.")

    action_cols = st.columns((1.2, 1.2, 4))
    with action_cols[0]:
        submitted = st.button("Vytvořit report", type="primary", use_container_width=True)

    if submitted:
        selected_identifications_tuple = tuple(str(item).strip() for item in selected_identifications if str(item).strip())
        if not selected_identifications_tuple:
            st.session_state.pop(REPORT_RESULT_KEY, None)
            st.warning("Vyberte alespoň jedno odběrné místo.")
            return

        period_kind = label_to_kind[selected_period_label]
        report_period = resolve_report_period(period_kind, selected_date)
        with st.spinner("Vytvářím report a připravuji PDF..."):
            period_df = load_ote_measurements(
                report_period.period_start,
                report_period.period_end,
                selected_identifications_tuple,
            )
            curve_df = build_consumption_curve(period_df, report_period)
            device_summary_df = build_device_summary(period_df)
            period_label = (
                f"{report_period.label} report | {report_period.date_range_label} | krok {report_period.bucket_label}"
            )
            st.session_state[REPORT_RESULT_KEY] = _build_report_result(
                report_period=report_period,
                period_label=period_label,
                period_df=period_df,
                curve_df=curve_df,
                device_summary_df=device_summary_df,
                reserved_power_kw=reserved_power_kw,
                selected_identifications=selected_identifications_tuple,
                available_identification_count=len(identifikace_options),
            )

    report_result = st.session_state.get(REPORT_RESULT_KEY)
    if report_result is None:
        return

    with action_cols[1]:
        pdf_bytes = report_result.get("pdf_bytes")
        pdf_filename = report_result.get("pdf_filename")
        pdf_error = report_result.get("pdf_error")
        if pdf_bytes is not None and pdf_filename is not None:
            st.download_button(
                "Stáhnout PDF report",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf",
                width="stretch",
            )
        elif pdf_error:
            st.button("Stáhnout PDF report", disabled=True, use_container_width=True)
            st.warning(pdf_error)

    render_report_result(**report_result)


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodařilo se načíst OTE data z PostgreSQL.")
    st.exception(exc)
