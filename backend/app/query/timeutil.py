"""Resolve relative time expressions against the dataset anchor (latest loaded date).
Intervals are half-open [start, end). 'today' is anchor+1 so 'yesterday' is the latest full day."""
from __future__ import annotations

import re
from datetime import date, timedelta


def resolve(expr: str, anchor: date) -> tuple[date, date]:
    e = expr.strip().lower()
    today = anchor + timedelta(days=1)
    first_of_month = today.replace(day=1)
    if m := re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s*\.\.\s*(\d{4}-\d{2}-\d{2})", e):
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2)) + timedelta(days=1)
    if m := re.fullmatch(r"last_(\d+)_days|last_n_days:(\d+)", e):
        n = int(m.group(1) or m.group(2))
        return today - timedelta(days=n), today
    mon = today - timedelta(days=today.weekday())
    table = {
        "today": (today, today + timedelta(days=1)),
        "yesterday": (anchor, today),
        "this_week": (mon, today),
        "last_week": (mon - timedelta(days=7), mon),
        "this_month": (first_of_month, today),
        "mtd": (first_of_month, today),
        "last_month": ((first_of_month - timedelta(days=1)).replace(day=1), first_of_month),
        "all_time": (date(2000, 1, 1), today),
    }
    if e not in table:
        raise ValueError(f"unsupported time expression: {expr}")
    return table[e]


def previous_period(start: date, end: date) -> tuple[date, date]:
    n = end - start
    return start - n, start
