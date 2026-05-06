import datetime
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard import vodomery_reports


def _measurement(
    identifikace: str,
    dt: datetime.datetime,
    objem: float,
    *,
    delta: float | None = None,
    interval_minutes: int = 15,
    platne: bool = True,
    reset_detected: bool = False,
    zdroj: str = "AREAL",
) -> dict[str, object]:
    return {
        "identifikace": identifikace,
        "seriove_cislo": f"SN-{identifikace}",
        "date": dt,
        "objem": objem,
        "delta": delta,
        "interval_minutes": interval_minutes,
        "platne": platne,
        "reset_detected": reset_detected,
        "zdroj": zdroj,
    }


def test_resolve_report_period_builds_month_window_with_hour_bucket():
    period = vodomery_reports.resolve_report_period("month", datetime.date(2026, 2, 18))

    assert period.label == "Měsíční"
    assert period.period_start == datetime.datetime(2026, 2, 1, 0, 0)
    assert period.period_end == datetime.datetime(2026, 3, 1, 0, 0)
    assert period.bucket_frequency == "h"
    assert period.bucket_label == "hodina"
    assert period.date_range_label == "01.02.2026 - 28.02.2026"


def test_vodomery_records_to_dataframe_computes_consumption_and_zeroes_invalid_rows():
    df = vodomery_reports.vodomery_records_to_dataframe(
        [
            _measurement("A", datetime.datetime(2026, 2, 1, 0, 0), 100.0),
            _measurement("A", datetime.datetime(2026, 2, 1, 0, 15), 101.0),
            _measurement("B", datetime.datetime(2026, 2, 1, 0, 15), 50.0, delta=0.75),
            _measurement("C", datetime.datetime(2026, 2, 1, 0, 15), 20.0, delta=1.0, platne=False),
            _measurement("D", datetime.datetime(2026, 2, 1, 0, 15), 30.0, delta=1.2, reset_detected=True),
        ]
    )

    assert df[["identifikace", "spotreba_m3", "prutok_m3h"]].to_dict(orient="records") == [
        {"identifikace": "A", "spotreba_m3": 0.0, "prutok_m3h": 0.0},
        {"identifikace": "A", "spotreba_m3": 1.0, "prutok_m3h": 4.0},
        {"identifikace": "B", "spotreba_m3": 0.0, "prutok_m3h": 0.0},
        {"identifikace": "C", "spotreba_m3": 0.0, "prutok_m3h": 0.0},
        {"identifikace": "D", "spotreba_m3": 0.0, "prutok_m3h": 0.0},
    ]


def test_build_consumption_curve_day_aggregates_water_measurements():
    measurements = [
        _measurement("A", datetime.datetime(2026, 2, 1, 0, 0), 100.0),
        _measurement("A", datetime.datetime(2026, 2, 1, 0, 15), 101.0, delta=1.0),
        _measurement("B", datetime.datetime(2026, 2, 1, 0, 0), 50.0),
        _measurement("B", datetime.datetime(2026, 2, 1, 0, 15), 50.5, delta=0.5),
        _measurement("A", datetime.datetime(2026, 2, 1, 0, 30), 101.5, delta=0.5),
    ]
    df = vodomery_reports.vodomery_records_to_dataframe(measurements)
    period = vodomery_reports.resolve_report_period("day", datetime.date(2026, 2, 1))

    period_df = vodomery_reports.filter_measurements_for_period(df, period)
    curve = vodomery_reports.build_consumption_curve(period_df, period)
    summary = vodomery_reports.summarize_report(period_df, curve)

    assert curve[["spotreba_m3", "prutok_m3h", "pocet_mereni"]].to_dict(orient="records") == [
        {"spotreba_m3": 0.0, "prutok_m3h": 0.0, "pocet_mereni": 2},
        {"spotreba_m3": 1.5, "prutok_m3h": 6.0, "pocet_mereni": 2},
        {"spotreba_m3": 0.5, "prutok_m3h": 2.0, "pocet_mereni": 1},
    ]
    assert summary["total_consumption_m3"] == 2.0
    assert summary["device_count"] == 2
    assert summary["max_flow_m3h"] == 6.0
    assert summary["max_flow_at"] == datetime.datetime(2026, 2, 1, 0, 15)


