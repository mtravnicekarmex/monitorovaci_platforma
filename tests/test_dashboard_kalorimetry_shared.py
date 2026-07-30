import datetime
from pathlib import Path

import pandas as pd

from moduly.apps.dashboard import kalorimetry_shared
from moduly.apps.dashboard.api_client import DashboardApiError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_prediction_series_preserves_unavailable_empty_shape(monkeypatch):
    monkeypatch.setattr(
        kalorimetry_shared,
        "require_dashboard_api_token",
        lambda: "token",
    )
    monkeypatch.setattr(
        kalorimetry_shared,
        "get_kalorimetry_prediction_series",
        lambda *_args, **_kwargs: {
            "prediction_available": False,
            "availability_status": "unavailable",
            "availability_reason": "insufficient_history",
            "rows": [],
        },
    )
    result = kalorimetry_shared.load_prediction_series.__wrapped__(
        "KAL-01",
        datetime.date(2026, 7, 27),
        datetime.date(2026, 7, 28),
        "daily",
        ("KAL-01",),
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


def test_load_prediction_series_sorts_clamps_and_rebuilds_cumulative(monkeypatch):
    monkeypatch.setattr(
        kalorimetry_shared,
        "require_dashboard_api_token",
        lambda: "token",
    )
    monkeypatch.setattr(
        kalorimetry_shared,
        "get_kalorimetry_prediction_series",
        lambda *_args, **_kwargs: {
            "prediction_available": True,
            "availability_status": "available",
            "availability_reason": None,
            "rows": [
                {
                    "date": "2026-07-28T00:00:00",
                    "ocekavana_spotreba": 2.0,
                    "ocekavana_kumulovana_spotreba": 999.0,
                },
                {
                    "date": "2026-07-27T00:00:00",
                    "ocekavana_spotreba": -1.0,
                    "ocekavana_kumulovana_spotreba": 998.0,
                },
            ],
        },
    )
    result = kalorimetry_shared.load_prediction_series.__wrapped__(
        "KAL-01",
        datetime.date(2026, 7, 27),
        datetime.date(2026, 7, 28),
        "daily",
        ("KAL-01",),
        False,
    )
    rows = result["rows"]
    assert rows["ocekavana_spotreba"].tolist() == [0.0, 2.0]
    assert rows["ocekavana_kumulovana_spotreba"].tolist() == [0.0, 2.0]


def test_load_prediction_series_treats_missing_api_route_as_unavailable(monkeypatch):
    monkeypatch.setattr(
        kalorimetry_shared,
        "require_dashboard_api_token",
        lambda: "token",
    )

    def missing_route(*_args, **_kwargs):
        raise DashboardApiError("Not Found", status_code=404)

    monkeypatch.setattr(
        kalorimetry_shared,
        "get_kalorimetry_prediction_series",
        missing_route,
    )

    result = kalorimetry_shared.load_prediction_series.__wrapped__(
        "KAL-01",
        datetime.date(2026, 7, 27),
        datetime.date(2026, 7, 28),
        "daily",
        ("KAL-01",),
        False,
    )

    assert result["prediction_available"] is False
    assert result["availability_reason"] == "prediction_endpoint_unavailable"
    assert result["rows"].empty


def test_prediction_metric_summary_returns_deviation():
    measurements = pd.DataFrame({"kumulovana_spotreba": [3.0, 10.0]})
    prediction = pd.DataFrame({"ocekavana_spotreba": [4.0, 4.0]})
    result = kalorimetry_shared.build_prediction_metric_summary(
        measurements,
        prediction,
    )
    assert result == {
        "actual_total": 10.0,
        "expected_total": 8.0,
        "deviation": 2.0,
        "deviation_pct": 25.0,
    }


def test_overview_uses_prediction_overlay_and_four_metric_contract():
    source = (
        PROJECT_ROOT
        / "moduly"
        / "apps"
        / "dashboard"
        / "pages"
        / "11_kalorimetry.py"
    ).read_text(encoding="utf-8")
    assert 'PREDICTION_COLOR = "#dedcd9"' in source
    assert "color=PREDICTION_COLOR" in source
    assert 'value_column="ocekavana_kumulovana_spotreba"' in source
    assert "columns = st.columns(4)" in source
    assert source.count(
        "build_prediction_chart(prediction_df) + actual_chart"
    ) == 2
    assert "def render_graph_legend(show_prediction: bool)" in source
    assert "render_graph_legend(not prediction_df.empty)" in source
    assert '"Spotřeba energie</span>"' in source
    assert '"Predikce</span>"' in source
