from __future__ import annotations

import json
import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import bindparam, text

from core.db.connect import get_session_ms, get_session_pg
from moduly.mereni.vodomery.database.models import Vodomer_areal_Zarizeni
from services.api.services.dashboard_auth import DashboardUserContext


WEB_MAP_TARGET_SRID = 4326


@dataclass(frozen=True)
class MapLayerConfig:
    layer_id: str
    title: str
    schema: str
    table: str
    geometry_column: str
    identifier_column: str = "identifikace"
    source_srid: int = 3857
    target_srid: int = WEB_MAP_TARGET_SRID
    property_columns: tuple[str, ...] = ()
    property_aliases: Mapping[str, str] = field(default_factory=dict)
    restrict_to_allowed_devices: bool = True
    layer_kind: str = "context"
    device_section_key: str | None = None
    map_enabled: bool = True
    default_visible: bool = True
    show_photo: bool = False
    draw_order: int = 100
    filter_columns: tuple[str, ...] = ()
    popup_columns: tuple[str, ...] = ()
    style: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MapFeatureImageFile:
    path: Path
    media_type: str


class MapFeatureImageError(ValueError):
    """Raised when a map feature image cannot be resolved from supported metadata."""


class MapFeatureImageNotFound(FileNotFoundError):
    """Raised when a configured map feature image is missing or empty."""


SUPPORTED_IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}
PHOTO_PATH_PREFIX_FALLBACKS: tuple[tuple[str, str], ...] = (
    ("P:\\", "\\\\SERVER1A\\Company\\"),
)


VODOMERY_MAP_LAYER = MapLayerConfig(
    layer_id="vodomery",
    title="Vodomery",
    schema="evidence",
    table="vodom\u011bry",
    geometry_column="geom",
    property_columns=(
        "fid",
        "identifikace",
        "budova",
        "místnost",
        "mistnost_id",
        "patro",
    ),
    property_aliases={
        "budova": "evidence_budova",
        "místnost": "evidence_mistnost",
        "patro": "evidence_patro",
    },
    restrict_to_allowed_devices=True,
    layer_kind="device",
    device_section_key="vodomery",
    show_photo=True,
    draw_order=100,
    filter_columns=("budova", "patro", "mistnost_id", "identifikace"),
    popup_columns=(
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
    ),
    style={
        "color": "#0f5e9c",
        "fillColor": "#38bdf8",
        "weight": 3,
        "fillOpacity": 0.22,
        "radius": 6,
    },
)


BUDOVY_MAP_LAYER = MapLayerConfig(
    layer_id="budovy",
    title="Budovy",
    schema="evidence",
    table="BUDOVY",
    geometry_column="geom",
    identifier_column="fid",
    property_columns=(
        "fid",
        "budova",
        "po\u010det_podla\u017e\u00ed",
    ),
    property_aliases={
        "po\u010det_podla\u017e\u00ed": "pocet_podlazi",
    },
    restrict_to_allowed_devices=False,
    draw_order=10,
    filter_columns=("budova",),
    popup_columns=("fid", "budova", "pocet_podlazi"),
    style={
        "color": "#d97706",
        "fillColor": "#fbbf24",
        "weight": 2,
        "fillOpacity": 0.16,
    },
)


MISTNOSTI_MAP_LAYER = MapLayerConfig(
    layer_id="mistnosti",
    title="M\u00edstnosti",
    schema="evidence",
    table="M\u00cdSTNOSTI",
    geometry_column="geom",
    identifier_column="mistnost_id",
    property_columns=(
        "fid",
        "mistnost_id",
        "m\u00edstnost",
        "patro",
        "budova",
        "n\u00e1jemce",
        "popis",
        "plocha",
    ),
    property_aliases={
        "m\u00edstnost": "mistnost",
        "n\u00e1jemce": "najemce",
    },
    restrict_to_allowed_devices=False,
    draw_order=20,
    filter_columns=("budova", "patro", "mistnost_id", "n\u00e1jemce"),
    popup_columns=("mistnost_id", "mistnost", "budova", "patro", "najemce", "popis", "plocha"),
    style={
        "color": "#15803d",
        "fillColor": "#86efac",
        "weight": 1.5,
        "fillOpacity": 0.20,
    },
)


VODOMERY_DETAIL_COLUMNS: tuple[str, ...] = (
    "identifikace",
    "seriove_cislo",
    "MBUS",
    "pozice",
    "podruzny",
    "mistnost",
    "objekt",
    "patro",
    "umisteni",
    "napaji",
    "koncovy_odberatel",
    "platnost_cejchu",
    "redukcni_ventil",
    "filtr",
    "poznamka_vodomery",
)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _serialize_property_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _path_from_file_url(raw_value: str) -> Path:
    parsed = urlparse(raw_value)
    path_text = unquote(parsed.path or "")
    if parsed.netloc:
        path_text = f"//{parsed.netloc}{path_text}"
    elif len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
        path_text = path_text[1:]
    return Path(path_text)


