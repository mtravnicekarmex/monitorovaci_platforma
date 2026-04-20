import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.reporting import monthly_branch_report as report_module


def test_build_monthly_vodomery_branch_report_aggregates_daily_payloads(monkeypatch):
    period = report_module.MonthlyBranchReportPeriod(
        year=2026,
        month=3,
        period_start=datetime.datetime(2026, 3, 1, 0, 0, 0),
        period_end=datetime.datetime(2026, 3, 3, 0, 0, 0),
    )

    payload_by_date = {
        datetime.date(2026, 3, 1): [
            {
                "key": "SCVK_HE",
                "title": "HECHT",
                "billing_ident": "SCVK_HE",
                "daily_limit": 20.0,
                "active_devices": ["A_V1", "B_V1"],
                "actual_total": 12.0,
                "expected_total": 14.0,
                "hourly_rows": [
                    {"date": datetime.datetime(2026, 3, 1, 0, 0, 0), "fakturacni_spotreba": 3.0},
                    {"date": datetime.datetime(2026, 3, 1, 1, 0, 0), "fakturacni_spotreba": 8.0},
                ],
                "device_consumption_rows": [
                    {"identifikace": "A_V1", "start_value": 100.0, "end_value": 109.0, "spotreba": 9.0, "ocekavana_spotreba": 8.0},
                    {"identifikace": "B_V1", "start_value": 200.0, "end_value": 203.0, "spotreba": 3.0, "ocekavana_spotreba": 6.0},
                ],
            }
        ],
        datetime.date(2026, 3, 2): [
            {
                "key": "SCVK_HE",
                "title": "HECHT",
                "billing_ident": "SCVK_HE",
                "daily_limit": 20.0,
                "active_devices": ["A_V1", "C_V1"],
                "actual_total": 10.0,
                "expected_total": 8.0,
                "hourly_rows": [
                    {"date": datetime.datetime(2026, 3, 2, 0, 0, 0), "fakturacni_spotreba": 4.0},
                    {"date": datetime.datetime(2026, 3, 2, 1, 0, 0), "fakturacni_spotreba": 5.0},
                ],
                "device_consumption_rows": [
                    {"identifikace": "A_V1", "start_value": 109.0, "end_value": 113.0, "spotreba": 4.0, "ocekavana_spotreba": 3.0},
                    {"identifikace": "C_V1", "start_value": 300.0, "end_value": 306.0, "spotreba": 6.0, "ocekavana_spotreba": 5.0},
                ],
            }
        ],
    }

    monkeypatch.setattr(report_module, "_get_previous_month_period", lambda reference_date=None: period)
    monkeypatch.setattr(
        report_module,
        "load_branch_day_overview",
        lambda user_context, *, target_date: payload_by_date.get(target_date, []),
    )

    report = report_module.build_monthly_vodomery_branch_report(
        reference_date=datetime.date(2026, 4, 10),
        generated_at=datetime.datetime(2026, 4, 1, 6, 0, 0),
    )

    assert report.period.month_label == "03/2026"
    assert report.total_branch_count == 4

    hecht = next(branch for branch in report.branches if branch.key == "SCVK_HE")
    assert hecht.actual_total == 22.0
    assert hecht.expected_total == 22.0
    assert hecht.billing_total == 20.0
    assert hecht.period_limit == 40.0
    assert hecht.remaining_to_limit == 18.0
    assert hecht.difference_vs_billing == 2.0
    assert hecht.actual_vs_billing_percent == 110.0
    assert hecht.deviation_per_meter_day == 0.333
    assert hecht.deviation_per_meter_hour == 0.014
    assert hecht.device_rows[0].identifikace == "A_V1"
    assert hecht.device_rows[0].start_value == 100.0
    assert hecht.device_rows[0].end_value == 113.0
    assert hecht.device_rows[0].spotreba == 13.0
    assert hecht.device_rows[1].identifikace == "C_V1"
    assert hecht.device_rows[1].start_value == 300.0
    assert hecht.device_rows[1].end_value == 306.0
    assert "<svg" in hecht.chart_svg

    html = report_module.build_monthly_vodomery_branch_report_html(report)
    header_template = report_module._build_pdf_header_template(report)
    assert "Měsíční report fakturačních vodoměrů" in html
    assert "Období reportu:</strong> 01.03.2026 - 02.03.2026" in html
    assert "HECHT" in html
    assert "Do limitu SČVK" not in html
    assert "Predikce období" in html
    assert "Pokrytí 110.0 %" in html
    assert "Odchylky" in html
    assert "Na 1 vodoměr / den" in html
    assert "Na 1 vodoměr / hodinu" in html
    assert "Počáteční stav" in html
    assert "Konečný stav" in html
    assert "100.000 m³" in html
    assert "113.000 m³" in html
    assert "+0.333 m³" in html
    assert "+0.014 m³" in html
    assert "stroke='#f97316'" in html
    assert "chart-line-legend" in html
    assert ">SČVK<" in html
    assert ">Predikce<" in html
    assert "display: none;" in html
    assert "margin: 10mm 8mm 10mm;" in html
    assert "data:image/png;base64" in header_template
    assert "Měsíční report" in header_template
    assert "pdf-header-table" in header_template
    assert "pdf-header-rule" in header_template


