import datetime
from pathlib import Path

import pandas as pd

from moduly.apps.dashboard import plynomery_shared


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_prediction_series_preserves_unavailable_empty_shape(monkeypatch):
    monkeypatch.setattr(
        plynomery_shared,
        "require_dashboard_api_token",
        lambda: "token",
    )
    monkeypatch.setattr(
        plynomery_shared,
        "get_plynomery_prediction_series",
        lambda *_args, **_kwargs: {
            "prediction_available": False,
            "availability_status": "unavailable",
            "availability_reason": "insufficient_history",
            "rows": [],
        },
    )

    result = plynomery_shared.load_prediction_series.__wrapped__(
        "P_A1",
        datetime.date(2026, 7, 1),
        datetime.date(2026, 7, 31),
        "daily",
        ("P_A1",),
        False,
    )

    assert result["availability_reason"] == "insufficient_history"
    assert result["rows"].empty
    assert result["rows"].columns.tolist() == [
        "date",
        "ocekavana_spotreba",
        "interval_count",
        "candidate_interval_count",
        "prediction_complete",
        "model_versions",
        "profile_kinds",
        "ocekavana_kumulovana_spotreba",
    ]


def test_load_prediction_series_parses_and_rebuilds_cumulative_values(monkeypatch):
    monkeypatch.setattr(
        plynomery_shared,
        "require_dashboard_api_token",
        lambda: "token",
    )
    monkeypatch.setattr(
        plynomery_shared,
        "get_plynomery_prediction_series",
        lambda *_args, **_kwargs: {
            "prediction_available": True,
            "availability_status": "available",
            "availability_reason": None,
            "rows": [
                {
                    "date": "2026-08-01T00:00:00",
                    "ocekavana_spotreba": "-2.5",
                    "interval_count": 10,
                    "candidate_interval_count": 10,
                    "prediction_complete": True,
                    "model_versions": [2],
                    "profile_kinds": ["weather_adjusted"],
                    "ocekavana_kumulovana_spotreba": "2.5",
                },
                {
                    "date": "2026-07-31T00:00:00",
                    "ocekavana_spotreba": "12.5",
                    "interval_count": 10,
                    "candidate_interval_count": 10,
                    "prediction_complete": True,
                    "model_versions": [2],
                    "profile_kinds": ["weather_adjusted"],
                    "ocekavana_kumulovana_spotreba": "999",
                },
            ],
        },
    )

    result = plynomery_shared.load_prediction_series.__wrapped__(
        "P_A1",
        datetime.date(2026, 7, 1),
        datetime.date(2026, 7, 31),
        "monthly",
        ("P_A1",),
        False,
    )

    rows = result["rows"]
    assert rows["date"].tolist() == [
        pd.Timestamp("2026-07-31"),
        pd.Timestamp("2026-08-01"),
    ]
    assert rows["ocekavana_spotreba"].tolist() == [12.5, 0.0]
    assert rows["ocekavana_kumulovana_spotreba"].tolist() == [12.5, 12.5]
    assert rows["ocekavana_kumulovana_spotreba"].is_monotonic_increasing


def test_overview_prediction_curve_uses_neutral_gray():
    source = (
        PROJECT_ROOT
        / "moduly"
        / "apps"
        / "dashboard"
        / "pages"
        / "9_plynomery.py"
    ).read_text(encoding="utf-8")

    assert 'PREDICTION_COLOR = "#dedcd9"' in source
    assert "color=PREDICTION_COLOR" in source
    assert "strokeDash=[6, 4]" not in source
    assert 'color="#dc2626"' not in source
    assert 'value_column="ocekavana_kumulovana_spotreba"' in source
    assert 'metric_cols = st.columns(4)' in source
    assert source.count("build_prediction_chart(prediction_df) + actual_chart") == 2
    assert (
        'tooltip_title="Očekávaná kumulovaná spotřeba",\n'
        "            )\n"
        "            + actual_chart"
    ) in source
    assert "def render_graph_legend(show_prediction: bool)" in source
    assert "render_graph_legend(not prediction_df.empty)" in source
    assert '"Spotřeba"' in source
    assert '"Predikce"' in source


def test_prediction_metric_summary_matches_vodomery_four_metric_contract():
    summary = plynomery_shared.build_prediction_metric_summary(
        pd.DataFrame({"kumulovana_spotreba": [1.0, 12.0]}),
        pd.DataFrame({"ocekavana_spotreba": [5.0, 5.0]}),
    )

    assert summary == {
        "actual_total": 12.0,
        "expected_total": 10.0,
        "deviation": 2.0,
        "deviation_pct": 20.0,
    }


def test_prediction_metric_summary_preserves_unavailable_state():
    summary = plynomery_shared.build_prediction_metric_summary(
        pd.DataFrame({"kumulovana_spotreba": [7.5]}),
        pd.DataFrame(columns=["ocekavana_spotreba"]),
    )

    assert summary == {
        "actual_total": 7.5,
        "expected_total": None,
        "deviation": None,
        "deviation_pct": None,
    }
