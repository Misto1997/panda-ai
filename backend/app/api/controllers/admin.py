from __future__ import annotations

from fastapi import APIRouter, Depends

from app.container import Container
from app.diagnostics import Diagnostics
from app.security.service import admin_user


class AdminController:
    """Operational endpoints. Open in AUTH_MODE=dev; in firebase mode only signed-in users listed in ADMIN_EMAILS."""

    def __init__(self, container: Container) -> None:
        self._cache = container.cache
        self._diagnostics = Diagnostics(container)
        self.router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])
        self.router.add_api_route("/cache/clear", self.clear_cache, methods=["POST"])
        self.router.add_api_route("/cache/stats", self.cache_stats, methods=["GET"])
        self.router.add_api_route("/diagnostics", self.diagnostics, methods=["GET"])

    def clear_cache(self) -> dict:
        self._cache.clear()
        return {"cleared": True}

    def cache_stats(self) -> dict:
        return self._cache.stats()

    def diagnostics(self, llm: bool = False) -> dict:
        """Checks config, warehouse tables, database, extensions, tables and the semantic index. `?llm=true` makes one real model call."""
        return self._diagnostics.run(ping_llm=llm)
