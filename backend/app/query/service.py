"""Orchestrates the two query paths. Used by the QnA executor and the RCA investigator.
 text-to-sql : logical SQL -> LogicalGuard -> normalise -> rewrite (rollup/raw) -> SqlGuard -> dry-run -> (cache) -> engine
 IR          : QueryIR -> compile -> SqlGuard -> (cache) -> engine   (deterministic fallback, and the RCA engine)"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.cache.semantic_cache import SemanticCache
from app.core.config import Settings
from app.core.enums import CacheStatus, QueryMode
from app.core.errors import GuardViolationError
from app.core.logging import get_logger
from app.engines.base import DryRunInfo, QueryEngine, QueryResult, SupportsDryRun
from app.query.compiler import CompiledQuery, QueryCompiler
from app.query.guard import LogicalGuard, SqlGuard
from app.query.ir import QueryIR
from app.query.logical import LogicalSchema
from app.query.normalizer import Intent, SqlNormalizer
from app.query.period import LazyPeriodResolver
from app.query.render import LogicalSqlRenderer
from app.query.rewriter import LogicalRewriter
from app.semantic.catalog import Catalog

log = get_logger("query.service")


@dataclass
class QueryOutcome:
    compiled: CompiledQuery
    result: QueryResult
    cache: CacheStatus


@dataclass
class PreparedSql:
    """LLM-written SQL that passed the logical guard: ready to dry-run or execute."""
    logical_sql: str
    physical_sql: str          # rewritten to physical tables, row-capped, in the engine dialect
    sources: dict[str, str]    # logical table -> physical table
    intent: Intent
    mode: QueryMode


@dataclass
class SqlOutcome:
    prepared: PreparedSql
    result: QueryResult
    cache: CacheStatus


class QueryService:
    def __init__(self, catalog: Catalog, engine: QueryEngine, cache: SemanticCache, settings: Settings) -> None:
        self.catalog, self.engine, self.cache, self.settings = catalog, engine, cache, settings
        self.compiler = QueryCompiler(catalog)
        self.sql_dialect = getattr(engine, "input_dialect", engine.dialect)  # dialect of the SQL handed to the engine (it may transpile)
        self.guard = SqlGuard(catalog.physical_tables(), self.sql_dialect, settings.max_rows)
        self.schema = LogicalSchema.from_catalog(catalog)
        self.logical_guard = LogicalGuard(self.schema, settings.max_rows, settings.sql_max_joins, settings.sql_max_chars)
        self.rewriter = LogicalRewriter(self.schema, self.sql_dialect)
        anchor_table = catalog.anchor_table()
        self.resolver = LazyPeriodResolver(lambda: engine.max_date(anchor_table.rollup, anchor_table.time_column))
        self.normalizer = SqlNormalizer(catalog, self.resolver)
        self.renderer = LogicalSqlRenderer(catalog, self.resolver)

    @property
    def anchor(self) -> date:
        return self.resolver.anchor

    # ---- text-to-sql path ----
    def prepare_sql(self, logical_sql: str, mode: QueryMode = QueryMode.AUTO) -> PreparedSql:
        """Guard, normalise and rewrite model-written SQL. Raises GuardViolationError with a user-safe, repair-ready message."""
        validated = self.logical_guard.validate(logical_sql)
        intent = self.normalizer.normalize(validated.tree)
        rewritten = self.rewriter.rewrite(validated, mode)
        return PreparedSql(logical_sql, self.guard.check(rewritten.sql), rewritten.sources, intent, mode)

    def dry_run(self, prepared: PreparedSql) -> DryRunInfo:
        """Ask the engine to plan the statement. Engines without dry-run are assumed fine. Errors are rewritten in logical terms."""
        if not isinstance(self.engine, SupportsDryRun):
            return DryRunInfo(ok=True)
        info = self.engine.dry_run(prepared.physical_sql)
        if not info.ok and info.error:
            message = info.error
            for logical, physical in prepared.sources.items():
                message = message.replace(physical, logical)
            return DryRunInfo(False, message[:300], info.bytes_processed)
        limit = self.settings.sql_max_bytes_processed
        if limit and info.bytes_processed and info.bytes_processed > limit:
            raise GuardViolationError(f"The query would scan {info.bytes_processed:,} bytes (limit {limit:,}). Narrow the period or filters.")
        return info

    def execute_sql(self, prepared: PreparedSql, use_cache: bool = True) -> SqlOutcome:
        cacheable = use_cache and self.cache.enabled
        key = self.cache.intent_key(prepared.intent, prepared.mode) if cacheable else None
        if key and (hit := self.cache.get_result(key)):
            return SqlOutcome(prepared, QueryResult(hit["columns"], hit["rows"], 0.1, hit.get("stats", {})), CacheStatus.HIT)
        log.debug("sql: %s", prepared.physical_sql if self.settings.trace_payloads else f"{len(prepared.physical_sql)} chars")
        result = self.engine.run(prepared.physical_sql, self.settings.query_timeout_s)
        if key:
            self.cache.put_result(key, {"columns": result.columns, "rows": result.rows, "stats": result.stats})
        return SqlOutcome(prepared, result, CacheStatus.MISS if cacheable else CacheStatus.OFF)

    # ---- IR path ----
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
