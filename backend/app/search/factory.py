from app.core.config import Settings
from app.llm.embeddings import Embedder
from app.search.hybrid import HybridSearch
from app.search.memory import MemoryBackend
from app.search.pgvector import PgVectorBackend
from app.semantic.catalog import Catalog


def create_search(settings: Settings, catalog: Catalog, embedder: Embedder) -> HybridSearch:
    backend = PgVectorBackend(settings.database_url, embedder) if settings.database_url else MemoryBackend(catalog.docs, embedder)
    return HybridSearch(catalog, backend)
