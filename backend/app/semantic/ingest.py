"""Index the semantic layer into Postgres/pgvector. Run in CI or `make ingest`."""
import psycopg

from app.config import get_settings
from app.llm import embed
from app.semantic.catalog import load_catalog

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS semantic_docs (
  id text PRIMARY KEY, kind text NOT NULL, title text NOT NULL, text text NOT NULL,
  embedding vector({dim}),
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || id || ' ' || text)) STORED
);
CREATE INDEX IF NOT EXISTS semantic_docs_tsv ON semantic_docs USING gin (tsv);
"""


def main() -> None:
    s = get_settings()
    assert s.database_url, "DATABASE_URL not set"
    docs = load_catalog().docs
    vecs = embed([d.text for d in docs])
    with psycopg.connect(s.database_url, autocommit=True) as c:
        c.execute(DDL.format(dim=s.embedding_dim))
        c.execute("TRUNCATE semantic_docs")
        for d, v in zip(docs, vecs):
            c.execute("INSERT INTO semantic_docs (id, kind, title, text, embedding) VALUES (%s,%s,%s,%s,%s::vector)",
                      (d.id, d.kind, d.title, d.text, "[" + ",".join(f"{x:.6f}" for x in v) + "]"))
    print(f"indexed {len(docs)} docs")


if __name__ == "__main__":
    main()
