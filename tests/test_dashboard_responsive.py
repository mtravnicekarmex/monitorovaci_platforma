from moduly.apps.dashboard.responsive import MOBILE_BREAKPOINT_PX, RESPONSIVE_PAGE_STYLE


def test_responsive_page_style_stacks_columns_only_below_mobile_breakpoint():
    assert MOBILE_BREAKPOINT_PX == 720
    assert "@media (max-width: 720px)" in RESPONSIVE_PAGE_STYLE
    assert '[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]' in RESPONSIVE_PAGE_STYLE
    assert "flex: 1 1 100% !important" in RESPONSIVE_PAGE_STYLE


def test_responsive_page_style_keeps_metric_grids_two_columns_wide():
    assert 'class*="st-key-mobile_metric_grid_' in RESPONSIVE_PAGE_STYLE
    assert "flex: 1 1 calc(50% - 0.375rem) !important" in RESPONSIVE_PAGE_STYLE
