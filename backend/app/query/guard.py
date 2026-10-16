"""Read-only SQL guardrails.

LogicalGuard validates LLM-written SQL against the logical semantic tables (AST based, messages double as repair feedback).
SqlGuard is the last line of defence on the physical SQL that is about to run (compiler output or rewriter output)."""
from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.core.errors import GuardViolationError
from app.query.logical import Analysis, LogicalSchema, analyze
from app.semantic.models import LOGICAL_DIALECT

_FORBIDDEN = tuple(getattr(exp, n) for n in (
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command", "Copy", "Merge", "Into", "Set", "Use", "Pragma",
    "Describe", "TruncateTable", "Transaction", "Commit", "Rollback", "Attach", "Detach", "Lock", "Install") if hasattr(exp, n))
_NO_SOURCE = tuple(getattr(exp, n) for n in ("Unnest", "Lateral", "Values", "Pivot", "TableSample") if hasattr(exp, n))

# Functions the model may call. Anything else (including every anonymous/unknown function such as read_csv, pg_sleep) is rejected.
_ALLOWED_FUNCTIONS = tuple(getattr(exp, n) for n in (
    "Sum", "Count", "Avg", "Min", "Max", "Round", "Cast", "TryCast", "Coalesce", "Nullif", "Abs", "Ceil", "Floor", "Sqrt", "Pow",
    "Ln", "Log", "Greatest", "Least", "If", "Case", "DateTrunc", "TimestampTrunc", "DateDiff", "TsOrDsAdd",
    "TsOrDsDiff", "TsOrDsToDate", "TsOrDsToTimestamp", "Date", "StrToDate", "Extract", "Year", "Month", "Day", 
     "Lower", "Upper", "Concat", "Length", "Substring", "Rank", "DenseRank", "RowNumber", "Lag", "Lead",
    "FirstValue", "LastValue", "Window", "Distinct", "Between", "In", "Exists", "Stddev", "StddevPop",
    "Variance", "Paren", "Div", "Mod", "SafeDivide", "DateStrToDate", "Trim", "Left", "Right") if hasattr(exp, n))
_JOIN_SOURCES = (exp.Table,)
MAX_SQL_CHARS = 6000


@dataclass
class ValidatedSql:
    """Parsed logical SQL plus the per-reference column usage the rewriter needs."""
    tree: exp.Expression
    analysis: Analysis


