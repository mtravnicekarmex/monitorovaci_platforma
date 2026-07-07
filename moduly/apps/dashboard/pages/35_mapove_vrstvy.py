from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    create_admin_map_layer,
    delete_admin_map_layer,
    list_admin_map_layers,
    update_admin_map_layer,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access


st.set_page_config(
    page_title="Mapove vrstvy",
    page_icon="🗺️",
    layout="wide",
)


require_page_access("map_layers_admin")


DEFAULT_STYLE = {
    "color": "#0f5e9c",
    "fillColor": "#38bdf8",
    "weight": 2,
    "fillOpacity": 0.2,
    "radius": 6,
}
CONDITIONAL_STYLE_KEY = "conditionalStyle"
CONDITIONAL_STYLE_OPERATORS = ("equals", "not_equals", "is_empty", "is_not_empty")
CONDITIONAL_VALUE_TYPES = ("boolean", "text", "number")
MAX_CONDITIONAL_RULES = 10


@st.cache_data(ttl=60)
def load_layers() -> list[dict[str, object]]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return list_admin_map_layers(access_token)


def _csv_to_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _list_to_csv(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value)


def _json_to_dict(value: str, *, field_name: str) -> dict[str, object]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} neni validni JSON objekt.") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} musi byt JSON objekt.")
    return dict(parsed)


