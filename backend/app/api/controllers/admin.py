from __future__ import annotations

from fastapi import APIRouter

from app.container import Container


class AdminController:
    """Operational endpoints for demos and debugging."""

    def __init__(self, container: Container) -> None:
        self._cache = container.cache
        self.router = APIRouter(prefix="/api/admin", tags=["admin"])
        self.router.add_api_route("/cache/clear", self.clear_cache, methods=["POST"])
        self.router.add_api_route("/cache/stats", self.cache_stats, methods=["GET"])

    def clear_cache(self) -> dict:
        self._cache.clear()
        return {"cleared": True}

    def cache_stats(self) -> dict:
        return self._cache.stats()
