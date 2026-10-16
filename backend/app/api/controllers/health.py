from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import HealthStatus
from app.container import Container


class HealthController:
    """/health = process is up (liveness). /ready = the engine answers (readiness)."""

    def __init__(self, container: Container) -> None:
        self._c = container
        self.router = APIRouter(tags=["health"])
        self.router.add_api_route("/health", self.live, methods=["GET"], response_model=HealthStatus)
        self.router.add_api_route("/ready", self.ready, methods=["GET"], response_model=HealthStatus)

    def live(self) -> HealthStatus:
        return HealthStatus(status="ok")

    def ready(self) -> HealthStatus:
        table = self._c.catalog.anchor_table()
        try:
            self._c.engine.max_date(table.rollup, table.time_column)
        except Exception as e:
            raise HTTPException(503, "engine unavailable") from e
        if self._c.pool is not None:
            try:
                self._c.pool.ping()
            except Exception as e:
                raise HTTPException(503, "database unavailable") from e
        return HealthStatus(status="ready")
