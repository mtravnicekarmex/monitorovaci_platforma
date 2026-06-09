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

    assert "osmBaseLayer" in html
    assert "aerialBaseLayer" in html
    assert "ORTOFOTO_WM/MapServer/tile/{z}/{y}/{x}" in html
    assert "L.control.layers" in html


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
    assert "layerConfig.default_visible !== false" in html
    assert "layerConfig.popup_columns" in html


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

    html = build_leaflet_map_html(
        payload,
        image_api_base_url="http://127.0.0.1:8000",
        access_token="test-token",
    )

    assert "map-popup-photo" in html
    assert "mapImageEndpointUrl" in html
    assert "http://127.0.0.1:8000/api/v1/map/images" in html
    assert "function photoPlaceholderHtml" in html
    assert "fetch(mapImageUrl" in html
    assert '"Authorization": `Bearer ${mapImageAccessToken}`' in html
    assert "properties.has_photo === true" in html
    assert 'String(key).toLowerCase() !== "foto"' in html
    assert "photoPlaceholderHtml(properties, layerId, layerConfig)" in html
    assert "map-popup-photo-button" in html
    assert "function openPhotoLightbox" in html
    assert "Otevrit v nove karte" in html
    assert 'event.key === "Escape"' in html
    assert "file:///" not in html


def test_leaflet_map_html_supports_same_origin_image_api():
    html = build_leaflet_map_html(
        {"layers": []},
        image_api_base_url="",
        access_token="test-token",
    )

    assert 'const mapImageEndpointUrl = "/api/v1/map/images";' in html
    assert "const parentUrl = document.referrer || window.location.href;" in html
    assert "new URL(mapImageEndpointUrl, parentUrl)" in html


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
