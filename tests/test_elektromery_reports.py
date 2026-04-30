import datetime
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard import elektromery_reports


def _measurement(identifikace: str, dt: datetime.datetime, objem: float) -> dict[str, object]:
    return {
        "identifikace": identifikace,
        "seriove_cislo": 1,
        "date": dt,
        "objem": objem,
        "source_file": "LDS 2026-02.xlsx",
    }


def test_resolve_report_period_builds_week_window():
    period = elektromery_reports.resolve_report_period("week", datetime.date(2026, 2, 18))

    assert period.label == "Týdenní"
    assert period.period_start == datetime.datetime(2026, 2, 16, 0, 0)
    assert period.period_end == datetime.datetime(2026, 2, 23, 0, 0)
    assert period.bucket_frequency == "h"
    assert period.date_range_label == "16.02.2026 - 22.02.2026"


def test_build_consumption_curve_aggregates_ote_measurements_from_db_shape():
    measurements = [
        _measurement("TS1 + TS3", datetime.datetime(2026, 2, 1, 0, 15), 1.0),
        _measurement("TS2", datetime.datetime(2026, 2, 1, 0, 15), 2.0),
        _measurement("TS1 + TS3", datetime.datetime(2026, 2, 1, 0, 30), 0.5),
    ]
    df = elektromery_reports.ote_records_to_dataframe(measurements)
    period = elektromery_reports.resolve_report_period("day", datetime.date(2026, 2, 1))

    period_df = elektromery_reports.filter_measurements_for_period(df, period)
    curve = elektromery_reports.build_consumption_curve(period_df, period)
    summary = elektromery_reports.summarize_report(period_df, curve)
    exceedance = elektromery_reports.build_threshold_exceedance(curve, 10.0)

    assert curve[["spotreba_kwh", "odber_kw", "pocet_mereni"]].to_dict(orient="records") == [
        {"spotreba_kwh": 3.0, "odber_kw": 12.0, "pocet_mereni": 2},
        {"spotreba_kwh": 0.5, "odber_kw": 2.0, "pocet_mereni": 1},
    ]
    assert summary["total_consumption_kwh"] == 3.5
    assert summary["device_count"] == 2
    assert summary["max_power_kw"] == 12.0
    assert exceedance[["odber_kw", "prekroceni_kw"]].to_dict(orient="records") == [
        {"odber_kw": 12.0, "prekroceni_kw": 2.0},
    ]


def test_build_device_summary_sorts_by_consumption():
    measurements = [
        _measurement("TS1 + TS3", datetime.datetime(2026, 2, 1, 0, 15), 1.0),
        _measurement("TS2", datetime.datetime(2026, 2, 1, 0, 15), 2.0),
        _measurement("TS1 + TS3", datetime.datetime(2026, 2, 1, 0, 30), 0.5),
    ]
    df = elektromery_reports.ote_records_to_dataframe(measurements)

    summary = elektromery_reports.build_device_summary(df)

    assert summary[["identifikace", "spotreba_kwh", "pocet_mereni"]].to_dict(orient="records") == [
        {"identifikace": "TS2", "spotreba_kwh": 2.0, "pocet_mereni": 1},
        {"identifikace": "TS1 + TS3", "spotreba_kwh": 1.5, "pocet_mereni": 2},
    ]


def test_ote_records_to_dataframe_keeps_zero_consumption():
    df = elektromery_reports.ote_records_to_dataframe(
        [
            _measurement("TS2", datetime.datetime(2026, 2, 1, 0, 15), 0.0),
        ]
    )

    assert df[["identifikace", "spotreba_kwh"]].to_dict(orient="records") == [
        {"identifikace": "TS2", "spotreba_kwh": 0.0},
    ]


def test_describe_selected_identifications_formats_full_selection():
    description = elektromery_reports.describe_selected_identifications(
        ("TS1", "TS2"),
        total_available_count=2,
    )

    assert description == "Všechna odběrná místa (2)"


