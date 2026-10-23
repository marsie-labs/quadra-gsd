"""Composition root: lifespan wiring, /healthz, and NiceGUI mounted last.

Every plain FastAPI route or router MUST be registered before ``ui.run_with``: NiceGUI
mounts itself at ``/`` and shadows anything added after it (Pitfall 1). Data changes reach
this process only through the Realtime subscription; nothing here polls the database.
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from nicegui import ui

from app import deps
from app.db.repository import Repository, connect
from app.deps import Services
from app.realtime.hub import RealtimeHub
from app.services.sessions import SessionService
from app.settings import Settings
from app.ui.pages import register_pages

logger = logging.getLogger("quadra")

health_router = APIRouter()


@health_router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    """Liveness plus the Realtime startup-check state. Exposes no settings, keys or URLs."""
    hub = getattr(request.app.state, "hub", None)
    if hub is None:
        realtime: dict[str, Any] = {
            "state": "pending",
            "stage": None,
            "latency_ms": None,
            "error": None,
        }
    else:
        realtime = hub.status()
    status = "ok" if realtime["state"] in ("verified", "disabled") else "degraded"
    return {"status": status, "realtime": realtime}


def make_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = await connect(settings)
        repo = Repository(client)
        hub = RealtimeHub(settings.supabase_url, settings.realtime_key())
        deps.services = Services(sessions=SessionService(repo), hub=hub)
        app.state.hub = hub
        try:
            # strict mode raises RealtimeCheckError here, which aborts startup.
            await hub.run_startup_check(settings.realtime_check, repo.upsert_probe)
            yield
        finally:
            await hub.stop()
            deps.services = None
            await client.postgrest.aclose()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Quadra", lifespan=make_lifespan(settings))
    app.include_router(health_router)
    register_pages()
    # LAST: NiceGUI mounts at "/" and would shadow any route registered after it.
    # max_age is one year so a browser's display name outlives Starlette's 14-day default.
    ui.run_with(
        app,
        title="Quadra",
        storage_secret=settings.storage_secret.get_secret_value(),
        session_middleware_kwargs={"max_age": 365 * 24 * 3600},
    )
    return app
