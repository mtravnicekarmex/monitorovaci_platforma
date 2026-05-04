import datetime
import sys
from pathlib import Path

import pandas as pd
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


def test_resolve_report_period_builds_month_window_with_hour_bucket():
    period = elektromery_reports.resolve_report_period("month", datetime.date(2026, 2, 18))

    assert period.label == "Měsíční"
    assert period.period_start == datetime.datetime(2026, 2, 1, 0, 0)
    assert period.period_end == datetime.datetime(2026, 3, 1, 0, 0)
    assert period.bucket_frequency == "h"
    assert period.bucket_label == "hodina"
    assert period.date_range_label == "01.02.2026 - 28.02.2026"


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


def test_build_consumption_curve_month_uses_hourly_peak_power_and_hourly_consumption():
    measurements = [
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 0), 1.0),
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 15), 2.0),
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 30), 0.5),
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 45), 4.0),
        _measurement("TS1", datetime.datetime(2026, 2, 1, 1, 0), 0.25),
        _measurement("TS1", datetime.datetime(2026, 2, 1, 1, 15), 0.25),
    ]
    df = elektromery_reports.ote_records_to_dataframe(measurements)
    period = elektromery_reports.resolve_report_period("month", datetime.date(2026, 2, 10))

    period_df = elektromery_reports.filter_measurements_for_period(df, period)
    curve = elektromery_reports.build_consumption_curve(period_df, period)
    interval_curve = elektromery_reports.build_interval_consumption_curve(period_df)
    summary = elektromery_reports.summarize_report(period_df, curve, peak_curve_df=interval_curve)
    exceedance = elektromery_reports.build_threshold_exceedance(interval_curve, 10.0)

    assert curve[["date", "peak_at", "spotreba_kwh", "odber_kw", "pocet_mereni"]].to_dict(orient="records") == [
        {
            "date": datetime.datetime(2026, 2, 1, 0, 0),
            "peak_at": datetime.datetime(2026, 2, 1, 0, 45),
            "spotreba_kwh": 7.5,
            "odber_kw": 16.0,
            "pocet_mereni": 4,
        },
        {
            "date": datetime.datetime(2026, 2, 1, 1, 0),
            "peak_at": datetime.datetime(2026, 2, 1, 1, 0),
            "spotreba_kwh": 0.5,
            "odber_kw": 1.0,
            "pocet_mereni": 2,
        },
    ]
    assert summary["max_power_kw"] == 16.0
    assert summary["max_power_at"] == datetime.datetime(2026, 2, 1, 0, 45)
    assert exceedance[["date", "odber_kw", "prekroceni_kw"]].to_dict(orient="records") == [
        {
            "date": datetime.datetime(2026, 2, 1, 0, 45),
            "odber_kw": 16.0,
            "prekroceni_kw": 6.0,
        },
    ]


