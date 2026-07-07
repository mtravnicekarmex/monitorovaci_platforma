from pathlib import Path

from moduly.apps.dashboard.responsive import (
    MOBILE_BREAKPOINT_PX,
    RESPONSIVE_PAGE_STYLE,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGIN_PAGE_PATH = PROJECT_ROOT / "moduly" / "apps" / "dashboard" / "login.py"


def test_responsive_page_style_stacks_columns_only_below_mobile_breakpoint():
    assert MOBILE_BREAKPOINT_PX == 720
    assert "@media (max-width: 720px)" in RESPONSIVE_PAGE_STYLE
    assert '[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]' in RESPONSIVE_PAGE_STYLE
    assert "flex: 1 1 100% !important" in RESPONSIVE_PAGE_STYLE


def test_responsive_page_style_keeps_metric_grids_two_columns_wide():
    assert ':has(' in RESPONSIVE_PAGE_STYLE
    assert '[data-testid="stMetric"]' in RESPONSIVE_PAGE_STYLE
    assert 'class*="st-key-mobile_metric_grid_' in RESPONSIVE_PAGE_STYLE
    assert "flex: 1 1 calc(50% - 0.375rem) !important" in RESPONSIVE_PAGE_STYLE


def test_responsive_page_style_covers_dense_dashboard_controls():
    assert '[data-testid="stDataFrame"]' in RESPONSIVE_PAGE_STYLE
    assert '[data-testid="stVegaLiteChart"]' in RESPONSIVE_PAGE_STYLE
    assert '[data-testid="stTabs"] [role="tablist"]' in RESPONSIVE_PAGE_STYLE
    assert '[data-testid="stDialog"] [role="dialog"]' in RESPONSIVE_PAGE_STYLE
    assert ".stFormSubmitButton > button" in RESPONSIVE_PAGE_STYLE
    assert "font-size: 16px !important" in RESPONSIVE_PAGE_STYLE


def test_dashboard_entrypoint_applies_responsive_styles_to_every_page():
    source = LOGIN_PAGE_PATH.read_text(encoding="utf-8")

    assert "from moduly.apps.dashboard import responsive as dashboard_responsive" in source
    assert "def _reload_dashboard_module(module):" in source
    assert "dashboard_responsive = _reload_dashboard_module(dashboard_responsive)" in source
    assert source.index("dashboard_responsive.render_responsive_page_styles()") < source.index("current_page.run()")
