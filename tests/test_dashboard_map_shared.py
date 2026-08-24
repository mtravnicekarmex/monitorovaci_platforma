import inspect

from moduly.apps.dashboard.map_shared import (
    build_leaflet_map_html,
    build_map_features_request,
    extract_layer_filter_options,
    merge_selected_filter_options,
    normalize_catalog_layers,
    normalize_filter_options_payload,
)


def test_leaflet_map_html_exposes_osm_and_aerial_base_layers():
    payload = {
        "title": "Vodomery",
        "source_srid": 3857,
        "target_srid": 4326,
        "feature_collection": {"type": "FeatureCollection", "features": []},
    }

    html = build_leaflet_map_html(payload)

    assert "Leaflet 1.9.4" in html
    assert "unpkg.com" not in html
    assert "<script src=" not in html
    assert "url(images/" not in html
    assert "data:image/png;base64," in html
    assert "L.Icon.Default.mergeOptions" in html
    assert "sourceMappingURL=leaflet.js.map" not in html
    assert "osmBaseLayer" in html
    assert "aerialBaseLayer" in html
    assert "emptyBaseLayer" in html
    assert '"Bez mapy": emptyBaseLayer' in html
    assert "background: #ffffff" in html
    assert "ORTOFOTO_WM/MapServer/tile/{z}/{y}/{x}" in html
    assert "L.control.layers" in html


def test_leaflet_map_html_can_fill_parent_height():
    payload = {
        "primary_layer_id": "vodomery",
        "layers": [
            {
                "layer_id": "vodomery",
                "title": "Vodomery",
                "feature_collection": {"type": "FeatureCollection", "features": []},
            }
        ],
    }

    html = build_leaflet_map_html(payload, height_px=920, fill_parent_height=True)

    assert "overflow: hidden" in html
    assert "height: 100vh" in html
    assert "height: 100dvh" in html
    assert "box-sizing: border-box" in html
    assert "height: 920px" not in html
    assert "function invalidateMapSize" in html
    assert "new ResizeObserver(() => invalidateMapSize())" in html
    assert 'resizeObserver.observe(document.getElementById("map"))' in html
    assert 'window.addEventListener("resize", invalidateMapSize)' in html
    assert "[0, 100, 300, 800].forEach" in html


def test_leaflet_map_html_exposes_budovy_overlay_layer():
    payload = {
        "primary_layer_id": "vodomery",
        "layers": [
            {
                "layer_id": "vodomery",
                "title": "Vodomery",
                "source_srid": 3857,
                "target_srid": 4326,
                "total": 0,
                "feature_collection": {"type": "FeatureCollection", "features": []},
            },
            {
                "layer_id": "budovy",
                "title": "Budovy",
                "source_srid": 3857,
                "target_srid": 4326,
                "total": 1,
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": []},
                            "properties": {"layer_id": "budovy", "budova": "A", "pocet_podlazi": 3},
                        }
                    ],
                },
            },
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "budovy:" in html
    assert "pocet_podlazi" in html
    assert 'if (layerId === "budovy")' in html


def test_leaflet_map_html_exposes_mistnosti_overlay_layer():
    payload = {
        "primary_layer_id": "vodomery",
        "layers": [
            {
                "layer_id": "mistnosti",
                "title": "M\u00edstnosti",
                "source_srid": 3857,
                "target_srid": 4326,
                "total": 1,
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": []},
                            "properties": {
                                "layer_id": "mistnosti",
                                "mistnost_id": "F-1NP-101",
                                "budova": "F",
                                "patro": "1.NP",
                                "mistnost": "101",
                            },
                        }
                    ],
                },
            },
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "mistnosti:" in html
    assert "mistnost_id" in html
    assert 'if (layerId === "mistnosti")' in html


