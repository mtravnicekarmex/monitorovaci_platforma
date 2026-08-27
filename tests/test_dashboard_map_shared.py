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


def test_leaflet_map_html_keeps_layer_draw_order_stable_with_leaflet_panes():
    payload = {
        "primary_layer_id": "spodni",
        "layers": [
            {
                "layer_id": "horni",
                "title": "Horni",
                "draw_order": 200,
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [14.1, 50.7]},
                            "properties": {},
                        }
                    ],
                },
            },
            {
                "layer_id": "spodni",
                "title": "Spodni",
                "draw_order": 10,
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": []},
                            "properties": {},
                        }
                    ],
                },
            },
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "function layerDrawOrder" in html
    assert "function orderedMapLayers" in html
    assert "function layerPaneName" in html
    assert "function ensureLayerPane" in html
    assert "const layers = orderedMapLayers(Array.isArray(mapPayload.layers) ? mapPayload.layers : [])" in html
    assert "pane.style.zIndex = String(410 + layerIndex)" in html
    assert "const paneName = ensureLayerPane(layerId, layerIndex)" in html
    assert "geoJsonLayerOptions(layerId, layerConfig, paneName)" in html
    assert "pane: paneName" in html
    assert "markerStyle(feature, layerId, layerConfig, paneName)" in html
    assert 'pane.style.zIndex = "620"' in html


def test_leaflet_map_html_uses_property_labels_for_popup_and_filter_labels():
    payload = {
        "primary_layer_id": "potrubi",
        "layers": [
            {
                "layer_id": "potrubi",
                "title": "Potrubi",
                "popup_columns": ["paterni_rozvod"],
                "filter_columns": ["paterni_rozvod"],
                "property_labels": {"paterni_rozvod": "Paterni rozvod"},
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[14.1, 50.7], [14.2, 50.8]]},
                            "properties": {"paterni_rozvod": True},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "function propertyLabels" in html
    assert "function propertyDisplayLabel" in html
    assert "function conditionalConditionDisplayName" in html
    assert "conditionalRuleDisplayName(rule, ruleIndex, layerConfig)" in html
    assert "layerConfig.popup_columns.map((key) => [key, propertyDisplayLabel(layerConfig, key)])" in html
    assert "Object.keys(properties).map((key) => [key, propertyDisplayLabel(layerConfig, key)])" in html
    assert "label: propertyDisplayLabel(layerConfig, column)" in html


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


def test_leaflet_map_html_can_toggle_configured_map_labels_by_layer():
    payload = {
        "primary_layer_id": "mistnosti",
        "layers": [
            {
                "layer_id": "mistnosti",
                "title": "Mistnosti",
                "map_label_columns": ["mistnost"],
                "map_labels_default_visible": False,
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [14.1, 50.7]},
                            "properties": {"mistnost": "101"},
                        }
                    ],
                },
            },
            {
                "layer_id": "bez_popisku",
                "title": "Bez popisku",
                "map_label_columns": [],
                "feature_collection": {"type": "FeatureCollection", "features": []},
            },
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "function createMapLabelControl" in html
    assert "const labelVisibilityByLayer = {}" in html
    assert "function layerHasMapLabels" in html
    assert "function layerLabelsVisible" in html
    assert "function layerLabelsDefaultVisible" in html
    assert "layerConfig.map_labels_default_visible !== false" in html
    assert "labelVisibilityByLayer[layerId] = false" in html
    assert "function setLayerLabelsVisible" in html
    assert "labelHtml && layerLabelsVisible(layerId)" in html
    assert 'toggle.textContent = "Popisky"' in html
    assert 'checkboxElement.type = "checkbox"' in html
    assert "checkboxElement.checked = layerLabelsVisible(layerId)" in html
    assert "setLayerLabelsVisible(layerId, checkboxElement.checked)" in html
    assert "const labelControl = createMapLabelControl()" in html
    assert "syncFilterControlWidthToLayerControl(filterControl, labelControl, legendControl)" in html


