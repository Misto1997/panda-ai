"""Per-user chat history: threads and their turns. Memory (per process) or Postgres (shared across Cloud Run instances).
Everything is scoped by `owner` (the authenticated uid). Callers treat history as best effort and must never let it fail a chat turn."""
from __future__ import annotations

import functools
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.core.db import PgPool, execute_script
from app.core.enums import StoreKind

MAX_THREADS = 50
MAX_TURNS = 60
RETENTION_DAYS = 30
TITLE_CHARS = 60

DDL = """
CREATE TABLE IF NOT EXISTS panda_threads (
  owner text NOT NULL, thread_id text NOT NULL, title text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner, thread_id)
);
CREATE TABLE IF NOT EXISTS panda_turns (
  owner text NOT NULL, thread_id text NOT NULL, idx integer NOT NULL, question text NOT NULL, response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner, thread_id, idx)
);
CREATE INDEX IF NOT EXISTS panda_threads_updated_idx ON panda_threads (updated_at)
"""

_dumps = functools.partial(json.dumps, allow_nan=False, default=str)


def make_title(question: str) -> str:
    text = " ".join(question.split())
    return text if len(text) <= TITLE_CHARS else text[:TITLE_CHARS]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HistoryStore(Protocol):
    def record(self, owner: str, thread_id: str, question: str, response: dict[str, Any]) -> None:
        """Append one finished turn (creates the thread on first use) and apply the caps and retention."""

    def list_threads(self, owner: str) -> list[dict[str, Any]]:
        """Newest first: {id, title, updated_at (datetime), turns}."""

    def get_thread(self, owner: str, thread_id: str) -> dict[str, Any] | None:
        """{id, title, updated_at, turns: [{question, response, created_at}]} in order, or None."""

    def delete_thread(self, owner: str, thread_id: str) -> bool: ...


class MemoryHistoryStore:
    def __init__(self, clock=_now) -> None:
        self._threads: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock, self._clock = threading.Lock(), clock

    def record(self, owner: str, thread_id: str, question: str, response: dict[str, Any]) -> None:
        now = self._clock()
        payload = json.loads(_dumps(response))  # same serialisation rules as Postgres; also detaches from live objects
        with self._lock:
            cutoff = now - timedelta(days=RETENTION_DAYS)
            self._threads = {k: v for k, v in self._threads.items() if v["updated_at"] >= cutoff}
            t = self._threads.setdefault((owner, thread_id), {"title": make_title(question), "updated_at": now, "turns": []})
            t["updated_at"] = now
            t["turns"] = (t["turns"] + [{"question": question, "response": payload, "created_at": now}])[-MAX_TURNS:]
            mine = sorted((k for k in self._threads if k[0] == owner), key=lambda k: self._threads[k]["updated_at"])
            for k in mine[:-MAX_THREADS]:
                del self._threads[k]

    def list_threads(self, owner: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [{"id": k[1], "title": v["title"], "updated_at": v["updated_at"], "turns": len(v["turns"])}
                    for k, v in self._threads.items() if k[0] == owner]
        return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    def get_thread(self, owner: str, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            t = self._threads.get((owner, thread_id))
            if t is None:
                return None
            return {"id": thread_id, "title": t["title"], "updated_at": t["updated_at"], "turns": [dict(x) for x in t["turns"]]}

    def delete_thread(self, owner: str, thread_id: str) -> bool:
        with self._lock:
            return self._threads.pop((owner, thread_id), None) is not None


class PostgresHistoryStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool, self._ready, self._lock = pool, False, threading.Lock()

    def _ensure(self, conn) -> None:
        with self._lock:
            if not self._ready:
                execute_script(conn, DDL)  # one statement at a time: the pool uses prepared statements
                self._ready = True

    def record(self, owner: str, thread_id: str, question: str, response: dict[str, Any]) -> None:
        payload = Jsonb(response, dumps=_dumps)
        with self._pool.connection() as conn:
            self._ensure(conn)
            with conn.transaction():
                conn.execute(
                    "INSERT INTO panda_threads (owner, thread_id, title) VALUES (%s, %s, %s) "
                    "ON CONFLICT (owner, thread_id) DO UPDATE SET updated_at = now()", (owner, thread_id, make_title(question)))
                row = conn.execute("SELECT coalesce(max(idx), -1) + 1 FROM panda_turns WHERE owner = %s AND thread_id = %s",
                                   (owner, thread_id)).fetchone()
                idx = row[0]
                conn.execute("INSERT INTO panda_turns (owner, thread_id, idx, question, response) VALUES (%s, %s, %s, %s, %s)",
                             (owner, thread_id, idx, question, payload))
                conn.execute("DELETE FROM panda_turns WHERE owner = %s AND thread_id = %s AND idx <= %s",
                             (owner, thread_id, idx - MAX_TURNS))
                # caps and retention, opportunistically on write
                conn.execute("DELETE FROM panda_threads WHERE updated_at < now() - make_interval(days => %s)", (RETENTION_DAYS,))
                conn.execute("DELETE FROM panda_threads WHERE owner = %s AND thread_id IN ("
                             "SELECT thread_id FROM panda_threads WHERE owner = %s ORDER BY updated_at DESC OFFSET %s)",
                             (owner, owner, MAX_THREADS))
                conn.execute("DELETE FROM panda_turns t WHERE NOT EXISTS ("
                             "SELECT 1 FROM panda_threads h WHERE h.owner = t.owner AND h.thread_id = t.thread_id)")

    def list_threads(self, owner: str) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            self._ensure(conn)
            rows = conn.execute(
                "SELECT h.thread_id, h.title, h.updated_at, (SELECT count(*) FROM panda_turns t WHERE t.owner = h.owner AND t.thread_id = h.thread_id) "
                "FROM panda_threads h WHERE h.owner = %s AND h.updated_at >= now() - make_interval(days => %s) "
                "ORDER BY h.updated_at DESC LIMIT %s", (owner, RETENTION_DAYS, MAX_THREADS)).fetchall()
        return [{"id": r[0], "title": r[1], "updated_at": r[2], "turns": r[3]} for r in rows]

    def get_thread(self, owner: str, thread_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            self._ensure(conn)
            head = conn.execute("SELECT title, updated_at FROM panda_threads WHERE owner = %s AND thread_id = %s",
                                (owner, thread_id)).fetchone()
            if head is None:
                return None
            turns = conn.execute("SELECT question, response, created_at FROM panda_turns WHERE owner = %s AND thread_id = %s ORDER BY idx",
                                 (owner, thread_id)).fetchall()
        return {"id": thread_id, "title": head[0], "updated_at": head[1],
                "turns": [{"question": t[0], "response": t[1], "created_at": t[2]} for t in turns]}

    def delete_thread(self, owner: str, thread_id: str) -> bool:
        with self._pool.connection() as conn:
            self._ensure(conn)
            with conn.transaction():
                conn.execute("DELETE FROM panda_turns WHERE owner = %s AND thread_id = %s", (owner, thread_id))
                cur = conn.execute("DELETE FROM panda_threads WHERE owner = %s AND thread_id = %s", (owner, thread_id))
                return cur.rowcount > 0


def create_history_store(settings: Settings, pool: PgPool | None) -> HistoryStore:
    return PostgresHistoryStore(pool) if settings.history_store == StoreKind.POSTGRES and pool else MemoryHistoryStore()