def test_build_ote_report_html_contains_pdf_sections():
    measurements = [
        _measurement("TS1 + TS3", datetime.datetime(2026, 2, 1, 0, 15), 1.0),
        _measurement("TS2", datetime.datetime(2026, 2, 1, 0, 15), 2.0),
        _measurement("TS1 + TS3", datetime.datetime(2026, 2, 1, 0, 30), 0.5),
    ]
    df = elektromery_reports.ote_records_to_dataframe(measurements)
    period = elektromery_reports.resolve_report_period("day", datetime.date(2026, 2, 1))
    period_df = elektromery_reports.filter_measurements_for_period(df, period)
    curve_df = elektromery_reports.build_consumption_curve(period_df, period)
    device_summary_df = elektromery_reports.build_device_summary(period_df)
    report = elektromery_reports.build_ote_pdf_report(
        period=period,
        period_label="Denní report | 01.02.2026 | krok 15 min",
        period_df=period_df,
        curve_df=curve_df,
        device_summary_df=device_summary_df,
        reserved_power_kw=10.0,
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        selected_identifications=("TS1 + TS3", "TS2"),
        available_identification_count=4,
    )

    html = elektromery_reports.build_ote_report_html(report)

    assert "Denní report spotřeby elektroměrů" in html
    assert "Křivka odběru a rezervovaná hladina" in html
    assert "Souhrn měřidel" in html
    assert "Překročení rezervované hladiny" in html
    assert "dbo.Mereni_elektromery_OTE" in html
    assert "chart-line-legend" in html
    assert "Odběrná místa:</strong> 2 / 4 odběrných míst: TS1 + TS3, TS2" in html
    assert "TS1 + TS3" in html
    assert "TS2" in html
    assert "3.500 kWh" in html
    assert "12.000 kW" in html
    assert "01.02.2026 00:15" in html
    assert "<svg" in html
    assert "data:image/png;base64" in html


def test_render_ote_report_pdf_uses_playwright(monkeypatch):
    report = elektromery_reports.OtePdfReport(
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        period=elektromery_reports.OteReportPeriod(
            kind="day",
            label="Denní",
            period_start=datetime.datetime(2026, 2, 1, 0, 0),
            period_end=datetime.datetime(2026, 2, 2, 0, 0),
            bucket_frequency="15min",
            bucket_label="15 min",
        ),
        period_label="Denní report | 01.02.2026 | krok 15 min",
        reserved_power_kw=10.0,
        total_consumption_kwh=3.5,
        measurement_count=3,
        device_count=2,
        max_power_kw=12.0,
        max_power_at=datetime.datetime(2026, 2, 1, 0, 15),
        exceedance_count=1,
        curve_rows=(),
        device_rows=(),
        exceedance_rows=(),
    )
    calls = {}

    class FakePage:
        def set_content(self, html: str, wait_until: str) -> None:
            calls["html"] = html
            calls["wait_until"] = wait_until

        def emulate_media(self, media: str) -> None:
            calls["media"] = media

        def pdf(self, **kwargs):
            calls["pdf_kwargs"] = kwargs
            return b"%PDF-1.4"

    class FakeBrowser:
        def new_page(self):
            calls["new_page"] = True
            return FakePage()

        def close(self) -> None:
            calls["closed"] = True

    class FakeChromium:
        def launch(self, *, headless: bool):
            calls["headless"] = headless
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeSyncPlaywright:
        def __enter__(self):
            calls["entered"] = True
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb) -> None:
            calls["exited"] = True

    monkeypatch.setattr(elektromery_reports, "_load_playwright_api", lambda: FakeSyncPlaywright)
    monkeypatch.setattr(elektromery_reports, "build_ote_report_html", lambda current_report: "<html>report</html>")

    pdf_bytes = elektromery_reports.render_ote_report_pdf(report)

    assert pdf_bytes == b"%PDF-1.4"
    assert calls["entered"] is True
    assert calls["headless"] is True
    assert calls["wait_until"] == "load"
    assert calls["media"] == "screen"
    assert calls["pdf_kwargs"]["format"] == "A4"
    assert calls["closed"] is True
    assert calls["exited"] is True


def test_render_ote_report_pdf_wraps_not_implemented_error_on_windows(monkeypatch):
    report = elektromery_reports.OtePdfReport(
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        period=elektromery_reports.OteReportPeriod(
            kind="day",
            label="Denní",
            period_start=datetime.datetime(2026, 2, 1, 0, 0),
            period_end=datetime.datetime(2026, 2, 2, 0, 0),
            bucket_frequency="15min",
            bucket_label="15 min",
        ),
        period_label="Denní report | 01.02.2026 | krok 15 min",
        reserved_power_kw=10.0,
        total_consumption_kwh=3.5,
        measurement_count=3,
        device_count=2,
        max_power_kw=12.0,
        max_power_at=datetime.datetime(2026, 2, 1, 0, 15),
        exceedance_count=1,
        curve_rows=(),
        device_rows=(),
        exceedance_rows=(),
    )

    monkeypatch.setattr(elektromery_reports, "build_ote_report_html", lambda current_report: "<html>report</html>")
    monkeypatch.setattr(
        elektromery_reports,
        "_render_pdf_from_html_windows_worker",
        lambda html: (_ for _ in ()).throw(NotImplementedError()),
    )

    with pytest.raises(elektromery_reports.ElektromeryDashboardReportError) as exc_info:
        elektromery_reports.render_ote_report_pdf(report)

    assert "Windows event loopu" in str(exc_info.value)
