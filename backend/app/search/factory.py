from app.core.config import Settings
from app.core.db import PgPool
from app.core.enums import SearchBackendKind
from app.core.errors import ConfigurationError
from app.llm.embeddings import Embedder
from app.search.hybrid import HybridSearch
from app.search.memory import MemoryBackend
from app.search.pgvector import PgVectorBackend
from app.semantic.catalog import Catalog


def create_search(settings: Settings, catalog: Catalog, embedder: Embedder, pool: PgPool | None = None) -> HybridSearch:
    if settings.search_backend == SearchBackendKind.PGVECTOR:
        if pool is None:
            raise ConfigurationError("search_backend=pgvector needs a Postgres pool (DATABASE_URL)")
        backend = PgVectorBackend(pool, embedder)
    else:
        backend = MemoryBackend(catalog.docs, embedder)
    return HybridSearch(catalog, backend)
