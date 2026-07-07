from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import io
from typing import Callable, Sequence

import pandas as pd
from decouple import config
from sqlalchemy import bindparam, text

from app.channels.email import send_email_outlook
from app.time_utils import prague_today
from core.db.connect import ENGINE_PG
from moduly.mereni.vodomery.reporting._email_config import (
    filter_placeholder_recipients,
    load_report_recipients,
    sanitize_sender_alias,
)
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


@dataclass(frozen=True)
class ReportPeriod:
    year: int
    month: int
    period_start: datetime
    period_end: datetime

    @property
    def title(self) -> str:
        return f"Spotřeba vody {self.month:02d}/{self.year}"

    @property
    def filename(self) -> str:
        return f"spotreba_vody_{self.month:02d}_{self.year}.xlsx"


@dataclass(frozen=True)
class BranchReportConfig:
    title: str
    sheet_name: str
    billing_ident: str
    intervals: tuple[tuple[datetime, datetime, list[str]], ...]
    membership_resolver: Callable[[datetime], list[str]]


@dataclass(frozen=True)
class BranchDailyReport:
    day: date
    branch_consumption: float | None
    billing_consumption: float | None
    difference: float | None


@dataclass(frozen=True)
class BranchControlReport:
    config: BranchReportConfig
    device_identifiers: tuple[str, ...]
    device_count: int
    active_meter_days: int
    billing_start_value: float | None
    billing_end_value: float | None
    billing_consumption: float | None
    branch_consumption: float | None
    difference: float | None
    average_difference_per_meter: float | None
    average_difference_per_active_meter_day: float | None
    detail_rows: tuple[BranchDailyReport, ...]


BRANCH_REPORT_CONFIGS: tuple[BranchReportConfig, ...] = (
    BranchReportConfig(
        title="Kontrola větve HECHT",
        sheet_name="HECHT",
        billing_ident="SCVK_HE",
        intervals=tuple(INTERVALY_vetev_L),
        membership_resolver=ziskej_vetev_L,
    ),
    BranchReportConfig(
        title="Kontrola větve DOKTOR voda",
        sheet_name="DOK voda",
        billing_ident="SCVK_DV",
        intervals=tuple(INTERVALY_vetev_dok_voda),
        membership_resolver=ziskej_vetev_dok_voda,
    ),
    BranchReportConfig(
        title="Kontrola větve DOKTOR požární voda",
        sheet_name="DOK požární",
        billing_ident="SCVK_DP",
        intervals=tuple(INTERVALY_vetev_dok_poz_voda),
        membership_resolver=ziskej_vetev_dok_poz_voda,
    ),
    BranchReportConfig(
        title="Kontrola větve GROBÁR",
        sheet_name="GROBÁR",
        billing_ident="SCVK_GR",
        intervals=tuple(INTERVALY_vetev_grobar),
        membership_resolver=ziskej_vetev_grobar,
    ),
)


