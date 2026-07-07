from __future__ import annotations

import base64
import json
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from moduly.apps.dashboard.api_client import get_map_features, get_map_filter_options, get_map_layer_catalog


DEFAULT_MAP_HEIGHT_PX = 720
LEAFLET_VERSION = "1.9.4"
LEAFLET_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "leaflet" / LEAFLET_VERSION
LEAFLET_CSS_IMAGE_NAMES = (
    "layers.png",
    "layers-2x.png",
    "marker-icon.png",
)


@st.cache_data(ttl=60)
def load_map_layer_catalog_payload(access_token: str) -> dict[str, object]:
    return get_map_layer_catalog(access_token)


@st.cache_data(ttl=60)
def load_map_features_payload(access_token: str, request_payload: dict[str, object]) -> dict[str, object]:
    return get_map_features(access_token, request_payload)


@st.cache_data(ttl=60)
def load_map_filter_options_payload(access_token: str, request_payload: dict[str, object]) -> dict[str, object]:
    return get_map_filter_options(access_token, request_payload)


def _json_payload_to_base64(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


@lru_cache(maxsize=None)
def _leaflet_image_data_uri(image_name: str) -> str:
    image_data = (LEAFLET_ASSET_DIR / "images" / image_name).read_bytes()
    return f"data:image/png;base64,{base64.b64encode(image_data).decode('ascii')}"


@lru_cache(maxsize=1)
def _leaflet_css_for_inline_html() -> str:
    css = (LEAFLET_ASSET_DIR / "leaflet.css").read_text(encoding="utf-8")
    for image_name in LEAFLET_CSS_IMAGE_NAMES:
        css = css.replace(
            f"url(images/{image_name})",
            f"url({_leaflet_image_data_uri(image_name)})",
        )
    if "url(images/" in css:
        raise RuntimeError("Leaflet CSS contains an unbundled image reference.")
    return css.replace("</style", "<\\/style")


@lru_cache(maxsize=1)
def _leaflet_javascript_for_inline_html() -> str:
    javascript = (LEAFLET_ASSET_DIR / "leaflet.js").read_text(encoding="utf-8")
    javascript = javascript.replace("\n//# sourceMappingURL=leaflet.js.map", "")
    return javascript.replace("</script", "<\\/script")


def _normalize_map_layers(payload: dict[str, object]) -> list[dict[str, Any]]:
    layers = payload.get("layers")
    if isinstance(layers, list):
        return [layer for layer in layers if isinstance(layer, dict)]

    feature_collection = payload.get("feature_collection")
    if isinstance(feature_collection, dict):
        return [
            {
                "layer_id": payload.get("layer_id") or "map",
                "title": payload.get("title") or "Mapa",
                "feature_collection": feature_collection,
            }
        ]

    return []


def normalize_catalog_layers(payload: dict[str, object]) -> list[dict[str, Any]]:
    layers = payload.get("layers")
    if not isinstance(layers, list):
        return []
    return [layer for layer in layers if isinstance(layer, dict)]


def normalize_filter_options_payload(payload: dict[str, object]) -> dict[str, dict[str, list[str]]]:
    layers = payload.get("layers")
    if not isinstance(layers, list):
        return {}

    options_by_layer: dict[str, dict[str, list[str]]] = {}
    for layer in layers:
        if not isinstance(layer, dict) or not layer.get("layer_id"):
            continue
        raw_options = layer.get("options")
        if not isinstance(raw_options, dict):
            raw_options = {}
        options_by_layer[str(layer["layer_id"])] = {
            str(key): [str(item) for item in values if item not in (None, "")]
            for key, values in raw_options.items()
            if isinstance(values, list)
        }
    return options_by_layer


def merge_selected_filter_options(options: list[str], selected_values: list[str]) -> list[str]:
    merged = {
        str(value)
        for value in [*options, *selected_values]
        if str(value).strip()
    }
    return sorted(merged, key=lambda item: item.casefold())


def build_map_features_request(
    layer_ids: list[str],
    filters_by_layer: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, object]:
    filters_by_layer = filters_by_layer or {}
    return {
        "layers": [
            {
                "layer_id": layer_id,
                "filters": {
                    filter_key: values
                    for filter_key, values in filters_by_layer.get(layer_id, {}).items()
                    if values
                },
            }
            for layer_id in layer_ids
        ]
    }


def extract_layer_filter_options(
    layer_payload: dict[str, object],
    filter_fields: list[dict[str, Any]],
) -> dict[str, list[str]]:
    feature_collection = layer_payload.get("feature_collection")
    if not isinstance(feature_collection, dict):
        return {str(field.get("key")): [] for field in filter_fields}

    features = feature_collection.get("features")
    if not isinstance(features, list):
        return {str(field.get("key")): [] for field in filter_fields}

    values_by_filter: dict[str, set[str]] = {
        str(field.get("key")): set()
        for field in filter_fields
        if field.get("key")
    }
    property_key_by_filter = {
        str(field.get("key")): str(field.get("property_key") or field.get("key"))
        for field in filter_fields
        if field.get("key")
    }

    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue
        for filter_key, property_key in property_key_by_filter.items():
            value = properties.get(property_key)
            if value in (None, ""):
                value = properties.get(filter_key)
            if value in (None, ""):
                continue
            values_by_filter[filter_key].add(str(value))

    return {
        filter_key: sorted(values, key=lambda item: item.casefold())
        for filter_key, values in values_by_filter.items()
    }


def build_leaflet_map_html(
    payload: dict[str, object],
    *,
    height_px: int = DEFAULT_MAP_HEIGHT_PX,
    image_endpoint_url: str = "/api/v1/map/images",
) -> str:
    layers = _normalize_map_layers(payload)

    encoded_payload = _json_payload_to_base64({"layers": layers})
    primary_layer_id = escape(str(payload.get("primary_layer_id") or "vodomery"))
    layer_title = escape(str(payload.get("title") or "Mapa"))
    leaflet_css = _leaflet_css_for_inline_html()
    leaflet_javascript = _leaflet_javascript_for_inline_html()
    map_image_endpoint_url = str(image_endpoint_url or "/api/v1/map/images")
    leaflet_default_icon_options = json.dumps(
        {
            "iconRetinaUrl": _leaflet_image_data_uri("marker-icon-2x.png"),
            "iconUrl": _leaflet_image_data_uri("marker-icon.png"),
            "shadowUrl": _leaflet_image_data_uri("marker-shadow.png"),
        },
        separators=(",", ":"),
    )
    return f"""
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
{leaflet_css}
    html, body {{
      margin: 0;
      padding: 0;
      height: 100%;
      font-family: "Segoe UI", sans-serif;
      background: #f6f8fb;
    }}
    #map {{
      width: 100%;
      height: {int(height_px)}px;
      border: 1px solid #d8dee9;
      border-radius: 14px;
      overflow: hidden;
    }}
    .map-badge {{
      position: absolute;
      top: 12px;
      left: 50px;
      z-index: 500;
      background: rgba(255,255,255,.94);
      border: 1px solid rgba(20,30,50,.12);
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 13px;
      box-shadow: 0 8px 20px rgba(15,23,42,.12);
    }}
    .popup-table {{
      border-collapse: collapse;
      font-size: 13px;
      min-width: 240px;
    }}
    .popup-table th {{
      text-align: left;
      color: #526070;
      font-weight: 600;
      padding: 3px 10px 3px 0;
      white-space: nowrap;
    }}
    .popup-table td {{
      color: #17202a;
      padding: 3px 0;
    }}
    .map-location-control a {{
      display: flex;
      width: 40px;
      height: 40px;
      align-items: center;
      justify-content: center;
      color: #0f172a;
      font-size: 23px;
      line-height: 1;
      text-decoration: none;
      background: #ffffff;
    }}
    .map-location-control {{
      display: none;
    }}
    .map-location-control a.is-locating {{
      color: #2563eb;
      cursor: progress;
    }}
    .map-location-status {{
      position: absolute;
      left: 12px;
      bottom: 12px;
      z-index: 700;
      display: none;
      max-width: min(360px, calc(100vw - 24px));
      box-sizing: border-box;
      padding: 9px 12px;
      border: 1px solid rgba(15, 23, 42, 0.16);
      border-radius: 10px;
      color: #0f172a;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.16);
      font-size: 13px;
    }}
    .map-location-status.is-visible {{
      display: block;
    }}
    .map-location-status.is-error {{
      color: #991b1b;
      border-color: rgba(185, 28, 28, 0.24);
      background: rgba(254, 242, 242, 0.97);
    }}
    .map-popup-photo {{
      display: block;
      width: 100%;
      max-width: 320px;
      max-height: 240px;
      object-fit: contain;
      border: 1px solid #d8dee9;
      border-radius: 10px;
      background: #ffffff;
    }}
    .map-popup-photo-button {{
      display: block;
      width: 100%;
      margin-top: 10px;
      padding: 0;
      border: 0;
      background: transparent;
      cursor: zoom-in;
    }}
    .map-popup-photo-hint {{
      display: block;
      margin-top: 4px;
      color: #526070;
      font-size: 11px;
      text-align: center;
    }}
    .map-popup-photo-loading,
    .map-popup-photo-error {{
      margin-top: 10px;
      color: #526070;
      font-size: 12px;
    }}
    .map-popup-photo-error {{
      color: #b91c1c;
    }}
    .map-photo-lightbox {{
      position: fixed;
      inset: 0;
      z-index: 2000;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      box-sizing: border-box;
      background: rgba(15, 23, 42, 0.92);
    }}
    .map-photo-lightbox.is-open {{
      display: flex;
    }}
    .map-photo-lightbox-content {{
      display: flex;
      flex-direction: column;
      align-items: center;
      max-width: 100%;
      max-height: 100%;
    }}
    .map-photo-lightbox-image {{
      display: block;
      max-width: calc(100vw - 48px);
      max-height: calc(100vh - 100px);
      object-fit: contain;
      border-radius: 8px;
      background: #ffffff;
      box-shadow: 0 18px 50px rgba(0, 0, 0, 0.35);
    }}
    .map-photo-lightbox-actions {{
      display: flex;
      gap: 10px;
      margin-top: 14px;
    }}
    .map-photo-lightbox-action {{
      border: 1px solid rgba(255, 255, 255, 0.55);
      border-radius: 8px;
      padding: 8px 12px;
      color: #ffffff;
      background: rgba(255, 255, 255, 0.12);
      font: inherit;
      text-decoration: none;
      cursor: pointer;
    }}
    .map-photo-lightbox-action:hover {{
      background: rgba(255, 255, 255, 0.22);
    }}
    @media (max-width: 720px) {{
      #map {{
        border-radius: 10px;
      }}
      .map-badge {{
        top: 10px;
        left: 56px;
        max-width: calc(100vw - 126px);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .leaflet-control-layers {{
        max-width: calc(100vw - 80px);
        max-height: 44vh;
        overflow-y: auto;
      }}
      .leaflet-popup-content {{
        width: auto !important;
        max-width: calc(100vw - 76px);
        margin: 12px;
      }}
      .popup-table {{
        min-width: 0;
        width: 100%;
        font-size: 12px;
      }}
      .popup-table th {{
        max-width: 42vw;
        white-space: normal;
      }}
      .map-location-control a {{
        width: 44px;
        height: 44px;
      }}
      .map-location-control {{
        display: block;
      }}
      .map-photo-lightbox {{
        padding: 12px;
      }}
      .map-photo-lightbox-image {{
        max-width: calc(100vw - 24px);
        max-height: calc(100vh - 92px);
      }}
    }}
  </style>
</head>
<body>
  <div style="position: relative;">
    <div id="map"></div>
    <div class="map-badge">{layer_title}</div>
    <div id="map-location-status" class="map-location-status" role="status" aria-live="polite"></div>
  </div>
  <div id="map-photo-lightbox" class="map-photo-lightbox" aria-hidden="true">
    <div class="map-photo-lightbox-content" role="dialog" aria-modal="true" aria-label="Zvetsena fotografie">
      <img id="map-photo-lightbox-image" class="map-photo-lightbox-image" alt="Foto zarizeni">
      <div class="map-photo-lightbox-actions">
        <a
          id="map-photo-lightbox-open"
          class="map-photo-lightbox-action"
          href="#"
          target="_blank"
          rel="noopener noreferrer"
        >Otevrit v nove karte</a>
        <button id="map-photo-lightbox-close" class="map-photo-lightbox-action" type="button">Zavrit</button>
      </div>
    </div>
  </div>
  <script>
{leaflet_javascript}
  </script>
  <script>
    L.Icon.Default.mergeOptions({leaflet_default_icon_options});
    const encodedPayload = "{encoded_payload}";
    const primaryLayerId = "{primary_layer_id}";
    const mapImageEndpointUrl = {json.dumps(map_image_endpoint_url)};
    const photoLightbox = document.getElementById("map-photo-lightbox");
    const photoLightboxImage = document.getElementById("map-photo-lightbox-image");
    const photoLightboxOpen = document.getElementById("map-photo-lightbox-open");
    const photoLightboxClose = document.getElementById("map-photo-lightbox-close");
    const locationStatus = document.getElementById("map-location-status");
    const displayFieldsByLayer = {{
      vodomery: [
        ["identifikace", "Identifikace"],
        ["detail_source_found", "Detail MS"],
        ["evidence_budova", "Evidence budova"],
        ["evidence_patro", "Evidence patro"],
        ["evidence_mistnost", "Evidence mistnost"],
        ["mistnost_id", "Mistnost ID"],
        ["seriove_cislo", "Seriove cislo"],
        ["MBUS", "MBUS"],
        ["objekt", "Objekt"],
        ["patro", "Patro"],
        ["mistnost", "Mistnost"],
        ["umisteni", "Umisteni"],
        ["pozice", "Pozice"],
        ["vetev", "Vetev"],
        ["koncovy_odberatel", "Koncovy odberatel"],
        ["platnost_cejchu", "Platnost cejchu"],
        ["redukcni_ventil", "Redukcni ventil"],
        ["filtr", "Filtr"],
        ["poznamka_vodomery", "Poznamka"],
        ["foto", "Foto"]
      ],
      budovy: [
        ["fid", "FID"],
        ["budova", "Budova"],
        ["pocet_podlazi", "Pocet podlazi"]
      ],
      mistnosti: [
        ["mistnost_id", "Mistnost ID"],
        ["mistnost", "Mistnost"],
        ["budova", "Budova"],
        ["patro", "Patro"],
        ["najemce", "Najemce"],
        ["popis", "Popis"],
        ["plocha", "Plocha"]
      ]
    }};

    function decodePayload(value) {{
      const binary = atob(value);
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
      return JSON.parse(new TextDecoder("utf-8").decode(bytes));
    }}

    function escapeHtml(value) {{
      return String(value ?? "-").replace(/[&<>"']/g, (char) => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\\"": "&quot;",
        "'": "&#039;"
      }}[char]));
    }}

    function formatValue(value) {{
      if (typeof value === "boolean") {{
        return value ? "Ano" : "Ne";
      }}
      return value;
    }}

    function featureIdentifier(properties, layerConfig) {{
      const identifierKey = String(layerConfig.identifier_column || "identifikace");
      const value = properties[identifierKey] ?? properties.identifikace ?? properties.mistnost_id ?? properties.fid;
      return String(value ?? "").trim();
    }}

    function photoPlaceholderHtml(properties, layerId, layerConfig) {{
      const hasPhoto = properties.has_photo === true || String(properties.foto ?? "").trim();
      if (!hasPhoto) {{
        return "";
      }}
      const identifier = featureIdentifier(properties, layerConfig);
      if (!identifier) {{
        return "";
      }}
      return `<div class="map-popup-photo-target" data-map-photo="pending" data-layer-id="${{escapeHtml(layerId)}}" data-identifier="${{escapeHtml(identifier)}}"><div class="map-popup-photo-loading">Nacitam foto...</div></div>`;
    }}

    function mapImageUrl(layerId, identifier) {{
      let url = null;
      const baseCandidates = [document.baseURI, document.referrer, window.location.href].filter(Boolean);
      for (const baseUrl of baseCandidates) {{
        try {{
          url = new URL(mapImageEndpointUrl, baseUrl);
          break;
        }} catch (_) {{}}
      }}
      if (!url) {{
        try {{
          url = new URL(mapImageEndpointUrl);
        }} catch (_) {{
          throw new Error("Map image endpoint URL is invalid.");
        }}
      }}
      url.searchParams.set("layer_id", layerId);
      url.searchParams.set("identifier", identifier);
      return url.toString();
    }}

    function openPhotoLightbox(image) {{
      if (!image || !image.src) {{
        return;
      }}
      photoLightboxImage.src = image.src;
      photoLightboxImage.alt = image.alt || "Foto zarizeni";
      photoLightboxOpen.href = image.src;
      photoLightbox.classList.add("is-open");
      photoLightbox.setAttribute("aria-hidden", "false");
      photoLightboxClose.focus();
    }}

    function closePhotoLightbox() {{
      photoLightbox.classList.remove("is-open");
      photoLightbox.setAttribute("aria-hidden", "true");
      photoLightboxImage.removeAttribute("src");
      photoLightboxOpen.href = "#";
    }}

    document.addEventListener("click", (event) => {{
      const photoButton = event.target.closest(".map-popup-photo-button");
      if (photoButton) {{
        event.preventDefault();
        event.stopPropagation();
        openPhotoLightbox(photoButton.querySelector(".map-popup-photo"));
      }}
    }});
    photoLightboxClose.addEventListener("click", closePhotoLightbox);
    photoLightbox.addEventListener("click", (event) => {{
      if (event.target === photoLightbox) {{
        closePhotoLightbox();
      }}
    }});
    document.addEventListener("keydown", (event) => {{
      if (event.key === "Escape" && photoLightbox.classList.contains("is-open")) {{
        closePhotoLightbox();
      }}
    }});

    async function loadPopupPhotos(container) {{
      if (!container) {{
        return;
      }}
      const targets = container.querySelectorAll('[data-map-photo="pending"]');
      targets.forEach(async (target) => {{
        target.dataset.mapPhoto = "loading";
        try {{
          const response = await fetch(mapImageUrl(target.dataset.layerId, target.dataset.identifier), {{
            credentials: "include",
            headers: {{
              "Accept": "image/*"
            }}
          }});
          if (response.status === 404) {{
            target.remove();
            return;
          }}
          if (!response.ok) {{
            throw new Error(`HTTP ${{response.status}}`);
          }}
          const blob = await response.blob();
          const objectUrl = URL.createObjectURL(blob);
          target.dataset.mapPhoto = "loaded";
          target.innerHTML = `
            <button class="map-popup-photo-button" type="button" aria-label="Zvetsit fotografii">
              <img class="map-popup-photo" src="${{escapeHtml(objectUrl)}}" alt="Foto zarizeni" loading="lazy">
              <span class="map-popup-photo-hint">Kliknutim zvetsit</span>
            </button>
          `;
        }} catch (_) {{
          target.dataset.mapPhoto = "error";
          target.innerHTML = '<div class="map-popup-photo-error">Fotku se nepodarilo nacist.</div>';
        }}
      }});
    }}

    function cleanupPopupPhotos(container) {{
      if (!container) {{
        return;
      }}
      container.querySelectorAll(".map-popup-photo").forEach((image) => {{
        if (photoLightboxImage.src === image.src) {{
          closePhotoLightbox();
        }}
        if (image.src && image.src.startsWith("blob:")) {{
          URL.revokeObjectURL(image.src);
        }}
      }});
    }}

    function popupHtml(properties, layerId, layerConfig) {{
      const configuredPopupFields = Array.isArray(layerConfig.popup_columns)
        ? layerConfig.popup_columns.map((key) => [key, key])
        : [];
      const displayFields = configuredPopupFields.length
        ? configuredPopupFields
        : (displayFieldsByLayer[layerId] || Object.keys(properties).map((key) => [key, key]));
      const rows = displayFields
        .filter(([key]) => String(key).toLowerCase() !== "foto")
        .filter(([key]) => properties[key] !== null && properties[key] !== undefined && properties[key] !== "")
        .map(([key, label]) => `<tr><th>${{escapeHtml(label)}}</th><td>${{escapeHtml(formatValue(properties[key]))}}</td></tr>`)
        .join("");
      const image = photoPlaceholderHtml(properties, layerId, layerConfig);
      return `<div><table class="popup-table">${{rows || "<tr><td>Bez detailu</td></tr>"}}</table>${{image}}</div>`;
    }}

    function defaultLayerStyle(layerId) {{
      if (layerId === "budovy") {{
        return {{
          color: "#d97706",
          weight: 2,
          fillColor: "#fbbf24",
          fillOpacity: 0.16
        }};
      }}
      if (layerId === "mistnosti") {{
        return {{
          color: "#15803d",
          weight: 1.5,
          fillColor: "#86efac",
          fillOpacity: 0.20
        }};
      }}
      return {{
        color: "#0f5e9c",
        weight: 3,
        fillColor: "#38bdf8",
        fillOpacity: 0.22
      }};
    }}

    function layerStyle(layerId, layerConfig) {{
      const style = {{
        ...defaultLayerStyle(layerId),
        ...(layerConfig.style || {{}})
      }};
      delete style.conditionalStyle;
      return style;
    }}

    function conditionalRules(conditionalStyle) {{
      if (!conditionalStyle || typeof conditionalStyle !== "object") {{
        return [];
      }}
      if (Array.isArray(conditionalStyle.rules)) {{
        return conditionalStyle.rules.filter((rule) => rule && typeof rule === "object");
      }}
      return [conditionalStyle];
    }}

    function isEmptyValue(value) {{
      return value === null || value === undefined || String(value).trim() === "";
    }}

    function normalizeConditionValue(value) {{
      if (typeof value === "boolean" || typeof value === "number") {{
        return value;
      }}
      if (typeof value === "string") {{
        const trimmed = value.trim();
        const lowered = trimmed.toLowerCase();
        if (lowered === "true") {{
          return true;
        }}
        if (lowered === "false") {{
          return false;
        }}
        if (trimmed !== "" && !Number.isNaN(Number(trimmed))) {{
          return Number(trimmed);
        }}
        return trimmed;
      }}
      return value;
    }}

    function conditionMatches(properties, conditionalStyle) {{
      if (!conditionalStyle || typeof conditionalStyle !== "object") {{
        return false;
      }}
      const propertyName = String(conditionalStyle.property || "");
      if (!propertyName) {{
        return false;
      }}
      const actual = properties[propertyName];
      const operator = String(conditionalStyle.operator || "equals");
      if (operator === "is_empty") {{
        return isEmptyValue(actual);
      }}
      if (operator === "is_not_empty") {{
        return !isEmptyValue(actual);
      }}
      const normalizedActual = normalizeConditionValue(actual);
      const normalizedExpected = normalizeConditionValue(conditionalStyle.value);
      if (operator === "not_equals") {{
        return normalizedActual !== normalizedExpected;
      }}
      return normalizedActual === normalizedExpected;
    }}

    function featureStyle(feature, layerId, layerConfig) {{
      const baseStyle = layerStyle(layerId, layerConfig);
      const conditionalStyle = (layerConfig.style || {{}}).conditionalStyle;
      if (!conditionalStyle || typeof conditionalStyle !== "object") {{
        return baseStyle;
      }}
      const properties = (feature && feature.properties) || {{}};
      const matchedRule = conditionalRules(conditionalStyle).find((rule) => conditionMatches(properties, rule));
      const styleOverride = matchedRule
        ? (matchedRule.style || matchedRule.match)
        : conditionalStyle.fallback;
      if (!styleOverride || typeof styleOverride !== "object") {{
        return baseStyle;
      }}
      return {{
        ...baseStyle,
        ...styleOverride
      }};
    }}

    function markerStyle(feature, layerId, layerConfig) {{
      const style = featureStyle(feature, layerId, layerConfig);
      if (layerId === "budovy") {{
        return {{
          radius: style.radius || 5,
          weight: style.weight || 2,
          color: style.color || "#d97706",
          fillColor: style.fillColor || "#fbbf24",
          fillOpacity: style.markerFillOpacity || 0.75
        }};
      }}
      if (layerId === "mistnosti") {{
        return {{
          radius: style.radius || 5,
          weight: style.weight || 2,
          color: style.color || "#15803d",
          fillColor: style.fillColor || "#86efac",
          fillOpacity: style.markerFillOpacity || 0.78
        }};
      }}
      return {{
        radius: style.radius || 6,
        weight: style.weight || 2,
        color: style.color || "#0f5e9c",
        fillColor: style.fillColor || "#38bdf8",
        fillOpacity: style.markerFillOpacity || 0.9
      }};
    }}

    const mapPayload = decodePayload(encodedPayload);
    const map = L.map("map", {{ center: [50.77, 14.23], zoom: 17, maxZoom: 22 }});
    const osmBaseLayer = L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 22,
      maxNativeZoom: 19,
      attribution: "&copy; OpenStreetMap contributors"
    }}).addTo(map);
    const aerialBaseLayer = L.tileLayer("https://ags.cuzk.gov.cz/arcgis1/rest/services/ORTOFOTO_WM/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
      maxZoom: 22,
      maxNativeZoom: 20,
      attribution: "&copy; ČÚZK"
    }});

    const overlayLayers = {{}};
    const leafletLayers = [];
    let currentLocationMarker = null;
    let currentAccuracyCircle = null;
    let locationStatusTimer = null;
    const layers = Array.isArray(mapPayload.layers) ? mapPayload.layers : [];
    layers.forEach((layerConfig) => {{
      const layerId = String(layerConfig.layer_id || "layer");
      const title = String(layerConfig.title || layerId);
      const featureCollection = layerConfig.feature_collection || {{ type: "FeatureCollection", features: [] }};
      const leafletLayer = L.geoJSON(featureCollection, {{
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, markerStyle(feature, layerId, layerConfig)),
      style: (feature) => featureStyle(feature, layerId, layerConfig),
      onEachFeature: (feature, leafletLayer) => {{
        leafletLayer.bindPopup(popupHtml(feature.properties || {{}}, layerId, layerConfig));
        leafletLayer.on("popupopen", (event) => loadPopupPhotos(event.popup.getElement()));
        leafletLayer.on("popupclose", (event) => cleanupPopupPhotos(event.popup.getElement()));
      }}
      }});
      if (layerConfig.default_visible !== false) {{
        leafletLayer.addTo(map);
      }}
      overlayLayers[title] = leafletLayer;
      leafletLayers.push({{ id: layerId, layer: leafletLayer }});
    }});

    const compactMapControls = window.matchMedia("(max-width: 720px)").matches;
    L.control.layers(
      {{
        "Zakladni mapa": osmBaseLayer,
        "Letecka mapa (CUZK)": aerialBaseLayer
      }},
      overlayLayers,
      {{ collapsed: compactMapControls, position: "topright" }}
    ).addTo(map);

    function showLocationStatus(message, isError = false) {{
      if (locationStatusTimer) {{
        window.clearTimeout(locationStatusTimer);
      }}
      locationStatus.textContent = message;
      locationStatus.classList.toggle("is-error", isError);
      locationStatus.classList.add("is-visible");
      locationStatusTimer = window.setTimeout(() => {{
        locationStatus.classList.remove("is-visible");
      }}, isError ? 8000 : 5000);
    }}

    const locationControl = L.control({{ position: "topleft" }});
    locationControl.onAdd = () => {{
      const container = L.DomUtil.create("div", "leaflet-bar map-location-control");
      const button = L.DomUtil.create("a", "", container);
      button.href = "#";
      button.title = "Zobrazit moji polohu";
      button.setAttribute("role", "button");
      button.setAttribute("aria-label", "Zobrazit moji polohu");
      button.innerHTML = "&#9678;";
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      L.DomEvent.on(button, "click", (event) => {{
        L.DomEvent.preventDefault(event);
        if (!window.isSecureContext) {{
          showLocationStatus("Poloha telefonu je dostupna pouze pri otevreni dashboardu pres HTTPS.", true);
          return;
        }}
        if (!navigator.geolocation) {{
          showLocationStatus("Tento prohlizec nepodporuje zjisteni polohy.", true);
          return;
        }}
        button.classList.add("is-locating");
        showLocationStatus("Zjistuji polohu telefonu...");
        map.locate({{
          setView: false,
          watch: false,
          enableHighAccuracy: true,
          timeout: 12000,
          maximumAge: 15000
        }});
      }});
      map.on("locationfound locationerror", () => button.classList.remove("is-locating"));
      return container;
    }};
    locationControl.addTo(map);

    map.on("locationfound", (event) => {{
      if (currentLocationMarker) {{
        map.removeLayer(currentLocationMarker);
      }}
      if (currentAccuracyCircle) {{
        map.removeLayer(currentAccuracyCircle);
      }}
      currentLocationMarker = L.circleMarker(event.latlng, {{
        radius: 9,
        color: "#ffffff",
        weight: 3,
        fillColor: "#2563eb",
        fillOpacity: 1
      }}).addTo(map);
      currentAccuracyCircle = L.circle(event.latlng, {{
        radius: event.accuracy,
        color: "#2563eb",
        weight: 1.5,
        fillColor: "#60a5fa",
        fillOpacity: 0.14
      }}).addTo(map);
      currentLocationMarker.bindPopup(
        `<strong>Moje poloha</strong><br>Presnost priblizne ${{Math.round(event.accuracy)}} m`
      );
      map.setView(event.latlng, Math.max(map.getZoom(), 19));
      currentLocationMarker.openPopup();
      showLocationStatus(`Poloha zobrazena s presnosti priblizne ${{Math.round(event.accuracy)}} m.`);
    }});

    map.on("locationerror", (event) => {{
      const message = event.code === 1
        ? "Pristup k poloze nebyl povolen."
        : "Polohu telefonu se nepodarilo zjistit.";
      showLocationStatus(message, true);
    }});

    try {{
      const primaryLayer = leafletLayers.find((item) => item.id === primaryLayerId)?.layer || leafletLayers[0]?.layer;
      const bounds = primaryLayer ? primaryLayer.getBounds() : null;
      if (bounds && bounds.isValid()) {{
        map.fitBounds(bounds, {{ padding: [24, 24], maxZoom: 20 }});
      }}
    }} catch (_) {{}}

    setTimeout(() => map.invalidateSize(), 200);
  </script>
</body>
</html>
"""
