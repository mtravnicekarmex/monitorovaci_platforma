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


def test_map_layers_admin_supports_named_conditional_style_rules():
    source = MAP_LAYERS_ADMIN_PATH.read_text(encoding="utf-8")

    assert '"Název pravidla"' in source
    assert "_conditional_rule_{rule_index}_name" in source
    assert "rule_name = str(st.session_state.get" in source
    assert 'rule["name"] = rule_name' in source


def test_map_layers_admin_supports_property_display_labels_json():
    source = MAP_LAYERS_ADMIN_PATH.read_text(encoding="utf-8")

    assert '"Popisky vlastnosti JSON"' in source
    assert "property_labels = _json_to_dict" in source
    assert 'st.session_state.get(f"{prefix}_property_labels", "{}")' in source
    assert '"property_labels": property_labels' in source
    assert 'key=f"{prefix}_property_labels"' in source


def test_map_layers_admin_supports_popup_document_links_json():
    source = MAP_LAYERS_ADMIN_PATH.read_text(encoding="utf-8")

    assert '"Dokumenty v popupu JSON"' in source
    assert "document_columns = _json_to_dict" in source
    assert 'st.session_state.get(f"{prefix}_document_columns", "{}")' in source
    assert '"document_columns": document_columns' in source
    assert 'key=f"{prefix}_document_columns"' in source
    assert '"dokumenty": "ANO" if layer.get("document_columns") else "NE"' in source
    assert "PDF se dohleda server-side pres autorizovany endpoint" in source


def test_map_layers_admin_supports_map_context_selection():
    source = MAP_LAYERS_ADMIN_PATH.read_text(encoding="utf-8")

    assert 'MAP_CONTEXT_OPTIONS = ("evidence", "revize", "pronajem", "shared")' in source
    assert '"pronajem": "Pronajem"' in source
    assert '"Mapa"' in source
    assert 'key=f"{prefix}_map_context"' in source
    assert '"map_context": str(st.session_state.get' in source
    assert '"kontext": MAP_CONTEXT_LABELS.get' in source


def test_map_layers_admin_supports_label_default_visibility_checkbox_with_help():
    source = MAP_LAYERS_ADMIN_PATH.read_text(encoding="utf-8")

    assert '"Popisek defaultne"' in source
    assert 'key=f"{prefix}_map_labels_default_visible"' in source
    assert '"map_labels_default_visible": bool(st.session_state.get' in source
    assert '"popisek_defaultne": "ANO" if layer.get("map_labels_default_visible", True) else "NE"' in source
    assert '"Prebirat filtr z Mistnosti"' in source
    assert 'key=f"{prefix}_sync_mistnosti_filters"' in source
    assert '"sync_mistnosti_filters": bool(st.session_state.get' in source
    assert '"prebira_mistnosti": "ANO" if layer.get("sync_mistnosti_filters", False) else "NE"' in source
    assert 'help="Vrstva je dostupna pro pouziti v dashboardu.' in source
    assert 'help="Vrstva se zobrazi v mapovem katalogu' in source
    assert 'help="Vrstva bude po otevreni mapy rovnou zapnuta.' in source
    assert 'help="Popisky nastavene ve Sloupce zobrazene v mape budou po otevreni mapy zapnute.' in source
    assert 'help="V mape Evidence se na tuto vrstvu propise vyber podporovanych filtru z vrstvy Mistnosti' in source
    assert 'help="U device vrstvy se nactou jen zarizeni prirazena prihlasenemu uzivateli.' in source
    assert 'help="Pri zapnuti se v popupu nabidne fotka zarizeni' in source


def test_map_layers_admin_orders_source_alias_usage_and_display_label_fields():
    source = MAP_LAYERS_ADMIN_PATH.read_text(encoding="utf-8")

    assert source.index('"Property sloupce"') < source.index('"Filter sloupce"')
    assert source.index('"Filter sloupce"') < source.index('"Aliasy vlastnosti JSON"')
    assert source.index('"Aliasy vlastnosti JSON"') < source.index('"Sloupce zobrazene v mape"')
    assert source.index('"Sloupce zobrazene v mape"') < source.index('"Popup sloupce"')
    assert source.index('"Popup sloupce"') < source.index('"Dokumenty v popupu JSON"')
    assert source.index('"Dokumenty v popupu JSON"') < source.index('"Popisky vlastnosti JSON"')