def _dict_to_json(value: object) -> str:
    if not isinstance(value, dict):
        return "{}"
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _safe_color(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.startswith("#") and len(value) in {4, 7}:
        return value
    return fallback


def _style_number(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _conditional_value_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    return "text"


def _state_value(*keys: str, default: object = None) -> object:
    for key in keys:
        if key in st.session_state:
            return st.session_state[key]
    return default


def _parse_conditional_value(prefix: str, operator: str) -> object | None:
    if operator in {"is_empty", "is_not_empty"}:
        return None

    value_type = str(_state_value(f"{prefix}_value_type", f"{prefix}_conditional_value_type", default="boolean"))
    if value_type == "boolean":
        return str(_state_value(f"{prefix}_value_bool", f"{prefix}_conditional_value_bool", default="true")) == "true"
    if value_type == "number":
        raw_value = str(_state_value(f"{prefix}_value", f"{prefix}_conditional_value", default="")).strip()
        if not raw_value:
            raise ValueError("Hodnota podminky je povinna.")
        number_value = float(raw_value)
        return int(number_value) if number_value.is_integer() else number_value
    return str(_state_value(f"{prefix}_value", f"{prefix}_conditional_value", default="")).strip()


def _conditional_rules_from_style(conditional_style: dict[str, object]) -> list[dict[str, object]]:
    rules = conditional_style.get("rules")
    if isinstance(rules, list):
        parsed_rules = [dict(rule) for rule in rules if isinstance(rule, dict)]
        if parsed_rules:
            return parsed_rules[:MAX_CONDITIONAL_RULES]
    if conditional_style.get("property"):
        return [conditional_style]
    return []


def _style_subset_from_state(prefix: str) -> dict[str, object]:
    return {
        "color": st.session_state.get(f"{prefix}_color", DEFAULT_STYLE["color"]),
        "fillColor": st.session_state.get(f"{prefix}_fill", DEFAULT_STYLE["fillColor"]),
        "weight": float(st.session_state.get(f"{prefix}_weight", DEFAULT_STYLE["weight"])),
        "fillOpacity": float(st.session_state.get(f"{prefix}_fill_opacity", DEFAULT_STYLE["fillOpacity"])),
        "radius": float(st.session_state.get(f"{prefix}_radius", DEFAULT_STYLE["radius"])),
    }


def render_compact_style_editor(prefix: str, style: dict[str, object], *, label: str) -> None:
    st.caption(label)
    merged_style = {**DEFAULT_STYLE, **style}
    color_col, fill_col, weight_col, opacity_col, radius_col = st.columns(5)
    color_col.color_picker(
        "Barva linie",
        value=_safe_color(merged_style.get("color"), str(DEFAULT_STYLE["color"])),
        key=f"{prefix}_color",
    )
    fill_col.color_picker(
        "Barva vyplne",
        value=_safe_color(merged_style.get("fillColor"), str(DEFAULT_STYLE["fillColor"])),
        key=f"{prefix}_fill",
    )
    weight_col.number_input(
        "Tloustka",
        min_value=0.0,
        max_value=20.0,
        value=_style_number(merged_style.get("weight"), float(DEFAULT_STYLE["weight"])),
        step=0.5,
        key=f"{prefix}_weight",
    )
    opacity_col.slider(
        "Pruhlednost vyplne",
        min_value=0.0,
        max_value=1.0,
        value=_style_number(merged_style.get("fillOpacity"), float(DEFAULT_STYLE["fillOpacity"])),
        step=0.05,
        key=f"{prefix}_fill_opacity",
    )
    radius_col.number_input(
        "Radius bodu",
        min_value=1.0,
        max_value=30.0,
        value=_style_number(merged_style.get("radius"), float(DEFAULT_STYLE["radius"])),
        step=1.0,
        key=f"{prefix}_radius",
    )


def render_conditional_style_editor(prefix: str, style: dict[str, object]) -> None:
    conditional_style = style.get(CONDITIONAL_STYLE_KEY)
    if not isinstance(conditional_style, dict):
        conditional_style = {}
    rules = _conditional_rules_from_style(conditional_style)
    enabled = bool(rules)

    st.markdown("#### Zobrazovat na zaklade podminek")
    st.checkbox(
        "Zapnout podminene stylovani",
        value=enabled,
        key=f"{prefix}_conditional_enabled",
    )
    if not st.session_state.get(f"{prefix}_conditional_enabled", enabled):
        return

    rule_count = st.number_input(
        "Pocet podminek",
        min_value=1,
        max_value=MAX_CONDITIONAL_RULES,
        value=max(1, len(rules)),
        step=1,
        key=f"{prefix}_conditional_rule_count",
    )
    for rule_index in range(int(rule_count)):
        rule = rules[rule_index] if rule_index < len(rules) else {}
        operator = str(rule.get("operator") or "equals")
        if operator not in CONDITIONAL_STYLE_OPERATORS:
            operator = "equals"
        value = rule.get("value", True)
        value_type = _conditional_value_type(value)
        st.caption(f"Podminka {rule_index + 1}")
        condition_cols = st.columns([2, 1, 1, 2])
        condition_cols[0].text_input(
            "Sloupec podminky",
            value=str(rule.get("property") or ""),
            key=f"{prefix}_conditional_rule_{rule_index}_property",
        )
        operator = condition_cols[1].selectbox(
            "Operator",
            options=list(CONDITIONAL_STYLE_OPERATORS),
            index=CONDITIONAL_STYLE_OPERATORS.index(operator),
            key=f"{prefix}_conditional_rule_{rule_index}_operator",
        )
        value_type = condition_cols[2].selectbox(
            "Typ hodnoty",
            options=list(CONDITIONAL_VALUE_TYPES),
            index=CONDITIONAL_VALUE_TYPES.index(value_type),
            key=f"{prefix}_conditional_rule_{rule_index}_value_type",
            disabled=operator in {"is_empty", "is_not_empty"},
        )
        if value_type == "boolean":
            condition_cols[3].selectbox(
                "Hodnota",
                options=["true", "false"],
                index=0 if bool(value) else 1,
                key=f"{prefix}_conditional_rule_{rule_index}_value_bool",
                disabled=operator in {"is_empty", "is_not_empty"},
            )
        else:
            condition_cols[3].text_input(
                "Hodnota",
                value="" if value is None else str(value),
                key=f"{prefix}_conditional_rule_{rule_index}_value",
                disabled=operator in {"is_empty", "is_not_empty"},
            )

        render_compact_style_editor(
            f"{prefix}_conditional_rule_{rule_index}_style",
            dict(rule.get("style") or rule.get("match") or {}),
            label="Styl pri splneni podminky",
        )

    use_base_fallback = "fallback" not in conditional_style
    st.checkbox(
        "Pri nesplneni pouzit zakladni styl vrstvy",
        value=use_base_fallback,
        key=f"{prefix}_conditional_use_base_fallback",
    )
    if not st.session_state.get(f"{prefix}_conditional_use_base_fallback", use_base_fallback):
        render_compact_style_editor(
            f"{prefix}_conditional_fallback",
            dict(conditional_style.get("fallback") or {}),
            label="Styl pri nesplneni podminky",
        )


def _conditional_rule_payload_from_state(prefix: str, rule_index: int) -> dict[str, object]:
    property_name = str(st.session_state.get(f"{prefix}_conditional_rule_{rule_index}_property", "")).strip()
    if not property_name:
        raise ValueError(f"Sloupec podminky {rule_index + 1} je povinny.")

    operator = str(st.session_state.get(f"{prefix}_conditional_rule_{rule_index}_operator", "equals"))
    if operator not in CONDITIONAL_STYLE_OPERATORS:
        raise ValueError(f"Neplatny operator podminky {rule_index + 1}.")

    rule: dict[str, object] = {
        "property": property_name,
        "operator": operator,
        "style": _style_subset_from_state(f"{prefix}_conditional_rule_{rule_index}_style"),
    }
    value = _parse_conditional_value(f"{prefix}_conditional_rule_{rule_index}", operator)
    if value is not None:
        rule["value"] = value
    return rule


def _conditional_style_payload_from_state(prefix: str) -> dict[str, object] | None:
    if not st.session_state.get(f"{prefix}_conditional_enabled", False):
        return None

    rule_count = int(st.session_state.get(f"{prefix}_conditional_rule_count", 1))
    rule_count = max(1, min(rule_count, MAX_CONDITIONAL_RULES))
    conditional_style: dict[str, object] = {
        "rules": [_conditional_rule_payload_from_state(prefix, index) for index in range(rule_count)]
    }

    if not st.session_state.get(f"{prefix}_conditional_use_base_fallback", True):
        conditional_style["fallback"] = _style_subset_from_state(f"{prefix}_conditional_fallback")

    return conditional_style


def _conditional_style_properties(style: dict[str, object]) -> list[str]:
    conditional_style = style.get(CONDITIONAL_STYLE_KEY)
    if not isinstance(conditional_style, dict):
        return []
    properties: list[str] = []
    for rule in _conditional_rules_from_style(conditional_style):
        property_name = str(rule.get("property") or "").strip()
        if property_name and property_name not in properties:
            properties.append(property_name)
    return properties


def render_style_editor(prefix: str, style: dict[str, object]) -> None:
    merged_style = {**DEFAULT_STYLE, **style}
    color_col, fill_col, weight_col, opacity_col, radius_col = st.columns(5)

    color = color_col.color_picker(
        "Barva linie",
        value=_safe_color(merged_style.get("color"), str(DEFAULT_STYLE["color"])),
        key=f"{prefix}_style_color",
    )
    fill_color = fill_col.color_picker(
        "Barva vyplne",
        value=_safe_color(merged_style.get("fillColor"), str(DEFAULT_STYLE["fillColor"])),
        key=f"{prefix}_style_fill",
    )
    weight = weight_col.number_input(
        "Tloustka",
        min_value=0.0,
        max_value=20.0,
        value=_style_number(merged_style.get("weight"), float(DEFAULT_STYLE["weight"])),
        step=0.5,
        key=f"{prefix}_style_weight",
    )
    fill_opacity = opacity_col.slider(
        "Pruhlednost vyplne",
        min_value=0.0,
        max_value=1.0,
        value=_style_number(merged_style.get("fillOpacity"), float(DEFAULT_STYLE["fillOpacity"])),
        step=0.05,
        key=f"{prefix}_style_fill_opacity",
    )
    radius = radius_col.number_input(
        "Radius bodu",
        min_value=1.0,
        max_value=30.0,
        value=_style_number(merged_style.get("radius"), float(DEFAULT_STYLE["radius"])),
        step=1.0,
        key=f"{prefix}_style_radius",
    )

    advanced_style = {
        key: value
        for key, value in style.items()
        if key not in {"color", "fillColor", "weight", "fillOpacity", "radius", CONDITIONAL_STYLE_KEY}
    }
    st.text_area(
        "Dalsi styl JSON",
        value=_dict_to_json(advanced_style),
        help="Volitelne doplnkove Leaflet styl hodnoty. Musi jit o JSON objekt.",
        key=f"{prefix}_style_extra",
    )
    render_conditional_style_editor(prefix, style)


def _style_payload_from_state(prefix: str) -> dict[str, object]:
    advanced_json = str(st.session_state.get(f"{prefix}_style_extra", "{}"))
    parsed_advanced = _json_to_dict(advanced_json, field_name="Dalsi styl JSON")
    parsed_advanced.pop(CONDITIONAL_STYLE_KEY, None)
    style = {
        **parsed_advanced,
        "color": st.session_state.get(f"{prefix}_style_color", DEFAULT_STYLE["color"]),
        "fillColor": st.session_state.get(f"{prefix}_style_fill", DEFAULT_STYLE["fillColor"]),
        "weight": float(st.session_state.get(f"{prefix}_style_weight", DEFAULT_STYLE["weight"])),
        "fillOpacity": float(st.session_state.get(f"{prefix}_style_fill_opacity", DEFAULT_STYLE["fillOpacity"])),
        "radius": float(st.session_state.get(f"{prefix}_style_radius", DEFAULT_STYLE["radius"])),
    }
    conditional_style = _conditional_style_payload_from_state(prefix)
    if conditional_style is not None:
        style[CONDITIONAL_STYLE_KEY] = conditional_style
    return style


def build_payload(prefix: str, current: dict[str, object] | None = None) -> dict[str, object]:
    current = current or {}
    property_aliases = _json_to_dict(
        st.session_state.get(f"{prefix}_property_aliases", "{}"),
        field_name="Aliasy vlastnosti",
    )
    style = _style_payload_from_state(prefix)

    property_columns = _csv_to_list(str(st.session_state.get(f"{prefix}_property_columns", "")))
    for conditional_property in _conditional_style_properties(style):
        if conditional_property not in property_columns:
            property_columns.append(conditional_property)

    return {
        "layer_id": str(st.session_state.get(f"{prefix}_layer_id", "")).strip(),
        "title": str(st.session_state.get(f"{prefix}_title", "")).strip(),
        "layer_kind": str(st.session_state.get(f"{prefix}_layer_kind", "context")),
        "source_schema": str(st.session_state.get(f"{prefix}_source_schema", "evidence")).strip(),
        "source_table": str(st.session_state.get(f"{prefix}_source_table", "")).strip(),
        "geometry_column": str(st.session_state.get(f"{prefix}_geometry_column", "geom")).strip(),
        "identifier_column": str(st.session_state.get(f"{prefix}_identifier_column", "")).strip(),
        "source_srid": int(st.session_state.get(f"{prefix}_source_srid", 3857)),
        "target_srid": int(st.session_state.get(f"{prefix}_target_srid", 4326)),
        "property_columns": property_columns,
        "property_aliases": property_aliases,
        "filter_columns": _csv_to_list(str(st.session_state.get(f"{prefix}_filter_columns", ""))),
        "popup_columns": _csv_to_list(str(st.session_state.get(f"{prefix}_popup_columns", ""))),
        "style": style,
        "device_section_key": str(st.session_state.get(f"{prefix}_device_section_key", "")).strip() or None,
        "restrict_to_allowed_devices": bool(st.session_state.get(f"{prefix}_restrict_to_allowed_devices", False)),
        "map_enabled": bool(st.session_state.get(f"{prefix}_map_enabled", True)),
        "default_visible": bool(st.session_state.get(f"{prefix}_default_visible", True)),
        "show_photo": bool(st.session_state.get(f"{prefix}_show_photo", False)),
        "is_active": bool(st.session_state.get(f"{prefix}_is_active", True)),
        "draw_order": int(st.session_state.get(f"{prefix}_draw_order", 100)),
    }


def render_layer_fields(prefix: str, current: dict[str, object] | None = None, *, allow_layer_id_edit: bool) -> None:
    current = current or {}
    top_cols = st.columns([1, 2, 1, 1])
    top_cols[0].text_input(
        "Layer ID",
        value=str(current.get("layer_id") or ""),
        disabled=not allow_layer_id_edit,
        key=f"{prefix}_layer_id",
    )
    top_cols[1].text_input("Nazev", value=str(current.get("title") or ""), key=f"{prefix}_title")
    top_cols[2].selectbox(
        "Typ vrstvy",
        options=["context", "device"],
        index=0 if str(current.get("layer_kind") or "context") == "context" else 1,
        key=f"{prefix}_layer_kind",
    )
    top_cols[3].number_input(
        "Poradi",
        min_value=0,
        max_value=10000,
        value=int(current.get("draw_order") or 100),
        step=10,
        key=f"{prefix}_draw_order",
    )

    source_cols = st.columns([1, 1, 1, 1, 1, 1])
    source_cols[0].text_input("Schema", value=str(current.get("source_schema") or "evidence"), key=f"{prefix}_source_schema")
    source_cols[1].text_input("Tabulka", value=str(current.get("source_table") or ""), key=f"{prefix}_source_table")
    source_cols[2].text_input("Geometry sloupec", value=str(current.get("geometry_column") or "geom"), key=f"{prefix}_geometry_column")
    source_cols[3].text_input("Identifikator", value=str(current.get("identifier_column") or ""), key=f"{prefix}_identifier_column")
    source_cols[4].number_input(
        "Source SRID",
        min_value=1,
        max_value=999999,
        value=int(current.get("source_srid") or 3857),
        key=f"{prefix}_source_srid",
    )
    source_cols[5].number_input(
        "Target SRID",
        min_value=1,
        max_value=999999,
        value=int(current.get("target_srid") or 4326),
        key=f"{prefix}_target_srid",
    )

    state_cols = st.columns([1, 1, 1, 1, 1])
    state_cols[0].checkbox("Aktivni", value=bool(current.get("is_active", True)), key=f"{prefix}_is_active")
    state_cols[1].checkbox("Mapove zobrazovani", value=bool(current.get("map_enabled", True)), key=f"{prefix}_map_enabled")
    state_cols[2].checkbox("Viditelna defaultne", value=bool(current.get("default_visible", True)), key=f"{prefix}_default_visible")
    state_cols[3].checkbox(
        "Omezit podle zarizeni",
        value=bool(current.get("restrict_to_allowed_devices", False)),
        key=f"{prefix}_restrict_to_allowed_devices",
    )
    state_cols[4].checkbox(
        "Zobrazit foto",
        value=bool(current.get("show_photo", False)),
        key=f"{prefix}_show_photo",
        help="Pri zapnuti se pro zarizeni nacita cesta ze sloupce foto.",
    )

    st.text_input(
        "Device sekce",
        value=str(current.get("device_section_key") or ""),
        help="Pro device vrstvy napr. vodomery. Kontextove vrstvy nech prazdne.",
        key=f"{prefix}_device_section_key",
    )

    st.text_area(
        "Property sloupce",
        value=_list_to_csv(current.get("property_columns")),
        help="Carkou oddeleny seznam zdrojovych sloupcu, ktere se maji poslat do GeoJSON properties.",
        key=f"{prefix}_property_columns",
    )
    st.text_area(
        "Filter sloupce",
        value=_list_to_csv(current.get("filter_columns")),
        help="Carkou oddeleny seznam zdrojovych sloupcu, ktere budou dostupne pro multiselect filtry.",
        key=f"{prefix}_filter_columns",
    )
    st.text_area(
        "Popup sloupce",
        value=_list_to_csv(current.get("popup_columns")),
        help="Carkou oddeleny seznam properties zobrazovanych v popupu. Muze obsahovat aliasy.",
        key=f"{prefix}_popup_columns",
    )
    st.text_area(
        "Aliasy vlastnosti JSON",
        value=_dict_to_json(current.get("property_aliases")),
        help='Mapovani zdrojovy_sloupec -> property_key, napr. {"místnost": "mistnost"}.',
        key=f"{prefix}_property_aliases",
    )
    st.caption("Styl vrstvy")
    render_style_editor(prefix, dict(current.get("style") or {}))


def render_page() -> None:
    st.title("Mapove vrstvy")
    st.caption(
        "Admin nastaveni mapovych vrstev. Zdrojova data se nemeni; uklada se jen konfigurace "
        "zobrazeni, filtru, opravneni a stylu."
    )

    layers = load_layers()
    if layers:
        overview_df = pd.DataFrame(
            [
                {
                    "layer_id": layer["layer_id"],
                    "nazev": layer["title"],
                    "typ": layer["layer_kind"],
                    "zdroj": f'{layer["source_schema"]}.{layer["source_table"]}',
                    "mapa": "ANO" if layer["map_enabled"] else "NE",
                    "aktivni": "ANO" if layer["is_active"] else "NE",
                    "device_filter": "ANO" if layer["restrict_to_allowed_devices"] else "NE",
                    "foto": "ANO" if layer["show_photo"] else "NE",
                    "poradi": layer["draw_order"],
                }
                for layer in layers
            ]
        )
        st.dataframe(overview_df, width="stretch", hide_index=True)
    else:
        st.info("Zatim neni nastavena zadna mapova vrstva.")

    st.markdown("---")
    st.subheader("Pridat vrstvu")
    with st.form("create_map_layer_form"):
        render_layer_fields(
            "create",
            {
                "layer_kind": "context",
                "source_schema": "evidence",
                "geometry_column": "geom",
                "source_srid": 3857,
                "target_srid": 4326,
                "map_enabled": True,
                "default_visible": True,
                "show_photo": False,
                "is_active": True,
                "draw_order": 100,
                "style": DEFAULT_STYLE,
            },
            allow_layer_id_edit=True,
        )
        create_pressed = st.form_submit_button("Vytvorit vrstvu")

    if create_pressed:
        try:
            payload = build_payload("create")
            create_admin_map_layer(get_auth_token(), payload)
        except (DashboardApiError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.success("Mapova vrstva byla vytvorena.")
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")
    st.subheader("Upravit vrstvy")
    for layer in layers:
        layer_id = str(layer["layer_id"])
        with st.expander(f'{layer["title"]} ({layer_id})', expanded=False):
            with st.form(f"edit_map_layer_{layer_id}"):
                render_layer_fields(f"edit_{layer_id}", layer, allow_layer_id_edit=False)
                confirm_delete = st.checkbox(
                    "Potvrzuji smazani konfigurace vrstvy",
                    value=False,
                    key=f"edit_{layer_id}_confirm_delete",
                )
                save_col, delete_col = st.columns(2)
                save_pressed = save_col.form_submit_button("Ulozit zmeny")
                delete_pressed = delete_col.form_submit_button("Smazat konfiguraci")

            if save_pressed:
                try:
                    payload = build_payload(f"edit_{layer_id}", layer)
                    update_admin_map_layer(get_auth_token(), layer_id, payload)
                except (DashboardApiError, ValueError) as exc:
                    st.error(str(exc))
                else:
                    st.success("Mapova vrstva byla aktualizovana.")
                    st.cache_data.clear()
                    st.rerun()

            if delete_pressed:
                if not confirm_delete:
                    st.error("Pro smazani vrstvy musis potvrdit smazani.")
                else:
                    try:
                        delete_admin_map_layer(get_auth_token(), layer_id)
                    except DashboardApiError as exc:
                        st.error(str(exc))
                    else:
                        st.warning("Konfigurace mapove vrstvy byla smazana.")
                        st.cache_data.clear()
                        st.rerun()


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist mapove vrstvy.")
    st.exception(exc)
