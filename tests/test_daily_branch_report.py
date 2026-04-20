import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.reporting import daily_branch_report as report_module


def test_build_daily_branch_report_computes_branch_metrics(monkeypatch):
    target_date = datetime.date(2026, 4, 15)
    raw_branch_payload = [
        {
            "key": "SCVK_HE",
            "title": "HECHT",
            "billing_ident": "SCVK_HE",
            "daily_limit": 20.0,
            "actual_total": 12.0,
            "expected_total": 14.0,
            "last_actual_timestamp": datetime.datetime(2026, 4, 15, 23, 0, 0),
            "hourly_rows": [
                {
                    "date": datetime.datetime(2026, 4, 15, 0, 0, 0),
                    "ocekavana_spotreba": 4.0,
                    "fakturacni_spotreba": 3.0,
                },
                {
                    "date": datetime.datetime(2026, 4, 15, 1, 0, 0),
                    "ocekavana_spotreba": 5.0,
                    "fakturacni_spotreba": 4.0,
                },
                {
                    "date": datetime.datetime(2026, 4, 15, 2, 0, 0),
                    "ocekavana_spotreba": 5.0,
                    "fakturacni_spotreba": 4.0,
                },
            ],
            "device_consumption_rows": [
                {
                    "identifikace": "A_V1",
                    "start_value": 100.0,
                    "end_value": 109.0,
                    "spotreba": 9.0,
                    "podil_procent": 75.0,
                    "ocekavana_spotreba": 8.0,
                },
                {
                    "identifikace": "B_V1",
                    "start_value": 50.0,
                    "end_value": 53.0,
                    "spotreba": 3.0,
                    "podil_procent": 25.0,
                    "ocekavana_spotreba": 6.0,
                },
            ],
            "device_hourly_rows": [
                {"date": datetime.datetime(2026, 4, 15, 0, 0, 0), "identifikace": "A_V1", "spotreba": 3.0},
                {"date": datetime.datetime(2026, 4, 15, 1, 0, 0), "identifikace": "A_V1", "spotreba": 4.0},
                {"date": datetime.datetime(2026, 4, 15, 2, 0, 0), "identifikace": "A_V1", "spotreba": 2.0},
                {"date": datetime.datetime(2026, 4, 15, 0, 0, 0), "identifikace": "B_V1", "spotreba": 1.0},
                {"date": datetime.datetime(2026, 4, 15, 1, 0, 0), "identifikace": "B_V1", "spotreba": 1.0},
                {"date": datetime.datetime(2026, 4, 15, 2, 0, 0), "identifikace": "B_V1", "spotreba": 1.0},
            ],
        }
    ]

    monkeypatch.setattr(report_module, "load_branch_day_overview", lambda *args, **kwargs: raw_branch_payload)

    report = report_module.build_daily_branch_report(
        target_date=target_date,
        generated_at=datetime.datetime(2026, 4, 16, 6, 0, 0),
    )

    assert report.target_date == target_date
    assert report.total_branch_count == 1
    branch = report.branches[0]
    assert branch.title == "HECHT"
    assert branch.billing_total == 11.0
    assert branch.remaining_to_limit == 8.0
    assert branch.difference_vs_billing == 1.0
    assert branch.actual_vs_billing_percent == 109.1
    assert branch.device_rows[0].identifikace == "A_V1"
    assert branch.device_rows[0].start_value == 100.0
    assert branch.device_rows[0].end_value == 109.0
    assert branch.device_rows[0].spotreba_ku_ocekavani_procent == 112.5
    assert "<svg" in branch.chart_svg

    html = report_module.build_daily_branch_report_html(report)
    assert "Denní report fakturačních vodoměrů" in html
    assert "HECHT" in html
    assert "Součet spotřeby vs. fakturační vodoměr" in html
    assert "Do limitu SČVK" in html
    assert "SPOTŘEBA SČVK" in html
    assert "-14%" in html
    assert "Pokrytí 109.1 %" in html
    assert "Odchylky" in html
    assert "Na 1 vodoměr / den" in html
    assert "Na 1 vodoměr / hodinu" in html
    assert "Počáteční stav" in html
    assert "Konečný stav" in html
    assert "100.000 m³" in html
    assert "109.000 m³" in html
    assert "+0.500 m³" in html
    assert "+0.021 m³" in html
    assert "stroke='#f97316'" in html
    assert "chart-line-legend" in html
    assert ">SČVK<" in html
    assert ">Predikce<" in html
    assert "Graf spotřeby větve" not in html
    assert "Odběrná místa" not in html
    assert "chart-legend" not in html
    assert "Barevná plocha:" not in html
    assert "Rozpočítání spotřeby podružných vodoměrů" not in html
    assert "Skutečná data do:" not in html
    assert "data:image/png;base64" in html
    assert ".branch-table thead th.numeric" in html


