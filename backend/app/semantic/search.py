"""Hybrid retrieval over the semantic layer: lexical (BM25 / Postgres FTS) + vector, fused with RRF.
Backends: in-memory (default, zero infra) or Postgres + pgvector (DATABASE_URL set)."""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

import numpy as np

from app.config import get_settings
from app.llm import embed
from app.semantic.catalog import Doc, load_catalog

_TOKEN = re.compile(r"[a-z0-9]+")
RRF_K = 60


def _tok(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    score: dict[str, float] = {}
    for ranking in rankings:
        for rank, id_ in enumerate(ranking):
            score[id_] = score.get(id_, 0.0) + 1.0 / (k + rank + 1)
    return score


class MemoryBackend:
    def __init__(self, docs: list[Doc]) -> None:
        self.docs = docs
        self.tokens = [_tok(f"{d.title} {d.id} {d.text}") for d in docs]
        self.df = Counter(t for toks in self.tokens for t in set(toks))
        self.avg = sum(map(len, self.tokens)) / max(1, len(docs))
        self.vecs = embed([d.text for d in docs])

    def lexical(self, q: str, n: int) -> list[str]:
        qt, N, scores = _tok(q), len(self.docs), []
        for d, toks in zip(self.docs, self.tokens):
            tf, s = Counter(toks), 0.0
            for t in qt:
                if t in tf:
                    idf = math.log(1 + (N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    s += idf * tf[t] * 2.5 / (tf[t] + 1.5 * (0.25 + 0.75 * len(toks) / self.avg))
            scores.append(s)
        order = np.argsort(scores)[::-1][:n]
        return [self.docs[i].id for i in order if scores[i] > 0]

    def vector(self, q: str, n: int) -> list[str]:
        sims = self.vecs @ embed([q])[0]
        return [self.docs[i].id for i in np.argsort(sims)[::-1][:n]]


class PgBackend:
    """pgvector + FTS. Table is rebuilt from the files by `python -m app.semantic.ingest`."""

    def __init__(self, url: str) -> None:
        import psycopg
        self.url = url
        self.psycopg = psycopg

    def lexical(self, q: str, n: int) -> list[str]:
        with self.psycopg.connect(self.url) as c:
            rows = c.execute(
                "SELECT id FROM semantic_docs WHERE tsv @@ plainto_tsquery('english', %s) "
                "ORDER BY ts_rank(tsv, plainto_tsquery('english', %s)) DESC LIMIT %s", (q, q, n)).fetchall()
        return [r[0] for r in rows]

    def vector(self, q: str, n: int) -> list[str]:
        vec = "[" + ",".join(f"{x:.6f}" for x in embed([q])[0]) + "]"
        with self.psycopg.connect(self.url) as c:
            rows = c.execute("SELECT id FROM semantic_docs ORDER BY embedding <=> %s::vector LIMIT %s", (vec, n)).fetchall()
        return [r[0] for r in rows]


class SemanticIndex:
    def __init__(self) -> None:
        self.cat = load_catalog()
        self.by_id = {d.id: d for d in self.cat.docs}
        url = get_settings().database_url
        self.backend = PgBackend(url) if url else MemoryBackend(self.cat.docs)
        self.backend_name = "pgvector+fts" if url else "memory(bm25+vector)"

    def search(self, query: str, k: int = 8, kinds: set[str] | None = None) -> list[Doc]:
        fused = rrf([self.backend.lexical(query, 20), self.backend.vector(query, 20)])
        ids = sorted(fused, key=fused.get, reverse=True)
        docs = [self.by_id[i] for i in ids if i in self.by_id and (not kinds or self.by_id[i].kind in kinds)][:k]
        # graph expansion: pull in the dimensions a hit metric allows, so the planner sees valid slices
        have = {d.id for d in docs}
        for d in list(docs):
            for dim in d.meta.get("dimensions", []):
                if dim not in have and dim in self.by_id:
                    docs.append(self.by_id[dim])
                    have.add(dim)
        return docs


@lru_cache
def get_index() -> SemanticIndex:
    return SemanticIndex()
