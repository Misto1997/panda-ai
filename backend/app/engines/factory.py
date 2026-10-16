from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.core.enums import EngineKind
from app.core.errors import ConfigurationError
from app.engines.base import QueryEngine
from app.engines.duckdb_engine import DuckDBEngine

def _bigquery(s: Settings) -> QueryEngine:
    from app.engines.bigquery_engine import BigQueryEngine  # lazy: keeps the BigQuery client off the DuckDB start-up path
    return BigQueryEngine.from_settings(s)


_REGISTRY: dict[EngineKind, Callable[[Settings], QueryEngine]] = {
    EngineKind.DUCKDB: lambda s: DuckDBEngine(s.duckdb_path),
    EngineKind.BIGQUERY: _bigquery,
}


def register_engine(kind: EngineKind, factory: Callable[[Settings], QueryEngine]) -> None:
    _REGISTRY[kind] = factory


def create_engine(settings: Settings) -> QueryEngine:
    try:
        return _REGISTRY[settings.engine](settings)
    except KeyError:
        raise ConfigurationError(f"engine '{settings.engine}' is not available yet") from None
