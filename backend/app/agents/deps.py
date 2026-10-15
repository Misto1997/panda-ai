from __future__ import annotations

from dataclasses import dataclass

from app.cache.semantic_cache import SemanticCache
from app.core.config import Settings
from app.llm.base import LlmClient, Vocabulary
from app.presentation.chart import ChartBuilder
from app.prompts.registry import PromptRegistry
from app.query.service import QueryService
from app.rca.investigator import RcaInvestigator
from app.search.hybrid import HybridSearch
from app.semantic.catalog import Catalog


@dataclass(frozen=True)
class NodeDependencies:
    """Everything a node may use. Built once by the Container; nodes never reach for globals."""
    settings: Settings
    catalog: Catalog
    llm: LlmClient
    prompts: PromptRegistry
    search: HybridSearch
    query_service: QueryService
    investigator: RcaInvestigator
    cache: SemanticCache
    charts: ChartBuilder
    vocabulary: Vocabulary