def test_prepare_charge_session_overlays_clips_period_and_assigns_lanes():
    charge_sessions_df = pd.DataFrame(
        [
            {
                "id_relace": "rel-001",
                "started_at": datetime.datetime(2026, 2, 1, 0, 10),
                "ended_at": datetime.datetime(2026, 2, 1, 0, 40),
                "lokace": "Budova E",
                "kwh": 7.5,
                "rychlost_nabijeni": 15.0,
            },
            {
                "id_relace": "rel-002",
                "started_at": datetime.datetime(2026, 2, 1, 0, 20),
                "ended_at": datetime.datetime(2026, 2, 1, 0, 55),
                "lokace": "Budova E",
                "kwh": 8.25,
                "rychlost_nabijeni": 14.143,
            },
            {
                "id_relace": "rel-003",
                "started_at": datetime.datetime(2026, 1, 31, 23, 50),
                "ended_at": datetime.datetime(2026, 2, 1, 0, 5),
                "lokace": "Budova F",
                "kwh": 1.0,
                "rychlost_nabijeni": 4.0,
            },
        ]
    )

    overlay_df = elektromery_reports.prepare_charge_session_overlays(
        charge_sessions_df,
        period_start=datetime.datetime(2026, 2, 1, 0, 0),
        period_end=datetime.datetime(2026, 2, 1, 1, 0),
    )

    assert overlay_df[["id_relace", "overlay_start", "overlay_end", "lane"]].to_dict(orient="records") == [
        {
            "id_relace": "rel-003",
            "overlay_start": datetime.datetime(2026, 2, 1, 0, 0),
            "overlay_end": datetime.datetime(2026, 2, 1, 0, 5),
            "lane": 0,
        },
        {
            "id_relace": "rel-001",
            "overlay_start": datetime.datetime(2026, 2, 1, 0, 10),
            "overlay_end": datetime.datetime(2026, 2, 1, 0, 40),
            "lane": 0,
        },
        {
            "id_relace": "rel-002",
            "overlay_start": datetime.datetime(2026, 2, 1, 0, 20),
            "overlay_end": datetime.datetime(2026, 2, 1, 0, 55),
            "lane": 1,
        },
    ]
    assert overlay_df["annotation_label"].tolist() == [
        "Trvání 15 min | Odebráno 1.000 kWh | Rychlost 4.000 kW",
        "Trvání 30 min | Odebráno 7.500 kWh | Rychlost 15.000 kW",
        "Trvání 35 min | Odebráno 8.250 kWh | Rychlost 14.143 kW",
    ]
    assert overlay_df["duration_line"].tolist() == [
        "Trvání: 15 min",
        "Trvání: 30 min",
        "Trvání: 35 min",
    ]
    assert overlay_df["kwh_line"].tolist() == [
        "Odebráno: 1.000 kWh",
        "Odebráno: 7.500 kWh",
        "Odebráno: 8.250 kWh",
    ]
    assert overlay_df["speed_line"].tolist() == [
        "Rychlost: 4.000 kW",
        "Rychlost: 15.000 kW",
        "Rychlost: 14.143 kW",
    ]


def test_build_charge_session_stripe_dataframe_keeps_at_least_one_stripe_per_session():
    overlay_df = pd.DataFrame(
        [
            {
                "id_relace": "rel-001",
                "overlay_start": datetime.datetime(2026, 2, 1, 0, 10),
                "overlay_end": datetime.datetime(2026, 2, 1, 0, 12),
            },
            {
                "id_relace": "rel-002",
                "overlay_start": datetime.datetime(2026, 2, 1, 0, 20),
                "overlay_end": datetime.datetime(2026, 2, 1, 0, 50),
            },
        ]
    )
    curve_df = pd.DataFrame(
        [
            {"date": datetime.datetime(2026, 2, 1, 0, 0), "odber_kw": 10.0},
            {"date": datetime.datetime(2026, 2, 1, 0, 30), "odber_kw": 20.0},
            {"date": datetime.datetime(2026, 2, 1, 1, 0), "odber_kw": 30.0},
        ]
    )

    stripe_df = elektromery_reports.build_charge_session_stripe_dataframe(overlay_df, curve_df=curve_df)

    first_row = stripe_df.iloc[0].to_dict()
    assert first_row["id_relace"] == "rel-001"
    assert first_row["stripe_at"] == datetime.datetime(2026, 2, 1, 0, 10)
    assert first_row["stripe_odber_kw"] == pytest.approx(13.333333333333332)
    assert first_row["zero_kw"] == 0.0
    rel_002_df = stripe_df[stripe_df["id_relace"] == "rel-002"].reset_index(drop=True)
    assert rel_002_df["stripe_at"].tolist() == [
        datetime.datetime(2026, 2, 1, 0, 20),
        datetime.datetime(2026, 2, 1, 0, 35),
    ]
    assert rel_002_df["stripe_odber_kw"].tolist() == pytest.approx([16.666666666666664, 21.666666666666668])


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


def test_describe_selected_identifications_can_force_explicit_full_selection_list():
    description = elektromery_reports.describe_selected_identifications(
        ("TS1", "TS2"),
        total_available_count=2,
        preview_limit=None,
        collapse_full_selection=False,
    )

    assert description == "2 / 2 odběrných míst: TS1, TS2"


