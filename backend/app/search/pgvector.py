"""Postgres backend: full-text search (tsvector) + pgvector cosine distance. Index built by `python -m app.search.ingest`."""
from __future__ import annotations

import psycopg

from app.core.errors import EngineError
from app.llm.embeddings import Embedder

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS semantic_docs (
  id text PRIMARY KEY, kind text NOT NULL, title text NOT NULL, text text NOT NULL,
  embedding vector({dim}),
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || id || ' ' || text)) STORED
);
CREATE INDEX IF NOT EXISTS semantic_docs_tsv ON semantic_docs USING gin (tsv);
"""


def vector_literal(vec) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


class PgVectorBackend:
    name = "pgvector+fts"

    def __init__(self, url: str, embedder: Embedder) -> None:
        self._url, self._embedder = url, embedder

    def lexical(self, query: str, limit: int) -> list[str]:
        sql = ("SELECT id FROM semantic_docs WHERE tsv @@ plainto_tsquery('english', %s) "
               "ORDER BY ts_rank(tsv, plainto_tsquery('english', %s)) DESC LIMIT %s")
        return self._fetch(sql, (query, query, limit))

    def vector(self, query: str, limit: int) -> list[str]:
        vec = vector_literal(self._embedder.embed([query])[0])
        return self._fetch("SELECT id FROM semantic_docs ORDER BY embedding <=> %s::vector LIMIT %s", (vec, limit))

    def _fetch(self, sql: str, params: tuple) -> list[str]:
        try:
            with psycopg.connect(self._url, connect_timeout=5) as conn:
                return [r[0] for r in conn.execute(sql, params).fetchall()]
        except psycopg.Error as e:
            raise EngineError(f"semantic index unavailable: {e}") from e
