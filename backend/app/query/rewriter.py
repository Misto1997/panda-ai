"""Deterministic logical -> physical rewrite. Every reference to a logical table becomes the daily rollup when all dimension
columns read through that reference exist in the rollup, otherwise the raw table (or always raw when forced).
The model never picks physical tables, so rollup selection stays a governed, reproducible decision."""
from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp

from app.core.enums import QueryMode
from app.query.guard import ValidatedSql, cap_limit
from app.query.logical import TABLE_ID_META, LogicalSchema


@dataclass(frozen=True)
class RewrittenSql:
    sql: str                  # physical SQL in the engine dialect
    sources: dict[str, str]   # logical table -> physical table (the widest scan wins when a table is referenced twice)


class LogicalRewriter:
    def __init__(self, schema: LogicalSchema, dialect: str) -> None:
        self.schema, self.dialect = schema, dialect

    def rewrite(self, validated: ValidatedSql, mode: QueryMode = QueryMode.AUTO, max_rows: int | None = None) -> RewrittenSql:
        tree = validated.tree.copy()
        sources: dict[str, str] = {}
        for table in tree.find_all(exp.Table):
            ref = table.meta.get(TABLE_ID_META)
            if ref is None:
                continue  # a CTE reference
            use = validated.analysis.uses[ref]
            t = use.table
            physical = t.rollup if mode == QueryMode.AUTO and use.dimensions <= t.rollup_columns else t.raw
            sources[t.id] = t.raw if sources.get(t.id) == t.raw else physical
            if not table.alias:  # keep `sales.zone` style references valid
                table.set("alias", exp.TableAlias(this=exp.to_identifier(t.id)))
            table.set("this", exp.to_identifier(physical))
        if max_rows is not None:
            tree = cap_limit(tree, max_rows)
        return RewrittenSql(tree.sql(dialect=self.dialect), sources)

