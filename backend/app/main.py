"""ASGI entrypoint. `uvicorn app.main:app`"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.controllers.a2ui import A2uiController
from app.api.controllers.admin import AdminController
from app.api.controllers.chat import ChatController
from app.api.controllers.history import HistoryController
from app.api.controllers.health import HealthController
from app.api.controllers.me import MeController
from app.api.controllers.meta import MetaController
from app.api.errors import register_error_handlers
from app.api.middleware import RequestIdMiddleware
from app.container import Container, build_container
from app.core.config import get_settings
from app.security.limits import BodyLimitMiddleware


def create_app(container: Container | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned = container is None  # a container injected by the caller (tests) is closed by its owner
        c: Container = container or build_container()
        app.state.container = c
        for controller in (HealthController(c), MetaController(c), ChatController(c), AdminController(c), A2uiController(), MeController(c), HistoryController(c)):
            app.include_router(controller.router)
        try:
            yield
        finally:
            if owned:
                c.close()

    app = FastAPI(title="PANDA gateway", version="0.2.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    settings_origins = (container.settings if container else get_settings()).cors_origins
    app.add_middleware(CORSMiddleware, allow_origins=settings_origins, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-Id"])
    app.add_middleware(BodyLimitMiddleware, max_bytes=(container.settings if container else get_settings()).max_request_bytes)  # outermost
    register_error_handlers(app)
    return app


app = create_app()
