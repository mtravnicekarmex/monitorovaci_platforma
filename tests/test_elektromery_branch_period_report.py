import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.elektromery.reporting import branch_period_report as report_module


def test_build_weekly_elektromery_branch_report_computes_period_metrics(monkeypatch):
    raw_branch_payload = [
        {
            "key": "TS1",
            "title": "TS1",
            "actual_total": 12.0,
            "vt_total": 7.0,
            "nt_total": 5.0,
            "last_actual_timestamp": datetime.datetime(2026, 4, 13, 0, 0, 0),
            "device_consumption_rows": [
                {
                    "identifikace": "A-1",
                    "start_value": 100.0,
                    "end_value": 109.0,
                    "spotreba": 9.0,
                    "spotreba_vt": 5.0,
                    "spotreba_nt": 4.0,
                    "podil_procent": 75.0,
                    "active_days": 7,
                },
                {
                    "identifikace": "B",
                    "start_value": 50.0,
                    "end_value": 53.0,
                    "spotreba": 3.0,
                    "spotreba_vt": 2.0,
                    "spotreba_nt": 1.0,
                    "podil_procent": 25.0,
                    "active_days": 7,
                },
            ],
            "daily_rows": [
                {
                    "date": datetime.datetime(2026, 4, 6, 0, 0, 0),
                    "actual_total": 4.0,
                    "vt_total": 2.0,
                    "nt_total": 2.0,
                    "device_values": {"A-1": 3.0, "B": 1.0},
                },
                {
                    "date": datetime.datetime(2026, 4, 7, 0, 0, 0),
                    "actual_total": 8.0,
                    "vt_total": 5.0,
                    "nt_total": 3.0,
                    "device_values": {"A-1": 6.0, "B": 2.0},
                },
            ],
        }
    ]

    monkeypatch.setattr(report_module, "load_branch_period_overview", lambda *args, **kwargs: raw_branch_payload)

    report = report_module.build_weekly_elektromery_branch_report(
        reference_date=datetime.date(2026, 4, 15),
        generated_at=datetime.datetime(2026, 4, 15, 6, 0, 0),
    )

    assert report.period.date_range_label == "06.04.2026 - 12.04.2026"
    assert report.total_branch_count == 1
    branch = report.branches[0]
    assert branch.title == "TS1"
    assert branch.actual_total == 12.0
    assert branch.vt_total == 7.0
    assert branch.nt_total == 5.0
    assert branch.device_rows[0].identifikace == "A-1"
    assert branch.device_rows[0].active_days == 7
    assert "<svg" in branch.chart_svg

    html = report_module.build_elektromery_branch_report_html(report)
    assert "Týdenní report spotřeby elektroměrů" in html
    assert "Celková spotřeba trafostanic" in html
    assert "Bilance po větvích" in html
    assert "Noční odběr" not in html
    assert "12.000 kWh" in html
    assert "data:image/png;base64" in html


def test_send_weekly_elektromery_branch_report_sends_pdf_attachment(monkeypatch):
    sent_messages = []
    report = report_module.BranchPeriodReport(
        generated_at=datetime.datetime(2026, 4, 15, 6, 0, 0),
        period=report_module.BranchReportPeriod(
            kind="weekly",
            title_prefix="Týdenní",
            file_prefix="Tydenni",
            period_start=datetime.datetime(2026, 4, 6, 0, 0, 0),
            period_end=datetime.datetime(2026, 4, 13, 0, 0, 0),
            label="2026-W15",
        ),
        branches=(
            report_module.BranchPeriodReportSection(
                key="TS1",
                title="TS1",
                actual_total=12.0,
                vt_total=7.0,
                nt_total=5.0,
                last_actual_timestamp=datetime.datetime(2026, 4, 13, 0, 0, 0),
                device_rows=(),
                daily_rows=(),
                chart_svg="<svg></svg>",
            ),
        ),
    )

    monkeypatch.setattr(report_module, "build_weekly_elektromery_branch_report", lambda **kwargs: report)
    monkeypatch.setattr(report_module, "render_elektromery_branch_report_pdf", lambda current_report: b"%PDF-1.4")
    monkeypatch.setattr(report_module, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))
    monkeypatch.setattr(report_module, "_load_weekly_recipients", lambda: ("elektro@armex.cz",))
    monkeypatch.setattr(report_module, "_resolve_weekly_sender_alias", lambda: "Monitoring")

    result = report_module.send_weekly_elektromery_branch_report()

    assert result == {
        "title": "Elektromery | týdenní report spotreby | 06.04.2026 - 12.04.2026",
        "recipient_count": 1,
        "recipients": ("elektro@armex.cz",),
        "period": "06.04.2026 - 12.04.2026",
        "branch_count": 1,
        "pdf_filename": "Tydenni report elektromeru - 06.04.2026 - 12.04.2026.pdf",
        "pdf_size_bytes": 8,
    }
    assert len(sent_messages) == 1
    assert sent_messages[0]["email_receiver"] == "elektro@armex.cz"
    assert sent_messages[0]["sender_alias"] == "Monitoring"
    assert sent_messages[0]["is_html"] is True
    assert "TS1" in sent_messages[0]["body"]
    assert sent_messages[0]["attachments"] == [
        ("Tydenni report elektromeru - 06.04.2026 - 12.04.2026.pdf", b"%PDF-1.4", "application", "pdf")
    ]


def test_send_monthly_elektromery_branch_report_skips_when_no_sendable_recipients(monkeypatch):
    report = report_module.BranchPeriodReport(
        generated_at=datetime.datetime(2026, 4, 1, 6, 0, 0),
        period=report_module.BranchReportPeriod(
            kind="monthly",
            title_prefix="Měsíční",
            file_prefix="Mesicni",
            period_start=datetime.datetime(2026, 3, 1, 0, 0, 0),
            period_end=datetime.datetime(2026, 4, 1, 0, 0, 0),
            label="03/2026",
        ),
        branches=(),
    )

    monkeypatch.setattr(report_module, "build_monthly_elektromery_branch_report", lambda **kwargs: report)
    monkeypatch.setattr(report_module, "_load_monthly_recipients", lambda: ())

    result = report_module.send_monthly_elektromery_branch_report()

    assert result == {
        "title": "Elektromery | měsíční report spotreby | 01.03.2026 - 31.03.2026",
        "recipient_count": 0,
        "recipients": (),
        "period": "01.03.2026 - 31.03.2026",
        "branch_count": 0,
        "pdf_filename": "Mesicni report elektromeru - 01.03.2026 - 31.03.2026.pdf",
        "pdf_size_bytes": 0,
        "skipped": True,
        "skip_reason": "no_sendable_recipients",
    }