def send_monthly_vodomery_consumption_report(reference_date: date | None = None) -> dict[str, object]:
    period = _get_previous_month_period(reference_date)
    recipients = filter_placeholder_recipients(
        _load_recipients(),
        context_label="send_monthly_vodomery_consumption_report",
    )
    if not recipients:
        return {
            "title": period.title,
            "filename": period.filename,
            "recipient_count": 0,
            "row_count": 0,
            "branch_sheet_count": 0,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }
    report_df, branch_reports = _build_monthly_report_dataset(period)
    report_bytes = _build_excel_bytes(report_df, branch_reports, period.title)
    subject = period.title
    body = (
        f"Dobrý den,<br><br>"
        f"v příloze zasílám měsíční report spotřeby všech vodoměrů za období "
        f"{period.period_start.strftime('%d.%m.%Y')} - {(period.period_end - timedelta(days=1)).strftime('%d.%m.%Y')}."
        f"<br><br>"
        f"Počet zařízení v reportu: {len(report_df)}"
    )

    for recipient in recipients:
        send_email_outlook(
            email_receiver=recipient,
            subject=subject,
            body=body,
            sender_alias=sanitize_sender_alias(
                config("O_EMAIL_UPOZORNENI", default=None),
                context_label="VODOMERY_MONTHLY_REPORT_SENDER_ALIAS",
            ),
            is_html=True,
            attachments=[(period.filename, report_bytes, "application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
        )

    return {
        "title": period.title,
        "filename": period.filename,
        "recipient_count": len(recipients),
        "row_count": len(report_df),
        "branch_sheet_count": len(branch_reports),
    }


def _load_recipients() -> list[str]:
    return list(
        load_report_recipients("VODOMERY_MONTHLY_CONSUMPTION_REPORT_RECIPIENTS")
    )


def _get_previous_month_period(reference_date: date | None = None) -> ReportPeriod:
    base_date = reference_date or prague_today()
    current_month_start = base_date.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return ReportPeriod(
        year=previous_month_start.year,
        month=previous_month_start.month,
        period_start=datetime.combine(previous_month_start, time.min),
        period_end=datetime.combine(current_month_start, time.min),
    )


def _build_monthly_report_dataframe(period: ReportPeriod) -> pd.DataFrame:
    with ENGINE_PG.connect() as conn:
        devices = _load_report_device_identifiers(conn, period)
        start_map = _load_last_valid_measurements_before(conn, devices, period.period_start)
        end_map = _load_last_valid_measurements_before(conn, devices, period.period_end)

    return _build_consumption_dataframe(devices, start_map, end_map)


def _load_report_device_identifiers(conn, period: ReportPeriod) -> list[str]:
    return list(
        conn.execute(
            text(
                """
                SELECT DISTINCT identifikace
                FROM monitoring."Mereni_vodomery_vse"
                WHERE identifikace IS NOT NULL
                  AND btrim(identifikace) <> ''
                  AND platne = TRUE
                  AND date < :period_end
                ORDER BY identifikace
                """
            ),
            {"period_end": period.period_end},
        )
        .scalars()
        .all()
    )


def _build_monthly_report_dataset(period: ReportPeriod) -> tuple[pd.DataFrame, tuple[BranchControlReport, ...]]:
    report_df = _build_monthly_report_dataframe(period)
    with ENGINE_PG.connect() as conn:
        branch_reports = tuple(
            _build_branch_control_report(conn, config_item, period)
            for config_item in BRANCH_REPORT_CONFIGS
        )
    return report_df, branch_reports


def _build_excel_bytes(
    report_df: pd.DataFrame,
    branch_reports: Sequence[BranchControlReport],
    title: str,
) -> bytes:
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        workbook = writer.book
        formats = _build_excel_formats(workbook)
        _write_main_sheet(writer, report_df, title, formats)

        for branch_report in branch_reports:
            _write_branch_sheet(writer, branch_report, title, formats)

    buffer.seek(0)
    return buffer.getvalue()


def _to_rounded_float(value: object) -> float | None:
    if value is None:
        return None
    numeric_value = float(value)
    if pd.isna(numeric_value):
        return None
    return round(numeric_value, 3)


def _load_last_valid_measurements_before(
    conn,
    identifiers: Sequence[str],
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
                    ORDER BY date DESC
                ) AS row_num
            FROM monitoring."Mereni_vodomery_vse"
            WHERE identifikace IN :identifiers
              AND date < :cutoff
              AND platne = TRUE
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


def _build_consumption_dataframe(
    identifiers: Sequence[str],
    start_map: dict[str, float | None],
    end_map: dict[str, float | None],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for identifikace in identifiers:
        ident_key = str(identifikace)
        start_value = start_map.get(ident_key)
        end_value = end_map.get(ident_key)
        rows.append(
            {
                "identifikace": identifikace,
                "počáteční stav měsíce": start_value,
                "konečný stav měsíce": end_value,
                "spotřeba": _compute_consumption(start_value, end_value),
            }
        )
    return pd.DataFrame(rows)


def _build_branch_control_report(conn, config_item: BranchReportConfig, period: ReportPeriod) -> BranchControlReport:
    device_identifiers, active_meter_days = _build_branch_membership_summary(config_item, period)
    billing_start_map = _load_last_valid_measurements_before(conn, [config_item.billing_ident], period.period_start)
    billing_end_map = _load_last_valid_measurements_before(conn, [config_item.billing_ident], period.period_end)

    billing_start_value = billing_start_map.get(config_item.billing_ident)
    billing_end_value = billing_end_map.get(config_item.billing_ident)
    billing_consumption = _compute_consumption(billing_start_value, billing_end_value)

    detail_rows = _build_branch_daily_rows(conn, config_item, period)

    branch_consumption_total = (
        round(sum(row.branch_consumption for row in detail_rows if row.branch_consumption is not None), 3)
        if any(row.branch_consumption is not None for row in detail_rows)
        else None
    )
    difference = _compute_difference(billing_consumption, branch_consumption_total)

    return BranchControlReport(
        config=config_item,
        device_identifiers=device_identifiers,
        device_count=len(device_identifiers),
        active_meter_days=active_meter_days,
        billing_start_value=billing_start_value,
        billing_end_value=billing_end_value,
        billing_consumption=billing_consumption,
        branch_consumption=branch_consumption_total,
        difference=difference,
        average_difference_per_meter=_compute_average(difference, len(device_identifiers)),
        average_difference_per_active_meter_day=_compute_average(difference, active_meter_days),
        detail_rows=tuple(detail_rows),
    )


def _build_branch_membership_summary(
    config_item: BranchReportConfig,
    period: ReportPeriod,
) -> tuple[tuple[str, ...], int]:
    effective_segments = _resolve_effective_branch_segments(config_item, period)
    device_identifiers = tuple(
        dict.fromkeys(
            identifier
            for _, _, segment_identifiers in effective_segments
            for identifier in segment_identifiers
        )
    )

    active_meter_days = 0
    day_cursor = period.period_start.date()
    period_end_date = period.period_end.date()
    while day_cursor < period_end_date:
        day_start = datetime.combine(day_cursor, time.min)
        day_end = day_start + timedelta(days=1)
        day_period = ReportPeriod(
            year=day_cursor.year,
            month=day_cursor.month,
            period_start=day_start,
            period_end=day_end,
        )
        day_segments = _resolve_effective_branch_segments(config_item, day_period)
        active_day_identifiers = tuple(
            dict.fromkeys(
                identifier
                for _, _, segment_identifiers in day_segments
                for identifier in segment_identifiers
            )
        )
        active_meter_days += len(active_day_identifiers)
        day_cursor += timedelta(days=1)

    return device_identifiers, active_meter_days


def _build_branch_daily_rows(conn, config_item: BranchReportConfig, period: ReportPeriod) -> list[BranchDailyReport]:
    day_boundaries: list[datetime] = []
    day_cursor = period.period_start
    while day_cursor <= period.period_end:
        day_boundaries.append(day_cursor)
        day_cursor += timedelta(days=1)

    effective_segments = _resolve_effective_branch_segments(
        config_item,
        period,
        additional_boundaries=day_boundaries,
        merge_adjacent=False,
    )

    all_identifiers = [config_item.billing_ident]
    for _, _, device_identifiers in effective_segments:
        all_identifiers.extend(device_identifiers)

    snapshot_cutoffs = sorted({
        period.period_start,
        period.period_end,
        *(segment_start for segment_start, _, _ in effective_segments),
        *(segment_end for _, segment_end, _ in effective_segments),
    })
    snapshot_cache = {
        cutoff: _load_last_valid_measurements_before(conn, all_identifiers, cutoff)
        for cutoff in snapshot_cutoffs
    }

    daily_totals: dict[date, dict[str, list[float]]] = {}
    for segment_start, segment_end, device_identifiers in effective_segments:
        start_map = snapshot_cache[segment_start]
        end_map = snapshot_cache[segment_end]
        day_key = segment_start.date()
        day_bucket = daily_totals.setdefault(day_key, {"branch": [], "billing": []})

        for identifier in device_identifiers:
            consumption = _compute_consumption(
                start_map.get(identifier),
                end_map.get(identifier),
            )
            if consumption is not None:
                day_bucket["branch"].append(consumption)

        billing_consumption = _compute_consumption(
            start_map.get(config_item.billing_ident),
            end_map.get(config_item.billing_ident),
        )
        if billing_consumption is not None:
            day_bucket["billing"].append(billing_consumption)

    detail_rows: list[BranchDailyReport] = []
    day_cursor_date = period.period_start.date()
    period_end_date = period.period_end.date()
    while day_cursor_date < period_end_date:
        day_bucket = daily_totals.get(day_cursor_date, {"branch": [], "billing": []})
        branch_consumption = (
            round(sum(day_bucket["branch"]), 3)
            if day_bucket["branch"]
            else None
        )
        billing_consumption = (
            round(sum(day_bucket["billing"]), 3)
            if day_bucket["billing"]
            else None
        )
        detail_rows.append(
            BranchDailyReport(
                day=day_cursor_date,
                branch_consumption=branch_consumption,
                billing_consumption=billing_consumption,
                difference=_compute_difference(billing_consumption, branch_consumption),
            )
        )
        day_cursor_date += timedelta(days=1)

    return detail_rows


def _resolve_effective_branch_segments(
    config_item: BranchReportConfig,
    period: ReportPeriod,
    additional_boundaries: Sequence[datetime] = (),
    merge_adjacent: bool = True,
) -> list[tuple[datetime, datetime, tuple[str, ...]]]:
    boundaries = {period.period_start, period.period_end}
    one_second = timedelta(seconds=1)

    for interval_start, interval_end, _ in config_item.intervals:
        effective_start = max(period.period_start, interval_start)
        effective_end = min(period.period_end, interval_end + one_second)
        if effective_start >= effective_end:
            continue
        boundaries.add(effective_start)
        boundaries.add(effective_end)

    for boundary in additional_boundaries:
        if period.period_start < boundary < period.period_end:
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


def _compute_consumption(start_value: float | None, end_value: float | None) -> float | None:
    if start_value is None or end_value is None or end_value < start_value:
        return None
    return round(end_value - start_value, 3)


def _compute_difference(billing_consumption: float | None, branch_consumption: float | None) -> float | None:
    if billing_consumption is None or branch_consumption is None:
        return None
    return round(billing_consumption - branch_consumption, 3)


def _compute_average(difference: float | None, denominator: int) -> float | None:
    if difference is None or denominator <= 0:
        return None
    return round(difference / denominator, 3)


def _build_excel_formats(workbook) -> dict[str, object]:
    return {
        "title": workbook.add_format({
            "bold": True,
            "font_size": 16,
            "align": "center",
            "valign": "vcenter",
        }),
        "header": workbook.add_format({
            "bold": True,
            "bg_color": "#D9EAF7",
            "border": 1,
        }),
        "number": workbook.add_format({
            "num_format": "0.000",
            "border": 1,
        }),
        "text": workbook.add_format({
            "border": 1,
        }),
        "wrap": workbook.add_format({
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }),
        "note": workbook.add_format({
            "italic": True,
        }),
    }


def _write_main_sheet(writer, report_df: pd.DataFrame, title: str, formats: dict[str, object]) -> None:
    export_df = report_df.copy()
    export_df.to_excel(writer, sheet_name="Spotřeba vody", index=False, startrow=2)
    worksheet = writer.sheets["Spotřeba vody"]

    worksheet.merge_range(0, 0, 0, 3, title, formats["title"])
    worksheet.set_row(0, 24)

    for column_index, column_name in enumerate(export_df.columns):
        worksheet.write(2, column_index, column_name, formats["header"])

    worksheet.set_column(0, 0, 28, formats["text"])
    worksheet.set_column(1, 3, 22, formats["number"])
    worksheet.freeze_panes(3, 0)


def _write_branch_sheet(writer, branch_report: BranchControlReport, report_title: str, formats: dict[str, object]) -> None:
    workbook = writer.book
    worksheet = workbook.add_worksheet(branch_report.config.sheet_name)
    writer.sheets[branch_report.config.sheet_name] = worksheet

    worksheet.merge_range(0, 0, 0, 10, f"{branch_report.config.title} - {report_title}", formats["title"])
    worksheet.set_row(0, 24)

    summary_headers = [
        "větev",
        "fakturační vodoměr",
        "seznam vodoměrů na větvi",
        "počet vodoměrů",
        "aktivní vodoměry a den",
        "počáteční stav fakturačního",
        "konečný stav fakturačního",
        "spotřeba fakturačního",
        "součet spotřeby větve",
        "rozdíl (fakturační - větev)",
        "průměrná odchylka na 1 vodoměr",
        "průměrná odchylka na 1 aktivní vodoměr a den",
    ]
    summary_values = [
        branch_report.config.title.replace("Kontrola větve ", ""),
        branch_report.config.billing_ident,
        ", ".join(branch_report.device_identifiers),
        branch_report.device_count,
        branch_report.active_meter_days,
        branch_report.billing_start_value,
        branch_report.billing_end_value,
        branch_report.billing_consumption,
        branch_report.branch_consumption,
        branch_report.difference,
        branch_report.average_difference_per_meter,
        branch_report.average_difference_per_active_meter_day,
    ]

    for column_index, header in enumerate(summary_headers):
        worksheet.write(2, column_index, header, formats["header"])
        value = summary_values[column_index]
        if column_index == 2:
            value_format = formats["wrap"]
        elif column_index in {3, 4, 5, 6, 7, 8, 9, 10, 11}:
            value_format = formats["number"]
        else:
            value_format = formats["text"]
        worksheet.write(3, column_index, value, value_format)

    worksheet.write(5, 0, "Detail po dnech", formats["note"])

    detail_headers = [
        "den",
        "vodoměry",
        "fakturační",
        "rozdíl (fakturační - vodoměry)",
    ]
    for column_index, header in enumerate(detail_headers):
        worksheet.write(6, column_index, header, formats["header"])

    if not branch_report.detail_rows:
        worksheet.write(7, 0, "Pro dané období není pro větev definovaný žádný aktivní interval.", formats["note"])
    else:
        for row_index, detail_row in enumerate(branch_report.detail_rows, start=7):
            display_values = [
                detail_row.day.strftime("%d.%m.%Y"),
                detail_row.branch_consumption,
                detail_row.billing_consumption,
                detail_row.difference,
            ]

            for column_index, value in enumerate(display_values):
                if column_index in {1, 2, 3}:
                    cell_format = formats["number"]
                else:
                    cell_format = formats["text"]
                worksheet.write(row_index, column_index, value, cell_format)

    worksheet.set_column(0, 1, 20, formats["text"])
    worksheet.set_column(2, 2, 70, formats["wrap"])
    worksheet.set_column(3, 4, 18, formats["number"])
    worksheet.set_column(5, 11, 22, formats["number"])
    worksheet.set_column(0, 0, 16, formats["text"])
    worksheet.freeze_panes(7, 0)



# end_monthly_vodomery_consumption_report()
