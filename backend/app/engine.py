"""Query engines. DuckDB for local; BigQuery adapter lands in phase 2 behind the same interface."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache

import duckdb
import sqlglot

from app.config import get_settings


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    elapsed_ms: float
    stats: dict = field(default_factory=dict)


def _jsonable(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    if isinstance(v, Decimal):
        return float(v)
    return v


class DuckDBEngine:
    name = "duckdb"
    dialect = "duckdb"

    def __init__(self, path: str) -> None:
        self.path = path
        self._con = duckdb.connect(path, read_only=True)

    def anchor(self) -> date:
        return self._con.execute("SELECT MAX(order_date) FROM agg_orders_daily").fetchone()[0]

    def row_count(self, table: str) -> int:
        return self._con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def run(self, sql: str) -> QueryResult:
        t0 = time.perf_counter()
        cur = self._con.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [[_jsonable(v) for v in r] for r in cur.fetchall()]
        return QueryResult(cols, rows, (time.perf_counter() - t0) * 1000)

    def transpile(self, sql: str, to: str) -> str:
        return sqlglot.transpile(sql, read="duckdb", write=to)[0]


@lru_cache
def get_engine():
    s = get_settings()
    if s.engine == "duckdb":
        return DuckDBEngine(s.duckdb_path)
    raise NotImplementedError(f"engine '{s.engine}' arrives in phase 2")
