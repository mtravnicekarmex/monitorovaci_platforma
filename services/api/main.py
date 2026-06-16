from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from moduly.apps.dashboard.database.db_init import ensure_dashboard_tables
from services.api.core.config import ApiSettings
from services.api.core.config import get_api_settings
from services.api.core.runtime_state import api_readiness
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
logger = logging.getLogger(__name__)
DATABASE_INIT_RETRY_SECONDS = 30


async def initialize_dashboard_tables_until_ready() -> None:
    api_readiness.mark_not_ready()
    while True:
        try:
            await asyncio.to_thread(ensure_dashboard_tables)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            api_readiness.mark_not_ready()
            logger.warning(
                "Dashboard database initialization failed; "
                "error_type=%s; retrying in %s seconds.",
                type(exc).__name__,
                DATABASE_INIT_RETRY_SECONDS,
            )
            await asyncio.sleep(DATABASE_INIT_RETRY_SECONDS)
        else:
            api_readiness.mark_ready()
            logger.info("Dashboard database initialization completed.")
            return


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialization_task = asyncio.create_task(
        initialize_dashboard_tables_until_ready()
    )
    try:
        yield
    finally:
        initialization_task.cancel()
        with suppress(asyncio.CancelledError):
            await initialization_task
        api_readiness.mark_not_ready()


def create_api_app(api_settings: ApiSettings = settings) -> FastAPI:
    application = FastAPI(
        title=api_settings.title,
        version=api_settings.version,
        docs_url="/docs" if api_settings.enable_docs else None,
        redoc_url="/redoc" if api_settings.enable_docs else None,
        openapi_url="/openapi.json" if api_settings.enable_docs else None,
        lifespan=lifespan,
    )

    if api_settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(api_settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Accept", "Authorization", "Content-Type"],
        )

    application.include_router(health_router)
    application.include_router(scheduler_health_router)
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(kalorimetry_router)
    application.include_router(map_router)
    application.include_router(manometry_router)
    application.include_router(plynomery_router)
    application.include_router(vodomery_router)
    application.include_router(web_search_router)
    return application


app = create_api_app(settings)