_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n?(.*?)\n?```\s*$", re.S)


def _strip_fence(sql: str | None) -> str:
    """Models often wrap SQL in a markdown code fence; accept it instead of burning a repair attempt."""
    text = (sql or "").strip()
    match = _FENCE.match(text)
    return (match.group(1) if match else text).strip().rstrip(";").strip()


class LogicalGuard:
    def __init__(self, schema: LogicalSchema, max_rows: int, max_joins: int = 3, max_chars: int = MAX_SQL_CHARS) -> None:
        self.schema, self.max_rows, self.max_joins, self.max_chars = schema, max_rows, max_joins, max_chars

    def validate(self, sql: str) -> ValidatedSql:
        tree = self._parse(sql)
        self._statement_rules(tree)
        self._source_rules(tree)
        self._function_rules(tree)
        analysis = analyze(tree, self.schema)
        self._measure_rules(analysis)
        return ValidatedSql(tree, analysis)

    # ---- rules ----
    def _parse(self, sql: str) -> exp.Expression:
        text = _strip_fence(sql)
        if not text:
            raise GuardViolationError("The SQL is empty.")
        if len(text) > self.max_chars:
            raise GuardViolationError(f"The SQL is too long ({len(text)} characters, max {self.max_chars}). Simplify it.")
        try:
            statements = [s for s in sqlglot.parse(text, dialect=LOGICAL_DIALECT) if s is not None]
        except sqlglot.errors.SqlglotError as e:
            raise GuardViolationError(f"Unparseable SQL: {str(e).splitlines()[0]}") from e
        if len(statements) != 1:
            raise GuardViolationError("Exactly one SELECT statement is allowed.")
        return statements[0]

    def _statement_rules(self, tree: exp.Expression) -> None:
        if not isinstance(tree, (exp.Select, exp.SetOperation)):
            raise GuardViolationError("Only a single SELECT (optionally with WITH) is allowed.")
        if any(tree.find(kind) for kind in _FORBIDDEN):
            raise GuardViolationError("Statement type not allowed. Only read-only SELECT queries are permitted.")
        for star in tree.find_all(exp.Star):
            if not isinstance(star.parent, exp.Count):  # COUNT(*) is judged by the row-count rule
                raise GuardViolationError("SELECT * is not allowed. List the columns you need explicitly.")

    def _source_rules(self, tree: exp.Expression) -> None:
        ctes = {c.alias.lower() for c in tree.find_all(exp.CTE)}
        for table in tree.find_all(exp.Table):
            if not isinstance(table.this, exp.Identifier) or table.args.get("db") or table.args.get("catalog"):
                raise GuardViolationError("Only the logical tables may appear in FROM (no table functions, files or schema-qualified names).")
            name = table.name.lower()
            if name not in self.schema.tables and name not in ctes:
                raise GuardViolationError(f"Unknown table '{table.name}'. Available tables: {', '.join(self.schema.tables)}.")
        if any(tree.find(kind) for kind in _NO_SOURCE):
            raise GuardViolationError("UNNEST, LATERAL, VALUES, PIVOT and sampling are not allowed. Select from the logical tables only.")
        joins = list(tree.find_all(exp.Join))
        if len(joins) > self.max_joins:
            raise GuardViolationError(f"Too many joins ({len(joins)}, max {self.max_joins}). Aggregate in CTEs, then join the CTEs.")
        for join in joins:
            if not isinstance(join.this, _JOIN_SOURCES):
                raise GuardViolationError("Join only logical tables or CTE names, not subqueries. Define the subquery as a CTE first.")

    def _function_rules(self, tree: exp.Expression) -> None:
        for node in tree.find_all(exp.Func):
            if isinstance(node, (exp.CurrentDate, exp.CurrentTimestamp, exp.CurrentDatetime)):
                raise GuardViolationError("CURRENT_DATE and CURRENT_TIMESTAMP are not allowed: the data ends at a fixed anchor date. "
                                          "Use explicit DATE 'YYYY-MM-DD' bounds computed from the anchor date given in the prompt.")
            if isinstance(node, exp.Anonymous):
                raise GuardViolationError(f"Function {node.name.upper()}() is not allowed.")
            if not isinstance(node, _ALLOWED_FUNCTIONS) and not isinstance(node, (exp.Binary, exp.Unary, exp.Condition, exp.Alias)):
                raise GuardViolationError(f"Function {node.sql_name()}() is not allowed. Use aggregates, DATE_TRUNC('week', col), CASE, "
                                          "COALESCE, NULLIF, ROUND and CAST, and write date ranges as explicit DATE 'YYYY-MM-DD' bounds.")

    @staticmethod
    def _measure_rules(analysis: Analysis) -> None:
        for col, use in analysis.measure_refs:
            agg = col.find_ancestor(exp.AggFunc)
            if not isinstance(agg, exp.Sum):
                raise GuardViolationError(
                    f"Measure column '{col.name}' of {use.table.id} must be wrapped in SUM(). "
                    "Measures are additive per row; AVG, MIN, MAX, COUNT or a bare column would differ between rollup and raw tables.")
        if analysis.row_counts:
            raise GuardViolationError("COUNT(*) and COUNT(column) count physical rows, which differ between rollup and raw tables. "
                                      "Use SUM(orders) for order counts or COUNT(DISTINCT <dimension column>).")

    # ---- shared helpers ----
    def enforce_limit(self, tree: exp.Expression) -> exp.Expression:
        return cap_limit(tree, self.max_rows)


def cap_limit(tree: exp.Expression, max_rows: int) -> exp.Expression:
    out = tree.copy()
    limit = out.args.get("limit")
    current = limit.expression if limit else None
    if isinstance(current, exp.Literal) and current.is_int and int(current.name) <= max_rows:
        return out
    out.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
    return out


class SqlGuard:
    """Physical-side guard. Defence in depth: whatever produced the SQL, only governed tables, one read-only statement, capped rows."""

    def __init__(self, allowed_tables: set[str], dialect: str, max_rows: int) -> None:
        self.allowed, self.dialect, self.max_rows = allowed_tables, dialect, max_rows

    def check(self, sql: str) -> str:
        """Returns the SQL with a row cap applied, or raises GuardViolationError."""
        stripped = _strip_fence(sql)
        try:
            statements = [s for s in sqlglot.parse(stripped, dialect=self.dialect) if s is not None]
        except sqlglot.errors.SqlglotError as e:
            raise GuardViolationError(f"Unparseable SQL: {str(e).splitlines()[0]}") from e
        if len(statements) != 1:
            raise GuardViolationError("Multiple statements are not allowed." if len(statements) > 1 else "Unparseable SQL.")
        tree = statements[0]
        if not isinstance(tree, (exp.Select, exp.SetOperation)):
            raise GuardViolationError("Only SELECT statements are allowed.")
        if any(tree.find(kind) for kind in _FORBIDDEN):
            raise GuardViolationError("Statement type not allowed.")
        cte_names = {c.alias.lower() for c in tree.find_all(exp.CTE)}
        illegal = {t.name for t in tree.find_all(exp.Table) if t.name.lower() not in cte_names} - self.allowed
        if illegal:
            raise GuardViolationError(f"Table(s) outside the governed layer: {sorted(illegal)}.")
        return cap_limit(tree, self.max_rows).sql(dialect=self.dialect)
