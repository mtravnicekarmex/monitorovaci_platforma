import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.reporting import billing_summary_report as report_module


def test_build_periodic_vodomery_billing_summary_report_aggregates_branch_report_rows(monkeypatch):
    period = report_module.BillingSummaryReportPeriod(
        kind="month",
        title_label="Měsíční",
        period_start=datetime.datetime(2026, 3, 1, 0, 0, 0),
        period_end=datetime.datetime(2026, 4, 1, 0, 0, 0),
    )
    branch_sections = (
        SimpleNamespace(
            title="HECHT",
            billing_ident="SCVK_HE",
            billing_total=12.0,
            billing_row=SimpleNamespace(
                start_value=100.0,
                end_value=112.0,
                spotreba=12.0,
            ),
            device_rows=(
                SimpleNamespace(identifikace="A_V1", start_value=100.0, end_value=108.0, spotreba=8.0),
                SimpleNamespace(identifikace="B_V1", start_value=200.0, end_value=202.0, spotreba=2.0),
            ),
        ),
        SimpleNamespace(
            title="DOKTOR voda",
            billing_ident="SCVK_DV",
            billing_total=8.0,
            billing_row=SimpleNamespace(
                start_value=50.0,
                end_value=58.0,
                spotreba=8.0,
            ),
            device_rows=(
                SimpleNamespace(identifikace="C_V1", start_value=300.0, end_value=304.0, spotreba=4.0),
                SimpleNamespace(identifikace="D_V1", start_value=400.0, end_value=402.0, spotreba=2.0),
            ),
        ),
    )

    monkeypatch.setattr(
        report_module,
        "_load_branch_sections_for_period",
        lambda current_period: branch_sections,
    )

    report = report_module.build_periodic_vodomery_billing_summary_report(
        period,
        generated_at=datetime.datetime(2026, 4, 1, 6, 0, 0),
    )

    assert report.period.date_range_label == "01.03.2026 - 31.03.2026"
    assert report.total_billing_consumption == 20.0
    assert report.total_submeter_consumption == 16.0
    assert report.total_difference == 4.0
    assert report.coverage_percent == 80.0
    assert report.total_billing_price == 1549.6
    assert report.total_billing_sewerage_price == 747.96
    assert report.total_billing_total_price == 2297.56
    assert report.total_submeter_baseline_price == 1239.68
    assert report.total_submeter_baseline_sewerage_price == 623.3
    assert report.total_submeter_baseline_total_price == 1862.98
    assert report.total_adjusted_submeter_consumption == 20.0
    assert report.total_adjusted_submeter_price == 1549.6
    assert report.total_adjusted_submeter_sewerage_price == 779.12
    assert report.total_adjusted_submeter_total_price == 2328.72
    assert report.total_submeter_difference_amount == 465.74

    billing_rows = {row.billing_ident: row for row in report.billing_rows}
    assert billing_rows["SCVK_HE"].start_value == 100.0
    assert billing_rows["SCVK_HE"].end_value == 112.0
    assert billing_rows["SCVK_HE"].consumption == 12.0
    assert billing_rows["SCVK_HE"].share_percent == 60.0
    assert billing_rows["SCVK_HE"].adjusted_consumption == 12.0
    assert billing_rows["SCVK_HE"].price_amount == 929.76
    assert billing_rows["SCVK_HE"].sewerage_price_amount == 747.96
    assert billing_rows["SCVK_HE"].total_price_amount == 1677.72
    assert billing_rows["SCVK_HE"].baseline_total_price_amount == 1677.72
    assert billing_rows["SCVK_HE"].difference_amount == 0.0
    assert billing_rows["SCVK_DV"].share_percent == 40.0
    assert billing_rows["SCVK_DV"].price_amount == 619.84
    assert billing_rows["SCVK_DV"].sewerage_price_amount == 0.0
    assert billing_rows["SCVK_DV"].total_price_amount == 619.84
    assert billing_rows["SCVK_DV"].baseline_total_price_amount == 619.84
    assert billing_rows["SCVK_DV"].difference_amount == 0.0

    submeter_rows = {row.identifikace: row for row in report.submeter_rows}
    assert submeter_rows["A_V1"].start_value == 100.0
    assert submeter_rows["A_V1"].end_value == 108.0
    assert submeter_rows["A_V1"].share_percent == 50.0
    assert submeter_rows["A_V1"].adjusted_consumption == 10.0
    assert submeter_rows["A_V1"].price_amount == 774.8
    assert submeter_rows["A_V1"].sewerage_price_amount == 623.3
    assert submeter_rows["A_V1"].total_price_amount == 1398.1
    assert submeter_rows["A_V1"].baseline_total_price_amount == 1118.48
    assert submeter_rows["A_V1"].difference_amount == 279.62
    assert submeter_rows["B_V1"].share_percent == 12.5
    assert submeter_rows["B_V1"].adjusted_consumption == 2.5
    assert submeter_rows["B_V1"].price_amount == 193.7
    assert submeter_rows["B_V1"].sewerage_price_amount == 155.82
    assert submeter_rows["B_V1"].total_price_amount == 349.52
    assert submeter_rows["B_V1"].baseline_total_price_amount == 279.62
    assert submeter_rows["B_V1"].difference_amount == 69.9
    assert submeter_rows["C_V1"].share_percent == 25.0
    assert submeter_rows["C_V1"].adjusted_consumption == 5.0
    assert submeter_rows["C_V1"].price_amount == 387.4
    assert submeter_rows["C_V1"].sewerage_price_amount == 0.0
    assert submeter_rows["C_V1"].total_price_amount == 387.4
    assert submeter_rows["C_V1"].baseline_total_price_amount == 309.92
    assert submeter_rows["C_V1"].difference_amount == 77.48
    assert submeter_rows["D_V1"].share_percent == 12.5
    assert submeter_rows["D_V1"].adjusted_consumption == 2.5
    assert submeter_rows["D_V1"].price_amount == 193.7
    assert submeter_rows["D_V1"].sewerage_price_amount == 0.0
    assert submeter_rows["D_V1"].total_price_amount == 193.7
    assert submeter_rows["D_V1"].baseline_total_price_amount == 154.96
    assert submeter_rows["D_V1"].difference_amount == 38.74

    html = report_module.build_vodomery_billing_summary_report_html(report)

    assert "Měsíční report SČVK vs. odběrná místa" in html
    assert "Souhrn spotřeby SČVK vodoměrů" in html
    assert "Souhrn spotřeby odběrných míst" in html
    assert "Upravená spotřeba" in html
    assert "Cena bez odchylky" in html
    assert "Rozdíl" in html
    assert "Cena vody" in html
    assert "Cena stočné" in html
    assert "Cena celkem" in html
    assert "Cena stočné" in html
    assert "SCVK_HE" in html
    assert "SCVK_DV" in html
    assert "A_V1" in html
    assert "01.03.2026 - 31.03.2026" in html
    assert "80.0 %" in html
    assert "100.0 %" in html
    assert "-4.000 m³" in html
    assert "Odběrná místa 16.000 m³ vs. SČVK 20.000 m³" in html
    assert "Pokrytí 80.0 %\nRozdíl cen -434.58 Kč" in html
    assert "-434.58 Kč" in html
    assert "1549.60 Kč" in html
    assert "747.96 Kč" in html
    assert "2297.56 Kč" in html
    assert "1862.98 Kč" in html
    assert "779.12 Kč" in html
    assert "2328.72 Kč" in html
    assert "465.74 Kč" in html
    assert "Cena stočné</div>" in html
    assert '<header class="page-header">' in html
    assert "display: none;" not in html
    assert ".branch-table .column-device" in html
    assert "width: 104px;" in html
    assert "<th class='column-device'>Odběrné místo</th>" in html
    assert "<th class='numeric'>Upravená spotřeba</th>" in html
    assert "<th class='numeric'>Cena bez odchylky</th>" in html
    assert "white-space: pre-line;" in html
    assert "Rozdíl cen</div>" not in html
    assert "Podíl v tabulce SČVK vodoměrů je počítán vůči součtu spotřeby všech SČVK vodoměrů." in html
    assert "Podíl v tabulce odběrných míst je počítán vůči součtu spotřeby všech odběrných míst." in html


