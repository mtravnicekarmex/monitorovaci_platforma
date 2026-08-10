from __future__ import annotations

from dataclasses import dataclass
import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.time_utils import prague_today
from moduly.apps.dashboard.auth import current_username, require_page_access
from moduly.apps.dashboard.vodomery_shared import render_page_styles
from moduly.mereni.plynomery.branches import PLYNOMERY_BRANCH_CONFIGS
from moduly.mereni.plynomery.reporting.monthly_billing_report import (
    PlynomeryMonthlyBillingReportError,
    build_monthly_plynomery_billing_report,
    build_monthly_plynomery_billing_report_pdf_filename,
    render_monthly_plynomery_billing_report_pdf,
)
from services.api.services.plynomery_billing import (
    BillingReadingInput,
    BillingReadingRecord,
    PlynomeryBillingError,
    list_billing_readings_for_period,
    load_latest_previous_billing_readings,
    resolve_month_period_from_date,
    upsert_billing_readings,
)


PAGE_KEY = "plynomery_billing_readings"
REPORT_RESULT_KEY = "plynomery_billing_report_result"
SAVE_STATUS_KEY = "plynomery_billing_save_status"


@dataclass(frozen=True)
class ReportInputIssue:
    identifikace: str
    title: str
    message: str


st.set_page_config(
    page_title="Plynoměry - Fakturacni odecty",
    page_icon="🧾",
    layout="wide",
)


require_page_access(PAGE_KEY)


def _default_month_date() -> datetime.date:
    today = prague_today()
    current_month_start = today.replace(day=1)
    previous_month_end = current_month_start - datetime.timedelta(days=1)
    return previous_month_end.replace(day=1)


def _format_volume(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "-"


def _format_datetime(value: datetime.datetime | None) -> str:
    return "-" if value is None else value.strftime("%d.%m.%Y %H:%M")


def _parse_volume(raw_value: object, *, identifikace: str) -> float:
    normalized = str(raw_value or "").strip().replace(" ", "").replace(",", ".")
    if not normalized:
        raise ValueError(f"{identifikace}: stav není vyplněný.")
    try:
        value = float(normalized)
    except ValueError as exc:
        raise ValueError(f"{identifikace}: stav musí být číslo.") from exc
    if value < 0:
        raise ValueError(f"{identifikace}: stav nesmí být záporný.")
    return value


def _reading_widget_key(field: str, period_start: datetime.datetime, identifikace: str) -> str:
    return f"billing_{field}_{period_start:%Y%m}_{identifikace}"


def _build_current_reading_lookup(
    rows: tuple[BillingReadingRecord, ...],
) -> dict[str, BillingReadingRecord]:
    return {row.identifikace: row for row in rows}


def _safe_consumption(
    previous: BillingReadingRecord | None,
    current: BillingReadingRecord | None,
) -> float | None:
    if previous is None or current is None:
        return None
    consumption = float(current.objem) - float(previous.objem)
    if consumption < -0.0005:
        return None
    return round(max(consumption, 0.0), 3)


def _build_readings_overview_dataframe(
    current_readings: dict[str, BillingReadingRecord],
    previous_readings: dict[str, BillingReadingRecord],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for config in PLYNOMERY_BRANCH_CONFIGS:
        current = current_readings.get(config.billing_ident)
        previous = previous_readings.get(config.billing_ident)
        rows.append(
            {
                "Větev": config.title,
                "Fakturační plynoměr": config.billing_ident,
                "Předchozí stav": _format_volume(None if previous is None else previous.objem),
                "Předchozí odečet": _format_datetime(None if previous is None else previous.reading_at),
                "Aktuální stav": _format_volume(None if current is None else current.objem),
                "Aktuální odečet": _format_datetime(None if current is None else current.reading_at),
                "Fakturační spotřeba": _format_volume(_safe_consumption(previous, current)),
                "Podružné plynoměry": ", ".join(config.direct_submeter_idents) or "bez podružných",
            }
        )
    return pd.DataFrame(rows)


def _build_report_summary_dataframe(report) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for branch in report.branches:
        rows.append(
            {
                "Větev": branch.title,
                "Fakturační plynoměr": branch.billing_ident,
                "Fakturační spotřeba": _format_volume(branch.billing_consumption),
                "Součet přímých podružných": _format_volume(branch.submeter_consumption_total),
                "Rozdíl fakturace - podružné": _format_volume(branch.difference_vs_submeters),
                "Pokrytí podružnými": (
                    "-" if branch.submeter_coverage_percent is None else f"{branch.submeter_coverage_percent:.1f} %"
                ),
                "Chybí podružné": branch.missing_direct_submeter_count,
            }
        )
    return pd.DataFrame(rows)


def _build_input_issues_dataframe(
    issues: tuple[ReportInputIssue, ...],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Větev": issue.title,
                "Fakturační plynoměr": issue.identifikace,
                "Problém": issue.message,
            }
            for issue in issues
        ]
    )