def test_build_consumption_curve_month_uses_hourly_peak_flow_and_hourly_consumption():
    measurements = [
        _measurement("A", datetime.datetime(2026, 2, 1, 0, 0), 100.0),
        _measurement("A", datetime.datetime(2026, 2, 1, 0, 15), 101.0, delta=1.0),
        _measurement("A", datetime.datetime(2026, 2, 1, 0, 30), 103.0, delta=2.0),
        _measurement("A", datetime.datetime(2026, 2, 1, 1, 15), 103.5, delta=0.5),
    ]
    df = vodomery_reports.vodomery_records_to_dataframe(measurements)
    period = vodomery_reports.resolve_report_period("month", datetime.date(2026, 2, 10))

    period_df = vodomery_reports.filter_measurements_for_period(df, period)
    curve = vodomery_reports.build_consumption_curve(period_df, period)
    interval_curve = vodomery_reports.build_interval_consumption_curve(period_df)
    summary = vodomery_reports.summarize_report(period_df, curve, peak_curve_df=interval_curve)

    assert curve[["date", "peak_at", "spotreba_m3", "prutok_m3h", "pocet_mereni"]].to_dict(orient="records") == [
        {
            "date": datetime.datetime(2026, 2, 1, 0, 0),
            "peak_at": datetime.datetime(2026, 2, 1, 0, 30),
            "spotreba_m3": 3.0,
            "prutok_m3h": 8.0,
            "pocet_mereni": 3,
        },
        {
            "date": datetime.datetime(2026, 2, 1, 1, 0),
            "peak_at": datetime.datetime(2026, 2, 1, 1, 15),
            "spotreba_m3": 0.5,
            "prutok_m3h": 2.0,
            "pocet_mereni": 1,
        },
    ]
    assert summary["max_flow_m3h"] == 8.0
    assert summary["max_flow_at"] == datetime.datetime(2026, 2, 1, 0, 30)


def test_build_vodomery_report_html_contains_expected_sections(monkeypatch):
    measurements = [
        _measurement("A", datetime.datetime(2026, 2, 1, 0, 0), 100.0),
        _measurement("A", datetime.datetime(2026, 2, 1, 0, 15), 101.0, delta=1.0),
        _measurement("B", datetime.datetime(2026, 2, 1, 0, 0), 50.0),
        _measurement("B", datetime.datetime(2026, 2, 1, 0, 15), 50.5, delta=0.5),
    ]
    df = vodomery_reports.vodomery_records_to_dataframe(measurements)
    period = vodomery_reports.resolve_report_period("day", datetime.date(2026, 2, 1))
    period_df = vodomery_reports.filter_measurements_for_period(df, period)
    curve_df = vodomery_reports.build_consumption_curve(period_df, period)
    device_summary_df = vodomery_reports.build_device_summary(period_df)
    report = vodomery_reports.build_vodomery_pdf_report(
        period=period,
        period_label="Denní report | 01.02.2026 | krok 15 min",
        period_df=period_df,
        curve_df=curve_df,
        device_summary_df=device_summary_df,
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        selected_identifications=("A", "B"),
        available_identification_count=4,
    )
    monkeypatch.setattr(vodomery_reports, "_load_image_data_uri", lambda path: "data:image/png;base64,TEST")

    html = vodomery_reports.build_vodomery_report_html(report)

    assert "Denní report spotřeby vodoměrů" in html
    assert "Křivka průtoku a spotřeby" in html
    assert "Souhrn měřidel" in html
    assert "monitoring.Mereni_vodomery_vse" in html
    assert "Odběrná místa:</strong> 2 / 4 odběrných míst: A, B" in html
    assert "1.500 m³" in html
    assert "6.000 m³/h" in html
    assert "<svg" in html
    assert "data:image/png;base64,TEST" in html


def test_render_vodomery_report_pdf_uses_playwright(monkeypatch):
    report = vodomery_reports.VodomeryPdfReport(
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        period=vodomery_reports.VodomeryReportPeriod(
            kind="day",
            label="Denní",
            period_start=datetime.datetime(2026, 2, 1, 0, 0),
            period_end=datetime.datetime(2026, 2, 2, 0, 0),
            bucket_frequency="15min",
            bucket_label="15 min",
        ),
        period_label="Denní report | 01.02.2026 | krok 15 min",
        total_consumption_m3=1.5,
        measurement_count=2,
        device_count=2,
        max_flow_m3h=6.0,
        max_flow_at=datetime.datetime(2026, 2, 1, 0, 15),
        curve_rows=(),
        device_rows=(),
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

    monkeypatch.setattr(vodomery_reports, "_load_playwright_api", lambda: FakeSyncPlaywright)
    monkeypatch.setattr(vodomery_reports, "build_vodomery_report_html", lambda current_report: "<html>report</html>")

    pdf_bytes = vodomery_reports.render_vodomery_report_pdf(report)

    assert pdf_bytes == b"%PDF-1.4"
    assert calls["entered"] is True
    assert calls["headless"] is True
    assert calls["wait_until"] == "load"
    assert calls["media"] == "screen"
    assert calls["pdf_kwargs"]["format"] == "A4"
    assert calls["closed"] is True
    assert calls["exited"] is True
