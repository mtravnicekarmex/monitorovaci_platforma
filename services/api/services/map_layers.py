from __future__ import annotations

import re
from typing import Any

from sqlalchemy import bindparam, text

from app.time_utils import utc_now_naive
from core.db.connect import get_session_pg
from moduly.apps.dashboard.database.models import Dashboard_MapLayer
from services.api.services.dashboard_admin import require_admin_access
from services.api.services.dashboard_auth import AuthorizationError, DashboardUserContext
from services.api.services.device_map import (
    MapFeatureImageFile,
    MapLayerConfig,
    WEB_MAP_TARGET_SRID,
    load_map_layer_features,
    resolve_map_feature_image_file,
)


LAYER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
VALID_LAYER_KINDS = {"context", "device"}


DEFAULT_MAP_LAYER_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "layer_id": "budovy",
        "title": "Budovy",
        "layer_kind": "context",
        "source_schema": "evidence",
        "source_table": "BUDOVY",
        "geometry_column": "geom",
        "identifier_column": "fid",
        "source_srid": 3857,
        "target_srid": WEB_MAP_TARGET_SRID,
        "property_columns": ["fid", "budova", "po\u010det_podla\u017e\u00ed"],
        "property_aliases": {"po\u010det_podla\u017e\u00ed": "pocet_podlazi"},
        "filter_columns": ["budova"],
        "popup_columns": ["fid", "budova", "pocet_podlazi"],
        "style": {
            "color": "#d97706",
            "fillColor": "#fbbf24",
            "weight": 2,
            "fillOpacity": 0.16,
        },
        "restrict_to_allowed_devices": False,
        "map_enabled": True,
        "default_visible": True,
        "show_photo": False,
        "is_active": True,
        "draw_order": 10,
    },
    {
        "layer_id": "mistnosti",
        "title": "M\u00edstnosti",
        "layer_kind": "context",
        "source_schema": "evidence",
        "source_table": "M\u00cdSTNOSTI",
        "geometry_column": "geom",
        "identifier_column": "mistnost_id",
        "source_srid": 3857,
        "target_srid": WEB_MAP_TARGET_SRID,
        "property_columns": ["fid", "mistnost_id", "m\u00edstnost", "patro", "budova", "n\u00e1jemce", "popis", "plocha"],
        "property_aliases": {"m\u00edstnost": "mistnost", "n\u00e1jemce": "najemce"},
        "filter_columns": ["budova", "patro", "mistnost_id", "n\u00e1jemce"],
        "popup_columns": ["mistnost_id", "mistnost", "budova", "patro", "najemce", "popis", "plocha"],
        "style": {
            "color": "#15803d",
            "fillColor": "#86efac",
            "weight": 1.5,
            "fillOpacity": 0.2,
        },
        "restrict_to_allowed_devices": False,
        "map_enabled": True,
        "default_visible": True,
        "show_photo": False,
        "is_active": True,
        "draw_order": 20,
    },
    {
        "layer_id": "vodomery",
        "title": "Vodom\u011bry",
        "layer_kind": "device",
        "source_schema": "evidence",
        "source_table": "vodom\u011bry",
        "geometry_column": "geom",
        "identifier_column": "identifikace",
        "source_srid": 3857,
        "target_srid": WEB_MAP_TARGET_SRID,
        "property_columns": ["fid", "identifikace", "budova", "m\u00edstnost", "mistnost_id", "patro"],
        "property_aliases": {"budova": "evidence_budova", "m\u00edstnost": "evidence_mistnost", "patro": "evidence_patro"},
        "filter_columns": ["budova", "patro", "mistnost_id", "identifikace"],
        "popup_columns": [
            "identifikace",
            "detail_source_found",
            "evidence_budova",
            "evidence_patro",
            "evidence_mistnost",
            "mistnost_id",
            "seriove_cislo",
            "MBUS",
            "objekt",
            "patro",
            "mistnost",
            "umisteni",
            "pozice",
        ],
        "style": {
            "color": "#0f5e9c",
            "fillColor": "#38bdf8",
            "weight": 3,
            "fillOpacity": 0.22,
            "radius": 6,
        },
        "device_section_key": "vodomery",
        "restrict_to_allowed_devices": True,
        "map_enabled": True,
        "default_visible": True,
        "show_photo": True,
        "is_active": True,
        "draw_order": 100,
    },
)


