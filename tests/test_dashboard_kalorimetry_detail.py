from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DETAIL_PAGE = (
    PROJECT_ROOT
    / "moduly"
    / "apps"
    / "dashboard"
    / "pages"
    / "12_kalorimetry_detail.py"
)


def test_detail_uses_shared_daily_and_monthly_prediction_series():
    source = DETAIL_PAGE.read_text(encoding="utf-8")
    assert "load_prediction_series" in source
    assert source.count("daily_prediction = load_prediction_series(") == 1
    assert source.count("monthly_prediction = load_prediction_series(") == 1
    assert '"daily"' in source
    assert '"monthly"' in source
    assert "today - datetime.timedelta(days=30)" in source
    assert "pd.DateOffset(months=23)" in source


def test_detail_preserves_unavailable_and_partial_states():
    source = DETAIL_PAGE.read_text(encoding="utf-8")
    assert '"Nedostupné"' in source
    assert '== "insufficient_history"' in source
    assert '== "partial"' in source
    assert "render_prediction_status(daily_prediction)" in source


def test_detail_overlays_prediction_below_actual_history():
    source = DETAIL_PAGE.read_text(encoding="utf-8")
    assert 'PREDICTION_COLOR = "#dedcd9"' in source
    assert "chart = prediction_line + chart" in source
    assert "monthly_chart = prediction_line + monthly_chart" in source
    assert "seven_day_prediction" in source
    assert "daily_prediction_df" in source
    assert "monthly_prediction_df" in source


def test_detail_keeps_device_metadata_reset_and_responsive_layout():
    source = DETAIL_PAGE.read_text(encoding="utf-8")
    assert "render_device_photo(device_detail)" in source
    assert 'st.subheader("Detail odběrného místa")' in source
    assert "build_change_table(history_df)" in source
    assert "st.columns(5, vertical_alignment=" in source
    assert "chart_col, status_col = st.columns([3, 2])" in source
