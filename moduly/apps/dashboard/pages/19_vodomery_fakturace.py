from __future__ import annotations

import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

from app.time_utils import prague_today


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.vodomery_shared import (
    format_consumption_with_unit,
    load_billing_options,
    load_billing_period,
    normalize_date_range,
    render_vodomery_header,
)


FILTER_BILLING_IDENT_KEY = "vodomery_billing_ident"
FILTER_DATE_RANGE_KEY = "vodomery_billing_date_range"
FILTER_INVOICE_AMOUNT_KEY = "vodomery_billing_invoice_amount"
PRICE_INTERVAL_IDS_KEY = "vodomery_billing_price_interval_ids"
PRICE_INTERVAL_SEQ_KEY = "vodomery_billing_price_interval_seq"
PRICE_INTERVAL_START_PREFIX = "vodomery_billing_price_interval_start"
PRICE_INTERVAL_END_PREFIX = "vodomery_billing_price_interval_end"
PRICE_INTERVAL_PRICE_PREFIX = "vodomery_billing_price_interval_price"


st.set_page_config(
    page_title="Vodoměry - Fakturace",
    page_icon="🧾",
    layout="wide",
)


require_page_access("vodomery_billing")


def get_default_date_range() -> tuple[datetime.date, datetime.date]:
    today = prague_today()
    current_month_start = today.replace(day=1)
    previous_month_end = current_month_start - datetime.timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return previous_month_start, previous_month_end


def init_page_state(default_billing_ident: str) -> None:
    default_start, default_end = get_default_date_range()
    st.session_state.setdefault(FILTER_BILLING_IDENT_KEY, default_billing_ident)
    st.session_state.setdefault(FILTER_DATE_RANGE_KEY, (default_start, default_end))
    st.session_state.setdefault(FILTER_INVOICE_AMOUNT_KEY, 0.0)
    st.session_state.setdefault(PRICE_INTERVAL_IDS_KEY, [])
    st.session_state.setdefault(PRICE_INTERVAL_SEQ_KEY, 0)


def format_currency(value: object) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value):
        return "-"
    return f"{numeric_value:,.2f}".replace(",", " ").replace(".", ",") + " Kč"


def format_percent(value: object) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value):
        return "-"
    return f"{numeric_value:.1f} %"


def format_timestamp(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return "-"
    return timestamp.strftime("%d.%m.%Y %H:%M")


def build_period_datetime_range(
    start_date: datetime.date,
    end_date: datetime.date,
) -> tuple[datetime.datetime, datetime.datetime]:
    period_start = datetime.datetime.combine(start_date, datetime.time.min)
    period_end = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min)
    return period_start, period_end


def get_price_interval_widget_keys(interval_id: int) -> tuple[str, str, str]:
    return (
        f"{PRICE_INTERVAL_START_PREFIX}_{interval_id}",
        f"{PRICE_INTERVAL_END_PREFIX}_{interval_id}",
        f"{PRICE_INTERVAL_PRICE_PREFIX}_{interval_id}",
    )


def add_price_interval(start_date: datetime.date, end_date: datetime.date) -> None:
    interval_id = int(st.session_state.get(PRICE_INTERVAL_SEQ_KEY, 0))
    st.session_state[PRICE_INTERVAL_SEQ_KEY] = interval_id + 1
    st.session_state[PRICE_INTERVAL_IDS_KEY] = [*st.session_state.get(PRICE_INTERVAL_IDS_KEY, []), interval_id]
    start_key, end_key, price_key = get_price_interval_widget_keys(interval_id)
    st.session_state[start_key] = start_date
    st.session_state[end_key] = end_date
    st.session_state[price_key] = 0.0


def remove_price_interval(interval_id: int) -> None:
    st.session_state[PRICE_INTERVAL_IDS_KEY] = [
        item for item in st.session_state.get(PRICE_INTERVAL_IDS_KEY, []) if item != interval_id
    ]
    for key in get_price_interval_widget_keys(interval_id):
        st.session_state.pop(key, None)


