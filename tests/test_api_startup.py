import asyncio
from threading import Event

from fastapi import Response, status

from services.api import main
from services.api.core.runtime_state import api_readiness
from services.api.routes.health import health_live, health_ready


def test_liveness_does_not_depend_on_database_readiness():
    api_readiness.mark_not_ready()

    assert health_live() == {"status": "ok"}


def test_readiness_is_unavailable_until_database_initialization_finishes():
    api_readiness.mark_not_ready()
    unavailable_response = Response()

    assert health_ready(unavailable_response) == {"status": "unavailable"}
    assert unavailable_response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    api_readiness.mark_ready()
    ready_response = Response()

    assert health_ready(ready_response) == {"status": "ready"}
    assert ready_response.status_code == status.HTTP_200_OK


def test_database_initialization_retries_without_blocking_api_startup(monkeypatch):
    attempts = []

    def initialize_tables():
        attempts.append(None)
        if len(attempts) == 1:
            raise OSError("database unavailable")

    monkeypatch.setattr(main, "ensure_dashboard_tables", initialize_tables)
    monkeypatch.setattr(main, "DATABASE_INIT_RETRY_SECONDS", 0)
    api_readiness.mark_not_ready()

    asyncio.run(main.initialize_dashboard_tables_until_ready())

    assert len(attempts) == 2
    assert api_readiness.is_ready() is True


def test_lifespan_does_not_wait_for_database_initialization(monkeypatch):
    initialization_started = Event()
    release_initialization = Event()

    def initialize_tables():
        initialization_started.set()
        release_initialization.wait(timeout=5)

    monkeypatch.setattr(main, "ensure_dashboard_tables", initialize_tables)
    api_readiness.mark_not_ready()

    async def run_scenario():
        async with main.lifespan(main.app):
            started = await asyncio.to_thread(initialization_started.wait, 1)
            assert started is True
            assert api_readiness.is_ready() is False

            release_initialization.set()
            for _ in range(20):
                if api_readiness.is_ready():
                    break
                await asyncio.sleep(0.01)
            assert api_readiness.is_ready() is True

        assert api_readiness.is_ready() is False

    asyncio.run(run_scenario())
