from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAP_LAYERS_ADMIN_PATH = PROJECT_ROOT / "moduly" / "apps" / "dashboard" / "pages" / "35_mapove_vrstvy.py"


def test_map_layers_admin_supports_compound_conditional_style_rules():
    source = MAP_LAYERS_ADMIN_PATH.read_text(encoding="utf-8")

    assert 'CONDITIONAL_STYLE_LOGIC_MODES = ("simple", "all", "any")' in source
    assert '"Vsechny podminky (AND)"' in source
    assert '"Alespon jedna podminka (OR)"' in source
    assert "MAX_CONDITIONAL_RULE_CONDITIONS = 10" in source
    assert "def render_conditional_condition_editor(" in source
    assert '"Pocet stylovych pravidel"' in source
    assert '"Pocet dilcich podminek"' in source
    assert "mode: conditions" in source
    assert 'for mode in ("all", "any")' in source
    assert "append_condition_properties(item)" in source
