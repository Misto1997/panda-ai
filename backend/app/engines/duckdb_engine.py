from __future__ import annotations

import threading
import time
from datetime import date, datetime
from decimal import Decimal

import duckdb

from app.core.errors import EngineError, QueryTimeoutError
from app.core.logging import get_logger
from app.engines.base import DryRunInfo, QueryResult

log = get_logger("engine.duckdb")


def to_jsonable(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    if isinstance(value, Decimal):
        return float(value)
    return value


class DuckDBEngine:
    name = "duckdb"
    dialect = "duckdb"

    def __init__(self, path: str) -> None:
        try:
            self._con = duckdb.connect(path, read_only=True)
        except duckdb.Error as e:
            raise EngineError(f"cannot open DuckDB at {path}: {e}. Run `make data` first.") from e

    def run(self, sql: str, timeout_s: float) -> QueryResult:
        cursor = self._con.cursor()
        timer = threading.Timer(timeout_s, cursor.interrupt)  # DuckDB has no statement timeout; interrupt the cursor
        timer.start()
        started = time.perf_counter()
        try:
            cursor.execute(sql)
            columns = [d[0] for d in cursor.description]
            rows = [[to_jsonable(v) for v in row] for row in cursor.fetchall()]
        except duckdb.InterruptException as e:
            raise QueryTimeoutError(f"The query took longer than {timeout_s:.0f}s. Narrow the period or the dimensions.") from e
        except duckdb.Error as e:
            raise EngineError(f"engine rejected the query: {e}") from e
        finally:
            timer.cancel()
            cursor.close()
        elapsed = (time.perf_counter() - started) * 1000
        log.debug("ran query in %.1f ms, %d rows", elapsed, len(rows))
        return QueryResult(columns, rows, elapsed)

    def dry_run(self, sql: str) -> DryRunInfo:
        """Plan the statement (binds tables and columns, type checks) without executing it."""
        cursor = self._con.cursor()
        try:
            cursor.execute(f"EXPLAIN {sql}")
            return DryRunInfo(ok=True)
        except duckdb.Error as e:
            return DryRunInfo(ok=False, error=str(e).splitlines()[0])
        finally:
            cursor.close()

    def max_date(self, table: str, column: str) -> date:
        value = self._con.execute(f"SELECT MAX({column}) FROM {table}").fetchone()[0]
        if value is None:
            raise EngineError(f"table {table} is empty")
        return value

    def row_count(self, table: str) -> int:
        return self._con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def close(self) -> None:
        self._con.close()
