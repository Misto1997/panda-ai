"""Daily question quotas: one per user and one global, counted per UTC day. Postgres when DATABASE_URL is set
(shared across Cloud Run instances), in-memory otherwise (per process)."""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Protocol

from app.core.db import PgPool
from app.core.errors import QuotaExceededError
from app.security.auth import AuthUser

GLOBAL_SUBJECT = "global"
NO_USER_LIMIT = 10**9

DDL = """
CREATE TABLE IF NOT EXISTS panda_usage (
  day date NOT NULL, subject text NOT NULL, count integer NOT NULL DEFAULT 0,
  PRIMARY KEY (day, subject)
)
"""
# Increment only while below the limit; no row returned means the limit was already reached.
BUMP_SQL = ("INSERT INTO panda_usage (day, subject, count) VALUES (%s, %s, 1) "
            "ON CONFLICT (day, subject) DO UPDATE SET count = panda_usage.count + 1 "
            "WHERE panda_usage.count < %s RETURNING count")


class LimitReached(Exception):
    def __init__(self, scope: str) -> None:
        super().__init__(scope)
        self.scope = scope  # "user" | "global"


class UsageStore(Protocol):
    def consume(self, day: date, subject: str, user_limit: int, global_limit: int) -> tuple[int, int]:
        """Atomically add one to the user and global counters, or raise LimitReached and change nothing."""

    def peek(self, day: date, subject: str) -> tuple[int, int]: ...


class MemoryUsageStore:
    def __init__(self) -> None:
        self._counts: dict[tuple[date, str], int] = {}
        self._lock = threading.Lock()

    def consume(self, day: date, subject: str, user_limit: int, global_limit: int) -> tuple[int, int]:
        with self._lock:
            self._counts = {k: v for k, v in self._counts.items() if k[0] >= day}  # drop past days
            used, total = self._counts.get((day, subject), 0), self._counts.get((day, GLOBAL_SUBJECT), 0)
            if used >= user_limit:
                raise LimitReached("user")
            if total >= global_limit:
                raise LimitReached("global")
            self._counts[(day, subject)], self._counts[(day, GLOBAL_SUBJECT)] = used + 1, total + 1
            return used + 1, total + 1

    def peek(self, day: date, subject: str) -> tuple[int, int]:
        with self._lock:
            return self._counts.get((day, subject), 0), self._counts.get((day, GLOBAL_SUBJECT), 0)


class PgUsageStore:
    def __init__(self, pool: PgPool) -> None:
        self._pool, self._ready, self._lock = pool, False, threading.Lock()

    def _ensure(self, conn) -> None:
        with self._lock:
            if not self._ready:
                conn.execute(DDL)
                self._ready = True

    def consume(self, day: date, subject: str, user_limit: int, global_limit: int) -> tuple[int, int]:
        with self._pool.connection() as conn:
            self._ensure(conn)
            try:
                with conn.transaction():  # raising inside rolls the user increment back when the global cap is hit
                    user = conn.execute(BUMP_SQL, (day, subject, user_limit)).fetchone()
                    if user is None:
                        raise LimitReached("user")
                    total = conn.execute(BUMP_SQL, (day, GLOBAL_SUBJECT, global_limit)).fetchone()
                    if total is None:
                        raise LimitReached("global")
            except LimitReached:
                raise
            return user[0], total[0]

    def peek(self, day: date, subject: str) -> tuple[int, int]:
        with self._pool.connection() as conn:
            self._ensure(conn)
            rows = dict(conn.execute("SELECT subject, count FROM panda_usage WHERE day = %s AND subject IN (%s, %s)",
                                     (day, subject, GLOBAL_SUBJECT)).fetchall())
        return rows.get(subject, 0), rows.get(GLOBAL_SUBJECT, 0)


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class QuotaService:
    def __init__(self, store: UsageStore, user_limit: int, global_limit: int, today: Callable[[], date] = _utc_today,
                 exempt_emails: frozenset[str] = frozenset()) -> None:
        self._store, self.user_limit, self.global_limit, self._today = store, user_limit, global_limit, today
        self._exempt = frozenset(e.lower() for e in exempt_emails)  # admins: no per-user cap (the global cap still applies)

    def _limit_for(self, user: AuthUser) -> int:
        return NO_USER_LIMIT if user.email.lower() in self._exempt else self.user_limit

    @staticmethod
    def _subject(user: AuthUser) -> str:
        return f"user:{user.uid}"

    def remaining(self, user: AuthUser) -> int:
        used, total = self._store.peek(self._today(), self._subject(user))
        return max(0, min(self._limit_for(user) - used, self.global_limit - total))

    def consume(self, user: AuthUser) -> int:
        """Charge one question. Returns what is left today, or raises QuotaExceededError (429)."""
        try:
            used, total = self._store.consume(self._today(), self._subject(user), self._limit_for(user), self.global_limit)
        except LimitReached as e:
            msg = (f"You have used your {self.user_limit} questions for today (UTC). Come back tomorrow." if e.scope == "user"
                   else "The demo reached its daily capacity. Please try again tomorrow.")
            raise QuotaExceededError(msg, details={"remaining": 0}) from e
        return max(0, min(self._limit_for(user) - used, self.global_limit - total))
