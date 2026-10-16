"""Composition root: the only place where concrete implementations are chosen and wired together."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.agents.checkpoint import create_checkpointer
from app.agents.deps import NodeDependencies
from app.agents.graph import build_graph
from app.agents.runner import TurnRunner
from app.cache.semantic_cache import SemanticCache
from app.core.config import Settings, get_settings
from app.core.db import PgPool
from app.core.logging import configure_logging, get_logger
from app.history import FeedbackStore, HistoryStore, create_feedback_store, create_history_store
from app.engines.base import QueryEngine
from app.engines.factory import create_engine
from app.llm.base import LlmClient
from app.llm.embeddings import create_embedder
from app.llm.factory import create_llm
from app.llm.vocabulary import build_vocabulary
from app.presentation.chart import ChartBuilder
from app.prompts.registry import PROMPTS
from app.query.service import QueryService
from app.rca.investigator import RcaInvestigator
from app.search.factory import create_search
from app.security.service import Security, build_security
from app.search.hybrid import HybridSearch
from app.semantic.catalog import Catalog
from app.semantic.loader import load_catalog

log = get_logger("container")


@dataclass
class Container:
    settings: Settings
    catalog: Catalog
    engine: QueryEngine
    cache: SemanticCache
    llm: LlmClient
    search: HybridSearch
    query_service: QueryService
    runner: TurnRunner
    security: Security
    history: HistoryStore
    feedback: FeedbackStore
    pool: PgPool | None = None
    _closers: list[Callable[[], None]] = field(default_factory=list)

    def close(self) -> None:
        for close in reversed(self._closers):
            close()


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    configure_logging("DEBUG" if settings.trace_payloads and settings.log_level.upper() == "INFO" else settings.log_level)
    catalog = load_catalog(settings.semantic_dir)
    engine = create_engine(settings)
    cache = SemanticCache(settings)
    llm = create_llm(settings)
    pool = PgPool.from_settings(settings) if settings.uses_postgres else None  # lazy: no connection until first use
    search = create_search(settings, catalog, create_embedder(settings), pool)
    service = QueryService(catalog, engine, cache, settings)
    deps = NodeDependencies(settings=settings, catalog=catalog, llm=llm, prompts=PROMPTS, search=search, query_service=service,
                            investigator=RcaInvestigator(catalog, service), cache=cache, charts=ChartBuilder(catalog),
                            vocabulary=build_vocabulary(catalog))
    checkpointer, close_checkpointer = create_checkpointer(settings)
    runner = TurnRunner(build_graph(deps, checkpointer))
    log.info("started: llm=%s engine=%s search=%s (data anchor is resolved on first use; see /ready)", llm.name, engine.name, search.backend_name)
    closers = [engine.close, cache.close, close_checkpointer] + ([pool.close] if pool else [])
    return Container(settings, catalog, engine, cache, llm, search, service, runner, build_security(settings, pool), create_history_store(settings, pool), create_feedback_store(settings, pool), pool, closers)
