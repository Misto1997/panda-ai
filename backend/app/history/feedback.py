"""Thumbs up/down on answers, with reasons and an optional comment. Recorded only (no model reads it yet): the table is the raw material for a
future adaptive loop (failing questions become examples or glossary fixes). Memory (per process) or Postgres, scoped by owner."""
from __future__ import annotations

import functools
import json
import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from psycopg.types.json import Jsonb

from app.core.config import Settings
from app.core.db import PgPool, execute_script
from app.core.enums import StoreKind

COMMENT_MAX = 240
REASON_MAX = 40
REASONS_MAX = 5
SQL_MAX = 4000
ANSWER_MAX = 2000
OWNER_CAP = 2000  # rows per user: feedback is bounded even if someone scripts the endpoint

DDL = """
CREATE TABLE IF NOT EXISTS panda_feedback (
  owner text NOT NULL, thread_id text NOT NULL, turn integer NOT NULL,
  question text NOT NULL, rating text NOT NULL CHECK (rating IN ('up', 'down')),
  reasons jsonb NOT NULL DEFAULT '[]', comment text NOT NULL DEFAULT '',
  route text, path text, sql text, answer text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner, thread_id, turn)
);
CREATE INDEX IF NOT EXISTS panda_feedback_rating_idx ON panda_feedback (rating, created_at)
"""

_dumps = functools.partial(json.dumps, allow_nan=False, default=str)


def clean_reasons(reasons: list[str]) -> list[str]:
    seen: list[str] = []
    for r in reasons:
        r = " ".join(str(r).split())[:REASON_MAX]
        if r and r not in seen:
            seen.append(r)
    return seen[:REASONS_MAX]


def snapshot(response: dict[str, Any] | None) -> dict[str, Any]:
    """What we keep about the answer being rated: enough to reproduce the problem, no result rows."""
    r = response or {}
    meta = r.get("meta") or {}
    return {"route": meta.get("route"), "path": meta.get("path"), "sql": (r.get("sql") or "")[:SQL_MAX] or None,
            "answer": (r.get("text") or "")[:ANSWER_MAX] or None}


class FeedbackStore(Protocol):
    def put(self, owner: str, thread_id: str, turn: int, question: str, rating: str, reasons: list[str], comment: str,
            context: dict[str, Any]) -> None:
        """Insert or replace the rating of one turn. Raises FeedbackCapReached past OWNER_CAP rows."""

    def ratings(self, owner: str, thread_id: str) -> dict[int, str]: ...

    def delete_thread(self, owner: str, thread_id: str) -> None:
        """Called when the user deletes a chat: its ratings (which hold question and SQL text) go with it."""


class FeedbackCapReached(Exception):
    pass


class MemoryFeedbackStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, owner, thread_id, turn, question, rating, reasons, comment, context) -> None:
        key = (owner, thread_id, turn)
        with self._lock:
            if key not in self._rows and sum(1 for k in self._rows if k[0] == owner) >= OWNER_CAP:
                raise FeedbackCapReached
            self._rows[key] = {"question": question, "rating": rating, "reasons": list(reasons), "comment": comment, **context,
                               "updated_at": datetime.now(timezone.utc)}

    def ratings(self, owner: str, thread_id: str) -> dict[int, str]:
        with self._lock:
            return {k[2]: v["rating"] for k, v in self._rows.items() if k[0] == owner and k[1] == thread_id}

    def delete_thread(self, owner: str, thread_id: str) -> None:
        with self._lock:
            for k in [k for k in self._rows if k[0] == owner and k[1] == thread_id]:
                del self._rows[k]

    def rows(self) -> list[dict[str, Any]]:  # tests and local inspection
        with self._lock:
            return [{"owner": k[0], "thread_id": k[1], "turn": k[2], **v} for k, v in self._rows.items()]


class PostgresFeedbackStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool, self._ready, self._lock = pool, False, threading.Lock()

    def _ensure(self, conn) -> None:
        with self._lock:
            if not self._ready:
                execute_script(conn, DDL)
                self._ready = True

    def put(self, owner, thread_id, turn, question, rating, reasons, comment, context) -> None:
        with self._pool.connection() as conn:
            self._ensure(conn)
            with conn.transaction():
                exists = conn.execute("SELECT 1 FROM panda_feedback WHERE owner = %s AND thread_id = %s AND turn = %s", (owner, thread_id, turn)).fetchone()
                if not exists and conn.execute("SELECT count(*) FROM panda_feedback WHERE owner = %s", (owner,)).fetchone()[0] >= OWNER_CAP:
                    raise FeedbackCapReached
                conn.execute(
                    "INSERT INTO panda_feedback (owner, thread_id, turn, question, rating, reasons, comment, route, path, sql, answer) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (owner, thread_id, turn) DO UPDATE SET rating = EXCLUDED.rating, reasons = EXCLUDED.reasons, "
                    "comment = EXCLUDED.comment, question = EXCLUDED.question, route = EXCLUDED.route, path = EXCLUDED.path, "
                    "sql = EXCLUDED.sql, answer = EXCLUDED.answer, updated_at = now()",
                    (owner, thread_id, turn, question, rating, Jsonb(reasons, dumps=_dumps), comment,
                     context.get("route"), context.get("path"), context.get("sql"), context.get("answer")))

    def delete_thread(self, owner: str, thread_id: str) -> None:
        with self._pool.connection() as conn:
            self._ensure(conn)
            conn.execute("DELETE FROM panda_feedback WHERE owner = %s AND thread_id = %s", (owner, thread_id))

    def ratings(self, owner: str, thread_id: str) -> dict[int, str]:
        with self._pool.connection() as conn:
            self._ensure(conn)
            rows = conn.execute("SELECT turn, rating FROM panda_feedback WHERE owner = %s AND thread_id = %s", (owner, thread_id)).fetchall()
        return {r[0]: r[1] for r in rows}


def create_feedback_store(settings: Settings, pool: PgPool | None) -> FeedbackStore:
    return PostgresFeedbackStore(pool) if settings.history_store == StoreKind.POSTGRES and pool else MemoryFeedbackStore()