def test_build_monthly_branch_report_email_body_contains_total_row():
    report = report_module.MonthlyBranchReport(
        generated_at=datetime.datetime(2026, 4, 1, 6, 0, 0),
        period=report_module.MonthlyBranchReportPeriod(
            year=2026,
            month=3,
            period_start=datetime.datetime(2026, 3, 1, 0, 0, 0),
            period_end=datetime.datetime(2026, 4, 1, 0, 0, 0),
        ),
        branches=(
            report_module.BranchMonthlyReportSection(
                key="SCVK_HE",
                title="HECHT",
                billing_ident="SCVK_HE",
                actual_total=22.0,
                expected_total=22.0,
                period_limit=620.0,
                remaining_to_limit=598.0,
                billing_total=20.0,
                difference_vs_billing=2.0,
                actual_vs_billing_percent=110.0,
                device_rows=(),
                chart_svg="<svg></svg>",
                deviation_per_meter_day=0.067,
                deviation_per_meter_hour=0.003,
            ),
            report_module.BranchMonthlyReportSection(
                key="SCVK_DV",
                title="DOKTOR voda",
                billing_ident="SCVK_DV",
                actual_total=8.0,
                expected_total=9.0,
                period_limit=310.0,
                remaining_to_limit=302.0,
                billing_total=7.0,
                difference_vs_billing=1.0,
                actual_vs_billing_percent=114.3,
                device_rows=(),
                chart_svg="<svg></svg>",
                deviation_per_meter_day=0.033,
                deviation_per_meter_hour=0.001,
            ),
        ),
    )

    body = report_module._build_report_email_body(report, "Mesicni report vodomeru - 03.2026.pdf")

    assert "Měsíční report fakturačních vodoměrů" in body
    assert "<strong>Celkem</strong>" in body
    assert "30.000 m³" in body
    assert "27.000 m³" in body
    assert "+3.000 m³" in body


def test_send_monthly_vodomery_branch_report_sends_pdf_attachment(monkeypatch):
    report = report_module.MonthlyBranchReport(
        generated_at=datetime.datetime(2026, 4, 1, 6, 0, 0),
        period=report_module.MonthlyBranchReportPeriod(
            year=2026,
            month=3,
            period_start=datetime.datetime(2026, 3, 1, 0, 0, 0),
            period_end=datetime.datetime(2026, 4, 1, 0, 0, 0),
        ),
        branches=(
            report_module.BranchMonthlyReportSection(
                key="SCVK_HE",
                title="HECHT",
                billing_ident="SCVK_HE",
                actual_total=22.0,
                expected_total=22.0,
                period_limit=620.0,
                remaining_to_limit=598.0,
                billing_total=20.0,
                difference_vs_billing=2.0,
                actual_vs_billing_percent=110.0,
                device_rows=(),
                chart_svg="<svg></svg>",
                deviation_per_meter_day=0.067,
                deviation_per_meter_hour=0.003,
            ),
        ),
    )
    sent_messages = []

    monkeypatch.setattr(report_module, "build_monthly_vodomery_branch_report", lambda **kwargs: report)
    monkeypatch.setattr(report_module, "render_monthly_vodomery_branch_report_pdf", lambda current_report: b"%PDF-1.4")
    monkeypatch.setattr(report_module, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))
    monkeypatch.setattr(report_module, "_load_recipients", lambda: ("monthly@armex.cz",))
    monkeypatch.setattr(report_module, "_resolve_sender_alias", lambda: "Monitoring")

    result = report_module.send_monthly_vodomery_branch_report()

    assert result == {
        "title": "Vodomery | mesicni report fakturacnich vodomeru | 03.2026",
        "recipient_count": 1,
        "recipients": ("monthly@armex.cz",),
        "period": "03/2026",
        "branch_count": 1,
        "pdf_filename": "Mesicni report vodomeru - 03.2026.pdf",
        "pdf_size_bytes": 8,
    }
    assert len(sent_messages) == 1
    assert sent_messages[0]["email_receiver"] == "monthly@armex.cz"
    assert sent_messages[0]["subject"] == "Vodomery | mesicni report fakturacnich vodomeru | 03.2026"
    assert sent_messages[0]["sender_alias"] == "Monitoring"
    assert sent_messages[0]["is_html"] is True
    assert "HECHT" in sent_messages[0]["body"]
    assert sent_messages[0]["attachments"] == [
        ("Mesicni report vodomeru - 03.2026.pdf", b"%PDF-1.4", "application", "pdf")
    ]
