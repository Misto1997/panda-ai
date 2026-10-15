"""Index the semantic layer into Postgres/pgvector. Run in CI or via `make ingest`."""
import psycopg

from app.core.config import get_settings
from app.core.errors import ConfigurationError
from app.llm.embeddings import create_embedder
from app.search.pgvector import DDL, vector_literal
from app.semantic.loader import load_catalog


def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL is not set")
    docs = load_catalog(settings.semantic_dir).docs
    vectors = create_embedder(settings).embed([d.text for d in docs])
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(DDL.format(dim=settings.embedding_dim))
        conn.execute("TRUNCATE semantic_docs")
        for doc, vec in zip(docs, vectors):
            conn.execute("INSERT INTO semantic_docs (id, kind, title, text, embedding) VALUES (%s,%s,%s,%s,%s::vector)",
                         (doc.id, doc.kind.value, doc.title, doc.text, vector_literal(vec)))
    print(f"indexed {len(docs)} docs")


if __name__ == "__main__":
    main()