def test_build_curve_layer_assigns_label_color_and_peak_timestamp():
    curve_df = pd.DataFrame(
        [
            {
                "date": datetime.datetime(2026, 2, 1, 0, 0),
                "peak_at": datetime.datetime(2026, 2, 1, 0, 15),
                "spotreba_kwh": 1.25,
                "odber_kw": 5.0,
                "pocet_mereni": 2,
            }
        ]
    )

    layer = elektromery_reports.build_curve_layer(
        index=1,
        curve_df=curve_df,
        selected_identifications=("TS3",),
    )

    assert layer.label == "Vrstva 1"
    assert layer.color == "#059669"
    assert layer.fill_color == "#d1fae5"
    assert layer.selected_identifications == ("TS3",)
    assert layer.curve_rows[0].peak_at == datetime.datetime(2026, 2, 1, 0, 15)
    assert elektromery_reports.curve_layer_legend_label(layer) == "TS3"


def test_build_curve_layer_respects_custom_color_and_derives_fill():
    curve_df = pd.DataFrame(
        [
            {
                "date": datetime.datetime(2026, 2, 1, 0, 0),
                "peak_at": datetime.datetime(2026, 2, 1, 0, 0),
                "spotreba_kwh": 1.0,
                "odber_kw": 4.0,
                "pocet_mereni": 1,
            }
        ]
    )

    layer = elektromery_reports.build_curve_layer(
        index=2,
        curve_df=curve_df,
        color="#008000",
    )

    assert layer.color == "#008000"
    assert layer.fill_color == "#d1e8d1"


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


def test_build_ote_report_html_contains_additional_curve_layer_summary():
    measurements = [
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 15), 1.0),
        _measurement("TS2", datetime.datetime(2026, 2, 1, 0, 30), 2.0),
        _measurement("TS3", datetime.datetime(2026, 2, 1, 0, 45), 0.5),
    ]
    df = elektromery_reports.ote_records_to_dataframe(measurements)
    period = elektromery_reports.resolve_report_period("day", datetime.date(2026, 2, 1))
    period_df = elektromery_reports.filter_measurements_for_period(df, period)
    primary_df = period_df[period_df["identifikace"].isin(["TS1", "TS2"])].copy()
    secondary_df = period_df[period_df["identifikace"].isin(["TS3"])].copy()
    curve_df = elektromery_reports.build_consumption_curve(primary_df, period)
    device_summary_df = elektromery_reports.build_device_summary(primary_df)
    report = elektromery_reports.build_ote_pdf_report(
        period=period,
        period_label="Denní report | 01.02.2026 | krok 15 min",
        period_df=primary_df,
        curve_df=curve_df,
        device_summary_df=device_summary_df,
        reserved_power_kw=10.0,
        curve_layers=(
            elektromery_reports.build_curve_layer(
                index=0,
                curve_df=curve_df,
                selected_identifications=("TS1", "TS2"),
            ),
            elektromery_reports.build_curve_layer(
                index=1,
                curve_df=elektromery_reports.build_consumption_curve(secondary_df, period),
                selected_identifications=("TS3",),
            ),
        ),
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        selected_identifications=("TS1", "TS2"),
        available_identification_count=4,
    )

    html = elektromery_reports.build_ote_report_html(report)

    assert "Vrstva 1:</strong> 1 / 4 odběrných míst: TS3" in html
    assert ">TS3</span></span>" in html


def test_build_ote_report_html_lists_all_selected_identifications_for_full_selection():
    measurements = [
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 15), 1.0),
        _measurement("TS2", datetime.datetime(2026, 2, 1, 0, 15), 2.0),
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
        selected_identifications=("TS1", "TS2"),
        available_identification_count=2,
    )

    html = elektromery_reports.build_ote_report_html(report)

    assert "Odběrná místa:</strong> 2 / 2 odběrných míst: TS1, TS2" in html
    assert "Všechna odběrná místa (2)" not in html


