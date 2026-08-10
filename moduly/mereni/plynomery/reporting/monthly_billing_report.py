from __future__ import annotations

import base64
import mimetypes
from datetime import datetime
from html import escape
from pathlib import Path

from services.api.services.plynomery_billing import (
    BranchBillingSummary,
    BranchDeviceConsumption,
    MonthlyBillingReportData,
    build_monthly_billing_report_data,
)


class PlynomeryMonthlyBillingReportError(RuntimeError):
    """Raised when the monthly plynomery billing report cannot be rendered."""


def _load_playwright_api():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlynomeryMonthlyBillingReportError(
            "Playwright je vyžadován pro render PDF měsíčního reportu plynoměrů."
        ) from exc
    return sync_playwright


def _format_volume(value: object, *, signed: bool = False) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(numeric_value) < 0.0005:
        numeric_value = 0.0
    format_spec = "+.3f" if signed else ".3f"
    return f"{numeric_value:{format_spec}} m³"


def _format_percent(value: object) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(numeric_value) < 0.05:
        numeric_value = 0.0
    return f"{numeric_value:.1f} %"


def _format_datetime(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%d.%m.%Y %H:%M")


def _format_optional_text(value: object) -> str:
    text_value = "" if value is None else str(value)
    return escape(text_value) if text_value else "-"


def _load_image_data_uri(image_path: Path) -> str | None:
    if not image_path.exists():
        return None
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _armex_logo_path() -> Path:
    return Path.cwd() / "data" / "ARMEX" / "logo_ARMEX.png"


def _sum_values(values: tuple[float | None, ...]) -> float:
    return round(sum(float(value) for value in values if value is not None), 3)


def _build_metric_card(
    label: str,
    value: str,
    caption: str = "",
    *,
    primary: bool = False,
) -> str:
    class_names = ["metric-card"]
    if primary:
        class_names.append("metric-card-primary")
    detail_html = (
        f'<div class="metric-detail">{escape(caption)}</div>' if caption else ""
    )
    return f"""
      <div class="{' '.join(class_names)}">
        <div class="metric-label">{escape(label)}</div>
        <div class="metric-value">{escape(value)}</div>
        {detail_html}
      </div>
    """


def _format_control_meter_note(row: BranchDeviceConsumption) -> str:
    if row.child_submeter_count <= 0:
        return ""
    note_parts = [
        f"součet podružných: {_format_volume(row.child_submeter_consumption_total)}",
        f"rozdíl: {_format_volume(row.child_submeter_difference, signed=True)}",
    ]
    if row.missing_child_submeter_count:
        note_parts.append(f"chybí {row.missing_child_submeter_count}")
    return f"({'; '.join(note_parts)})"


def _build_device_label_html(row: BranchDeviceConsumption) -> str:
    indent = "&nbsp;" * (row.level * 4)
    control_note = _format_control_meter_note(row)
    note_html = (
        f'<div class="cell-note">{escape(control_note)}</div>' if control_note else ""
    )
    return f"{indent}{escape(row.identifikace)}{note_html}"


def _device_role_label(row: BranchDeviceConsumption) -> str:
    if row.child_submeter_count:
        return f"kontrolní meziměřidlo pro {row.child_submeter_count} koncových"
    if row.parent_identifikace:
        return f"koncové pod {row.parent_identifikace}"
    if row.included_in_branch_sum:
        return "přímé odběrné místo"
    return "podružný detail"


def _format_branch_share_percent(row: BranchDeviceConsumption) -> str:
    if row.child_submeter_count > 0:
        return "-"
    return _format_percent(row.branch_share_percent)


def _build_device_row_html(row: BranchDeviceConsumption) -> str:
    row_classes = []
    if row.child_submeter_count:
        row_classes.append("control-meter-row")
    if row.parent_identifikace:
        row_classes.append("nested-meter-row")
    class_attr = f' class="{" ".join(row_classes)}"' if row_classes else ""
    return f"""
      <tr{class_attr}>
        <td>{_build_device_label_html(row)}</td>
        <td>{escape(_device_role_label(row))}</td>
        <td class="numeric">{_format_volume(row.start_value)}</td>
        <td class="numeric">{_format_volume(row.end_value)}</td>
        <td class="numeric strong">{_format_volume(row.consumption)}</td>
        <td class="numeric">{_format_branch_share_percent(row)}</td>
      </tr>
    """


def _build_device_table_html(branch: BranchBillingSummary) -> str:
    if not branch.device_rows:
        return '<p class="muted">Větev nemá evidované podružné plynoměry.</p>'
    rows_html = "\n".join(_build_device_row_html(row) for row in branch.device_rows)
    return f"""
      <table class="branch-table">
        <thead>
          <tr>
            <th>Odběrné místo</th>
            <th>Role</th>
            <th class="numeric">Počáteční stav</th>
            <th class="numeric">Koncový stav</th>
            <th class="numeric">Spotřeba</th>
            <th class="numeric">% podíl na větvi</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    """


def _branch_status_text(branch: BranchBillingSummary) -> str:
    if branch.billing_consumption is None:
        return "Chybí předchozí nebo aktuální ruční stav fakturačního plynoměru."
    if branch.direct_submeter_count == 0:
        return "Větev bez podružných plynoměrů."
    if branch.missing_direct_submeter_count:
        return f"Chybí data pro {branch.missing_direct_submeter_count} přímý podružný plynoměr."
    return "Kompletní měsíční porovnání."


def _build_branch_section_html(branch: BranchBillingSummary) -> str:
    residual_html = ""
    if branch.residual_label and branch.residual_consumption is not None:
        residual_html = _build_metric_card(
            branch.residual_label,
            _format_volume(branch.residual_consumption),
            "fakturační spotřeba minus přímé podružné měření",
        )

    return f"""
      <section class="branch-section">
        <div class="branch-heading">
          <div>
            <h2>{escape(branch.title)}</h2>
            <p>Fakturační plynoměr: <strong>{escape(branch.billing_ident)}</strong></p>
          </div>
          <div class="status-pill">{escape(_branch_status_text(branch))}</div>
        </div>

        <div class="metric-grid">
          {_build_metric_card("Fakturační spotřeba", _format_volume(branch.billing_consumption), primary=True)}
          {_build_metric_card("Součet přímých podružných", _format_volume(branch.submeter_consumption_total))}
          {_build_metric_card("Rozdíl", _format_volume(branch.difference_vs_submeters, signed=True), "fakturace - podružné")}
          {_build_metric_card("Pokrytí podružnými", _format_percent(branch.submeter_coverage_percent))}
          {residual_html}
        </div>

        <div class="readings-grid">
          <div class="branch-table-wrap">
            <div class="branch-subtitle">Fakturační odečty</div>
            <table class="branch-table branch-readings-table">
              <tbody>
                <tr><th>Počáteční stav</th><td class="numeric">{_format_volume(branch.billing_start_value)}</td></tr>
                <tr><th>Čas počátečního odečtu</th><td>{escape(_format_datetime(branch.billing_start_reading_at))}</td></tr>
                <tr><th>Koncový stav</th><td class="numeric">{_format_volume(branch.billing_end_value)}</td></tr>
                <tr><th>Čas koncového odečtu</th><td>{escape(_format_datetime(branch.billing_end_reading_at))}</td></tr>
              </tbody>
            </table>
          </div>
          <div class="branch-table-wrap branch-note-wrap">
            <div class="branch-subtitle">Metodika porovnání</div>
            <p class="muted">
              Do porovnání větve se počítají pouze přímé podružné plynoměry.
              Sloupec podílu ukazuje spotřebu odběrného místa vůči fakturační spotřebě větve.
              U kontrolních meziměřidel s rozepsanými koncovými odběry se procentní podíl nezobrazuje,
              aby stejná spotřeba nebyla ve sloupci započtena dvakrát.
              Kontrolní meziměřidla, například L2-L3_P8, mají u názvu uveden součet koncových
              podružných a rozdíl proti vlastní spotřebě, aby byla nesrovnalost vidět bez dalšího výpočtu.
            </p>
          </div>
        </div>

        <div class="branch-table-wrap">
          <div class="branch-subtitle">Odběrná místa a podružné plynoměry</div>
          {_build_device_table_html(branch)}
        </div>
      </section>
    """


def build_monthly_plynomery_billing_report_html(report: MonthlyBillingReportData) -> str:
    logo_data_uri = _load_image_data_uri(_armex_logo_path())
    logo_html = f'<img src="{logo_data_uri}" alt="ARMEX">' if logo_data_uri else ""
    total_billing = _sum_values(tuple(branch.billing_consumption for branch in report.branches))
    total_submeters = _sum_values(tuple(branch.submeter_consumption_total for branch in report.branches))
    total_difference = _sum_values(tuple(branch.difference_vs_submeters for branch in report.branches))
    branches_html = "\n".join(_build_branch_section_html(branch) for branch in report.branches)
    generated_at = report.generated_at.strftime("%d.%m.%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Plynoměry | měsíční report fakturačních odečtů {escape(report.month_label)}</title>
  <style>
    @page {{
      size: A4;
      margin: 9mm 8mm 10mm;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: #16202a;
      background: #ffffff;
      font-size: 10.2px;
      line-height: 1.35;
    }}
    .page-header {{
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) auto minmax(220px, 0.95fr);
      align-items: center;
      gap: 14px;
      padding: 0 0 10px;
      border-bottom: 1.5px solid #0f4c81;
      margin-bottom: 10px;
    }}
    .title-eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #64748b;
      font-size: 10px;
      margin-bottom: 4px;
    }}
    .page-header h1 {{
      margin: 0;
      font-size: 24px;
      color: #0f4c81;
      line-height: 1.08;
    }}
    .page-logo {{
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 52px;
    }}
    .page-logo img {{
      display: block;
      max-width: 160px;
      max-height: 42px;
      width: auto;
      height: auto;
    }}
    .page-meta {{
      text-align: right;
      color: #52606d;
      font-size: 11px;
    }}
    .page-meta strong {{
      color: #111827;
    }}
    .report-section {{
      padding-top: 2px;
    }}
    .report-hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 8px;
      align-items: stretch;
      margin-bottom: 8px;
    }}
    .report-title-block {{
      padding: 4px 0;
    }}
    .report-title-block h2 {{
      margin: 0;
      font-size: 20px;
      color: #0f4c81;
    }}
    .report-description, .report-meta {{
      margin-top: 5px;
      color: #52606d;
    }}
    .summary-grid, .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 8px;
      margin-bottom: 8px;
    }}
    .metric-card {{
      border: 1px solid #d8e1eb;
      border-radius: 12px;
      background: linear-gradient(180deg, #ffffff 0%, #f8fbfd 100%);
      padding: 8px 10px;
      box-shadow: 0 4px 14px rgba(15, 76, 129, 0.06);
    }}
    .metric-card-primary {{
      background: linear-gradient(135deg, #0f4c81 0%, #1d6fa5 100%);
      border-color: #0f4c81;
      color: #ffffff;
      box-shadow: 0 8px 20px rgba(15, 76, 129, 0.16);
    }}
    .metric-label {{
      font-size: 8px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #6b7280;
      margin-bottom: 4px;
    }}
    .metric-card-primary .metric-label {{
      color: rgba(255,255,255,0.8);
    }}
    .metric-value {{
      font-size: 16px;
      font-weight: 700;
      line-height: 1.2;
      color: #111827;
    }}
    .metric-card-primary .metric-value {{
      color: #ffffff;
    }}
    .metric-detail {{
      margin-top: 4px;
      color: #52606d;
      font-size: 9px;
    }}
    .metric-card-primary .metric-detail {{
      color: rgba(255,255,255,0.85);
    }}
    .branch-section {{
      margin: 0 0 12px;
      break-before: page;
      page-break-before: always;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .branch-heading {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      border: 1px solid #d8e1eb;
      border-radius: 10px;
      background: #ffffff;
      padding: 8px 10px;
      margin-bottom: 8px;
      box-shadow: 0 3px 12px rgba(15, 76, 129, 0.05);
      break-inside: avoid-page;
      page-break-inside: avoid;
    }}
    .branch-heading h2 {{
      margin: 0 0 3px;
      font-size: 17px;
      color: #0f4c81;
    }}
    .branch-heading p {{
      margin: 0;
      color: #52606d;
    }}
    .status-pill {{
      max-width: 250px;
      color: #0f4c81;
      background: #eef6fc;
      border: 1px solid #b9d4e8;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 9px;
      font-weight: 700;
    }}
    .readings-grid {{
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 8px;
      margin-bottom: 8px;
      break-inside: avoid-page;
      page-break-inside: avoid;
    }}
    .branch-table-wrap {{
      border: 1px solid #d8e1eb;
      border-radius: 10px;
      background: #ffffff;
      padding: 6px 8px 7px;
      box-shadow: 0 3px 12px rgba(15, 76, 129, 0.05);
      margin-bottom: 8px;
      break-inside: avoid-page;
      page-break-inside: avoid;
    }}
    .branch-subtitle {{
      margin-bottom: 6px;
      font-size: 10px;
      font-weight: 700;
      color: #0f4c81;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .branch-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 9px;
      line-height: 1.2;
    }}
    .branch-table thead th {{
      text-align: left;
      padding: 5px 6px;
      background: #0f4c81;
      color: #ffffff;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-size: 7.6px;
    }}
    .branch-table thead th.numeric {{
      text-align: right;
    }}
    .branch-table tbody td, .branch-table tbody th {{
      padding: 4px 6px;
      border-bottom: 1px solid #e5e7eb;
      vertical-align: top;
    }}
    .branch-table tbody th {{
      text-align: left;
      background: #f8fafc;
      color: #52606d;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-size: 7.6px;
      width: 44%;
    }}
    .branch-table tbody tr:nth-child(even) {{
      background: #f8fafc;
    }}
    .branch-table tbody tr.control-meter-row {{
      background: #eef6fc;
    }}
    .branch-table tbody tr.nested-meter-row td:first-child {{
      color: #475569;
    }}
    .branch-table tbody tr:last-child td, .branch-table tbody tr:last-child th {{
      border-bottom: none;
    }}
    .numeric {{
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }}
    .strong {{
      font-weight: 700;
    }}
    .cell-note {{
      margin-top: 2px;
      color: #52606d;
      font-size: 7.8px;
      line-height: 1.25;
    }}
    .muted {{
      color: #64748b;
      margin: 0;
      line-height: 1.45;
    }}
  </style>
</head>
<body>
  <header class="page-header">
    <div>
      <div class="title-eyebrow">Monitoring platforma</div>
      <h1>Měsíční report fakturačních plynoměrů</h1>
    </div>
    <div class="page-logo">{logo_html}</div>
    <div class="page-meta">
      <strong>Období:</strong> {escape(report.date_range_label)}<br>
      <strong>Vygenerováno:</strong> {escape(generated_at)}<br>
      <strong>Zdroj:</strong> monitoring.plynomery_fakturacni_odecty
    </div>
  </header>

  <section class="report-section">
    <div class="report-hero">
      <div class="report-title-block">
        <div class="title-eyebrow">Souhrn reportu</div>
        <h2>Měsíční porovnání fakturačních a podružných plynoměrů</h2>
        <div class="report-meta"><strong>Typ reportu:</strong> Měsíční</div>
        <div class="report-description">
          Report vychází z ručních fakturačních odečtů a provozních měření podružných
          plynoměrů. Přímé podružné plynoměry jsou započtené do porovnání větve,
          hierarchické detailní měření je uvedené informativně.
        </div>
      </div>
    </div>

    <div class="summary-grid">
      {_build_metric_card("Celkem fakturační plynoměry", _format_volume(total_billing), primary=True)}
      {_build_metric_card("Celkem přímé podružné", _format_volume(total_submeters))}
      {_build_metric_card("Celkový rozdíl", _format_volume(total_difference, signed=True), "fakturace - podružné")}
      {_build_metric_card("Počet větví", str(len(report.branches)))}
    </div>

    {branches_html}
  </section>
</body>
</html>"""


def render_monthly_plynomery_billing_report_pdf(report: MonthlyBillingReportData) -> bytes:
    sync_playwright = _load_playwright_api()
    html = build_monthly_plynomery_billing_report_html(report)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.emulate_media(media="screen")
            return page.pdf(
                format="A4",
                print_background=True,
                margin={
                    "top": "12mm",
                    "right": "10mm",
                    "bottom": "12mm",
                    "left": "10mm",
                },
            )
        finally:
            browser.close()


def build_monthly_plynomery_billing_report_pdf_filename(report: MonthlyBillingReportData) -> str:
    return f"Mesicni report plynomeru - {report.month:02d}.{report.year}.pdf"


def build_monthly_plynomery_billing_report(
    *,
    year: int,
    month: int,
) -> MonthlyBillingReportData:
    return build_monthly_billing_report_data(year=year, month=month)
