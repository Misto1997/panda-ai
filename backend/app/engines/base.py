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


@dataclass
class DryRunInfo:
    """Outcome of validating a statement without running it (DuckDB: EXPLAIN; BigQuery: dry-run job)."""
    ok: bool
    error: str | None = None            # engine message when not ok (fed back to the SQL repair prompt)
    bytes_processed: int | None = None  # estimated scan size when the engine reports one


@runtime_checkable
class SupportsDryRun(Protocol):
    """Optional capability. Callers use `isinstance(engine, SupportsDryRun)`; engines without it are simply executed."""

    def dry_run(self, sql: str) -> DryRunInfo: ...


@runtime_checkable
class QueryEngine(Protocol):
    """Port implemented by every analytics backend. The compiler emits DuckDB SQL; engines with another
    dialect transpile in `prepare`."""
    name: str
    dialect: str

    def run(self, sql: str, timeout_s: float) -> QueryResult: ...
    def max_date(self, table: str, column: str) -> date: ...
    def date_range(self, table: str, column: str) -> tuple[date, date]: ...
    def row_count(self, table: str) -> int: ...
    def close(self) -> None: ...