def clear_price_intervals() -> None:
    for interval_id in st.session_state.get(PRICE_INTERVAL_IDS_KEY, []):
        for key in get_price_interval_widget_keys(interval_id):
            st.session_state.pop(key, None)
    st.session_state[PRICE_INTERVAL_IDS_KEY] = []


def collect_price_intervals() -> list[dict[str, object]]:
    intervals: list[dict[str, object]] = []
    for interval_id in st.session_state.get(PRICE_INTERVAL_IDS_KEY, []):
        start_key, end_key, price_key = get_price_interval_widget_keys(interval_id)
        intervals.append(
            {
                "id": interval_id,
                "start_date": st.session_state.get(start_key),
                "end_date": st.session_state.get(end_key),
                "price_per_m3": st.session_state.get(price_key, 0.0),
            }
        )
    return intervals


def normalize_interval_boundaries(
    start_date: datetime.date,
    end_date: datetime.date,
) -> tuple[datetime.datetime, datetime.datetime]:
    interval_start = datetime.datetime.combine(start_date, datetime.time.min)
    interval_end = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min)
    return interval_start, interval_end


def clamp_date_to_period(
    value: object,
    min_date: datetime.date,
    max_date: datetime.date,
) -> datetime.date:
    if not isinstance(value, datetime.date):
        return min_date
    if value < min_date:
        return min_date
    if value > max_date:
        return max_date
    return value


def prepare_price_interval_summary(
    payload: dict[str, object],
    start_date: datetime.date,
    end_date: datetime.date,
    intervals: list[dict[str, object]],
) -> tuple[pd.DataFrame, dict[str, float | None], list[str], list[str]]:
    period_start, period_end = build_period_datetime_range(start_date, end_date)
    errors: list[str] = []
    warnings: list[str] = []
    normalized_intervals: list[dict[str, object]] = []

    for index, interval in enumerate(intervals, start=1):
        row_start = interval.get("start_date")
        row_end = interval.get("end_date")
        price_per_m3 = interval.get("price_per_m3", 0.0)

        if not isinstance(row_start, datetime.date) or not isinstance(row_end, datetime.date):
            errors.append(f"Interval {index}: datum od/do není platný.")
            continue
        if row_start > row_end:
            errors.append(f"Interval {index}: datum `od` je větší než datum `do`.")
            continue

        interval_start, interval_end = normalize_interval_boundaries(row_start, row_end)
        if interval_start < period_start or interval_end > period_end:
            errors.append(
                f"Interval {index}: musí ležet uvnitř vybraného období "
                f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}."
            )
            continue

        try:
            numeric_price = round(float(price_per_m3), 2)
        except (TypeError, ValueError):
            errors.append(f"Interval {index}: cena vody není číslo.")
            continue
        if numeric_price < 0:
            errors.append(f"Interval {index}: cena vody nemůže být záporná.")
            continue

        normalized_intervals.append(
            {
                "index": index,
                "start_date": row_start,
                "end_date": row_end,
                "interval_start": interval_start,
                "interval_end": interval_end,
                "price_per_m3": numeric_price,
            }
        )

    sorted_intervals = sorted(normalized_intervals, key=lambda item: item["interval_start"])
    for previous, current in zip(sorted_intervals, sorted_intervals[1:]):
        if current["interval_start"] < previous["interval_end"]:
            errors.append(
                f"Intervaly {previous['index']} a {current['index']} se překrývají. "
                "Překryv není povolen."
            )

    if errors:
        return pd.DataFrame(), {"total_cost": None, "covered_consumption": None, "coverage_percent": None, "uncovered_consumption": None}, errors, warnings

    segment_rows = payload.get("segment_rows", [])
    summary_rows: list[dict[str, object]] = []
    covered_consumption = 0.0
    total_cost = 0.0

    for interval in sorted_intervals:
        estimated_consumption = 0.0
        for segment in segment_rows:
            segment_start = pd.to_datetime(segment.get("start_time"), errors="coerce")
            segment_end_inclusive = pd.to_datetime(segment.get("end_time"), errors="coerce")
            billing_consumption = segment.get("billing_consumption")
            if pd.isna(segment_start) or pd.isna(segment_end_inclusive) or billing_consumption is None:
                continue

            segment_end = segment_end_inclusive.to_pydatetime() + datetime.timedelta(seconds=1)
            segment_start_dt = segment_start.to_pydatetime()
            overlap_start = max(segment_start_dt, interval["interval_start"])
            overlap_end = min(segment_end, interval["interval_end"])
            overlap_seconds = (overlap_end - overlap_start).total_seconds()
            if overlap_seconds <= 0:
                continue

            segment_duration_seconds = (segment_end - segment_start_dt).total_seconds()
            if segment_duration_seconds <= 0:
                continue

            estimated_consumption += float(billing_consumption) * (overlap_seconds / segment_duration_seconds)

        estimated_consumption = round(estimated_consumption, 3)
        estimated_cost = round(estimated_consumption * float(interval["price_per_m3"]), 2)
        covered_consumption = round(covered_consumption + estimated_consumption, 3)
        total_cost = round(total_cost + estimated_cost, 2)
        summary_rows.append(
            {
                "Interval": (
                    f"{interval['start_date'].strftime('%d.%m.%Y')} - "
                    f"{interval['end_date'].strftime('%d.%m.%Y')}"
                ),
                "Cena vody [Kč/m³]": format_currency(interval["price_per_m3"]).replace(" Kč", ""),
                "Odhad spotřeby fakturačního [m³]": format_consumption_with_unit(estimated_consumption),
                "Odhad ceny [Kč]": format_currency(estimated_cost),
            }
        )

    billing_consumption = payload.get("billing_consumption")
    coverage_percent = None
    uncovered_consumption = None
    if billing_consumption is not None:
        billing_numeric = round(float(billing_consumption), 3)
        uncovered_consumption = round(max(billing_numeric - covered_consumption, 0.0), 3)
        if billing_numeric > 0:
            coverage_percent = round(covered_consumption / billing_numeric * 100, 1)
        if uncovered_consumption > 0:
            warnings.append(
                "Intervaly ceny vody nepokrývají celé zvolené období. "
                "Část spotřeby fakturačního vodoměru zůstává bez ceny."
            )

    return (
        pd.DataFrame(summary_rows),
        {
            "total_cost": total_cost,
            "covered_consumption": covered_consumption,
            "coverage_percent": coverage_percent,
            "uncovered_consumption": uncovered_consumption,
        },
        errors,
        warnings,
    )