def test_build_daily_branch_report_email_body_contains_total_row():
    report = report_module.DailyBranchReport(
        generated_at=datetime.datetime(2026, 4, 16, 6, 0, 0),
        target_date=datetime.date(2026, 4, 15),
        branches=(
            report_module.BranchDailyReportSection(
                key="SCVK_HE",
                title="HECHT",
                billing_ident="SCVK_HE",
                actual_total=12.0,
                expected_total=14.0,
                daily_limit=20.0,
                remaining_to_limit=8.0,
                billing_total=11.0,
                difference_vs_billing=1.0,
                actual_vs_billing_percent=109.1,
                last_actual_timestamp=datetime.datetime(2026, 4, 15, 23, 0, 0),
                device_rows=(),
                chart_svg="<svg></svg>",
            ),
            report_module.BranchDailyReportSection(
                key="SCVK_DV",
                title="DOKTOR voda",
                billing_ident="SCVK_DV",
                actual_total=8.5,
                expected_total=9.0,
                daily_limit=10.0,
                remaining_to_limit=1.5,
                billing_total=7.25,
                difference_vs_billing=1.25,
                actual_vs_billing_percent=117.2,
                last_actual_timestamp=datetime.datetime(2026, 4, 15, 23, 0, 0),
                device_rows=(),
                chart_svg="<svg></svg>",
            ),
        ),
    )

    body = report_module._build_report_email_body(report, "Denni report vodomeru - 15.04.2026.pdf")

    assert "<strong>Celkem</strong>" in body
    assert "20.500 m³" in body
    assert "18.250 m³" in body
    assert "+2.250 m³" in body


def test_send_daily_vodomery_branch_report_sends_pdf_attachment(monkeypatch):
    sent_messages = []
    report = report_module.DailyBranchReport(
        generated_at=datetime.datetime(2026, 4, 16, 6, 0, 0),
        target_date=datetime.date(2026, 4, 15),
        branches=(
            report_module.BranchDailyReportSection(
                key="SCVK_HE",
                title="HECHT",
                billing_ident="SCVK_HE",
                actual_total=12.0,
                expected_total=14.0,
                daily_limit=20.0,
                remaining_to_limit=8.0,
                billing_total=11.0,
                difference_vs_billing=1.0,
                actual_vs_billing_percent=109.1,
                last_actual_timestamp=datetime.datetime(2026, 4, 15, 23, 0, 0),
                device_rows=(),
                chart_svg="<svg></svg>",
            ),
        ),
    )

    monkeypatch.setattr(report_module, "build_daily_branch_report", lambda **kwargs: report)
    monkeypatch.setattr(report_module, "render_daily_branch_report_pdf", lambda current_report: b"%PDF-1.4")
    monkeypatch.setattr(report_module, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))
    monkeypatch.setattr(report_module, "_load_recipients", lambda: ("branch@armex.cz",))
    monkeypatch.setattr(report_module, "_resolve_sender_alias", lambda: "Monitoring")

    result = report_module.send_daily_vodomery_branch_report()

    assert result == {
        "title": "Vodomery | denni report fakturacnich vodomeru | 15.04.2026",
        "recipient_count": 1,
        "recipients": ("branch@armex.cz",),
        "target_date": "2026-04-15",
        "branch_count": 1,
        "pdf_filename": "Denni report vodomeru - 15.04.2026.pdf",
        "pdf_size_bytes": 8,
    }
    assert len(sent_messages) == 1
    assert sent_messages[0]["email_receiver"] == "branch@armex.cz"
    assert sent_messages[0]["subject"] == "Vodomery | denni report fakturacnich vodomeru | 15.04.2026"
    assert sent_messages[0]["sender_alias"] == "Monitoring"
    assert sent_messages[0]["is_html"] is True
    assert "HECHT" in sent_messages[0]["body"]
    assert sent_messages[0]["attachments"] == [
        ("Denni report vodomeru - 15.04.2026.pdf", b"%PDF-1.4", "application", "pdf")
    ]


def test_send_daily_vodomery_branch_report_skips_when_no_sendable_recipients(monkeypatch):
    build_calls = []
    sent_messages = []

    monkeypatch.setattr(report_module, "_load_recipients", lambda: ())
    monkeypatch.setattr(
        report_module,
        "build_daily_branch_report",
        lambda **kwargs: build_calls.append(kwargs),
    )
    monkeypatch.setattr(report_module, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))

    result = report_module.send_daily_vodomery_branch_report(
        target_date=datetime.date(2026, 4, 15),
    )

    assert result == {
        "title": "Vodomery | denni report fakturacnich vodomeru | 15.04.2026",
        "recipient_count": 0,
        "recipients": (),
        "target_date": "2026-04-15",
        "branch_count": 0,
        "pdf_filename": "Denni report vodomeru - 15.04.2026.pdf",
        "pdf_size_bytes": 0,
        "skipped": True,
        "skip_reason": "no_sendable_recipients",
    }
    assert build_calls == []
    assert sent_messages == []
