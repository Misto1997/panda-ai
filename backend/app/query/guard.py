"""Read-only SQL guardrail applied to every statement before execution. The compiler is the primary
control; the guard is defence in depth against anything unexpected."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.core.errors import GuardViolationError

_FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Copy, exp.Merge)


class SqlGuard:
    def __init__(self, allowed_tables: set[str], dialect: str, max_rows: int) -> None:
        self.allowed, self.dialect, self.max_rows = allowed_tables, dialect, max_rows

    def check(self, sql: str) -> str:
        """Returns the SQL wrapped with a row cap, or raises GuardViolationError."""
        stripped = sql.strip().rstrip(";")
        if ";" in stripped:
            raise GuardViolationError("Multiple statements are not allowed.")
        try:
            tree = sqlglot.parse_one(stripped, dialect=self.dialect)
        except sqlglot.errors.ParseError as e:
            raise GuardViolationError(f"Unparseable SQL: {e}") from e
        if not isinstance(tree, (exp.Select, exp.Subquery, exp.With)) and tree.find(exp.Select) is None:
            raise GuardViolationError("Only SELECT statements are allowed.")
        if any(tree.find(kind) for kind in _FORBIDDEN):
            raise GuardViolationError("Statement type not allowed.")
        cte_names = {c.alias for c in tree.find_all(exp.CTE)}
        illegal = {t.name for t in tree.find_all(exp.Table)} - cte_names - self.allowed
        if illegal:
            raise GuardViolationError(f"Table(s) outside the governed layer: {sorted(illegal)}.")
        return f"SELECT * FROM ({stripped}) g LIMIT {self.max_rows}"
