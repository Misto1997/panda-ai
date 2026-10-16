"""Logical semantic tables: what the model writes SQL against. Each logical table (sales, traffic, bu_traffic) exposes the
dimension columns, the time column and the additive base measures of its physical raw/rollup pair. The rewriter later
maps every reference to the rollup or the raw table, so the model never chooses physical tables."""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from app.core.errors import GuardViolationError
from app.semantic.catalog import Catalog
from app.semantic.models import LOGICAL_DIALECT

TABLE_ID_META = "logical_ref"  # key stored in Table.meta to link a node of the original tree to its qualified copy
_UNQUALIFIED_HINT = "Use only columns of the logical tables, and prefix a column with its table alias when several sources share the name."


@dataclass(frozen=True)
class LogicalTable:
    id: str
    time_column: str
    dimension_columns: tuple[str, ...]
    measures: tuple[str, ...]
    raw: str
    rollup: str
    rollup_columns: frozenset[str]  # dimension columns that exist in the rollup table

    @property
    def columns(self) -> tuple[str, ...]:
        return (self.time_column, *self.dimension_columns, *self.measures)


@dataclass(frozen=True)
class LogicalSchema:
    tables: dict[str, LogicalTable]

    @classmethod
    def from_catalog(cls, catalog: Catalog) -> "LogicalSchema":
        tables = {}
        for t in catalog.tables.values():
            dims = tuple(d.column for d in catalog.dimensions.values() if t.id in d.tables and d.id != "date")
            rollup = frozenset(catalog.dimension(i).column for i in t.rollup_dimensions)
            tables[t.id] = LogicalTable(t.id, t.time_column, dims, tuple(t.measures), t.raw, t.rollup, rollup)
        return cls(tables)

    def mapping(self) -> dict[str, dict[str, str]]:
        """Schema in the shape sqlglot's optimizer expects."""
        out = {}
        for t in self.tables.values():
            out[t.id] = {t.time_column: "date", **{c: "varchar" for c in t.dimension_columns}, **{c: "double" for c in t.measures}}
        return out

    def describe(self, catalog: Catalog) -> str:
        lines = []
        for t in self.tables.values():
            spec = catalog.tables[t.id]
            lines.append(f"- {t.id}: {spec.description}\n"
                         f"    time column: {t.time_column} (DATE)\n"
                         f"    dimension columns: {', '.join(t.dimension_columns)}\n"
                         f"    additive measures (use only inside SUM): {', '.join(t.measures)}")
        return "\n".join(lines)


@dataclass
class TableUse:
    """One reference to a logical table in a statement and the columns read through it."""
    table: LogicalTable
    columns: set[str] = field(default_factory=set)

    @property
    def dimensions(self) -> set[str]:
        return self.columns & set(self.table.dimension_columns)


@dataclass
class Analysis:
    uses: dict[int, TableUse]                                    # reference id (Table.meta) -> usage
    measure_refs: list[tuple[exp.Column, TableUse]] = field(default_factory=list)  # nodes belong to the qualified copy
    row_counts: list[exp.Count] = field(default_factory=list)    # COUNT over rows of a logical table


def analyze(tree: exp.Expression, schema: LogicalSchema) -> Analysis:
    """Tags every logical table reference of `tree` (in place) and resolves columns on a qualified copy.
    Raises GuardViolationError for unknown or ambiguous columns."""
    ctes = {c.alias.lower() for c in tree.find_all(exp.CTE)}
    clash = ctes & set(schema.tables)
    if clash:
        raise GuardViolationError(f"CTE name(s) {sorted(clash)} clash with logical tables. Pick another CTE name.")
    uses: dict[int, TableUse] = {}
    for i, table in enumerate(t for t in tree.find_all(exp.Table) if t.name.lower() in schema.tables and t.name.lower() not in ctes):
        table.meta[TABLE_ID_META] = i
        uses[i] = TableUse(schema.tables[table.name.lower()])
    try:
        qualified = qualify(tree.copy(), schema=schema.mapping(), dialect=LOGICAL_DIALECT, validate_qualify_columns=True,
                            expand_stars=False, quote_identifiers=False, identify=False)
        scopes = list(traverse_scope(qualified))
    except sqlglot.errors.SqlglotError as e:
        message = str(e).split(" Line:")[0].rstrip(".")
        raise GuardViolationError(f"{message}. {_UNQUALIFIED_HINT}") from e
    result = Analysis(uses)
    for scope in scopes:
        scoped = {alias: src for alias, src in scope.sources.items() if isinstance(src, exp.Table) and TABLE_ID_META in src.meta}
        for col in scope.columns:
            src = scoped.get(col.table)
            if src is None:
                continue
            use = uses[src.meta[TABLE_ID_META]]
            use.columns.add(col.name.lower())
            if col.name.lower() in use.table.measures:
                result.measure_refs.append((col, use))
        if scoped:
            for count in scope.expression.find_all(exp.Count):
                if _in_scope(count, scope.expression) and not isinstance(count.this, exp.Distinct):
                    result.row_counts.append(count)
    return result


def _in_scope(node: exp.Expression, select: exp.Expression) -> bool:
    """True when `node` belongs to `select` itself, not to a nested subquery."""
    return node.find_ancestor(exp.Select) is select
