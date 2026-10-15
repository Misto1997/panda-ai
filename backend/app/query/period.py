"""Resolve relative time expressions against the dataset anchor (latest loaded date).
Intervals are half-open [start, end). 'today' is anchor+1, so 'yesterday' is the latest full day."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.errors import UnsupportedTimeExpressionError

_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*\.\.\s*(\d{4}-\d{2}-\d{2})")
_LAST_N = re.compile(r"last_(\d+)_days|last_n_days:(\d+)")
MAX_DAYS = 3660


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