def test_build_ote_report_html_contains_charge_overlay_annotations():
    measurements = [
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 0), 1.0),
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 15), 2.0),
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 30), 1.5),
        _measurement("TS1", datetime.datetime(2026, 2, 1, 0, 45), 1.0),
    ]
    df = elektromery_reports.ote_records_to_dataframe(measurements)
    period = elektromery_reports.resolve_report_period("day", datetime.date(2026, 2, 1))
    period_df = elektromery_reports.filter_measurements_for_period(df, period)
    curve_df = elektromery_reports.build_consumption_curve(period_df, period)
    interval_curve_df = elektromery_reports.build_interval_consumption_curve(period_df)
    device_summary_df = elektromery_reports.build_device_summary(period_df)
    charge_overlay_df = elektromery_reports.prepare_charge_session_overlays(
        pd.DataFrame(
            [
                {
                    "id_relace": "rel-001",
                    "started_at": datetime.datetime(2026, 2, 1, 0, 5),
                    "ended_at": datetime.datetime(2026, 2, 1, 0, 35),
                    "lokace": "Budova E",
                    "kwh": 7.5,
                    "rychlost_nabijeni": 15.0,
                }
            ]
        ),
        period_start=period.period_start,
        period_end=period.period_end,
    )
    report = elektromery_reports.build_ote_pdf_report(
        period=period,
        period_label="Denní report | 01.02.2026 | krok 15 min",
        period_df=period_df,
        curve_df=curve_df,
        device_summary_df=device_summary_df,
        reserved_power_kw=10.0,
        peak_curve_df=interval_curve_df,
        exceedance_curve_df=interval_curve_df,
        charge_overlay_df=charge_overlay_df,
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        selected_identifications=("TS1",),
        available_identification_count=1,
    )

    html = elektromery_reports.build_ote_report_html(report)

    assert "Nabíjecí relace" in html
    assert "Trvání: 30 min" in html
    assert "Odebráno: 7.500 kWh" in html
    assert "Rychlost: 15.000 kW" in html


def _svg_report(period: elektromery_reports.OteReportPeriod) -> elektromery_reports.OtePdfReport:
    curve_rows = (
        elektromery_reports.OteCurveRow(
            date=period.period_start + datetime.timedelta(minutes=15),
            spotreba_kwh=1.0,
            odber_kw=4.0,
            pocet_mereni=1,
        ),
        elektromery_reports.OteCurveRow(
            date=period.period_start + (period.period_end - period.period_start) / 2,
            spotreba_kwh=2.0,
            odber_kw=8.0,
            pocet_mereni=1,
        ),
        elektromery_reports.OteCurveRow(
            date=period.period_end - datetime.timedelta(minutes=15),
            spotreba_kwh=1.5,
            odber_kw=6.0,
            pocet_mereni=1,
        ),
    )
    return elektromery_reports.OtePdfReport(
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        period=period,
        period_label=f"{period.label} report",
        reserved_power_kw=10.0,
        total_consumption_kwh=4.5,
        measurement_count=3,
        device_count=1,
        max_power_kw=8.0,
        max_power_at=curve_rows[1].date,
        exceedance_count=0,
        curve_rows=curve_rows,
        device_rows=(),
        exceedance_rows=(),
        charge_overlay_rows=(),
    )


def test_build_curve_svg_day_axis_uses_period_ticks():
    period = elektromery_reports.resolve_report_period("day", datetime.date(2026, 2, 1))

    svg = elektromery_reports._build_curve_svg(_svg_report(period))

    assert ">00:00</text>" in svg
    assert ">01:00</text>" in svg
    assert ">02:00</text>" in svg
    assert ">04:00</text>" in svg
    assert ">08:00</text>" in svg
    assert ">20:00</text>" in svg
    assert ">00:15</text>" not in svg