def _path_from_photo_value(value: object) -> Path:
    raw_value = str(value or "").strip().strip('"').strip("'")
    if not raw_value:
        raise MapFeatureImageNotFound("Fotka neni nastavena.")

    parsed = urlparse(raw_value)
    if parsed.scheme in {"http", "https", "data", "blob"}:
        raise MapFeatureImageError("Fotka neni souborova cesta.")
    if parsed.scheme == "file":
        return _path_from_file_url(raw_value)
    return Path(raw_value)


def _photo_path_candidates(value: object) -> tuple[Path, ...]:
    primary_path = _path_from_photo_value(value)
    primary_text = str(primary_path)
    candidates = [primary_path]

    for source_prefix, replacement_prefix in PHOTO_PATH_PREFIX_FALLBACKS:
        if not primary_text.casefold().startswith(source_prefix.casefold()):
            continue
        relative_path = primary_text[len(source_prefix):].lstrip("\\/")
        candidates.append(Path(f"{replacement_prefix}{relative_path}"))

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate_key = str(candidate).casefold()
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        unique_candidates.append(candidate)
    return tuple(unique_candidates)


def _resolve_image_file(value: object) -> MapFeatureImageFile:
    path = next((candidate for candidate in _photo_path_candidates(value) if candidate.is_file()), None)
    if path is None:
        raise MapFeatureImageNotFound("Soubor fotky neexistuje.")

    suffix = path.suffix.casefold()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES:
        raise MapFeatureImageError("Soubor fotky nema podporovanou obrazovou priponu.")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if not media_type.startswith("image/"):
        raise MapFeatureImageError("Soubor fotky nema podporovany obrazovy typ.")

    return MapFeatureImageFile(path=path, media_type=media_type)


def _property_key(column: str, config: MapLayerConfig) -> str:
    return config.property_aliases.get(column, column)


