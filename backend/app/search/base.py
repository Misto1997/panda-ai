from typing import Protocol


class SearchBackend(Protocol):
    """Ranked retrieval returning doc ids. Hybrid search fuses the two rankings."""
    name: str

    def lexical(self, query: str, limit: int) -> list[str]: ...
    def vector(self, query: str, limit: int) -> list[str]: ...
