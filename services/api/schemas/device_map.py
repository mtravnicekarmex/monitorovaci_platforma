from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class MapLayerFilterField(BaseModel):
    key: str
    source_column: str
    property_key: str
    label: str
    multiple: bool = True


class MapLayerCatalogItem(BaseModel):
    layer_id: str
    title: str
    layer_kind: str = "context"
    device_section_key: str | None = None
    default_visible: bool = True
    draw_order: int = 100
    filter_fields: list[MapLayerFilterField] = Field(default_factory=list)
    popup_columns: list[str] = Field(default_factory=list)
    style: dict[str, Any] = Field(default_factory=dict)


class MapLayerCatalogResponse(BaseModel):
    total: int = Field(ge=0)
    layers: list[MapLayerCatalogItem]


class MapLayerResponse(BaseModel):
    layer_id: str
    title: str
    layer_kind: str = "context"
    device_section_key: str | None = None
    identifier_column: str = "identifikace"
    source_srid: int
    target_srid: int
    map_enabled: bool = True
    default_visible: bool = True
    draw_order: int = 100
    filter_columns: list[str] = Field(default_factory=list)
    popup_columns: list[str] = Field(default_factory=list)
    style: dict[str, Any] = Field(default_factory=dict)
    total: int = Field(ge=0)
    feature_collection: dict[str, Any]


class MapLayersResponse(BaseModel):
    primary_layer_id: str | None
    layers: list[MapLayerResponse]


class MapLayerFeaturesRequest(BaseModel):
    layer_id: str = Field(min_length=1)
    filters: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("filters", mode="before")
    @classmethod
    def normalize_filter_values(cls, value: object) -> dict[str, list[str]]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            return {}

        normalized: dict[str, list[str]] = {}
        for key, raw_values in value.items():
            if isinstance(raw_values, list):
                values = [str(item) for item in raw_values]
            else:
                values = [str(raw_values)]
            normalized[str(key)] = values
        return normalized


class MapFeaturesRequest(BaseModel):
    layers: list[MapLayerFeaturesRequest] = Field(default_factory=list)


class MapFilterOptionsRequest(BaseModel):
    layers: list[MapLayerFeaturesRequest] = Field(default_factory=list)


class MapLayerFilterOptionsResponse(BaseModel):
    layer_id: str
    options: dict[str, list[str]] = Field(default_factory=dict)


class MapFilterOptionsResponse(BaseModel):
    layers: list[MapLayerFilterOptionsResponse] = Field(default_factory=list)
