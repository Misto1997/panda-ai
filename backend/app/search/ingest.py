"""Index the semantic layer into Postgres/pgvector (AlloyDB or Cloud SQL). Idempotent and safe to re-run while the API serves.
`make ingest` or `python -m app.bootstrap index`."""
from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.db import PgPool, execute_script
from app.core.enums import VectorIndexKind
from app.core.errors import ConfigurationError
from app.llm.embeddings import create_embedder
from app.search.pgvector import DDL, INDEX_DDL, vector_literal
from app.semantic.loader import load_catalog

_DIM_SQL = ("SELECT a.atttypmod FROM pg_attribute a WHERE a.attrelid = to_regclass('semantic_docs') "
            "AND a.attname = 'embedding' AND NOT a.attisdropped")


def build_index(settings: Settings, pool: PgPool | None = None) -> int:
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL is not set")
    docs = load_catalog(settings.semantic_dir).docs
    vectors = create_embedder(settings).embed([d.text for d in docs])
    owned = pool is None
    pool = pool or PgPool.from_settings(settings)
    try:
        with pool.connection() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            row = conn.execute(_DIM_SQL).fetchone()
            with conn.transaction():  # atomic: the API never sees a moment without the table
                if row and row[0] != settings.embedding_dim:  # embedding model/dimension changed: the index is derived data, rebuild it
                    conn.execute("DROP TABLE semantic_docs")
                execute_script(conn, DDL.format(dim=settings.embedding_dim))
            with conn.transaction():
                for doc, vec in zip(docs, vectors):
                    conn.execute(
                        "INSERT INTO semantic_docs (id, kind, title, text, embedding) VALUES (%s,%s,%s,%s,%s::vector) "
                        "ON CONFLICT (id) DO UPDATE SET kind=EXCLUDED.kind, title=EXCLUDED.title, text=EXCLUDED.text, embedding=EXCLUDED.embedding",
                        (doc.id, doc.kind.value, doc.title, doc.text, vector_literal(vec)))
                conn.execute("DELETE FROM semantic_docs WHERE NOT (id = ANY(%s))", ([d.id for d in docs],))
            if settings.vector_index != VectorIndexKind.NONE:
                execute_script(conn, INDEX_DDL[settings.vector_index])
    finally:
        if owned:
            pool.close()
    return len(docs)


def main() -> None:
    print(f"indexed {build_index(get_settings())} docs")


if __name__ == "__main__":
    main()