def test_build_curve_svg_week_axis_uses_daily_ticks():
    period = elektromery_reports.resolve_report_period("week", datetime.date(2026, 2, 18))

    svg = elektromery_reports._build_curve_svg(_svg_report(period))

    assert ">16.02.</text>" in svg
    assert ">19.02.</text>" in svg
    assert ">22.02.</text>" in svg
    assert ">16.02. 00:00</text>" not in svg


def test_build_curve_svg_month_axis_uses_regular_date_ticks():
    period = elektromery_reports.resolve_report_period("month", datetime.date(2026, 2, 18))

    svg = elektromery_reports._build_curve_svg(_svg_report(period))

    assert ">01.02.</text>" in svg
    assert ">02.02.</text>" in svg
    assert ">03.02.</text>" in svg
    assert ">16.02.</text>" in svg
    assert ">26.02.</text>" in svg
    assert ">01.02. 00:00</text>" not in svg


def test_build_curve_svg_adds_vertical_dashed_gridline_for_each_x_tick():
    period = elektromery_reports.resolve_report_period("week", datetime.date(2026, 2, 18))

    svg = elektromery_reports._build_curve_svg(_svg_report(period))

    assert svg.count("stroke='#d1d5db' stroke-width='1' stroke-dasharray='4 4'") == len(
        elektromery_reports.build_axis_tick_times(period)
    )


def test_build_curve_svg_renders_additional_curve_layer_paths_and_legend():
    period = elektromery_reports.resolve_report_period("day", datetime.date(2026, 2, 1))
    primary_layer = elektromery_reports.build_curve_layer(
        index=0,
        curve_df=pd.DataFrame(
            [
                {
                    "date": period.period_start + datetime.timedelta(hours=1),
                    "peak_at": period.period_start + datetime.timedelta(hours=1),
                    "spotreba_kwh": 1.0,
                    "odber_kw": 4.0,
                    "pocet_mereni": 1,
                },
                {
                    "date": period.period_start + datetime.timedelta(hours=2),
                    "peak_at": period.period_start + datetime.timedelta(hours=2),
                    "spotreba_kwh": 2.0,
                    "odber_kw": 8.0,
                    "pocet_mereni": 1,
                },
            ]
        ),
        selected_identifications=("TS1",),
    )
    secondary_layer = elektromery_reports.build_curve_layer(
        index=1,
        curve_df=pd.DataFrame(
            [
                {
                    "date": period.period_start + datetime.timedelta(hours=1),
                    "peak_at": period.period_start + datetime.timedelta(hours=1),
                    "spotreba_kwh": 0.5,
                    "odber_kw": 2.0,
                    "pocet_mereni": 1,
                },
                {
                    "date": period.period_start + datetime.timedelta(hours=2),
                    "peak_at": period.period_start + datetime.timedelta(hours=2),
                    "spotreba_kwh": 1.0,
                    "odber_kw": 4.0,
                    "pocet_mereni": 1,
                },
            ]
        ),
        selected_identifications=("TS2",),
    )
    report = elektromery_reports.OtePdfReport(
        generated_at=datetime.datetime(2026, 2, 2, 6, 0, 0),
        period=period,
        period_label="Denní report",
        reserved_power_kw=10.0,
        total_consumption_kwh=3.0,
        measurement_count=2,
        device_count=1,
        max_power_kw=8.0,
        max_power_at=period.period_start + datetime.timedelta(hours=2),
        exceedance_count=0,
        curve_rows=primary_layer.curve_rows,
        device_rows=(),
        exceedance_rows=(),
        curve_layers=(primary_layer, secondary_layer),
        charge_overlay_rows=(),
        selected_identifications=("TS1",),
        available_identification_count=2,
    )

    svg = elektromery_reports._build_curve_svg(report)

    assert "stroke='#dc2626'" in svg
    assert "stroke='#059669'" in svg
    assert "fill='#fee2e2'" in svg
    assert "fill='#d1fae5'" in svg
    assert ">TS1</span></span>" in svg
    assert ">TS2</span></span>" in svg


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
        charge_overlay_rows=(),
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
        charge_overlay_rows=(),
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
