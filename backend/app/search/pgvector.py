"""Postgres backend: full-text search (tsvector) + pgvector cosine distance. Index built by `python -m app.search.ingest`.
Standard SQL: runs unchanged on AlloyDB and Cloud SQL."""
from __future__ import annotations

from app.core.db import PgPool
from app.core.enums import VectorIndexKind
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

# Optional ANN indexes. Pointless for a few dozen rows (exact scan is faster), useful as a scale-up demo.
# ScaNN is AlloyDB-only and unverified here; check parameters in the AlloyDB docs before enabling.
INDEX_DDL = {
    VectorIndexKind.NONE: "",
    VectorIndexKind.HNSW: "CREATE INDEX IF NOT EXISTS semantic_docs_embedding ON semantic_docs USING hnsw (embedding vector_cosine_ops);",
    VectorIndexKind.SCANN: ("CREATE EXTENSION IF NOT EXISTS alloydb_scann;"
                            "CREATE INDEX IF NOT EXISTS semantic_docs_embedding ON semantic_docs USING scann (embedding cosine) WITH (num_leaves=5);"),
}


def vector_literal(vec) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


class PgVectorBackend:
    name = "pgvector+fts"

    def __init__(self, pool: PgPool, embedder: Embedder) -> None:
        self._pool, self._embedder = pool, embedder

    def lexical(self, query: str, limit: int) -> list[str]:
        sql = ("SELECT id FROM semantic_docs WHERE tsv @@ plainto_tsquery('english', %s) "
               "ORDER BY ts_rank(tsv, plainto_tsquery('english', %s)) DESC LIMIT %s")
        return self._fetch(sql, (query, query, limit))

    def vector(self, query: str, limit: int) -> list[str]:
        vec = vector_literal(self._embedder.embed([query])[0])
        return self._fetch("SELECT id FROM semantic_docs ORDER BY embedding <=> %s::vector LIMIT %s", (vec, limit))

    def _fetch(self, sql: str, params: tuple) -> list[str]:
        with self._pool.connection() as conn:
            return [r[0] for r in conn.execute(sql, params).fetchall()]
