from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from moduly.apps.dashboard.database.db_init import ensure_dashboard_tables
from services.api.core.config import get_api_settings
from services.api.routes.admin import router as admin_router
from services.api.routes.auth import router as auth_router
from services.api.routes.health import router as health_router
from services.api.routes.kalorimetry import router as kalorimetry_router
from services.api.routes.map import router as map_router
from services.api.routes.manometry import router as manometry_router
from services.api.routes.plynomery import router as plynomery_router
from services.api.routes.scheduler_health import router as scheduler_health_router
from services.api.routes.vodomery import router as vodomery_router
from services.api.routes.web_search import router as web_search_router


settings = get_api_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dashboard_tables()
    yield


app = FastAPI(
    title=settings.title,
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type"],
    )

app.include_router(health_router)
app.include_router(scheduler_health_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(kalorimetry_router)
app.include_router(map_router)
app.include_router(manometry_router)
app.include_router(plynomery_router)
app.include_router(vodomery_router)
app.include_router(web_search_router)
