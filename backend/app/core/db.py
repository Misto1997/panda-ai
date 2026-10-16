"""Lazily created psycopg connection pool shared by search, quota and bootstrap. Plain Postgres SQL only, so
AlloyDB and Cloud SQL are interchangeable (change DATABASE_URL). Put the password in PGPASSWORD, not in the URL."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

from app.core.config import Settings
from app.core.errors import ConfigurationError, DatabaseUnavailableError


class PgPool:
    def __init__(self, url: str, *, max_size: int = 5, connect_timeout_s: float = 5.0, pool_timeout_s: float = 10.0) -> None:
        if not url:
            raise ConfigurationError("DATABASE_URL is not set")
        self._url, self._max, self._connect, self._timeout = url, max_size, connect_timeout_s, pool_timeout_s
        self._pool: ConnectionPool | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, s: Settings) -> "PgPool":
        return cls(s.database_url, max_size=s.db_pool_max, connect_timeout_s=s.db_connect_timeout_s, pool_timeout_s=s.db_pool_timeout_s)

    def _get(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None:  # min_size=0: no connection is opened until the first query, so cold starts stay fast
                self._pool = ConnectionPool(
                    self._url, min_size=0, max_size=self._max, timeout=self._timeout, open=True,
                    kwargs={"connect_timeout": int(self._connect), "autocommit": True, "prepare_threshold": 0})
            return self._pool

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        """Autocommit connection; use `with conn.transaction():` for atomic multi-statement work."""
        try:
            with self._get().connection() as conn:
                yield conn
        except (PoolTimeout, psycopg.OperationalError) as e:
            raise DatabaseUnavailableError(f"database unavailable: {e}") from e
        except psycopg.Error as e:
            raise DatabaseUnavailableError(f"database error: {e}") from e

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()


def execute_script(conn: psycopg.Connection, script: str) -> None:
    """Run several DDL statements one by one. The pool uses prepared statements (prepare_threshold=0), and Postgres
    refuses multiple commands inside one prepared statement. Only for trusted, literal-free DDL: it splits on ';'."""
    for statement in filter(None, (part.strip() for part in script.split(";"))):
        conn.execute(statement)
