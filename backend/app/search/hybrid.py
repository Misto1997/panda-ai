"""Hybrid retrieval: lexical + vector rankings fused with reciprocal rank fusion (RRF), then graph expansion."""
from __future__ import annotations

from app.core.enums import DocKind
from app.core.errors import PandaError
from app.core.logging import get_logger
from app.search.base import SearchBackend
from app.semantic.catalog import Catalog
from app.semantic.models import Doc

log = get_logger("search")
RRF_K = 60
CANDIDATES = 20


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


class HybridSearch:
    def __init__(self, catalog: Catalog, backend: SearchBackend) -> None:
        self._by_id = {d.id: d for d in catalog.docs}
        self._backend = backend

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @staticmethod
    def _ranking(fn, query: str) -> list[str]:
        """One half of the hybrid failing (embedding outage, database blip) degrades to the other half instead of failing the turn."""
        try:
            return fn(query, CANDIDATES)
        except PandaError as e:
            log.warning("search half unavailable, continuing with the other: %s", e)
            return []

    def search(self, query: str, limit: int = 8, kinds: set[DocKind] | None = None) -> list[Doc]:
        fused = reciprocal_rank_fusion([self._ranking(self._backend.lexical, query), self._ranking(self._backend.vector, query)])
        ranked = [self._by_id[i] for i in sorted(fused, key=fused.get, reverse=True) if i in self._by_id]
        hits = [d for d in ranked if not kinds or d.kind in kinds][:limit]
        # Graph expansion: a metric hit pulls in the dimensions it allows so the planner only sees valid slices.
        seen = {d.id for d in hits}
        for doc in list(hits):
            for related in doc.related:
                if related not in seen and related in self._by_id:
                    hits.append(self._by_id[related])
                    seen.add(related)
        return hits
