"""Read-only SQL guardrail applied to every statement before execution (defence in depth:
the compiler is the primary control, the guard catches anything unexpected)."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.config import get_settings


class GuardError(ValueError):
    pass


def check(sql: str, allowed_tables: set[str], dialect: str = "duckdb") -> str:
    if ";" in sql.strip().rstrip(";"):
        raise GuardError("multiple statements are not allowed")
    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"unparseable SQL: {e}") from e
    if not isinstance(tree, (exp.Select, exp.Subquery, exp.With)) and not tree.find(exp.Select):
        raise GuardError("only SELECT statements are allowed")
    banned = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Copy)
    if any(tree.find(b) for b in banned):
        raise GuardError("statement type not allowed")
    cte_names = {c.alias for c in tree.find_all(exp.CTE)}
    tables = {t.name for t in tree.find_all(exp.Table)} - cte_names
    illegal = tables - allowed_tables
    if illegal:
        raise GuardError(f"table(s) not in the governed layer: {sorted(illegal)}")
    cap = get_settings().max_rows
    return f"SELECT * FROM ({sql.strip().rstrip(';')}) g LIMIT {cap}"