class MapLayerOperationError(ValueError):
    """Raised when map-layer configuration is invalid."""


def _clean_text(value: str | None, *, field_name: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise MapLayerOperationError(f"{field_name} je povinne.")
    return cleaned


def _clean_layer_id(layer_id: str) -> str:
    cleaned = _clean_text(layer_id, field_name="layer_id")
    if not LAYER_ID_PATTERN.match(cleaned):
        raise MapLayerOperationError("layer_id muze obsahovat jen pismena, cisla, pomlcku a podtrzitko.")
    return cleaned


def _clean_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _clean_aliases(value: dict[str, object] | None) -> dict[str, str]:
    if not value:
        return {}
    return {str(key).strip(): str(item).strip() for key, item in value.items() if str(key).strip() and str(item).strip()}


def _clean_style(value: dict[str, object] | None) -> dict[str, object]:
    if not value:
        return {}
    return {str(key).strip(): item for key, item in value.items() if str(key).strip()}


def _table_columns(source_schema: str, source_table: str) -> set[str]:
    session = get_session_pg()
    try:
        rows = session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table
                """
            ),
            {
                "schema": source_schema,
                "table": source_table,
            },
        ).all()
    finally:
        session.close()
    return {str(row[0]) for row in rows}


def _validate_source_columns(
    *,
    source_schema: str,
    source_table: str,
    geometry_column: str,
    identifier_column: str,
    property_columns: list[str],
    filter_columns: list[str],
) -> None:
    columns = _table_columns(source_schema, source_table)
    if not columns:
        raise MapLayerOperationError(f"Zdrojova tabulka {source_schema}.{source_table} neexistuje nebo nema sloupce.")

    required = {geometry_column, identifier_column}
    optional = set(property_columns) | set(filter_columns)
    missing_required = sorted(required - columns)
    missing_optional = sorted(optional - columns)
    if missing_required:
        raise MapLayerOperationError(f"Chybi povinne sloupce: {', '.join(missing_required)}.")
    if missing_optional:
        raise MapLayerOperationError(f"Chybi nastavene sloupce: {', '.join(missing_optional)}.")


def _serialize_record(layer: Dashboard_MapLayer) -> dict[str, object]:
    return {
        "layer_id": layer.layer_id,
        "title": layer.title,
        "layer_kind": layer.layer_kind,
        "source_schema": layer.source_schema,
        "source_table": layer.source_table,
        "geometry_column": layer.geometry_column,
        "identifier_column": layer.identifier_column,
        "source_srid": int(layer.source_srid),
        "target_srid": int(layer.target_srid),
        "property_columns": layer.get_property_columns(),
        "property_aliases": layer.get_property_aliases(),
        "filter_columns": layer.get_filter_columns(),
        "popup_columns": layer.get_popup_columns(),
        "style": layer.get_style(),
        "device_section_key": layer.device_section_key,
        "restrict_to_allowed_devices": bool(layer.restrict_to_allowed_devices),
        "map_enabled": bool(layer.map_enabled),
        "default_visible": bool(layer.default_visible),
        "show_photo": bool(layer.show_photo),
        "is_active": bool(layer.is_active),
        "draw_order": int(layer.draw_order),
        "created_at": layer.created_at,
        "updated_at": layer.updated_at,
    }


def map_layer_record_to_config(record: dict[str, object]) -> MapLayerConfig:
    aliases = {str(key): str(value) for key, value in dict(record.get("property_aliases") or {}).items()}
    return MapLayerConfig(
        layer_id=str(record["layer_id"]),
        title=str(record["title"]),
        schema=str(record["source_schema"]),
        table=str(record["source_table"]),
        geometry_column=str(record["geometry_column"]),
        identifier_column=str(record["identifier_column"]),
        source_srid=int(record["source_srid"]),
        target_srid=int(record["target_srid"]),
        property_columns=tuple(str(column) for column in record.get("property_columns", []) or []),
        property_aliases=aliases,
        restrict_to_allowed_devices=bool(record.get("restrict_to_allowed_devices", False)),
        layer_kind=str(record.get("layer_kind") or "context"),
        device_section_key=str(record["device_section_key"]) if record.get("device_section_key") else None,
        map_enabled=bool(record.get("map_enabled", True)),
        default_visible=bool(record.get("default_visible", True)),
        show_photo=bool(record.get("show_photo", False)),
        draw_order=int(record.get("draw_order", 100)),
        filter_columns=tuple(str(column) for column in record.get("filter_columns", []) or []),
        popup_columns=tuple(str(column) for column in record.get("popup_columns", []) or []),
        style=dict(record.get("style") or {}),
    )


def _apply_record_fields(layer: Dashboard_MapLayer, values: dict[str, object]) -> None:
    layer.title = str(values["title"])
    layer.layer_kind = str(values["layer_kind"])
    layer.source_schema = str(values["source_schema"])
    layer.source_table = str(values["source_table"])
    layer.geometry_column = str(values["geometry_column"])
    layer.identifier_column = str(values["identifier_column"])
    layer.source_srid = int(values["source_srid"])
    layer.target_srid = int(values["target_srid"])
    layer.set_property_columns(list(values["property_columns"]))
    layer.set_property_aliases(dict(values["property_aliases"]))
    layer.set_filter_columns(list(values["filter_columns"]))
    layer.set_popup_columns(list(values["popup_columns"]))
    layer.set_style(dict(values["style"]))
    layer.device_section_key = str(values["device_section_key"]) if values.get("device_section_key") else None
    layer.restrict_to_allowed_devices = bool(values["restrict_to_allowed_devices"])
    layer.map_enabled = bool(values["map_enabled"])
    layer.default_visible = bool(values["default_visible"])
    layer.show_photo = bool(values["show_photo"])
    layer.is_active = bool(values["is_active"])
    layer.draw_order = int(values["draw_order"])
    layer.updated_at = utc_now_naive()


def _prepare_record_values(
    *,
    layer_id: str,
    title: str,
    layer_kind: str,
    source_schema: str,
    source_table: str,
    geometry_column: str,
    identifier_column: str,
    source_srid: int,
    target_srid: int,
    property_columns: list[str] | None,
    property_aliases: dict[str, object] | None,
    filter_columns: list[str] | None,
    popup_columns: list[str] | None,
    style: dict[str, object] | None,
    device_section_key: str | None,
    restrict_to_allowed_devices: bool,
    map_enabled: bool,
    default_visible: bool,
    show_photo: bool,
    is_active: bool,
    draw_order: int,
) -> dict[str, object]:
    cleaned_layer_id = _clean_layer_id(layer_id)
    cleaned_layer_kind = _clean_text(layer_kind, field_name="layer_kind")
    if cleaned_layer_kind not in VALID_LAYER_KINDS:
        raise MapLayerOperationError("layer_kind musi byt context nebo device.")

    values: dict[str, object] = {
        "layer_id": cleaned_layer_id,
        "title": _clean_text(title, field_name="title"),
        "layer_kind": cleaned_layer_kind,
        "source_schema": _clean_text(source_schema, field_name="source_schema"),
        "source_table": _clean_text(source_table, field_name="source_table"),
        "geometry_column": _clean_text(geometry_column, field_name="geometry_column"),
        "identifier_column": _clean_text(identifier_column, field_name="identifier_column"),
        "source_srid": int(source_srid),
        "target_srid": int(target_srid),
        "property_columns": _clean_list(property_columns),
        "property_aliases": _clean_aliases(property_aliases),
        "filter_columns": _clean_list(filter_columns),
        "popup_columns": _clean_list(popup_columns),
        "style": _clean_style(style),
        "device_section_key": (device_section_key or "").strip() or None,
        "restrict_to_allowed_devices": bool(restrict_to_allowed_devices),
        "map_enabled": bool(map_enabled),
        "default_visible": bool(default_visible),
        "show_photo": bool(show_photo),
        "is_active": bool(is_active),
        "draw_order": int(draw_order),
    }
    _validate_source_columns(
        source_schema=str(values["source_schema"]),
        source_table=str(values["source_table"]),
        geometry_column=str(values["geometry_column"]),
        identifier_column=str(values["identifier_column"]),
        property_columns=list(values["property_columns"]),
        filter_columns=list(values["filter_columns"]),
    )
    return values


def ensure_default_map_layers() -> None:
    session = get_session_pg()
    try:
        changed = False
        for seed in DEFAULT_MAP_LAYER_SEEDS:
            existing = session.get(Dashboard_MapLayer, str(seed["layer_id"]))
            if existing is not None:
                continue
            layer = Dashboard_MapLayer(layer_id=str(seed["layer_id"]))
            _apply_record_fields(layer, seed)
            session.add(layer)
            changed = True
        if changed:
            session.commit()
    finally:
        session.close()


def list_map_layers_admin(user_context: DashboardUserContext) -> list[dict[str, object]]:
    require_admin_access(user_context)
    session = get_session_pg()
    try:
        rows = (
            session.query(Dashboard_MapLayer)
            .order_by(Dashboard_MapLayer.draw_order.asc(), Dashboard_MapLayer.layer_id.asc())
            .all()
        )
        return [_serialize_record(row) for row in rows]
    finally:
        session.close()


def list_enabled_map_layer_configs(layer_ids: tuple[str, ...] | None = None) -> list[MapLayerConfig]:
    session = get_session_pg()
    try:
        existing_query = session.query(Dashboard_MapLayer.layer_id)
        if layer_ids is not None:
            existing_query = existing_query.filter(Dashboard_MapLayer.layer_id.in_(layer_ids))
        existing_ids = {str(row[0]) for row in existing_query.all()}

        query = session.query(Dashboard_MapLayer).filter(
            Dashboard_MapLayer.is_active.is_(True),
            Dashboard_MapLayer.map_enabled.is_(True),
        )
        if layer_ids is not None:
            query = query.filter(Dashboard_MapLayer.layer_id.in_(layer_ids))
        rows = query.order_by(Dashboard_MapLayer.draw_order.asc(), Dashboard_MapLayer.layer_id.asc()).all()
        records = [_serialize_record(row) for row in rows]
    finally:
        session.close()

    if layer_ids is not None:
        for seed in DEFAULT_MAP_LAYER_SEEDS:
            if seed["layer_id"] in existing_ids or seed["layer_id"] not in layer_ids:
                continue
            if seed.get("is_active", True) and seed.get("map_enabled", True):
                records.append(dict(seed))
    elif not records and not existing_ids:
        records = [dict(seed) for seed in DEFAULT_MAP_LAYER_SEEDS if seed.get("is_active", True) and seed.get("map_enabled", True)]

    records.sort(key=lambda item: (int(item.get("draw_order", 100)), str(item.get("layer_id", ""))))
    return [map_layer_record_to_config(record) for record in records]


def get_enabled_map_layer_config(layer_id: str) -> MapLayerConfig | None:
    configs = list_enabled_map_layer_configs((layer_id,))
    return configs[0] if configs else None


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _filter_property_key(config: MapLayerConfig, column: str) -> str:
    return config.property_aliases.get(column, column)


def map_layer_config_to_catalog_record(config: MapLayerConfig) -> dict[str, object]:
    return {
        "layer_id": config.layer_id,
        "title": config.title,
        "layer_kind": config.layer_kind,
        "device_section_key": config.device_section_key,
        "default_visible": config.default_visible,
        "draw_order": config.draw_order,
        "filter_fields": [
            {
                "key": column,
                "source_column": column,
                "property_key": _filter_property_key(config, column),
                "label": _filter_property_key(config, column),
                "multiple": True,
            }
            for column in config.filter_columns
        ],
        "popup_columns": list(config.popup_columns),
        "style": dict(config.style),
    }


def user_can_access_map_layer(user_context: DashboardUserContext, config: MapLayerConfig) -> bool:
    if not config.map_enabled:
        return False
    if user_context.is_admin:
        return True
    if config.layer_kind != "device" and not config.restrict_to_allowed_devices:
        return True
    if config.device_section_key and config.device_section_key not in user_context.allowed_sections:
        return False
    if config.restrict_to_allowed_devices and not user_context.allowed_devices:
        return False
    return True


def list_available_map_layer_configs(
    user_context: DashboardUserContext,
    layer_ids: tuple[str, ...] | None = None,
) -> list[MapLayerConfig]:
    configs = list_enabled_map_layer_configs(layer_ids)
    return [config for config in configs if user_can_access_map_layer(user_context, config)]


def list_map_layer_catalog(user_context: DashboardUserContext) -> list[dict[str, object]]:
    configs = list_available_map_layer_configs(user_context)
    return [map_layer_config_to_catalog_record(config) for config in configs]


def _normalize_requested_filters(
    config: MapLayerConfig,
    filters: dict[str, list[str]],
) -> dict[str, tuple[str, ...]]:
    if not filters:
        return {}

    allowed_by_key: dict[str, str] = {}
    for column in config.filter_columns:
        allowed_by_key[column] = column
        allowed_by_key[_filter_property_key(config, column)] = column

    normalized: dict[str, tuple[str, ...]] = {}
    for filter_key, raw_values in filters.items():
        source_column = allowed_by_key.get(str(filter_key))
        if source_column is None:
            raise MapLayerOperationError(f"Vrstva {config.layer_id} nepodporuje filtr {filter_key}.")

        values = tuple(dict.fromkeys(str(value).strip() for value in raw_values if str(value).strip()))
        if values:
            normalized[source_column] = values
    return normalized


def _load_layer_filter_options(
    user_context: DashboardUserContext,
    config: MapLayerConfig,
    filters: dict[str, list[str]],
) -> dict[str, object]:
    if not config.filter_columns:
        return {
            "layer_id": config.layer_id,
            "options": {},
        }

    available_columns = _table_columns(config.schema, config.table)
    missing_columns = sorted(({config.geometry_column, config.identifier_column} | set(config.filter_columns)) - available_columns)
    if missing_columns:
        raise MapLayerOperationError(
            f"Mapova vrstva {config.layer_id} nema sloupce pro filtrovani: {', '.join(missing_columns)}."
        )

    normalized_filters = _normalize_requested_filters(config, filters)
    restrict_identifiers = config.restrict_to_allowed_devices and not user_context.is_admin
    identifiers: tuple[str, ...] = ()
    if restrict_identifiers:
        identifiers = tuple(str(identifier) for identifier in user_context.allowed_devices if identifier)
        if not identifiers:
            return {
                "layer_id": config.layer_id,
                "options": {column: [] for column in config.filter_columns},
            }

    table_ref = f"{_quote_identifier(config.schema)}.{_quote_identifier(config.table)}"
    geometry_ref = f"t.{_quote_identifier(config.geometry_column)}"
    identifier_ref = f"t.{_quote_identifier(config.identifier_column)}"

    options: dict[str, list[str]] = {}
    session = get_session_pg()
    try:
        for option_column in config.filter_columns:
            option_ref = f"t.{_quote_identifier(option_column)}"
            filter_values = {
                column: values
                for column, values in normalized_filters.items()
                if column != option_column
            }
            query = (
                f"SELECT DISTINCT {option_ref} AS value "
                f"FROM {table_ref} AS t "
                f"WHERE {geometry_ref} IS NOT NULL "
                f"AND {option_ref} IS NOT NULL "
                f"AND CAST({option_ref} AS TEXT) <> ''"
            )

            params: dict[str, object] = {}
            if restrict_identifiers:
                query += f" AND {identifier_ref} IN :identifiers"
                params["identifiers"] = identifiers

            for index, column in enumerate(filter_values):
                query += f" AND t.{_quote_identifier(column)} IN :filter_{index}"
                params[f"filter_{index}"] = filter_values[column]

            query += f" ORDER BY {option_ref} ASC"
            statement = text(query)
            if restrict_identifiers:
                statement = statement.bindparams(bindparam("identifiers", expanding=True))
            for index, _column in enumerate(filter_values):
                statement = statement.bindparams(bindparam(f"filter_{index}", expanding=True))

            rows = session.execute(statement, params).all()
            option_key = option_column
            options[option_key] = [str(row[0]) for row in rows if row[0] not in (None, "")]
    finally:
        session.close()

    return {
        "layer_id": config.layer_id,
        "options": options,
    }


def load_requested_map_filter_options(
    user_context: DashboardUserContext,
    requested_layers: list[dict[str, object]],
) -> dict[str, object]:
    if not requested_layers:
        requested_layers = [
            {
                "layer_id": config.layer_id,
                "filters": {},
            }
            for config in list_available_map_layer_configs(user_context)
        ]

    requested_ids: list[str] = []
    for request in requested_layers:
        layer_id = str(request.get("layer_id", "")).strip()
        if not layer_id:
            raise MapLayerOperationError("layer_id je povinne.")
        if layer_id not in requested_ids:
            requested_ids.append(layer_id)

    all_requested_configs = list_enabled_map_layer_configs(tuple(requested_ids))
    config_by_id = {config.layer_id: config for config in all_requested_configs}
    available_by_id = {
        config.layer_id: config
        for config in all_requested_configs
        if user_can_access_map_layer(user_context, config)
    }

    layers: list[dict[str, object]] = []
    for request in requested_layers:
        layer_id = str(request.get("layer_id", "")).strip()
        config = config_by_id.get(layer_id)
        if config is None:
            raise MapLayerOperationError(f"Mapova vrstva {layer_id} neexistuje nebo neni aktivni.")
        if layer_id not in available_by_id:
            raise AuthorizationError(f"Nemate opravneni k mapove vrstve {layer_id}.")

        filters = request.get("filters")
        if not isinstance(filters, dict):
            filters = {}
        normalized_input = {
            str(key): [str(value) for value in values]
            for key, values in filters.items()
            if isinstance(values, list)
        }
        layers.append(_load_layer_filter_options(user_context, config, normalized_input))

    return {
        "layers": layers,
    }


def load_map_feature_image_file(
    user_context: DashboardUserContext,
    *,
    layer_id: str,
    identifier: str,
) -> MapFeatureImageFile:
    cleaned_layer_id = str(layer_id or "").strip()
    cleaned_identifier = str(identifier or "").strip()
    if not cleaned_layer_id:
        raise MapLayerOperationError("layer_id je povinne.")
    if not cleaned_identifier:
        raise MapLayerOperationError("identifier je povinne.")

    config = get_enabled_map_layer_config(cleaned_layer_id)
    if config is None:
        raise MapLayerOperationError(f"Mapova vrstva {cleaned_layer_id} neexistuje nebo neni aktivni.")
    if not user_can_access_map_layer(user_context, config):
        raise AuthorizationError(f"Nemate opravneni k mapove vrstve {cleaned_layer_id}.")
    if config.restrict_to_allowed_devices and not user_context.is_admin:
        allowed_identifiers = {str(identifier) for identifier in user_context.allowed_devices if identifier}
        if cleaned_identifier not in allowed_identifiers:
            raise AuthorizationError(f"Nemate opravneni k zarizeni {cleaned_identifier}.")

    return resolve_map_feature_image_file(config, cleaned_identifier)


def load_requested_map_features(
    user_context: DashboardUserContext,
    requested_layers: list[dict[str, object]],
) -> dict[str, object]:
    if not requested_layers:
        configs = list_available_map_layer_configs(user_context)
        layers = [
            load_map_layer_features(user_context, config)
            for config in configs
        ]
        return {
            "primary_layer_id": layers[0]["layer_id"] if layers else None,
            "layers": layers,
        }

    requested_ids: list[str] = []
    for request in requested_layers:
        layer_id = str(request.get("layer_id", "")).strip()
        if not layer_id:
            raise MapLayerOperationError("layer_id je povinne.")
        if layer_id not in requested_ids:
            requested_ids.append(layer_id)

    all_requested_configs = list_enabled_map_layer_configs(tuple(requested_ids))
    config_by_id = {config.layer_id: config for config in all_requested_configs}
    available_by_id = {
        config.layer_id: config
        for config in all_requested_configs
        if user_can_access_map_layer(user_context, config)
    }

    layers: list[dict[str, object]] = []
    for request in requested_layers:
        layer_id = str(request.get("layer_id", "")).strip()
        config = config_by_id.get(layer_id)
        if config is None:
            raise MapLayerOperationError(f"Mapova vrstva {layer_id} neexistuje nebo neni aktivni.")
        if layer_id not in available_by_id:
            raise AuthorizationError(f"Nemate opravneni k mapove vrstve {layer_id}.")

        filters = request.get("filters")
        if not isinstance(filters, dict):
            filters = {}
        normalized_filters = _normalize_requested_filters(
            config,
            {str(key): [str(value) for value in values] for key, values in filters.items() if isinstance(values, list)},
        )
        layers.append(
            load_map_layer_features(
                user_context,
                config,
                filter_values_by_column=normalized_filters,
            )
        )

    return {
        "primary_layer_id": layers[0]["layer_id"] if layers else None,
        "layers": layers,
    }


def create_map_layer_admin(
    user_context: DashboardUserContext,
    **kwargs: object,
) -> dict[str, object]:
    require_admin_access(user_context)
    values = _prepare_record_values(**kwargs)
    session = get_session_pg()
    try:
        existing = session.get(Dashboard_MapLayer, str(values["layer_id"]))
        if existing is not None:
            raise MapLayerOperationError("Vrstva s timto layer_id uz existuje.")
        layer = Dashboard_MapLayer(layer_id=str(values["layer_id"]))
        _apply_record_fields(layer, values)
        session.add(layer)
        session.commit()
        session.refresh(layer)
        return _serialize_record(layer)
    finally:
        session.close()


def update_map_layer_admin(
    user_context: DashboardUserContext,
    *,
    layer_id: str,
    **kwargs: object,
) -> dict[str, object]:
    require_admin_access(user_context)
    cleaned_layer_id = _clean_layer_id(layer_id)
    values = _prepare_record_values(layer_id=cleaned_layer_id, **kwargs)
    session = get_session_pg()
    try:
        layer = session.get(Dashboard_MapLayer, cleaned_layer_id)
        if layer is None:
            raise MapLayerOperationError("Vrstva neexistuje.")
        _apply_record_fields(layer, values)
        session.commit()
        session.refresh(layer)
        return _serialize_record(layer)
    finally:
        session.close()


def delete_map_layer_admin(user_context: DashboardUserContext, *, layer_id: str) -> None:
    require_admin_access(user_context)
    cleaned_layer_id = _clean_layer_id(layer_id)
    session = get_session_pg()
    try:
        layer = session.get(Dashboard_MapLayer, cleaned_layer_id)
        if layer is None:
            return
        session.delete(layer)
        session.commit()
    finally:
        session.close()