def test_send_monthly_vodomery_billing_summary_report_sends_pdf_attachment(monkeypatch):
    report = report_module.BillingSummaryReport(
        generated_at=datetime.datetime(2026, 4, 1, 6, 0, 0),
        period=report_module.BillingSummaryReportPeriod(
            kind="month",
            title_label="Měsíční",
            period_start=datetime.datetime(2026, 3, 1, 0, 0, 0),
            period_end=datetime.datetime(2026, 4, 1, 0, 0, 0),
        ),
        water_price_per_m3=77.48,
        sewerage_price_per_m3=62.33,
        billing_rows=(
            report_module.BillingSummaryBillingRow(
                branch_title="HECHT",
                billing_ident="SCVK_HE",
                start_value=100.0,
                end_value=112.0,
                consumption=12.0,
                share_percent=100.0,
                adjusted_consumption=12.0,
                price_amount=929.76,
                sewerage_price_amount=747.96,
                total_price_amount=1677.72,
                baseline_total_price_amount=1677.72,
                difference_amount=0.0,
            ),
        ),
        submeter_rows=(
            report_module.BillingSummarySubmeterRow(
                branch_title="HECHT",
                billing_ident="SCVK_HE",
                identifikace="A_V1",
                start_value=100.0,
                end_value=108.0,
                consumption=10.0,
                share_percent=83.3,
                adjusted_consumption=12.0,
                price_amount=774.8,
                sewerage_price_amount=623.3,
                total_price_amount=1398.1,
                baseline_total_price_amount=1398.1,
                difference_amount=0.0,
            ),
        ),
        total_billing_consumption=12.0,
        total_submeter_consumption=10.0,
        total_difference=2.0,
        coverage_percent=83.3,
        total_billing_price=929.76,
        total_billing_sewerage_price=747.96,
        total_billing_total_price=1677.72,
        total_submeter_baseline_price=774.8,
        total_submeter_baseline_sewerage_price=623.3,
        total_submeter_baseline_total_price=1398.1,
        total_adjusted_submeter_consumption=12.0,
        total_adjusted_submeter_price=929.76,
        total_adjusted_submeter_sewerage_price=747.96,
        total_adjusted_submeter_total_price=1677.72,
        total_submeter_difference_amount=279.62,
    )
    sent_messages = []

    monkeypatch.setattr(report_module, "build_monthly_vodomery_billing_summary_report", lambda **kwargs: report)
    monkeypatch.setattr(report_module, "render_vodomery_billing_summary_report_pdf", lambda current_report: b"%PDF-1.4")
    monkeypatch.setattr(report_module, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))
    monkeypatch.setattr(report_module, "_load_monthly_recipients", lambda: ("souhrn@armex.cz",))
    monkeypatch.setattr(report_module, "_resolve_monthly_sender_alias", lambda: "Monitoring")

    result = report_module.send_monthly_vodomery_billing_summary_report()

    assert result == {
        "title": "Vodomery | mesicni souhrn SCVK vs odberna mista | 03.2026",
        "recipient_count": 1,
        "recipients": ("souhrn@armex.cz",),
        "period": "01.03.2026 - 31.03.2026",
        "pdf_filename": "Mesicni souhrn SCVK vodomeru - 03.2026.pdf",
        "pdf_size_bytes": 8,
    }
    assert len(sent_messages) == 1
    assert sent_messages[0]["email_receiver"] == "souhrn@armex.cz"
    assert sent_messages[0]["subject"] == "Vodomery | mesicni souhrn SCVK vs odberna mista | 03.2026"
    assert sent_messages[0]["sender_alias"] == "Monitoring"
    assert sent_messages[0]["is_html"] is True
    assert sent_messages[0]["attachments"] == [
        ("Mesicni souhrn SCVK vodomeru - 03.2026.pdf", b"%PDF-1.4", "application", "pdf")
    ]


