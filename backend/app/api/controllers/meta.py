from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import MetricInfo, RuntimeInfo
from app.container import Container
from app.core.errors import PandaError

SUGGESTIONS = [
    "Net GMV by zone for the last 7 days",
    "Daily visits by marketplace last 14 days",
    "Why did Net GMV drop in the last 14 days?",
    "Why did visits drop in the last 14 days?",
    "Why did ASP drop in the last 14 days?",
    "Net units by state for Acme Express last 30 days",
    "What is BU visits?",
]
RAW_TABLES = ("fact_sales", "agg_sales_daily", "agg_traffic_city_daily", "agg_bu_traffic_daily")


class MetaController:
    """GET /api/meta: runtime facts for the UI sidebar."""

    def __init__(self, container: Container) -> None:
        self._c = container
        self.router = APIRouter(prefix="/api", tags=["meta"])
        self.router.add_api_route("/meta", self.runtime, methods=["GET"], response_model=RuntimeInfo)

    def _anchor(self) -> str:
        try:
            return str(self._c.query_service.anchor)
        except PandaError:
            return "data not loaded"

    def _rows(self, table: str) -> int:
        try:
            return self._c.engine.row_count(table)
        except PandaError:
            return 0  # table not loaded yet

    def runtime(self) -> RuntimeInfo:
        c = self._c
        return RuntimeInfo(
            profile=c.settings.profile, app_env=c.settings.app_env.value, llm=c.llm.name, engine=c.engine.name, search=c.search.backend_name, anchor=self._anchor(),
            tables={t: self._rows(t) for t in RAW_TABLES},
            metrics=[MetricInfo(id=m.id, title=m.title, description=m.description) for m in c.catalog.metrics.values()],
            suggestions=SUGGESTIONS, cache=c.cache.stats())
