"""Resolve relative time expressions against the dataset anchor (latest loaded date).
Intervals are half-open [start, end). 'today' is anchor+1, so 'yesterday' is the latest full day."""
from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.errors import UnsupportedTimeExpressionError

_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*\.\.\s*(\d{4}-\d{2}-\d{2})")
_LAST_N = re.compile(r"last_(\d+)_days|last_n_days:(\d+)")
MAX_DAYS = 3660


TIME_GRAMMAR = ("today, yesterday, last_7_days, last_14_days, last_30_days, last_90_days, this_week, last_week, this_month, last_month, mtd, "
                "all_time, last_N_days (N a number), or an explicit range YYYY-MM-DD..YYYY-MM-DD")
_WORDS = re.compile(r"^(?:last|past|previous)_(\d+)_(day|days|week|weeks|month|months)$")


def normalize_time_expr(expr: str) -> str:
    """Tolerate how models spell periods: 'last 7 days', 'Past 2 weeks', 'last-month' -> the grammar resolve() understands."""
    e = re.sub(r"[\s\-]+", "_", (expr or "").strip().lower())
    if m := _WORDS.match(e):
        n, unit = int(m.group(1)), m.group(2)
        return f"last_{n * (7 if unit.startswith('week') else 30 if unit.startswith('month') else 1)}_days"
    return e.replace("past_", "last_", 1) if e.startswith("past_") else e


_COUNT = re.compile(r"\b(?:last|past|previous)\s+(\d+)\s+(day|days|week|weeks|month|months)\b")
_EXPLICIT = re.compile(r"(\d{4}-\d{2}-\d{2})\s*(?:to|until|through|\.\.|-|and)\s*(\d{4}-\d{2}-\d{2})")
_NAMED = [(re.compile(p), v) for p, v in (
    (r"\byesterday\b", "yesterday"), (r"\b(?:last|previous) week\b", "last_week"), (r"\bpast week\b", "last_7_days"),
    (r"\bthis week\b", "this_week"), (r"\b(?:last|previous) month\b", "last_month"), (r"\bpast month\b", "last_30_days"),
    (r"\b(?:this month|month to date|mtd)\b", "mtd"), (r"\ball time\b", "all_time"))]


def extract_time_expr(text: str) -> str | None:
    """The period a question names, in the grammar PeriodResolver understands, or None. Deterministic: models never get to guess dates."""
    q = (text or "").lower()
    if m := _EXPLICIT.search(q):
        return f"{m.group(1)}..{m.group(2)}"
    if m := _COUNT.search(q):
        n, unit = int(m.group(1)), m.group(2)
        return f"last_{n * (7 if unit.startswith('week') else 30 if unit.startswith('month') else 1)}_days"
    return next((value for pattern, value in _NAMED if pattern.search(q)), None)


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # exclusive

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    @property
    def last_day(self) -> date:
        return self.end - timedelta(days=1)

    def previous(self) -> "Period":
        return Period(self.start - (self.end - self.start), self.start)

    def as_expr(self) -> str:
        return f"{self.start}..{self.last_day}"


class PeriodResolver:
    def __init__(self, anchor: date) -> None:
        self.anchor = anchor
        self.today = anchor + timedelta(days=1)

    def resolve(self, expr: str) -> Period:
        e = expr.strip().lower()
        if m := _RANGE.fullmatch(e):
            try:
                start, last = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
            except ValueError as err:
                raise UnsupportedTimeExpressionError(f"Invalid date in '{expr}'.") from err
            if last < start:
                raise UnsupportedTimeExpressionError(f"Range '{expr}' ends before it starts.")
            return Period(start, last + timedelta(days=1))
        if m := _LAST_N.fullmatch(e):
            n = int(m.group(1) or m.group(2))
            if not 1 <= n <= MAX_DAYS:
                raise UnsupportedTimeExpressionError(f"'{expr}' is outside the supported range.")
            return Period(self.today - timedelta(days=n), self.today)
        named = self._named()
        if e not in named:
            raise UnsupportedTimeExpressionError(f"Unsupported time expression '{expr}'.")
        return named[e]

    def _named(self) -> dict[str, Period]:
        today, monday = self.today, self.today - timedelta(days=self.today.weekday())
        month_start = today.replace(day=1)
        return {
            "today": Period(today, today + timedelta(days=1)),
            "yesterday": Period(self.anchor, today),
            "this_week": Period(monday, today),
            "last_week": Period(monday - timedelta(days=7), monday),
            "this_month": Period(month_start, today),
            "mtd": Period(month_start, today),
            "last_month": Period((month_start - timedelta(days=1)).replace(day=1), month_start),
            "all_time": Period(date(2000, 1, 1), today),
        }


class LazyPeriodResolver(PeriodResolver):
    """Looks the anchor date up on first use (so the service can start, and report not-ready, before any data is loaded) and re-reads it every
    `ttl_s` seconds: the nightly refresh moves the data window while instances keep running. A failed re-read keeps the last known anchor."""

    def __init__(self, load_anchor: Callable[[], "date | tuple[date, date]"], ttl_s: float = 60.0, clock: Callable[[], float] = time.monotonic) -> None:
        """`load_anchor` returns the latest date, or (earliest, latest)."""
        self._load, self._ttl, self._clock = load_anchor, ttl_s, clock
        self._anchor: date | None = None
        self._first: date | None = None
        self._read_at = 0.0
        self._lock = threading.Lock()

    @property
    def anchor(self) -> date:
        with self._lock:
            known, fresh = self._anchor, self._anchor is not None and self._clock() - self._read_at < self._ttl
            if not fresh and known is not None:
                self._read_at = self._clock()  # one caller re-reads; the others keep using the known date meanwhile (and a flapping warehouse is not hammered)
        if fresh:
            return known
        try:
            loaded = self._load()  # warehouse call outside the lock; raises EngineError while the tables do not exist (retried on the next call)
        except Exception:
            if known is None:
                raise
            return known
        first, last = loaded if isinstance(loaded, tuple) else (None, loaded)
        with self._lock:
            self._anchor, self._first, self._read_at = last, first, self._clock()
        return last

    @property
    def first(self) -> date | None:
        """Earliest loaded date, or None when the loader does not report it."""
        self.anchor  # refreshes both bounds
        return self._first

    @property
    def today(self) -> date:
        return self.anchor + timedelta(days=1)