def _load_table_columns(session, config: MapLayerConfig) -> set[str]:
    rows = session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            """
        ),
        {
            "schema": config.schema,
            "table": config.table,
        },
    ).all()
    return {str(row[0]) for row in rows}


def _build_layer_statement(
    config: MapLayerConfig,
    *,
    restrict_identifiers: bool,
    available_columns: set[str],
    filter_values_by_column: Mapping[str, tuple[str, ...]] | None = None,
):
    required_columns = {config.geometry_column, config.identifier_column}
    missing_required = sorted(required_columns - available_columns)
    if missing_required:
        raise ValueError(
            f"Mapova vrstva {config.layer_id} nema povinne sloupce: {', '.join(missing_required)}"
        )

    table_ref = f"{_quote_identifier(config.schema)}.{_quote_identifier(config.table)}"
    geometry_ref = f"t.{_quote_identifier(config.geometry_column)}"
    selected_columns = [
        f"t.{_quote_identifier(column)} AS {_quote_identifier(column)}"
        for column in config.property_columns
        if column in available_columns
    ]
    selected_columns.append(
        "ST_AsGeoJSON("
        f"ST_Transform(ST_SetSRID({geometry_ref}, :source_srid), :target_srid)"
        ") AS geometry"
    )

    query = (
        f"SELECT {', '.join(selected_columns)} "
        f"FROM {table_ref} AS t "
        f"WHERE {geometry_ref} IS NOT NULL"
    )

    if restrict_identifiers:
        query += f" AND t.{_quote_identifier(config.identifier_column)} IN :identifiers"

    if filter_values_by_column:
        for index, column in enumerate(filter_values_by_column):
            query += f" AND t.{_quote_identifier(column)} IN :filter_{index}"

    query += f" ORDER BY t.{_quote_identifier(config.identifier_column)} ASC"

    statement = text(query)
    if restrict_identifiers:
        statement = statement.bindparams(bindparam("identifiers", expanding=True))
    if filter_values_by_column:
        for index, _column in enumerate(filter_values_by_column):
            statement = statement.bindparams(bindparam(f"filter_{index}", expanding=True))
    return statement


def _load_vodomery_device_details(
    identifiers: tuple[str, ...],
    *,
    include_photo: bool,
) -> dict[str, dict[str, object]]:
    if not identifiers:
        return {}

    detail_columns = VODOMERY_DETAIL_COLUMNS + (("foto",) if include_photo else ())
    selected_columns = [getattr(Vodomer_areal_Zarizeni, column) for column in detail_columns]
    session = get_session_ms()
    try:
        rows = (
            session.query(*selected_columns)
            .filter(Vodomer_areal_Zarizeni.identifikace.in_(identifiers))
            .all()
        )
    finally:
        session.close()

    details: dict[str, dict[str, object]] = {}
    for row in rows:
        record = {
            column: _serialize_property_value(value)
            for column, value in zip(detail_columns, tuple(row), strict=True)
        }
        identifier = record.get("identifikace")
        if identifier:
            details[str(identifier)] = record
    return details


def _load_detail_properties(
    config: MapLayerConfig,
    identifiers: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    if config.layer_id == VODOMERY_MAP_LAYER.layer_id:
        return _load_vodomery_device_details(
            identifiers,
            include_photo=config.show_photo,
        )
    return {}


def resolve_map_feature_image_file(config: MapLayerConfig, identifier: str) -> MapFeatureImageFile:
    cleaned_identifier = str(identifier or "").strip()
    if not cleaned_identifier:
        raise MapFeatureImageError("identifier je povinne.")

    if not config.show_photo:
        raise MapFeatureImageError("Zobrazeni fotek neni pro vrstvu povoleno.")
    if config.layer_id != VODOMERY_MAP_LAYER.layer_id:
        raise MapFeatureImageError("Vrstva nema podporovane fotky.")

    detail = _load_vodomery_device_details(
        (cleaned_identifier,),
        include_photo=True,
    ).get(cleaned_identifier)
    if not detail:
        raise MapFeatureImageNotFound("Detail zarizeni nebyl nalezen.")
    return _resolve_image_file(detail.get("foto"))


def _row_to_feature(
    row: dict[str, Any],
    config: MapLayerConfig,
    detail_properties: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object] | None:
    geometry_raw = row.get("geometry")
    if not geometry_raw:
        return None
    try:
        geometry = json.loads(str(geometry_raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(geometry, dict):
        return None

    properties = {
        _property_key(column, config): _serialize_property_value(row.get(column))
        for column in config.property_columns
        if column in row
    }
    identifier = properties.get(config.identifier_column)
    detail = dict(detail_properties.get(str(identifier), {}) if detail_properties else {})
    properties["detail_source_found"] = bool(detail)
    photo_value = detail.pop("foto", None)
    if config.show_photo:
        properties["has_photo"] = bool(str(photo_value or "").strip())
    properties.update(detail)
    properties["layer_id"] = config.layer_id
    properties["layer_title"] = config.title

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


def load_map_layer_features(
    user_context: DashboardUserContext,
    config: MapLayerConfig,
    *,
    filter_values_by_column: Mapping[str, tuple[str, ...]] | None = None,
) -> dict[str, object]:
    identifiers: tuple[str, ...] = ()
    restrict_identifiers = config.restrict_to_allowed_devices and not user_context.is_admin
    if restrict_identifiers:
        identifiers = tuple(str(identifier) for identifier in user_context.allowed_devices if identifier)
        if not identifiers:
            return _empty_layer_response(config)

    params: dict[str, object] = {
        "source_srid": config.source_srid,
        "target_srid": config.target_srid,
    }
    if restrict_identifiers:
        params["identifiers"] = identifiers
    if filter_values_by_column:
        for index, values in enumerate(filter_values_by_column.values()):
            params[f"filter_{index}"] = values

    session = get_session_pg()
    try:
        available_columns = _load_table_columns(session, config)
        if filter_values_by_column:
            missing_filter_columns = sorted(set(filter_values_by_column) - available_columns)
            if missing_filter_columns:
                raise ValueError(
                    f"Mapova vrstva {config.layer_id} nema filtrovaci sloupce: "
                    f"{', '.join(missing_filter_columns)}"
                )
        statement = _build_layer_statement(
            config,
            restrict_identifiers=restrict_identifiers,
            available_columns=available_columns,
            filter_values_by_column=filter_values_by_column,
        )
        rows = [dict(row) for row in session.execute(statement, params).mappings().all()]
    finally:
        session.close()

    row_identifiers = tuple(
        dict.fromkeys(
            str(row.get(config.identifier_column))
            for row in rows
            if row.get(config.identifier_column)
        )
    )
    detail_properties = _load_detail_properties(config, row_identifiers)
    features = [
        feature
        for row in rows
        if (feature := _row_to_feature(row, config, detail_properties)) is not None
    ]

    return {
        "layer_id": config.layer_id,
        "title": config.title,
        "layer_kind": config.layer_kind,
        "device_section_key": config.device_section_key,
        "identifier_column": config.identifier_column,
        "source_srid": config.source_srid,
        "target_srid": config.target_srid,
        "map_enabled": config.map_enabled,
        "default_visible": config.default_visible,
        "draw_order": config.draw_order,
        "filter_columns": list(config.filter_columns),
        "popup_columns": list(config.popup_columns),
        "style": dict(config.style),
        "total": len(features),
        "feature_collection": {
            "type": "FeatureCollection",
            "features": features,
        },
    }


def load_map_layers(
    user_context: DashboardUserContext,
    configs: tuple[MapLayerConfig, ...],
    *,
    primary_layer_id: str,
) -> dict[str, object]:
    return {
        "primary_layer_id": primary_layer_id,
        "layers": [load_map_layer_features(user_context, config) for config in configs],
    }


def _empty_layer_response(config: MapLayerConfig) -> dict[str, object]:
    return {
        "layer_id": config.layer_id,
        "title": config.title,
        "layer_kind": config.layer_kind,
        "device_section_key": config.device_section_key,
        "identifier_column": config.identifier_column,
        "source_srid": config.source_srid,
        "target_srid": config.target_srid,
        "map_enabled": config.map_enabled,
        "default_visible": config.default_visible,
        "draw_order": config.draw_order,
        "filter_columns": list(config.filter_columns),
        "popup_columns": list(config.popup_columns),
        "style": dict(config.style),
        "total": 0,
        "feature_collection": {
            "type": "FeatureCollection",
            "features": [],
        },
    }