def test_leaflet_map_html_keeps_top_right_control_stack_scrollable():
    payload = {
        "primary_layer_id": "potrubi",
        "layers": [
            {
                "layer_id": "potrubi",
                "title": "Potrubi",
                "map_label_columns": ["nazev"],
                "filter_fields": [
                    {
                        "key": "stav",
                        "source_column": "stav",
                        "property_key": "stav",
                        "label": "Stav",
                    }
                ],
                "filter_options": {"stav": ["tece", "netece"]},
                "style": {
                    "conditionalStyle": {
                        "rules": [
                            {
                                "name": "Tece",
                                "property": "stav",
                                "operator": "equals",
                                "value": "tece",
                                "style": {"color": "#2563eb"},
                            }
                        ]
                    }
                },
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[14.1, 50.7], [14.2, 50.8]]},
                            "properties": {"nazev": "P1", "stav": "tece"},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert ".leaflet-top.leaflet-right" in html
    assert "max-height: calc(100vh - 12px)" in html
    assert "max-height: calc(100dvh - 12px)" in html
    assert "overflow-y: auto" in html
    assert "overscroll-behavior: contain" in html
    assert "padding-bottom: 10px" in html
    assert "pointer-events: auto" in html
    assert "scrollbar-width: thin" in html


def test_leaflet_map_html_syncs_revize_mistnosti_filters_to_revision_terms_layer():
    payload = {
        "map_context": "revize",
        "primary_layer_id": "revize_terminy_zarizeni",
        "layers": [
            {
                "layer_id": "mistnosti",
                "title": "Mistnosti",
                "filter_fields": [
                    {"key": "budova", "source_column": "budova", "property_key": "budova", "label": "Budova"},
                    {"key": "patro", "source_column": "patro", "property_key": "patro", "label": "Patro"},
                ],
                "filter_options": {"budova": ["A", "B"], "patro": ["1.NP"]},
                "feature_collection": {"type": "FeatureCollection", "features": []},
            },
            {
                "layer_id": "revize_terminy_zarizeni",
                "title": "Terminy revizi a kontrol",
                "filter_fields": [
                    {"key": "budova", "source_column": "budova", "property_key": "budova", "label": "Budova"},
                    {"key": "patro", "source_column": "patro", "property_key": "patro", "label": "Patro"},
                    {
                        "key": "stav_terminu",
                        "source_column": "stav_terminu",
                        "property_key": "stav_terminu",
                        "label": "Stav terminu",
                    },
                ],
                "filter_options": {"budova": ["A", "B"], "patro": ["1.NP"], "stav_terminu": ["platna"]},
                "feature_collection": {"type": "FeatureCollection", "features": []},
            },
        ],
    }

    html = build_leaflet_map_html(payload)

    assert 'const mapContext = String(mapPayload.map_context || "")' in html
    assert "function layerSupportsFilter" in html
    assert "function linkedFilterTargets" in html
    assert 'mapContext !== "revize"' in html
    assert 'String(layerId) !== "mistnosti"' in html
    assert 'const targetLayerId = "revize_terminy_zarizeni"' in html
    assert 'budova: "budova"' in html
    assert 'patro: "patro"' in html
    assert "function syncLinkedLayerFilters" in html
    assert "syncLinkedLayerFilters(layerId, field.key, selectedValues)" in html
    assert "renderPanel();" in html
    assert "applyLayerFilters();" in html


def test_leaflet_map_html_preserves_filter_layer_expansion_after_panel_rerender():
    payload = {
        "primary_layer_id": "mistnosti",
        "layers": [
            {
                "layer_id": "mistnosti",
                "title": "Mistnosti",
                "filter_fields": [
                    {"key": "budova", "source_column": "budova", "property_key": "budova", "label": "Budova"},
                ],
                "filter_options": {"budova": ["A", "B"]},
                "feature_collection": {"type": "FeatureCollection", "features": []},
            },
            {
                "layer_id": "revize_terminy_zarizeni",
                "title": "Terminy revizi a kontrol",
                "filter_fields": [
                    {"key": "budova", "source_column": "budova", "property_key": "budova", "label": "Budova"},
                ],
                "filter_options": {"budova": ["A", "B"]},
                "feature_collection": {"type": "FeatureCollection", "features": []},
            },
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "const filterLayerOpenState = {}" in html
    assert "const rememberFilterLayerOpenState = () =>" in html
    assert 'details.map-filter-layer[data-layer-id]' in html
    assert "layerElement.dataset.layerId = layerId" in html
    assert "Object.prototype.hasOwnProperty.call(filterLayerOpenState, layerId)" in html
    assert "filterLayerOpenState[layerId] = layerElement.open" in html


def test_leaflet_map_html_allows_deeper_vector_zoom_without_changing_native_tile_zoom():
    payload = {
        "primary_layer_id": "potrubi",
        "layers": [
            {
                "layer_id": "potrubi",
                "title": "Potrubi",
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[14.1, 50.7], [14.2, 50.8]]},
                            "properties": {},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert 'L.map("map", { center: [50.77, 14.23], zoom: 17, maxZoom: 24 })' in html
    assert "maxNativeZoom: 19" in html
    assert "maxNativeZoom: 20" in html
    assert "map.fitBounds(bounds, { padding: [24, 24], maxZoom: 22 })" in html


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
    assert (
        "pointToLayer: (feature, latlng) => "
        "L.circleMarker(latlng, markerStyle(feature, layerId, layerConfig, paneName))"
    ) in html


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


def test_leaflet_map_html_can_toggle_conditional_style_legend_by_layer():
    payload = {
        "primary_layer_id": "potrubi",
        "layers": [
            {
                "layer_id": "potrubi",
                "title": "Potrubi",
                "style": {
                    "color": "#64748b",
                    "conditionalStyle": {
                        "rules": [
                            {
                                "name": "Studena voda tece",
                                "property": "stav",
                                "operator": "equals",
                                "value": "tece",
                                "style": {"color": "#2563eb", "fillColor": "#bfdbfe"},
                            },
                            {
                                "name": "Bez prutoku",
                                "property": "stav",
                                "operator": "equals",
                                "value": "netece",
                                "style": {"color": "#dc2626", "fillColor": "#fecaca"},
                            },
                        ]
                    },
                },
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[14.1, 50.7], [14.2, 50.8]]},
                            "properties": {"stav": "tece"},
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "function createMapLegendControl" in html
    assert "const legendVisibilityByLayer = {}" in html
    assert "function conditionalRuleDisplayName" in html
    assert "rule.name || rule.title || rule.label" in html
    assert "function layerGeometryKind" in html
    assert "function layerLegendEntries" in html
    assert "function layerHasLegend" in html
    assert "function layerLegendVisible" in html
    assert "function setLayerLegendVisible" in html
    assert "function colorWithOpacity" in html
    assert "function applyLegendSwatchStyle" in html
    assert 'toggle.textContent = "Legenda"' in html
    assert 'checkboxElement.className = "map-legend-checkbox"' in html
    assert "checkboxElement.checked = layerLegendVisible(layerId)" in html
    assert "setLayerLegendVisible(layerId, checkboxElement.checked)" in html
    assert "applyLegendSwatchStyle(swatchElement, legendEntry)" in html
    assert "swatchElement.style.opacity" not in html
    assert 'swatchElement.classList.add("is-line")' in html
    assert "swatchElement.style.background = colorWithOpacity(fillColor, fillOpacity)" in html
    assert "textElement.textContent = legendEntry.label" in html
    assert "const legendControl = createMapLegendControl()" in html
    assert "syncFilterControlWidthToLayerControl(filterControl, labelControl, legendControl)" in html


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
    assert 'controlContainer.style.setProperty("--map-filter-panel-width", `${measuredWidth}px`)' in html
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
    assert "!item.loaded && !map.hasLayer(item.layer)" in html
    assert "const isInitiallyVisible = layerConfig.default_visible !== false" in html
    assert 'isInitiallyVisible ? filteredFeatureCollection(layerConfig) : { type: "FeatureCollection", features: [] }' in html
    assert "loaded: isInitiallyVisible" in html
    assert 'map.on("overlayadd", (event) =>' in html
    assert "ensureLayerDataLoaded(item)" in html
    assert "filteredFeatureCollection(layerConfig)" in html
    assert "geoJsonLayerOptions(layerId, layerConfig, paneName)" in html
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


def test_leaflet_map_html_renders_pdf_document_links_without_raw_paths():
    payload = {
        "primary_layer_id": "revize_terminy_zarizeni",
        "layers": [
            {
                "layer_id": "revize_terminy_zarizeni",
                "title": "Terminy revizi",
                "identifier_column": "map_id",
                "popup_columns": ["identifikace", "stav_terminu"],
                "document_columns": {
                    "revize_soubor": "Zobrazit revizi",
                    "servisni_smlouva": "Zobrazit servisni smlouvu",
                },
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [14.1, 50.7]},
                            "properties": {
                                "map_id": "HYDRANTY:1",
                                "identifikace": "H-1",
                                "stav_terminu": "Platne",
                                "document_links": [
                                    {"key": "revize_soubor", "label": "Zobrazit revizi"},
                                    {"key": "servisni_smlouva", "label": "Zobrazit servisni smlouvu"},
                                ],
                            },
                        }
                    ],
                },
            }
        ],
    }

    html = build_leaflet_map_html(payload)

    assert "mapDocumentEndpointUrl" in html
    assert 'const mapDocumentEndpointUrl = "/api/v1/map/documents";' in html
    assert "function mapDocumentUrl" in html
    assert "function documentLinksHtml" in html
    assert "document_key" in html
    assert "map-popup-document-link" in html
    assert "target=\"_blank\"" in html
    assert "rel=\"noopener noreferrer\"" in html
    assert "documentLinksHtml(properties, layerId, layerConfig)" in html
    assert "P:\\\\" not in html
    assert "file:///" not in html


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
