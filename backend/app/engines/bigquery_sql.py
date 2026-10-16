"""DuckDB-style SQL (what the compiler emits) -> BigQuery SQL, with physical tables qualified as `project.dataset.table`."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.core.errors import EngineError

SOURCE_DIALECT = "duckdb"
TARGET_DIALECT = "bigquery"


def _fix_date_trunc(node: exp.Expression) -> exp.Expression:
    """sqlglot turns DuckDB DATE_TRUNC into TIMESTAMP_TRUNC, which BigQuery rejects on DATE columns. All our time
    columns are DATE, so emit DATE_TRUNC. DuckDB weeks start on Monday, BigQuery's WEEK on Sunday: pin WEEK(MONDAY)."""
    if isinstance(node, (exp.TimestampTrunc, exp.DateTrunc)) and isinstance(node.args.get("unit"), (exp.Var, exp.Literal)):
        unit = node.args["unit"].name.upper()
        bq_unit = exp.WeekStart(this=exp.var("MONDAY")) if unit == "WEEK" else exp.var(unit)
        return exp.DateTrunc(this=node.this, unit=bq_unit)
    return node


def to_bigquery(sql: str, project: str, dataset: str) -> str:
    try:
        tree = sqlglot.parse_one(sql, read=SOURCE_DIALECT)
    except sqlglot.errors.ParseError as e:
        raise EngineError(f"cannot translate SQL for BigQuery: {e}") from e
    ctes = {c.alias for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.name not in ctes and not table.args.get("db"):
            table.set("this", exp.to_identifier(table.name, quoted=True))  # project ids contain hyphens: must be quoted
            table.set("db", exp.to_identifier(dataset, quoted=True))
            table.set("catalog", exp.to_identifier(project, quoted=True))
    return tree.transform(_fix_date_trunc).sql(dialect=TARGET_DIALECT)