def test_render_vodomery_billing_summary_report_pdf_does_not_use_repeating_header(monkeypatch):
    report = report_module.BillingSummaryReport(
        generated_at=datetime.datetime(2026, 4, 1, 6, 0, 0),
        period=report_module.BillingSummaryReportPeriod(
            kind="day",
            title_label="Denní",
            period_start=datetime.datetime(2026, 5, 4, 0, 0, 0),
            period_end=datetime.datetime(2026, 5, 5, 0, 0, 0),
        ),
        water_price_per_m3=77.48,
        sewerage_price_per_m3=62.33,
        billing_rows=(),
        submeter_rows=(),
        total_billing_consumption=0.0,
        total_submeter_consumption=0.0,
        total_difference=0.0,
        coverage_percent=None,
        total_billing_price=None,
        total_billing_sewerage_price=None,
        total_billing_total_price=None,
        total_submeter_baseline_price=None,
        total_submeter_baseline_sewerage_price=None,
        total_submeter_baseline_total_price=None,
        total_adjusted_submeter_consumption=None,
        total_adjusted_submeter_price=None,
        total_adjusted_submeter_sewerage_price=None,
        total_adjusted_submeter_total_price=None,
        total_submeter_difference_amount=None,
    )
    pdf_call = {}

    class FakePage:
        def set_content(self, html, wait_until=None):
            pdf_call["html"] = html
            pdf_call["wait_until"] = wait_until

        def emulate_media(self, media=None):
            pdf_call["media"] = media

        def pdf(self, **kwargs):
            pdf_call["kwargs"] = kwargs
            return b"%PDF-1.4"

    class FakeBrowser:
        def __init__(self):
            self.page = FakePage()

        def new_page(self):
            return self.page

        def close(self):
            pdf_call["closed"] = True

    class FakePlaywrightContext:
        def __enter__(self):
            return SimpleNamespace(
                chromium=SimpleNamespace(
                    launch=lambda headless=True: FakeBrowser()
                )
            )

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(report_module, "_load_playwright_api", lambda: (lambda: FakePlaywrightContext()))
    monkeypatch.setattr(report_module, "_load_image_data_uri", lambda path: "data:image/png;base64,TEST")

    pdf_bytes = report_module.render_vodomery_billing_summary_report_pdf(report)

    assert pdf_bytes == b"%PDF-1.4"
    assert pdf_call["wait_until"] == "load"
    assert pdf_call["media"] == "screen"
    assert pdf_call["kwargs"] == {
        "format": "A4",
        "print_background": True,
        "margin": {"top": "10mm", "right": "8mm", "bottom": "10mm", "left": "8mm"},
    }
    assert pdf_call["closed"] is True