def test_leaflet_map_html_uses_configured_layer_style_and_default_visibility():
    payload = {
        "primary_layer_id": "vodomery",
        "layers": [
            {
                "layer_id": "custom",
                "title": "Custom",
                "default_visible": False,
                "style": {"color": "#123456", "fillColor": "#abcdef", "fillOpacity": 0.35},
                "map_label_columns": ["name"],
                "popup_columns": ["name"],
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [14.1, 50.7]},
                            "properties": {"name": "A"},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "layerConfig.style" in html
    assert "leafletLayer.addTo(map);" in html
    assert "layerConfig.default_visible !== false" in html
    assert "layerConfig.map_label_columns" in html
    assert "layerConfig.popup_columns" in html


def test_leaflet_map_html_binds_configured_map_labels_as_permanent_tooltips():
    payload = {
        "primary_layer_id": "mistnosti",
        "layers": [
            {
                "layer_id": "mistnosti",
                "title": "Mistnosti",
                "layer_kind": "device",
                "style": {"color": "#15803d"},
                "map_label_columns": ["mistnost"],
                "popup_columns": ["mistnost_id"],
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[14.1, 50.7], [14.2, 50.7], [14.2, 50.8], [14.1, 50.7]]],
                            },
                            "properties": {"mistnost_id": "F-1NP-101", "mistnost": "101"},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "function featureMapLabel" in html
    assert "function featureLabelColor" in html
    assert "function featureLabelTooltipOptions" in html
    assert "function applyFeatureLabelStyle" in html
    assert "leafletLayer.bindTooltip(labelHtml" in html
    assert "permanent: true" in html
    assert 'direction: isDeviceLayer ? "top" : "center"' in html
    assert "offset: isDeviceLayer ? [0, -10] : [0, 0]" in html
    assert 'className: "map-feature-label"' in html
    assert "element.style.color = featureLabelColor(layerId, layerConfig)" in html
    assert "background: transparent" in html
    assert "box-shadow: none" in html
    assert "layerConfig.map_label_columns" in html


def test_leaflet_map_html_supports_conditional_feature_style():
    payload = {
        "primary_layer_id": "potrubi",
        "layers": [
            {
                "layer_id": "potrubi",
                "title": "Potrubi",
                "style": {
                    "color": "#2563eb",
                    "weight": 3,
                    "conditionalStyle": {
                        "property": "bez_vody",
                        "operator": "equals",
                        "value": True,
                        "match": {"color": "#dc2626", "weight": 5},
                        "fallback": {"color": "#2563eb", "weight": 3},
                    },
                },
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[14.1, 50.7], [14.2, 50.8]]},
                            "properties": {"id": "P-1", "bez_vody": True},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "conditionalStyle" in html
    assert "function conditionMatches" in html
    assert "function featureStyle" in html
    assert "delete style.conditionalStyle" in html
    assert "style: (feature) => featureStyle(feature, layerId, layerConfig)" in html
    assert "pointToLayer: (feature, latlng) => L.circleMarker(latlng, markerStyle(feature, layerId, layerConfig))" in html


def test_leaflet_map_html_supports_multiple_conditional_feature_styles():
    payload = {
        "primary_layer_id": "potrubi",
        "layers": [
            {
                "layer_id": "potrubi",
                "title": "Potrubi",
                "style": {
                    "color": "#2563eb",
                    "conditionalStyle": {
                        "rules": [
                            {"property": "stav", "operator": "equals", "value": "bez_vody", "style": {"color": "#dc2626"}},
                            {"property": "stav", "operator": "equals", "value": "tece", "style": {"color": "#16a34a"}},
                            {"property": "stav", "operator": "equals", "value": "stoji", "style": {"color": "#ca8a04"}},
                        ],
                        "fallback": {"color": "#64748b"},
                    },
                },
                "feature_collection": {"type": "FeatureCollection", "features": []},
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "function conditionalRules" in html
    assert "Array.isArray(conditionalStyle.rules)" in html
    assert "const matchedRule = conditionalRules(conditionalStyle).find" in html
    assert "? (matchedRule.style || matchedRule.match)" in html


def test_leaflet_map_html_supports_compound_conditional_feature_styles():
    payload = {
        "primary_layer_id": "potrubi",
        "layers": [
            {
                "layer_id": "potrubi",
                "title": "Potrubi",
                "style": {
                    "color": "#94a3b8",
                    "conditionalStyle": {
                        "rules": [
                            {
                                "all": [
                                    {"property": "teplota", "operator": "equals", "value": "studena"},
                                    {"property": "stav_prutoku", "operator": "equals", "value": "tece"},
                                ],
                                "style": {"color": "#2563eb", "weight": 5},
                            },
                            {
                                "any": [
                                    {"property": "stav_prutoku", "operator": "equals", "value": "netece"},
                                    {"property": "stav_prutoku", "operator": "is_empty"},
                                ],
                                "style": {"color": "#dc2626", "weight": 5},
                            },
                        ],
                    },
                },
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[14.1, 50.7], [14.2, 50.8]]},
                            "properties": {"teplota": "studena", "stav_prutoku": "tece"},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "Array.isArray(condition.all)" in html
    assert "conditions.every((item) => conditionMatches(properties, item))" in html
    assert "Array.isArray(condition.any)" in html
    assert "conditions.some((item) => conditionMatches(properties, item))" in html
    assert "const normalizedExpected = normalizeConditionValue(condition.value)" in html


def test_leaflet_map_html_renders_in_map_filter_control():
    payload = {
        "primary_layer_id": "mistnosti",
        "layers": [
            {
                "layer_id": "mistnosti",
                "title": "Mistnosti",
                "default_visible": False,
                "filter_fields": [
                    {
                        "key": "budova",
                        "source_column": "budova",
                        "property_key": "evidence_budova",
                        "label": "Budova",
                        "multiple": True,
                    }
                ],
                "filter_options": {"budova": ["F", "A"]},
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [14.1, 50.7]},
                            "properties": {"evidence_budova": "F"},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "map-filter-control" in html
    assert "map-filter-toggle" in html
    assert "map-filter-select" in html
    assert "const layersControl = L.control.layers" in html
    assert "function syncFilterControlWidthToLayerControl" in html
    assert 'filterContainer.style.setProperty("--map-filter-panel-width", `${measuredWidth}px`)' in html
    assert '["mouseover", "focusin", "click"].forEach((eventName) =>' in html
    assert "width: var(--map-filter-panel-width, auto)" in html
    assert "--map-control-panel-width" not in html
    assert ".leaflet-control-layers-expanded," not in html
    assert "width: min(var(--map-control-panel-width), calc(100vw - 92px))" not in html
    assert "max-width: min(var(--map-control-panel-width), calc(100vw - 92px))" not in html
    assert "max-width: min(320px, calc(100vw - 92px))" not in html
    assert "Vynulovat filtry" in html
    assert "function layerFilterFields" in html
    assert "function featureFilterOptions" in html
    assert "function featurePassesLayerFilters" in html
    assert "function filteredFeatureCollection" in html
    assert "function createMapFilterControl" in html
    assert "function ensureLayerDataLoaded" in html
    assert "const filterableLayerEntries = () => leafletLayers" in html
    assert "const visibleEntries = filterableLayerEntries().filter((item) => map.hasLayer(item.layer))" in html
    assert 'document.createElement("details")' in html
    assert 'document.createElement("summary")' in html
    assert "Zapnete vrstvu s filtrem pres ovladani vrstev." in html
    assert 'map.on("overlayadd overlayremove", renderPanel)' in html
    assert "const activeLayerFilters = {}" in html
    assert "item.layer.clearLayers()" in html
    assert "item.layer.addData(filteredFeatureCollection(item.config))" in html
    assert "item.loaded || map.hasLayer(item.layer)" in html
    assert "const isInitiallyVisible = layerConfig.default_visible !== false" in html
    assert 'isInitiallyVisible ? filteredFeatureCollection(layerConfig) : { type: "FeatureCollection", features: [] }' in html
    assert "loaded: isInitiallyVisible" in html
    assert 'map.on("overlayadd", (event) =>' in html
    assert "ensureLayerDataLoaded(item)" in html
    assert "filteredFeatureCollection(layerConfig)" in html
    assert "geoJsonLayerOptions(layerId, layerConfig)" in html
    assert "layerConfig.default_visible !== false" in html
    assert "filter_options" in html
    assert "selectElements" not in html
    assert "Authorization" not in html
    assert "Bearer" not in html


def test_leaflet_map_html_normalizes_boolean_like_filter_values():
    payload = {
        "primary_layer_id": "vodovodni_potrubi",
        "layers": [
            {
                "layer_id": "vodovodni_potrubi",
                "title": "Vodovodni potrubi",
                "filter_fields": [
                    {
                        "key": "paterni_rozvod",
                        "source_column": "páteřní rozvod",
                        "property_key": "páteřní rozvod",
                        "label": "páteřní rozvod",
                        "multiple": True,
                    }
                ],
                "filter_options": {"paterni_rozvod": ["True", "False"]},
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[14.1, 50.7], [14.2, 50.8]]},
                            "properties": {"páteřní rozvod": True},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "function normalizeFilterCompareValue" in html
    assert 'return value ? "true" : "false"' in html
    assert 'if (lowered === "true" || lowered === "false")' in html
    assert "normalizeFilterCompareValue(value)" in html
    assert "optionElement.value = normalizeFilterCompareValue(optionValue)" in html
    assert "optionElement.textContent = optionValue" in html


def test_leaflet_map_html_renders_foto_as_popup_image_only_when_present():
    payload = {
        "primary_layer_id": "vodomery",
        "layers": [
            {
                "layer_id": "vodomery",
                "title": "Vodomery",
                "popup_columns": ["identifikace", "foto"],
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [14.1, 50.7]},
                            "properties": {"identifikace": "V-1", "has_photo": True},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "map-popup-photo" in html
    assert "mapImageEndpointUrl" in html
    assert 'const mapImageEndpointUrl = "/api/v1/map/images";' in html
    assert "function photoPlaceholderHtml" in html
    assert "fetch(mapImageUrl" in html
    assert 'credentials: "include"' in html
    assert "Authorization" not in html
    assert "Bearer" not in html
    assert "mapImageAccessToken" not in html
    assert "access_token" not in inspect.signature(build_leaflet_map_html).parameters
    assert "properties.has_photo === true" in html
    assert 'String(key).toLowerCase() !== "foto"' in html
    assert "photoPlaceholderHtml(properties, layerId, layerConfig)" in html
    assert "map-popup-photo-button" in html
    assert "function openPhotoLightbox" in html
    assert "Otevrit v nove karte" in html
    assert 'event.key === "Escape"' in html
    assert "file:///" not in html


def test_leaflet_map_html_supports_same_origin_image_api():
    html = build_leaflet_map_html({"layers": []})

    assert 'const mapImageEndpointUrl = "/api/v1/map/images";' in html
    assert "const baseCandidates = [document.baseURI, document.referrer, window.location.href]" in html
    assert "new URL(mapImageEndpointUrl, baseUrl)" in html
    assert "DASHBOARD_BROWSER_API_BASE_URL" not in html


def test_leaflet_map_html_accepts_absolute_image_endpoint_without_token():
    html = build_leaflet_map_html(
        {"layers": []},
        image_endpoint_url="https://monitoring.armexholding.cz/api/v1/map/images",
    )

    assert (
        'const mapImageEndpointUrl = "https://monitoring.armexholding.cz/api/v1/map/images";'
        in html
    )
    assert "Authorization" not in html
    assert "Bearer" not in html


def test_leaflet_map_html_supports_mobile_device_location():
    html = build_leaflet_map_html({"layers": []})

    assert "map-location-control" in html
    assert 'window.matchMedia("(max-width: 720px)")' in html
    assert "navigator.geolocation" in html
    assert "map.locate({" in html
    assert 'map.on("locationfound"' in html
    assert 'map.on("locationerror"' in html
    assert "currentAccuracyCircle" in html
    assert "Poloha telefonu je dostupna pouze" in html
    assert "window.isSecureContext" in html
    assert "collapsed: compactMapControls" in html


def test_normalize_catalog_layers_keeps_only_layer_dicts():
    payload = {
        "layers": [
            {"layer_id": "budovy"},
            "invalid",
            {"layer_id": "mistnosti"},
        ]
    }

    layers = normalize_catalog_layers(payload)

    assert [layer["layer_id"] for layer in layers] == ["budovy", "mistnosti"]


def test_build_map_features_request_omits_empty_filters():
    request = build_map_features_request(
        ["budovy", "mistnosti"],
        {
            "budovy": {"budova": ["F"], "empty": []},
            "mistnosti": {},
        },
    )

    assert request == {
        "layers": [
            {"layer_id": "budovy", "filters": {"budova": ["F"]}},
            {"layer_id": "mistnosti", "filters": {}},
        ]
    }


def test_extract_layer_filter_options_uses_property_aliases_and_sorts_values():
    layer_payload = {
        "feature_collection": {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"evidence_budova": "F", "patro": "2.NP"}},
                {"type": "Feature", "properties": {"evidence_budova": "A", "patro": "1.NP"}},
                {"type": "Feature", "properties": {"evidence_budova": "F", "patro": "1.NP"}},
            ],
        }
    }
    filter_fields = [
        {"key": "budova", "property_key": "evidence_budova"},
        {"key": "patro", "property_key": "patro"},
    ]

    options = extract_layer_filter_options(layer_payload, filter_fields)

    assert options == {
        "budova": ["A", "F"],
        "patro": ["1.NP", "2.NP"],
    }


def test_normalize_filter_options_payload_groups_options_by_layer():
    payload = {
        "layers": [
            {
                "layer_id": "mistnosti",
                "options": {
                    "budova": ["F", "A"],
                    "patro": ["1.NP", None, ""],
                },
            },
            "invalid",
            {
                "layer_id": "vodomery",
                "options": {"identifikace": ["V-1"]},
            },
        ]
    }

    options = normalize_filter_options_payload(payload)

    assert options == {
        "mistnosti": {
            "budova": ["F", "A"],
            "patro": ["1.NP"],
        },
        "vodomery": {
            "identifikace": ["V-1"],
        },
    }


def test_merge_selected_filter_options_keeps_selected_values_not_in_options():
    options = merge_selected_filter_options(["A", "F"], ["Z", "F", ""])

    assert options == ["A", "F", "Z"]
