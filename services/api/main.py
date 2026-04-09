from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from moduly.apps.dashboard.database.db_init import ensure_dashboard_tables
from services.api.core.config import get_api_settings
from services.api.routes.admin import router as admin_router
from services.api.routes.auth import router as auth_router
from services.api.routes.health import router as health_router
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

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(vodomery_router)
app.include_router(web_search_router)
