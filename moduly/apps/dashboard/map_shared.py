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
    fill_parent_height: bool = False,
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
    body_overflow = "hidden" if fill_parent_height else "auto"
    if fill_parent_height:
        map_height_rules = "height: 100vh;\n      height: 100dvh;"
    else:
        map_height_rules = f"height: {int(height_px)}px;"
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
      overflow: {body_overflow};
      font-family: "Segoe UI", sans-serif;
      background: #f6f8fb;
    }}
    #map {{
      width: 100%;
      {map_height_rules}
      box-sizing: border-box;
      border: 1px solid #d8dee9;
      border-radius: 14px;
      background: #ffffff;
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
    .map-feature-label {{
      border: 0;
      padding: 0;
      color: inherit;
      background: transparent;
      box-shadow: none;
      font-size: 12px;
      font-weight: 700;
      line-height: 1.15;
      text-align: center;
      white-space: nowrap;
      pointer-events: none;
    }}
    .map-feature-label::before {{
      display: none;
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
    .leaflet-control-layers-expanded {{
      max-height: min(520px, calc(100vh - 90px));
      overflow-y: auto;
    }}
    .map-filter-control,
    .map-label-control,
    .map-legend-control {{
      width: var(--map-filter-panel-width, auto);
      min-width: 0;
      max-width: calc(100vw - 92px);
      box-sizing: border-box;
      color: #0f172a;
      background: rgba(255, 255, 255, 0.97);
      border: 1px solid rgba(15, 23, 42, 0.16);
      border-radius: 6px;
      box-shadow: 0 8px 22px rgba(15, 23, 42, 0.16);
      overflow: hidden;
      font-size: 12px;
    }}
    .map-filter-toggle,
    .map-label-toggle,
    .map-legend-toggle {{
      display: flex;
      width: 100%;
      align-items: center;
      justify-content: space-between;
      border: 0;
      padding: 8px 10px;
      color: #0f172a;
      background: #ffffff;
      font: inherit;
      font-weight: 700;
      text-align: left;
      cursor: pointer;
    }}
    .map-filter-panel,
    .map-label-panel,
    .map-legend-panel {{
      display: none;
      max-height: min(520px, calc(100vh - 150px));
      overflow-y: auto;
      padding: 8px 10px 10px;
      border-top: 1px solid rgba(15, 23, 42, 0.12);
    }}
    .map-filter-control.is-open .map-filter-panel,
    .map-label-control.is-open .map-label-panel,
    .map-legend-control.is-open .map-legend-panel {{
      display: block;
    }}
    .map-filter-layer {{
      padding: 8px 0;
      border-top: 1px solid rgba(15, 23, 42, 0.10);
    }}
    .map-filter-layer:first-child {{
      border-top: 0;
      padding-top: 0;
    }}
    .map-filter-layer-title {{
      margin-bottom: 6px;
      font-weight: 700;
      cursor: pointer;
    }}
    .map-filter-field {{
      display: block;
      margin-top: 8px;
    }}
    .map-filter-label {{
      display: block;
      margin-bottom: 4px;
      color: #475569;
      font-weight: 600;
    }}
    .map-filter-select {{
      width: 100%;
      min-height: 58px;
      box-sizing: border-box;
      border: 1px solid rgba(15, 23, 42, 0.18);
      border-radius: 6px;
      padding: 4px;
      color: #0f172a;
      background: #ffffff;
      font: inherit;
    }}
    .map-filter-reset {{
      width: 100%;
      margin-top: 8px;
      border: 1px solid rgba(15, 23, 42, 0.18);
      border-radius: 6px;
      padding: 6px 8px;
      color: #0f172a;
      background: #f8fafc;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }}
    .map-label-field {{
      display: flex;
      gap: 8px;
      align-items: flex-start;
      padding: 6px 0;
      color: #0f172a;
      font-weight: 600;
      line-height: 1.25;
      cursor: pointer;
    }}
    .map-label-checkbox {{
      margin-top: 1px;
      flex: 0 0 auto;
    }}
    .map-legend-layer {{
      padding: 8px 0;
      border-top: 1px solid rgba(15, 23, 42, 0.10);
    }}
    .map-legend-layer:first-child {{
      border-top: 0;
      padding-top: 0;
    }}
    .map-legend-layer-toggle {{
      display: flex;
      gap: 8px;
      align-items: flex-start;
      color: #0f172a;
      font-weight: 700;
      line-height: 1.25;
      cursor: pointer;
    }}
    .map-legend-checkbox {{
      margin-top: 1px;
      flex: 0 0 auto;
    }}
    .map-legend-items {{
      display: grid;
      gap: 6px;
      margin-top: 8px;
    }}
    .map-legend-item {{
      display: grid;
      grid-template-columns: 22px minmax(0, 1fr);
      gap: 8px;
      align-items: center;
      color: #334155;
      line-height: 1.25;
    }}
    .map-legend-swatch {{
      display: block;
      width: 18px;
      height: 12px;
      box-sizing: border-box;
      border: 3px solid #0f172a;
      border-radius: 3px;
      background: #ffffff;
    }}
    .map-filter-empty,
    .map-label-empty,
    .map-legend-empty {{
      color: #64748b;
      line-height: 1.35;
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
      .map-filter-control {{
        max-width: calc(100vw - 80px);
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

    function featureMapLabel(feature, layerConfig) {{
      const properties = (feature && feature.properties) || {{}};
      return layerLabelFields(layerConfig)
        .map((key) => properties[key])
        .filter((value) => value !== null && value !== undefined && value !== "")
        .map((value) => escapeHtml(formatValue(value)))
        .join("<br>");
    }}

    function layerLabelFields(layerConfig) {{
      return Array.isArray(layerConfig.map_label_columns)
        ? layerConfig.map_label_columns.map((key) => String(key || "").trim()).filter((key) => key)
        : [];
    }}

    const labelVisibilityByLayer = {{}};

    function layerHasMapLabels(layerConfig) {{
      return layerLabelFields(layerConfig).length > 0;
    }}

    function layerLabelsVisible(layerId) {{
      return labelVisibilityByLayer[String(layerId)] !== false;
    }}

    function setLayerLabelsVisible(layerId, isVisible) {{
      const normalizedLayerId = String(layerId);
      if (isVisible) {{
        delete labelVisibilityByLayer[normalizedLayerId];
      }} else {{
        labelVisibilityByLayer[normalizedLayerId] = false;
      }}
      const item = leafletLayers.find((entry) => entry.id === normalizedLayerId);
      refreshLayerData(item);
    }}

    function featureLabelColor(layerId, layerConfig) {{
      const style = layerStyle(layerId, layerConfig);
      const color = String(style.color || style.fillColor || "").trim();
      return color || "#0f172a";
    }}

    function featureLabelTooltipOptions(layerConfig) {{
      const isDeviceLayer = String(layerConfig.layer_kind || "").toLowerCase() === "device";
      return {{
        permanent: true,
        direction: isDeviceLayer ? "top" : "center",
        offset: isDeviceLayer ? [0, -10] : [0, 0],
        className: "map-feature-label",
        opacity: 1
      }};
    }}

    function applyFeatureLabelStyle(tooltip, layerId, layerConfig) {{
      const element = tooltip && typeof tooltip.getElement === "function"
        ? tooltip.getElement()
        : null;
      if (!element) {{
        return;
      }}
      element.style.color = featureLabelColor(layerId, layerConfig);
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

    function conditionalRuleDisplayName(rule, ruleIndex) {{
      const configuredName = String(
        (rule && (rule.name || rule.title || rule.label)) || ""
      ).trim();
      return configuredName || `Stylove pravidlo ${{ruleIndex + 1}}`;
    }}

    function conditionalRuleStyleOverride(rule) {{
      const styleOverride = rule && typeof rule === "object"
        ? (rule.style || rule.match)
        : null;
      return styleOverride && typeof styleOverride === "object" ? styleOverride : null;
    }}

    function layerLegendEntries(layerId, layerConfig) {{
      const conditionalStyle = (layerConfig.style || {{}}).conditionalStyle;
      if (!conditionalStyle || typeof conditionalStyle !== "object") {{
        return [];
      }}
      return conditionalRules(conditionalStyle)
        .map((rule, ruleIndex) => {{
          const styleOverride = conditionalRuleStyleOverride(rule);
          if (!styleOverride) {{
            return null;
          }}
          return {{
            label: conditionalRuleDisplayName(rule, ruleIndex),
            style: {{
              ...layerStyle(layerId, layerConfig),
              ...styleOverride
            }}
          }};
        }})
        .filter((entry) => entry && entry.label);
    }}

    const legendVisibilityByLayer = {{}};

    function layerHasLegend(layerId, layerConfig) {{
      return layerLegendEntries(layerId, layerConfig).length > 0;
    }}

    function layerLegendVisible(layerId) {{
      return legendVisibilityByLayer[String(layerId)] !== false;
    }}

    function setLayerLegendVisible(layerId, isVisible) {{
      const normalizedLayerId = String(layerId);
      if (isVisible) {{
        delete legendVisibilityByLayer[normalizedLayerId];
      }} else {{
        legendVisibilityByLayer[normalizedLayerId] = false;
      }}
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

    function conditionMatches(properties, condition) {{
      if (!condition || typeof condition !== "object") {{
        return false;
      }}
      if (Array.isArray(condition.all)) {{
        const conditions = condition.all.filter((item) => item && typeof item === "object");
        return conditions.length > 0 && conditions.every((item) => conditionMatches(properties, item));
      }}
      if (Array.isArray(condition.any)) {{
        const conditions = condition.any.filter((item) => item && typeof item === "object");
        return conditions.length > 0 && conditions.some((item) => conditionMatches(properties, item));
      }}
      const propertyName = String(condition.property || "");
      if (!propertyName) {{
        return false;
      }}
      const actual = properties[propertyName];
      const operator = String(condition.operator || "equals");
      if (operator === "is_empty") {{
        return isEmptyValue(actual);
      }}
      if (operator === "is_not_empty") {{
        return !isEmptyValue(actual);
      }}
      const normalizedActual = normalizeConditionValue(actual);
      const normalizedExpected = normalizeConditionValue(condition.value);
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

    function layerFeatureCollection(layerConfig) {{
      const featureCollection = layerConfig.feature_collection || {{ type: "FeatureCollection", features: [] }};
      const features = Array.isArray(featureCollection.features) ? featureCollection.features : [];
      return {{
        ...featureCollection,
        features
      }};
    }}

    function layerFilterFields(layerConfig) {{
      if (Array.isArray(layerConfig.filter_fields) && layerConfig.filter_fields.length) {{
        return layerConfig.filter_fields
          .filter((field) => field && typeof field === "object" && field.key)
          .map((field) => ({{
            key: String(field.key),
            property_key: String(field.property_key || field.key),
            label: String(field.label || field.property_key || field.key)
          }}));
      }}
      const filterColumns = Array.isArray(layerConfig.filter_columns) ? layerConfig.filter_columns : [];
      return filterColumns
        .filter((column) => String(column).trim())
        .map((column) => ({{
          key: String(column),
          property_key: String(column),
          label: String(column)
        }}));
    }}

    function uniqueSortedValues(values) {{
      return Array.from(
        new Set(
          values
            .map((value) => String(value).trim())
            .filter((value) => value)
        )
      ).sort((left, right) => left.localeCompare(right, "cs", {{ sensitivity: "base" }}));
    }}

    function featureFilterValue(feature, field) {{
      const properties = (feature && feature.properties) || {{}};
      const propertyKey = String(field.property_key || field.key || "");
      const filterKey = String(field.key || propertyKey);
      let value = properties[propertyKey];
      if (isEmptyValue(value)) {{
        value = properties[filterKey];
      }}
      return value;
    }}

    function featureFilterOptions(layerConfig, field) {{
      const filterOptions = layerConfig.filter_options && typeof layerConfig.filter_options === "object"
        ? layerConfig.filter_options
        : {{}};
      const configuredOptions = Array.isArray(filterOptions[field.key]) ? filterOptions[field.key] : [];
      if (configuredOptions.length) {{
        return uniqueSortedValues(configuredOptions);
      }}
      const featureCollection = layerFeatureCollection(layerConfig);
      return uniqueSortedValues(
        featureCollection.features
          .map((feature) => featureFilterValue(feature, field))
          .filter((value) => !isEmptyValue(value))
      );
    }}

    function normalizeFilterCompareValue(value) {{
      if (typeof value === "boolean") {{
        return value ? "true" : "false";
      }}
      if (typeof value === "string") {{
        const trimmed = value.trim();
        const lowered = trimmed.toLowerCase();
        if (lowered === "true" || lowered === "false") {{
          return lowered;
        }}
        return trimmed;
      }}
      if (value === null || value === undefined) {{
        return "";
      }}
      return String(value).trim();
    }}

    const activeLayerFilters = {{}};

    function selectedLayerFilterValues(layerId, filterKey) {{
      const layerFilters = activeLayerFilters[layerId] || {{}};
      const values = Array.isArray(layerFilters[filterKey]) ? layerFilters[filterKey] : [];
      return values.map((value) => String(value));
    }}

    function setLayerFilterValues(layerId, filterKey, values) {{
      if (!activeLayerFilters[layerId]) {{
        activeLayerFilters[layerId] = {{}};
      }}
      const cleanedValues = uniqueSortedValues(values.map((value) => normalizeFilterCompareValue(value)));
      if (cleanedValues.length) {{
        activeLayerFilters[layerId][filterKey] = cleanedValues;
      }} else {{
        delete activeLayerFilters[layerId][filterKey];
      }}
      if (!Object.keys(activeLayerFilters[layerId]).length) {{
        delete activeLayerFilters[layerId];
      }}
    }}

    function featurePassesLayerFilters(feature, layerConfig) {{
      const layerId = String(layerConfig.layer_id || "layer");
      return layerFilterFields(layerConfig).every((field) => {{
        const selectedValues = selectedLayerFilterValues(layerId, field.key);
        if (!selectedValues.length) {{
          return true;
        }}
        const value = featureFilterValue(feature, field);
        if (isEmptyValue(value)) {{
          return false;
        }}
        const normalizedValue = normalizeFilterCompareValue(value);
        return selectedValues.some((selectedValue) => normalizeFilterCompareValue(selectedValue) === normalizedValue);
      }});
    }}

    function filteredFeatureCollection(layerConfig) {{
      const featureCollection = layerFeatureCollection(layerConfig);
      return {{
        ...featureCollection,
        features: featureCollection.features.filter((feature) => featurePassesLayerFilters(feature, layerConfig))
      }};
    }}

    function geoJsonLayerOptions(layerId, layerConfig) {{
      return {{
        pointToLayer: (feature, latlng) => L.circleMarker(latlng, markerStyle(feature, layerId, layerConfig)),
        style: (feature) => featureStyle(feature, layerId, layerConfig),
        onEachFeature: (feature, leafletLayer) => {{
          const labelHtml = featureMapLabel(feature, layerConfig);
          if (labelHtml && layerLabelsVisible(layerId)) {{
            leafletLayer.bindTooltip(labelHtml, featureLabelTooltipOptions(layerConfig));
            leafletLayer.on("tooltipopen", (event) => applyFeatureLabelStyle(event.tooltip, layerId, layerConfig));
          }}
          leafletLayer.bindPopup(popupHtml(feature.properties || {{}}, layerId, layerConfig));
          leafletLayer.on("popupopen", (event) => loadPopupPhotos(event.popup.getElement()));
          leafletLayer.on("popupclose", (event) => cleanupPopupPhotos(event.popup.getElement()));
        }}
      }};
    }}

    function refreshLayerData(item) {{
      if (!item || (!item.loaded && !map.hasLayer(item.layer))) {{
        return;
      }}
      item.layer.clearLayers();
      item.layer.addData(filteredFeatureCollection(item.config));
      item.loaded = true;
    }}

    function applyLayerFilters() {{
      leafletLayers.forEach((item) => refreshLayerData(item));
    }}

    function ensureLayerDataLoaded(item) {{
      if (!item || item.loaded) {{
        return;
      }}
      refreshLayerData(item);
    }}

    function createMapFilterControl() {{
      const filterableLayerEntries = () => leafletLayers
        .map((item) => {{
          const layerConfig = item.config;
          const fields = layerFilterFields(layerConfig)
            .map((field) => ({{
              ...field,
              options: featureFilterOptions(layerConfig, field)
            }}))
            .filter((field) => field.options.length);
          return {{ ...item, layerConfig, fields }};
        }})
        .filter((item) => item.fields.length);

      if (!filterableLayerEntries().length) {{
        return null;
      }}

      const control = L.control({{ position: "topright" }});
      control.onAdd = () => {{
        const container = L.DomUtil.create("div", "leaflet-control map-filter-control");
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "map-filter-toggle";
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = "Filtry";

        const panel = document.createElement("div");
        panel.className = "map-filter-panel";

        const renderPanel = () => {{
          while (panel.firstChild) {{
            panel.removeChild(panel.firstChild);
          }}

          const visibleEntries = filterableLayerEntries().filter((item) => map.hasLayer(item.layer));
          if (!visibleEntries.length) {{
            const emptyElement = document.createElement("div");
            emptyElement.className = "map-filter-empty";
            emptyElement.textContent = "Zapnete vrstvu s filtrem pres ovladani vrstev.";
            panel.appendChild(emptyElement);
            return;
          }}

          visibleEntries.forEach((item) => {{
          const layerId = String(item.layerConfig.layer_id || "layer");
          const layerTitle = String(item.layerConfig.title || layerId);
          const layerElement = document.createElement("details");
          layerElement.className = "map-filter-layer";
          layerElement.open = visibleEntries.length === 1;

          const titleElement = document.createElement("summary");
          titleElement.className = "map-filter-layer-title";
          titleElement.textContent = layerTitle;
          layerElement.appendChild(titleElement);

          item.fields.forEach((field) => {{
            const fieldElement = document.createElement("label");
            fieldElement.className = "map-filter-field";

            const labelElement = document.createElement("span");
            labelElement.className = "map-filter-label";
            labelElement.textContent = field.label;
            fieldElement.appendChild(labelElement);

            const selectElement = document.createElement("select");
            selectElement.className = "map-filter-select";
            selectElement.multiple = true;
            selectElement.size = Math.min(6, Math.max(2, field.options.length));

            field.options.forEach((optionValue) => {{
              const optionElement = document.createElement("option");
              optionElement.value = normalizeFilterCompareValue(optionValue);
              optionElement.textContent = optionValue;
              selectElement.appendChild(optionElement);
            }});

            selectElement.addEventListener("change", () => {{
              setLayerFilterValues(
                layerId,
                field.key,
                Array.from(selectElement.selectedOptions).map((option) => option.value)
              );
              applyLayerFilters();
            }});

            const selectedValues = new Set(selectedLayerFilterValues(layerId, field.key));
            Array.from(selectElement.options).forEach((optionElement) => {{
              optionElement.selected = selectedValues.has(optionElement.value);
            }});

            fieldElement.appendChild(selectElement);
            layerElement.appendChild(fieldElement);
          }});

          panel.appendChild(layerElement);
          }});

          const resetButton = document.createElement("button");
          resetButton.type = "button";
          resetButton.className = "map-filter-reset";
          resetButton.textContent = "Vynulovat filtry";
          resetButton.addEventListener("click", () => {{
            Object.keys(activeLayerFilters).forEach((layerId) => delete activeLayerFilters[layerId]);
            renderPanel();
            applyLayerFilters();
          }});
          panel.appendChild(resetButton);
        }};

        toggle.addEventListener("click", () => {{
          const isOpen = container.classList.toggle("is-open");
          toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }});

        container.appendChild(toggle);
        container.appendChild(panel);
        L.DomEvent.disableClickPropagation(container);
        L.DomEvent.disableScrollPropagation(container);
        renderPanel();
        map.on("overlayadd overlayremove", renderPanel);
        return container;
      }};
      return control;
    }}

    function createMapLabelControl() {{
      const labelLayerEntries = () => leafletLayers
        .map((item) => ({{ ...item, layerConfig: item.config }}))
        .filter((item) => layerHasMapLabels(item.layerConfig));

      if (!labelLayerEntries().length) {{
        return null;
      }}

      const control = L.control({{ position: "topright" }});
      control.onAdd = () => {{
        const container = L.DomUtil.create("div", "leaflet-control map-label-control");
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "map-label-toggle";
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = "Popisky";

        const panel = document.createElement("div");
        panel.className = "map-label-panel";

        const renderPanel = () => {{
          while (panel.firstChild) {{
            panel.removeChild(panel.firstChild);
          }}

          const visibleEntries = labelLayerEntries().filter((item) => map.hasLayer(item.layer));
          if (!visibleEntries.length) {{
            const emptyElement = document.createElement("div");
            emptyElement.className = "map-label-empty";
            emptyElement.textContent = "Zapnete vrstvu s popisky pres ovladani vrstev.";
            panel.appendChild(emptyElement);
            return;
          }}

          visibleEntries.forEach((item) => {{
            const layerId = String(item.layerConfig.layer_id || item.id || "layer");
            const layerTitle = String(item.layerConfig.title || layerId);
            const fieldElement = document.createElement("label");
            fieldElement.className = "map-label-field";

            const checkboxElement = document.createElement("input");
            checkboxElement.type = "checkbox";
            checkboxElement.className = "map-label-checkbox";
            checkboxElement.checked = layerLabelsVisible(layerId);
            checkboxElement.addEventListener("change", () => {{
              setLayerLabelsVisible(layerId, checkboxElement.checked);
            }});

            const labelElement = document.createElement("span");
            labelElement.textContent = layerTitle;

            fieldElement.appendChild(checkboxElement);
            fieldElement.appendChild(labelElement);
            panel.appendChild(fieldElement);
          }});
        }};

        toggle.addEventListener("click", () => {{
          const isOpen = container.classList.toggle("is-open");
          toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
          if (isOpen) {{
            renderPanel();
          }}
        }});

        container.appendChild(toggle);
        container.appendChild(panel);
        L.DomEvent.disableClickPropagation(container);
        L.DomEvent.disableScrollPropagation(container);
        renderPanel();
        map.on("overlayadd overlayremove", renderPanel);
        return container;
      }};
      return control;
    }}

    function createMapLegendControl() {{
      const legendLayerEntries = () => leafletLayers
        .map((item) => ({{
          ...item,
          layerConfig: item.config,
          legendEntries: layerLegendEntries(item.id, item.config)
        }}))
        .filter((item) => item.legendEntries.length);

      if (!legendLayerEntries().length) {{
        return null;
      }}

      const control = L.control({{ position: "topright" }});
      control.onAdd = () => {{
        const container = L.DomUtil.create("div", "leaflet-control map-legend-control");
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "map-legend-toggle";
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = "Legenda";

        const panel = document.createElement("div");
        panel.className = "map-legend-panel";

        const renderPanel = () => {{
          while (panel.firstChild) {{
            panel.removeChild(panel.firstChild);
          }}

          const visibleEntries = legendLayerEntries().filter((item) => map.hasLayer(item.layer));
          if (!visibleEntries.length) {{
            const emptyElement = document.createElement("div");
            emptyElement.className = "map-legend-empty";
            emptyElement.textContent = "Zapnete vrstvu s legendou pres ovladani vrstev.";
            panel.appendChild(emptyElement);
            return;
          }}

          visibleEntries.forEach((item) => {{
            const layerId = String(item.layerConfig.layer_id || item.id || "layer");
            const layerTitle = String(item.layerConfig.title || layerId);
            const layerElement = document.createElement("div");
            layerElement.className = "map-legend-layer";

            const fieldElement = document.createElement("label");
            fieldElement.className = "map-legend-layer-toggle";

            const checkboxElement = document.createElement("input");
            checkboxElement.type = "checkbox";
            checkboxElement.className = "map-legend-checkbox";
            checkboxElement.checked = layerLegendVisible(layerId);
            checkboxElement.addEventListener("change", () => {{
              setLayerLegendVisible(layerId, checkboxElement.checked);
              renderPanel();
            }});

            const labelElement = document.createElement("span");
            labelElement.textContent = layerTitle;

            fieldElement.appendChild(checkboxElement);
            fieldElement.appendChild(labelElement);
            layerElement.appendChild(fieldElement);

            if (layerLegendVisible(layerId)) {{
              const itemsElement = document.createElement("div");
              itemsElement.className = "map-legend-items";
              item.legendEntries.forEach((legendEntry) => {{
                const itemElement = document.createElement("div");
                itemElement.className = "map-legend-item";

                const swatchElement = document.createElement("span");
                swatchElement.className = "map-legend-swatch";
                swatchElement.style.borderColor = String(legendEntry.style.color || legendEntry.style.fillColor || "#0f172a");
                swatchElement.style.background = String(legendEntry.style.fillColor || legendEntry.style.color || "#ffffff");
                swatchElement.style.opacity = String(legendEntry.style.fillOpacity ?? 1);

                const textElement = document.createElement("span");
                textElement.textContent = legendEntry.label;

                itemElement.appendChild(swatchElement);
                itemElement.appendChild(textElement);
                itemsElement.appendChild(itemElement);
              }});
              layerElement.appendChild(itemsElement);
            }}

            panel.appendChild(layerElement);
          }});
        }};

        toggle.addEventListener("click", () => {{
          const isOpen = container.classList.toggle("is-open");
          toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
          if (isOpen) {{
            renderPanel();
          }}
        }});

        container.appendChild(toggle);
        container.appendChild(panel);
        L.DomEvent.disableClickPropagation(container);
        L.DomEvent.disableScrollPropagation(container);
        renderPanel();
        map.on("overlayadd overlayremove", renderPanel);
        return container;
      }};
      return control;
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

    const emptyBaseLayer = L.layerGroup();

    const overlayLayers = {{}};
    const leafletLayers = [];
    let currentLocationMarker = null;
    let currentAccuracyCircle = null;
    let locationStatusTimer = null;
    const layers = Array.isArray(mapPayload.layers) ? mapPayload.layers : [];
    layers.forEach((layerConfig) => {{
      const layerId = String(layerConfig.layer_id || "layer");
      const title = String(layerConfig.title || layerId);
      const isInitiallyVisible = layerConfig.default_visible !== false;
      const leafletLayer = L.geoJSON(
        isInitiallyVisible ? filteredFeatureCollection(layerConfig) : {{ type: "FeatureCollection", features: [] }},
        geoJsonLayerOptions(layerId, layerConfig)
      );
      if (isInitiallyVisible) {{
        leafletLayer.addTo(map);
      }}
      overlayLayers[title] = leafletLayer;
      leafletLayers.push({{
        id: layerId,
        layer: leafletLayer,
        config: layerConfig,
        loaded: isInitiallyVisible
      }});
    }});

    const compactMapControls = window.matchMedia("(max-width: 720px)").matches;
    const layersControl = L.control.layers(
      {{
        "Zakladni mapa": osmBaseLayer,
        "Letecka mapa (CUZK)": aerialBaseLayer,
        "Bez mapy": emptyBaseLayer
      }},
      overlayLayers,
      {{ collapsed: compactMapControls, position: "topright" }}
    ).addTo(map);
    function syncFilterControlWidthToLayerControl(...controlInstances) {{
      const layersContainer = layersControl.getContainer ? layersControl.getContainer() : null;
      if (!layersContainer) {{
        return;
      }}
      if (!layersContainer.classList.contains("leaflet-control-layers-expanded")) {{
        return;
      }}
      const measuredWidth = Math.ceil(layersContainer.getBoundingClientRect().width);
      if (measuredWidth > 0) {{
        controlInstances
          .filter((controlInstance) => controlInstance && typeof controlInstance.getContainer === "function")
          .map((controlInstance) => controlInstance.getContainer())
          .filter((controlContainer) => controlContainer)
          .forEach((controlContainer) => {{
            controlContainer.style.setProperty("--map-filter-panel-width", `${{measuredWidth}}px`);
          }});
      }}
    }}
    map.on("overlayadd", (event) => {{
      const item = leafletLayers.find((entry) => entry.layer === event.layer);
      ensureLayerDataLoaded(item);
    }});
    const filterControl = createMapFilterControl();
    if (filterControl) {{
      filterControl.addTo(map);
    }}
    const labelControl = createMapLabelControl();
    if (labelControl) {{
      labelControl.addTo(map);
    }}
    const legendControl = createMapLegendControl();
    if (legendControl) {{
      legendControl.addTo(map);
    }}
    if (filterControl || labelControl || legendControl) {{
      const syncFilterWidth = () => syncFilterControlWidthToLayerControl(filterControl, labelControl, legendControl);
      window.requestAnimationFrame(syncFilterWidth);
      window.addEventListener("resize", syncFilterWidth);
      const layersContainer = layersControl.getContainer ? layersControl.getContainer() : null;
      if (layersContainer) {{
        ["mouseover", "focusin", "click"].forEach((eventName) => {{
          layersContainer.addEventListener(eventName, () => window.setTimeout(syncFilterWidth, 0));
        }});
      }}
    }}

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
      const primaryLayer = leafletLayers.find((item) => item.id === primaryLayerId && item.loaded)?.layer
        || leafletLayers.find((item) => item.loaded)?.layer
        || leafletLayers[0]?.layer;
      const bounds = primaryLayer ? primaryLayer.getBounds() : null;
      if (bounds && bounds.isValid()) {{
        map.fitBounds(bounds, {{ padding: [24, 24], maxZoom: 20 }});
      }}
    }} catch (_) {{}}

    function invalidateMapSize() {{
      try {{
        map.invalidateSize({{ pan: false }});
      }} catch (_) {{}}
    }}

    if (window.ResizeObserver) {{
      const resizeObserver = new ResizeObserver(() => invalidateMapSize());
      resizeObserver.observe(document.body);
      resizeObserver.observe(document.getElementById("map"));
    }}
    window.addEventListener("resize", invalidateMapSize);
    [0, 100, 300, 800].forEach((delay) => setTimeout(invalidateMapSize, delay));
  </script>
</body>
</html>
"""