def _validate_report_input_issues(
    *,
    current_readings: dict[str, BillingReadingRecord],
    previous_readings: dict[str, BillingReadingRecord],
) -> tuple[ReportInputIssue, ...]:
    issues: list[ReportInputIssue] = []
    for config in PLYNOMERY_BRANCH_CONFIGS:
        current = current_readings.get(config.billing_ident)
        previous = previous_readings.get(config.billing_ident)
        if current is None:
            issues.append(
                ReportInputIssue(
                    identifikace=config.billing_ident,
                    title=config.title,
                    message="Chybí aktuální fakturační stav pro zvolené období.",
                )
            )
            continue
        if previous is None:
            issues.append(
                ReportInputIssue(
                    identifikace=config.billing_ident,
                    title=config.title,
                    message="Chybí předchozí fakturační stav pro výpočet spotřeby.",
                )
            )
            continue
        if current.reading_at <= previous.reading_at:
            issues.append(
                ReportInputIssue(
                    identifikace=config.billing_ident,
                    title=config.title,
                    message="Aktuální čas odečtu musí být po předchozím odečtu.",
                )
            )
            continue
        if _safe_consumption(previous, current) is None:
            issues.append(
                ReportInputIssue(
                    identifikace=config.billing_ident,
                    title=config.title,
                    message="Aktuální stav je nižší než předchozí fakturační stav.",
                )
            )
    return tuple(issues)


def _collect_form_readings(
    *,
    period_start: datetime.datetime,
    period_end: datetime.datetime,
    previous_readings: dict[str, BillingReadingRecord],
) -> tuple[tuple[BillingReadingInput, ...], list[str]]:
    readings: list[BillingReadingInput] = []
    errors: list[str] = []
    entered_by = current_username() or None

    for config in PLYNOMERY_BRANCH_CONFIGS:
        raw_value = st.session_state.get(_reading_widget_key("objem", period_start, config.billing_ident), "")
        if not str(raw_value or "").strip():
            continue
        reading_date = st.session_state.get(_reading_widget_key("date", period_start, config.billing_ident))
        reading_time = st.session_state.get(_reading_widget_key("time", period_start, config.billing_ident))
        note = (
            str(st.session_state.get(_reading_widget_key("note", period_start, config.billing_ident), "") or "").strip()
            or None
        )
        if not isinstance(reading_date, datetime.date):
            errors.append(f"{config.billing_ident}: datum odečtu není platné.")
            continue
        if not isinstance(reading_time, datetime.time):
            errors.append(f"{config.billing_ident}: čas odečtu není platný.")
            continue
        try:
            objem = _parse_volume(raw_value, identifikace=config.billing_ident)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        reading_at = datetime.datetime.combine(reading_date, reading_time)
        previous = previous_readings.get(config.billing_ident)
        if previous is not None and reading_at <= previous.reading_at:
            errors.append(
                f"{config.billing_ident}: čas odečtu musí být po předchozím "
                f"odečtu {_format_datetime(previous.reading_at)}."
            )
            continue
        if previous is not None and objem < float(previous.objem) - 0.0005:
            errors.append(
                f"{config.billing_ident}: aktuální stav nesmí být nižší než "
                f"předchozí stav {_format_volume(previous.objem)}."
            )
            continue
        readings.append(
            BillingReadingInput(
                identifikace=config.billing_ident,
                period_start=period_start,
                period_end=period_end,
                reading_at=reading_at,
                objem=objem,
                entered_by=entered_by,
                note=note,
            )
        )
    return tuple(readings), errors


def _render_reading_form(
    *,
    period_start: datetime.datetime,
    period_end: datetime.datetime,
    current_readings: dict[str, BillingReadingRecord],
    previous_readings: dict[str, BillingReadingRecord],
) -> None:
    st.subheader("Zadání stavů fakturačních plynoměrů")
    st.caption(
        "Vyplňují se kumulativní stavy fakturačních plynoměrů. "
        "Prázdný řádek se neukládá a existující řádek tím nesmaže."
    )

    with st.form("plynomery_billing_readings_form"):
        header_cols = st.columns((1.2, 1.2, 1, 1, 1.8))
        header_cols[0].markdown("**Fakturační plynoměr**")
        header_cols[1].markdown("**Stav**")
        header_cols[2].markdown("**Datum odečtu**")
        header_cols[3].markdown("**Čas odečtu**")
        header_cols[4].markdown("**Poznámka**")

        default_reading_at = period_end
        for config in PLYNOMERY_BRANCH_CONFIGS:
            existing = current_readings.get(config.billing_ident)
            reading_at = existing.reading_at if existing is not None else default_reading_at
            cols = st.columns((1.2, 1.2, 1, 1, 1.8))
            cols[0].write(config.billing_ident)
            cols[0].caption(config.title)
            cols[1].text_input(
                "Stav",
                value="" if existing is None else f"{existing.objem:.3f}",
                key=_reading_widget_key("objem", period_start, config.billing_ident),
                label_visibility="collapsed",
                placeholder="např. 12345,678",
            )
            cols[2].date_input(
                "Datum odečtu",
                value=reading_at.date(),
                key=_reading_widget_key("date", period_start, config.billing_ident),
                label_visibility="collapsed",
            )
            cols[3].time_input(
                "Čas odečtu",
                value=reading_at.time().replace(second=0, microsecond=0),
                key=_reading_widget_key("time", period_start, config.billing_ident),
                label_visibility="collapsed",
            )
            cols[4].text_input(
                "Poznámka",
                value="" if existing is None or existing.note is None else str(existing.note),
                key=_reading_widget_key("note", period_start, config.billing_ident),
                label_visibility="collapsed",
            )

        submitted = st.form_submit_button("Uložit odečty", type="primary", width="stretch")

    if not submitted:
        return

    readings, errors = _collect_form_readings(
        period_start=period_start,
        period_end=period_end,
        previous_readings=previous_readings,
    )
    if errors:
        for error in errors:
            st.error(error)
        return
    if not readings:
        st.warning("Není vyplněný žádný stav k uložení.")
        return

    saved_count = upsert_billing_readings(readings)
    st.session_state[SAVE_STATUS_KEY] = f"Uloženo {saved_count} fakturačních odečtů."
    st.session_state.pop(REPORT_RESULT_KEY, None)
    st.rerun()