def render_sidebar_filters(options: list[dict[str, object]]) -> tuple[str, datetime.date, datetime.date, float]:
    option_ids = [str(option["billing_ident"]) for option in options]
    if st.session_state.get(FILTER_BILLING_IDENT_KEY) not in option_ids:
        st.session_state[FILTER_BILLING_IDENT_KEY] = option_ids[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        with st.form("vodomery_billing_filters"):
            billing_ident = st.selectbox(
                "Fakturační vodoměr",
                options=option_ids,
                key=FILTER_BILLING_IDENT_KEY,
                format_func=lambda value: next(
                    (
                        f"{option['title']} ({option['billing_ident']})"
                        for option in options
                        if option["billing_ident"] == value
                    ),
                    value,
                ),
            )
            date_range = st.date_input(
                "Období",
                key=FILTER_DATE_RANGE_KEY,
                value=st.session_state[FILTER_DATE_RANGE_KEY],
            )
            invoice_amount = st.number_input(
                "Částka faktury [Kč]",
                key=FILTER_INVOICE_AMOUNT_KEY,
                min_value=0.0,
                step=100.0,
                help="Volitelné. Pokud vyplníš částku, tabulka dopočítá i rozdělení v Kč.",
            )
            st.form_submit_button("Načíst rozpočítání", use_container_width=True)

    start_date, end_date = normalize_date_range(date_range)
    return billing_ident, start_date, end_date, float(invoice_amount)


def render_filter_summary(
    branch_title: str,
    billing_ident: str,
    start_date: datetime.date,
    end_date: datetime.date,
    invoice_amount: float,
) -> None:
    pills = [
        f"Větev: {branch_title}",
        f"Fakturační vodoměr: {billing_ident}",
        f"Období: {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
    ]
    if invoice_amount > 0:
        pills.append(f"Částka faktury: {format_currency(invoice_amount)}")

    st.markdown(
        "".join(
            (
                '<span style="display:inline-flex;align-items:center;margin:0 0.4rem 0.4rem 0;'
                'padding:0.35rem 0.7rem;border-radius:999px;background:#f1f5f9;'
                'border:1px solid #dbe4ee;color:#0f172a;font-size:0.85rem;">'
                f"{pill}</span>"
            )
            for pill in pills
        ),
        unsafe_allow_html=True,
    )


def prepare_device_table(payload: dict[str, object], invoice_amount: float) -> pd.DataFrame:
    rows = pd.DataFrame(payload.get("device_rows", []))
    if rows.empty:
        return rows

    rows["Aktivní od"] = rows["active_from"].apply(format_timestamp)
    rows["Aktivní do"] = rows["active_to"].apply(format_timestamp)
    rows["Spotřeba [m³]"] = rows["spotreba"].apply(format_consumption_with_unit)
    rows["Podíl na podružných"] = rows["podil_na_podruznych_procent"].apply(format_percent)
    rows["Podíl na fakturačním"] = rows["podil_na_fakturacnim_procent"].apply(format_percent)
    rows["Rozpočtená spotřeba z fakturačního [m³]"] = rows["rozpoctena_fakturacni_spotreba"].apply(
        format_consumption_with_unit
    )
    if invoice_amount > 0:
        rows["Rozpočtená částka [Kč]"] = (
            pd.to_numeric(rows["podil_na_podruznych_procent"], errors="coerce").fillna(0.0) / 100 * invoice_amount
        ).round(2).apply(format_currency)

    display_columns = [
        "identifikace",
        "Spotřeba [m³]",
        "Podíl na podružných",
        "Podíl na fakturačním",
        "Rozpočtená spotřeba z fakturačního [m³]",
        "active_segment_count",
        "segments_with_data_count",
        "segments_without_data_count",
        "Aktivní od",
        "Aktivní do",
    ]
    rename_map = {
        "identifikace": "Podružný vodoměr",
        "active_segment_count": "Aktivní segmenty",
        "segments_with_data_count": "Segmenty s daty",
        "segments_without_data_count": "Segmenty bez dat",
    }
    if invoice_amount > 0:
        display_columns.insert(5, "Rozpočtená částka [Kč]")

    return rows.loc[:, display_columns].rename(columns=rename_map)


def prepare_assignment_table(payload: dict[str, object]) -> pd.DataFrame:
    rows = pd.DataFrame(payload.get("assignment_rows", []))
    if rows.empty:
        return rows

    rows["Od"] = rows["start_time"].apply(format_timestamp)
    rows["Do"] = rows["end_time"].apply(format_timestamp)
    rows["Trvání [h]"] = pd.to_numeric(rows["duration_hours"], errors="coerce").round(2)
    return rows.loc[:, ["identifikace", "Od", "Do", "Trvání [h]"]].rename(
        columns={"identifikace": "Podružný vodoměr"}
    )


def prepare_segment_table(payload: dict[str, object]) -> pd.DataFrame:
    rows = pd.DataFrame(payload.get("segment_rows", []))
    if rows.empty:
        return rows

    rows["Od"] = rows["start_time"].apply(format_timestamp)
    rows["Do"] = rows["end_time"].apply(format_timestamp)
    rows["Aktivní podružné vodoměry"] = rows["active_devices"].apply(lambda values: ", ".join(values) if values else "-")
    rows["Spotřeba podružných [m³]"] = rows["submeter_consumption"].apply(format_consumption_with_unit)
    rows["Spotřeba fakturačního [m³]"] = rows["billing_consumption"].apply(format_consumption_with_unit)
    rows["Rozdíl [m³]"] = rows["difference"].apply(lambda value: format_consumption_with_unit(value, signed=True))
    return rows.loc[
        :,
        [
            "Od",
            "Do",
            "device_count",
            "devices_with_data_count",
            "devices_without_data_count",
            "Spotřeba podružných [m³]",
            "Spotřeba fakturačního [m³]",
            "Rozdíl [m³]",
            "Aktivní podružné vodoměry",
        ],
    ].rename(
        columns={
            "device_count": "Počet podružných",
            "devices_with_data_count": "S daty",
            "devices_without_data_count": "Bez dat",
        }
    )


def render_metrics(payload: dict[str, object], invoice_amount: float) -> None:
    metric_cols = st.columns(6)
    metric_cols[0].metric("Spotřeba fakturačního", format_consumption_with_unit(payload.get("billing_consumption")))
    metric_cols[1].metric("Součet podružných", format_consumption_with_unit(payload.get("submeter_consumption_total")))
    metric_cols[2].metric("Rozdíl", format_consumption_with_unit(payload.get("difference"), signed=True))
    metric_cols[3].metric("Pokrytí podružnými", format_percent(payload.get("coverage_percent")))
    metric_cols[4].metric("Podružné vodoměry", str(int(payload.get("active_device_count", 0))))
    metric_cols[5].metric("Aktivní segmenty", str(int(payload.get("active_segment_count", 0))))

    st.caption(
        "Počáteční stav fakturačního: "
        f"{format_consumption_with_unit(payload.get('billing_start_value'))} | "
        "Konečný stav fakturačního: "
        f"{format_consumption_with_unit(payload.get('billing_end_value'))}"
    )
    if invoice_amount > 0:
        st.caption(f"Částka faktury pro rozdělení: {format_currency(invoice_amount)}")


def render_price_section(
    payload: dict[str, object],
    start_date: datetime.date,
    end_date: datetime.date,
) -> None:
    with st.container(border=True):
        header_col, actions_col = st.columns((3, 2))
        with header_col:
            st.subheader("Cena vody")
            st.caption(
                "Volitelné cenové intervaly pro odhad ceny vody v rámci vybraného období. "
                "Intervaly se nesmí překrývat."
            )
        with actions_col:
            add_col, clear_col = st.columns(2)
            with add_col:
                if st.button("Přidat interval", key="vodomery_billing_add_price_interval", use_container_width=True):
                    add_price_interval(start_date, end_date)
                    st.rerun()
            with clear_col:
                if st.button("Smazat vše", key="vodomery_billing_clear_price_intervals", use_container_width=True):
                    clear_price_intervals()
                    st.rerun()

        interval_ids = list(st.session_state.get(PRICE_INTERVAL_IDS_KEY, []))
        if not interval_ids:
            st.info("Zatím není zadaný žádný interval ceny vody.")
            return

        for order, interval_id in enumerate(interval_ids, start=1):
            start_key, end_key, price_key = get_price_interval_widget_keys(interval_id)
            st.session_state[start_key] = clamp_date_to_period(st.session_state.get(start_key), start_date, end_date)
            st.session_state[end_key] = clamp_date_to_period(st.session_state.get(end_key), start_date, end_date)
            row_cols = st.columns((1.15, 1.15, 1.0, 0.65))
            with row_cols[0]:
                st.date_input(
                    f"Od #{order}",
                    key=start_key,
                    min_value=start_date,
                    max_value=end_date,
                )
            with row_cols[1]:
                st.date_input(
                    f"Do #{order}",
                    key=end_key,
                    min_value=start_date,
                    max_value=end_date,
                )
            with row_cols[2]:
                st.number_input(
                    f"Cena #{order} [Kč/m³]",
                    key=price_key,
                    min_value=0.0,
                    step=1.0,
                )
            with row_cols[3]:
                st.write("")
                st.write("")
                if st.button("Smazat", key=f"vodomery_billing_remove_interval_{interval_id}", use_container_width=True):
                    remove_price_interval(interval_id)
                    st.rerun()

        summary_df, totals, errors, warnings = prepare_price_interval_summary(
            payload,
            start_date,
            end_date,
            collect_price_intervals(),
        )

        for message in errors:
            st.error(message)
        for message in warnings:
            st.warning(message)

        if summary_df.empty:
            return

        metric_cols = st.columns(4)
        metric_cols[0].metric("Odhad ceny vody", format_currency(totals["total_cost"]))
        metric_cols[1].metric(
            "Oceněná spotřeba",
            format_consumption_with_unit(totals["covered_consumption"]),
        )
        metric_cols[2].metric(
            "Pokrytí ceny",
            format_percent(totals["coverage_percent"]),
        )
        metric_cols[3].metric(
            "Neoceněná spotřeba",
            format_consumption_with_unit(totals["uncovered_consumption"]),
        )

        st.caption(
            "Odhad ceny vychází z poměrného rozdělení spotřeby fakturačního vodoměru "
            "do zadaných intervalů podle jejich časového překryvu s aktivními segmenty."
        )
        st.dataframe(summary_df, hide_index=True, use_container_width=True)


def render_dashboard() -> None:
    render_vodomery_header(
        "Fakturace",
        "Rozpočítání spotřeby fakturačního vodoměru na podružné vodoměry podle historie větví.",
    )

    billing_options = load_billing_options()
    if not billing_options:
        st.info("Pro fakturaci nejsou k dispozici žádné fakturační vodoměry.")
        return

    init_page_state(str(billing_options[0]["billing_ident"]))
    billing_ident, start_date, end_date, invoice_amount = render_sidebar_filters(billing_options)
    st.caption("Filtr se aplikuje po kliknutí na `Načíst rozpočítání` v sidebaru.")

    payload = load_billing_period(billing_ident, start_date, end_date)

    render_filter_summary(
        str(payload["branch_title"]),
        str(payload["billing_ident"]),
        start_date,
        end_date,
        invoice_amount,
    )
    render_metrics(payload, invoice_amount)
    render_price_section(payload, start_date, end_date)

    billing_consumption = payload.get("billing_consumption")
    submeter_total = float(payload.get("submeter_consumption_total", 0.0) or 0.0)
    if billing_consumption is None:
        st.warning("Spotřebu fakturačního vodoměru se nepodařilo spolehlivě určit z dostupných odečtů.")
    elif float(payload.get("difference", 0.0) or 0.0) > 0:
        st.warning(
            "Součet podružných vodoměrů je nižší než spotřeba fakturačního vodoměru. "
            "Rozpočtená spotřeba v tabulce rozdíl poměrově přenáší na podružné vodoměry."
        )
    elif billing_consumption is not None and submeter_total > float(billing_consumption):
        st.info("Součet podružných vodoměrů je vyšší než spotřeba fakturačního vodoměru.")

    device_table = prepare_device_table(payload, invoice_amount)
    assignment_table = prepare_assignment_table(payload)
    segment_table = prepare_segment_table(payload)

    top_left, top_right = st.columns((3.5, 2.5))
    with top_left:
        with st.container(border=True):
            st.subheader("Rozpočítání podle spotřeby")
            if device_table.empty:
                st.info("Ve zvoleném období nejsou pro tuto větev k dispozici žádné podružné vodoměry.")
            else:
                st.dataframe(device_table, hide_index=True, use_container_width=True)

    with top_right:
        with st.container(border=True):
            st.subheader("Přiřazení podružných vodoměrů")
            st.caption("Aktivní intervaly odvozené z `historie_vetve.py` pro zvolené období.")
            if assignment_table.empty:
                st.info("Ve zvoleném období není pro tuto větev definované žádné přiřazení podružných vodoměrů.")
            else:
                st.dataframe(assignment_table, hide_index=True, use_container_width=True)

    with st.container(border=True):
        st.subheader("Kontrola po intervalech")
        st.caption("Porovnání součtu podružných vodoměrů a fakturačního vodoměru v jednotlivých aktivních intervalech.")
        if segment_table.empty:
            st.info("Pro zvolené období není k dispozici žádný aktivní interval větve.")
        else:
            st.dataframe(segment_table, hide_index=True, use_container_width=True)


try:
    render_dashboard()
except DashboardApiError as exc:
    st.error("Nepodařilo se načíst data pro fakturaci vodoměrů.")
    st.exception(exc)
