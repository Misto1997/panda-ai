"""Orchestrates compile -> guard -> (cache) -> execute. Used by the QnA executor and the RCA investigator."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.cache.semantic_cache import SemanticCache
from app.core.config import Settings
from app.core.enums import CacheStatus, QueryMode
from app.core.logging import get_logger
from app.engines.base import QueryEngine, QueryResult
from app.query.compiler import CompiledQuery, QueryCompiler
from app.query.guard import SqlGuard
from app.query.ir import QueryIR
from app.query.period import PeriodResolver
from app.semantic.catalog import Catalog

log = get_logger("query.service")


@dataclass
class QueryOutcome:
    compiled: CompiledQuery
    result: QueryResult
    cache: CacheStatus


class QueryService:
    def __init__(self, catalog: Catalog, engine: QueryEngine, cache: SemanticCache, settings: Settings) -> None:
        self.catalog, self.engine, self.cache, self.settings = catalog, engine, cache, settings
        self.compiler = QueryCompiler(catalog)
        self.guard = SqlGuard(catalog.physical_tables(), engine.dialect, settings.max_rows)
        anchor_table = catalog.anchor_table()
        self.anchor: date = engine.max_date(anchor_table.rollup, anchor_table.time_column)
        self.resolver = PeriodResolver(self.anchor)

    def execute(self, ir: QueryIR, mode: QueryMode = QueryMode.AUTO, use_cache: bool = True,
                split_ratios: bool = False) -> QueryOutcome:
        compiled = self.compiler.compile(ir, self.resolver, mode, split_ratios)
        guarded = self.guard.check(compiled.sql)
        log.debug("sql: %s", compiled.sql if self.settings.trace_payloads else f"{len(compiled.sql)} chars")
        cacheable = use_cache and not split_ratios and self.cache.enabled
        key = self.cache.result_key(ir, compiled.period, mode) if cacheable else None
        if key and (hit := self.cache.get_result(key)):
            return QueryOutcome(compiled, QueryResult(hit["columns"], hit["rows"], 0.1), CacheStatus.HIT)
        result = self.engine.run(guarded, self.settings.query_timeout_s)
        if key:
            self.cache.put_result(key, {"columns": result.columns, "rows": result.rows})
        return QueryOutcome(compiled, result, CacheStatus.MISS if cacheable else CacheStatus.OFF)