def _render_report_actions(
    target_month: datetime.date,
    *,
    input_issues: tuple[ReportInputIssue, ...],
) -> None:
    st.subheader("Měsíční report")
    st.caption("Report se vytváří pouze ručně po zadání fakturačních stavů.")

    if input_issues:
        st.warning(
            "Report zatím nelze vytvořit: doplň nebo oprav fakturační odečty níže."
        )
        st.dataframe(
            _build_input_issues_dataframe(input_issues),
            width="stretch",
            hide_index=True,
        )

    if st.button(
        "Vytvor report",
        type="primary",
        width="stretch",
        disabled=bool(input_issues),
    ):
        with st.spinner("Vytvářím report a připravuji PDF..."):
            report = build_monthly_plynomery_billing_report(
                year=target_month.year,
                month=target_month.month,
            )
            pdf_bytes = None
            pdf_filename = build_monthly_plynomery_billing_report_pdf_filename(report)
            pdf_error = None
            try:
                pdf_bytes = render_monthly_plynomery_billing_report_pdf(report)
            except PlynomeryMonthlyBillingReportError as exc:
                pdf_error = str(exc)
            st.session_state[REPORT_RESULT_KEY] = {
                "report": report,
                "pdf_bytes": pdf_bytes,
                "pdf_filename": pdf_filename,
                "pdf_error": pdf_error,
            }

    report_result = st.session_state.get(REPORT_RESULT_KEY)
    if not report_result:
        return

    report = report_result["report"]
    st.dataframe(_build_report_summary_dataframe(report), width="stretch", hide_index=True)

    pdf_bytes = report_result.get("pdf_bytes")
    pdf_filename = report_result.get("pdf_filename")
    pdf_error = report_result.get("pdf_error")
    if pdf_bytes and pdf_filename:
        st.download_button(
            "Stáhnout PDF report",
            data=pdf_bytes,
            file_name=pdf_filename,
            mime="application/pdf",
            width="stretch",
        )
    elif pdf_error:
        st.warning(f"PDF se nepodařilo vytvořit: {pdf_error}")


def render_dashboard() -> None:
    render_page_styles()
    st.title("Fakturacni odecty plynomeru")
    st.caption(
        "Ruční zadání měsíčních stavů fakturačních plynoměrů INNOGY a ruční vytvoření měsíčního PDF reportu."
    )

    save_status = st.session_state.pop(SAVE_STATUS_KEY, None)
    if save_status:
        st.success(str(save_status))

    target_month = st.date_input(
        "Měsíc reportu",
        value=_default_month_date(),
        help="Bere se měsíc vybraného data. Odečet může mít samostatné datum a čas.",
    )
    if not isinstance(target_month, datetime.date):
        st.error("Vybraný měsíc není platný.")
        return

    period_start, period_end = resolve_month_period_from_date(target_month)
    st.info(f"Období reportu: {period_start:%d.%m.%Y} - {(period_end - datetime.timedelta(days=1)):%d.%m.%Y}")

    current_readings = _build_current_reading_lookup(
        list_billing_readings_for_period(period_start, period_end)
    )
    previous_readings = load_latest_previous_billing_readings(period_start)
    input_issues = _validate_report_input_issues(
        current_readings=current_readings,
        previous_readings=previous_readings,
    )

    st.subheader("Aktuální stav dat pro zvolené období")
    st.dataframe(
        _build_readings_overview_dataframe(current_readings, previous_readings),
        width="stretch",
        hide_index=True,
    )

    _render_reading_form(
        period_start=period_start,
        period_end=period_end,
        current_readings=current_readings,
        previous_readings=previous_readings,
    )
    _render_report_actions(target_month, input_issues=input_issues)


try:
    render_dashboard()
except (SQLAlchemyError, PlynomeryBillingError) as exc:
    st.error("Nepodařilo se zpracovat fakturační odečty plynoměrů.")
    st.exception(exc)
