from __future__ import annotations

import base64
import json
from html import escape
from typing import Any

import streamlit as st

from moduly.apps.dashboard.api_client import get_map_features, get_map_filter_options, get_map_layer_catalog


DEFAULT_MAP_HEIGHT_PX = 720


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


def _json_string_for_script(value: str) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _map_image_endpoint_url(image_api_base_url: str | None) -> str:
    if image_api_base_url is None:
        return ""
    base_url = image_api_base_url.rstrip("/")
    return f"{base_url}/api/v1/map/images" if base_url else "/api/v1/map/images"


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
    image_api_base_url: str | None = None,
    access_token: str | None = None,
) -> str:
    layers = _normalize_map_layers(payload)

    encoded_payload = _json_payload_to_base64({"layers": layers})
    primary_layer_id = escape(str(payload.get("primary_layer_id") or "vodomery"))
    layer_title = escape(str(payload.get("title") or "Mapa"))
    image_endpoint_url = _map_image_endpoint_url(image_api_base_url)
    image_endpoint_js = _json_string_for_script(image_endpoint_url)
    access_token_js = _json_string_for_script(access_token or "")

    return f"""
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
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
    .map-popup-photo {{
      display: block;
      width: 100%;
      max-width: 320px;
      max-height: 240px;
      object-fit: contain;
      margin-top: 10px;
      border: 1px solid #d8dee9;
      border-radius: 10px;
      background: #ffffff;
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
  </style>
</head>
<body>
  <div style="position: relative;">
    <div id="map"></div>
    <div class="map-badge">{layer_title}</div>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const encodedPayload = "{encoded_payload}";
    const primaryLayerId = "{primary_layer_id}";
    const mapImageEndpointUrl = {image_endpoint_js};
    const mapImageAccessToken = {access_token_js};
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
      if (!hasPhoto || !mapImageEndpointUrl || !mapImageAccessToken) {{
        return "";
      }}
      const identifier = featureIdentifier(properties, layerConfig);
      if (!identifier) {{
        return "";
      }}
      return `<div class="map-popup-photo-target" data-map-photo="pending" data-layer-id="${{escapeHtml(layerId)}}" data-identifier="${{escapeHtml(identifier)}}"><div class="map-popup-photo-loading">Nacitam foto...</div></div>`;
    }}

    function mapImageUrl(layerId, identifier) {{
      let url;
      try {{
        url = new URL(mapImageEndpointUrl);
      }} catch (_) {{
        const parentUrl = document.referrer || window.location.href;
        url = new URL(mapImageEndpointUrl, parentUrl);
      }}
      url.searchParams.set("layer_id", layerId);
      url.searchParams.set("identifier", identifier);
      return url.toString();
    }}

    async function loadPopupPhotos(container) {{
      if (!container || !mapImageEndpointUrl || !mapImageAccessToken) {{
        return;
      }}
      const targets = container.querySelectorAll('[data-map-photo="pending"]');
      targets.forEach(async (target) => {{
        target.dataset.mapPhoto = "loading";
        try {{
          const response = await fetch(mapImageUrl(target.dataset.layerId, target.dataset.identifier), {{
            headers: {{
              "Accept": "image/*",
              "Authorization": `Bearer ${{mapImageAccessToken}}`
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
          target.innerHTML = `<img class="map-popup-photo" src="${{escapeHtml(objectUrl)}}" alt="Foto zarizeni" loading="lazy">`;
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
      return {{
        ...defaultLayerStyle(layerId),
        ...(layerConfig.style || {{}})
      }};
    }}

    function markerStyle(layerId, layerConfig) {{
      const style = layerStyle(layerId, layerConfig);
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
    const layers = Array.isArray(mapPayload.layers) ? mapPayload.layers : [];
    layers.forEach((layerConfig) => {{
      const layerId = String(layerConfig.layer_id || "layer");
      const title = String(layerConfig.title || layerId);
      const featureCollection = layerConfig.feature_collection || {{ type: "FeatureCollection", features: [] }};
      const leafletLayer = L.geoJSON(featureCollection, {{
      pointToLayer: (_feature, latlng) => L.circleMarker(latlng, markerStyle(layerId, layerConfig)),
      style: layerStyle(layerId, layerConfig),
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

    L.control.layers(
      {{
        "Zakladni mapa": osmBaseLayer,
        "Letecka mapa (CUZK)": aerialBaseLayer
      }},
      overlayLayers,
      {{ collapsed: false, position: "topright" }}
    ).addTo(map);

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
