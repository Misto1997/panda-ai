from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    elapsed_ms: float
    stats: dict = field(default_factory=dict)  # engine-specific (e.g. bytes scanned on BigQuery)


@runtime_checkable
class QueryEngine(Protocol):
    """Port implemented by every analytics backend. The compiler emits DuckDB SQL; engines with another
    dialect transpile in `prepare`."""
    name: str
    dialect: str

    def run(self, sql: str, timeout_s: float) -> QueryResult: ...
    def max_date(self, table: str, column: str) -> date: ...
    def row_count(self, table: str) -> int: ...
    def close(self) -> None: ...
