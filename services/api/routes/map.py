from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from services.api.core.dependencies import get_current_map_image_session_user, get_current_user
from services.api.schemas.device_map import (
    MapFilterOptionsRequest,
    MapFilterOptionsResponse,
    MapFeaturesRequest,
    MapLayerCatalogResponse,
    MapLayersResponse,
)
from services.api.services.dashboard_auth import AuthorizationError, DashboardUserContext
from services.api.services.map_layers import (
    MapLayerOperationError,
    list_map_layer_catalog,
    load_map_feature_document_file,
    load_map_feature_image_file,
    load_requested_map_filter_options,
    load_requested_map_features,
)
from services.api.services.device_map import (
    MapFeatureDocumentError,
    MapFeatureDocumentNotFound,
    MapFeatureImageError,
    MapFeatureImageNotFound,
)


router = APIRouter(prefix="/api/v1/map", tags=["map"])


@router.get(
    "/layers/catalog",
    response_model=MapLayerCatalogResponse,
    summary="List available map layers",
    description=(
        "Vraci katalog mapovych vrstev dostupnych pro aktualniho uzivatele. "
        "Device vrstvy jsou dostupne jen pri odpovidajicich opravnenich a zapnutem mapovem zobrazeni."
    ),
)
def get_map_layer_catalog(
    current_user: DashboardUserContext = Depends(get_current_user),
    map_context: str = Query(default="evidence", pattern="^(evidence|revize|pronajem|shared)$"),
) -> MapLayerCatalogResponse:
    layers = list_map_layer_catalog(current_user, map_context=map_context)
    return MapLayerCatalogResponse(total=len(layers), layers=layers)


@router.post(
    "/features",
    response_model=MapLayersResponse,
    summary="Load selected map layer features",
    description=(
        "Vraci GeoJSON vrstvy podle vyberu uzivatele. "
        "Kazda vrstva muze mit vlastni multiselect filtry, kde vice hodnot znamena IN a vice filtru znamena AND."
    ),
)
def post_map_features(
    payload: MapFeaturesRequest,
    current_user: DashboardUserContext = Depends(get_current_user),
    map_context: str = Query(default="evidence", pattern="^(evidence|revize|pronajem|shared)$"),
) -> MapLayersResponse:
    try:
        response = load_requested_map_features(
            current_user,
            [layer.model_dump() for layer in payload.layers],
            map_context=map_context,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (MapLayerOperationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return MapLayersResponse(**response)


@router.post(
    "/filter-options",
    response_model=MapFilterOptionsResponse,
    summary="Load selected map layer filter options",
    description=(
        "Vraci distinct hodnoty pro nastavene filtry vybranych vrstev. "
        "Aktualni filtry v payloadu se pouziji pro faceted filtrovani hodnot bez nacitani cele GeoJSON vrstvy."
    ),
)
def post_map_filter_options(
    payload: MapFilterOptionsRequest,
    current_user: DashboardUserContext = Depends(get_current_user),
    map_context: str = Query(default="evidence", pattern="^(evidence|revize|pronajem|shared)$"),
) -> MapFilterOptionsResponse:
    try:
        response = load_requested_map_filter_options(
            current_user,
            [layer.model_dump() for layer in payload.layers],
            map_context=map_context,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except (MapLayerOperationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return MapFilterOptionsResponse(**response)


@router.get(
    "/images",
    response_class=FileResponse,
    summary="Load map feature image",
    description=(
        "Vraci fotku zarizeni podle layer_id a identifier. "
        "Cesta k souboru se neprebira z klienta, ale dohledava se server-side z povoleneho detailu zarizeni. "
        "Endpoint pouziva HttpOnly dashboard session cookie misto bearer tokenu v mapovem iframe."
    ),
)
def get_map_image(
    layer_id: str = Query(min_length=1),
    identifier: str = Query(min_length=1),
    current_user: DashboardUserContext = Depends(get_current_map_image_session_user),
) -> FileResponse:
    try:
        image_file = load_map_feature_image_file(
            current_user,
            layer_id=layer_id,
            identifier=identifier,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except MapFeatureImageNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fotka neni dostupna.",
        ) from exc
    except (MapFeatureImageError, MapLayerOperationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return FileResponse(
        image_file.path,
        media_type=image_file.media_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "Vary": "Cookie",
        },
    )


@router.get(
    "/documents",
    response_class=FileResponse,
    summary="Load map feature PDF document",
    description=(
        "Vraci PDF dokument mapoveho prvku podle layer_id, identifier a document_key. "
        "Cesta k souboru se neprebira z klienta, ale dohledava se server-side z povolene konfigurace vrstvy. "
        "Endpoint pouziva HttpOnly dashboard session cookie misto bearer tokenu v mapovem iframe."
    ),
)
def get_map_document(
    layer_id: str = Query(min_length=1),
    identifier: str = Query(min_length=1),
    document_key: str = Query(min_length=1),
    current_user: DashboardUserContext = Depends(get_current_map_image_session_user),
) -> FileResponse:
    try:
        document_file = load_map_feature_document_file(
            current_user,
            layer_id=layer_id,
            identifier=identifier,
            document_key=document_key,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except MapFeatureDocumentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument neni dostupny.",
        ) from exc
    except (MapFeatureDocumentError, MapLayerOperationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return FileResponse(
        document_file.path,
        media_type=document_file.media_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "Vary": "Cookie",
        },
    )
