from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import MetricInfo, RuntimeInfo
from app.container import Container

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

    def runtime(self) -> RuntimeInfo:
        c = self._c
        return RuntimeInfo(
            profile=c.settings.profile, app_env=c.settings.app_env.value, llm=c.llm.name, engine=c.engine.name, search=c.search.backend_name, anchor=str(c.query_service.anchor),
            tables={t: c.engine.row_count(t) for t in RAW_TABLES},
            metrics=[MetricInfo(id=m.id, title=m.title, description=m.description) for m in c.catalog.metrics.values()],
            suggestions=SUGGESTIONS, cache=c.cache.stats())
