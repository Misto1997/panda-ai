"""SQL -> canonical intent. Parses validated logical SQL back into a QueryIR-shaped intent so that
 - the semantic cache can key results on meaning (paraphrases that yield equivalent SQL share an entry),
 - follow-up questions can modify the previous intent,
 - the UI can explain the query in business terms.
Anything the normaliser cannot represent degrades gracefully: the cache key falls back to a hash of the normalised SQL text and the
IR is marked inexact. Normalisation never fails a turn."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta

import sqlglot
from sqlglot import exp

from app.core.enums import TimeGrain
from app.core.logging import get_logger
from app.query.ir import Filter, QueryIR
from app.query.period import Period, PeriodResolver
from app.semantic.catalog import Catalog
from app.semantic.models import LOGICAL_DIALECT, MetricSpec

log = get_logger("query.normalizer")
DATE_ALIAS = "date"
MAX_LIMIT = 500
_TRUNC = (exp.DateTrunc, exp.TimestampTrunc)  # DuckDB parses DATE_TRUNC as TimestampTrunc


@dataclass
class Intent:
    ir: QueryIR | None                 # best-effort canonical intent (None when no governed metric is recognised)
    exact: bool                        # the IR reproduces the SQL result (columns, order, rows); only then may it key the cache
    period: Period | None
    fingerprint: str                   # hash of the normalised SQL text
    column_metrics: dict[str, str] = field(default_factory=dict)  # result column -> governed metric id
    date_columns: list[str] = field(default_factory=list)         # result columns that hold a date bucket

    def describe(self) -> str:
        if not self.ir:
            return "ungoverned expression (no matching metric)"
        ir = self.ir
        parts = [", ".join(ir.metrics)]
        if ir.dimensions:
            parts.append("by " + ", ".join(ir.dimensions))
        if ir.grain != TimeGrain.NONE:
            parts.append(f"per {ir.grain.value}")
        parts += [f"{f.dim}{' not' if f.negate else ''} in {f.values}" for f in ir.filters]
        parts.append(ir.time_expr)
        return " | ".join(parts)


class SqlNormalizer:
    def __init__(self, catalog: Catalog, resolver: PeriodResolver) -> None:
        self.cat, self.resolver = catalog, resolver
        self._dim_by_column = {d.column: d.id for d in catalog.dimensions.values() if d.id != DATE_ALIAS}
        self._time_columns = {t.time_column for t in catalog.tables.values()}
        self._metric_by_canon: dict[str, list[MetricSpec]] = {}
        for m in catalog.metrics.values():
            self._metric_by_canon.setdefault(self._canon(self._metric_expr(m)), []).append(m)

    # ---- public ----
    def normalize(self, tree: exp.Expression) -> Intent:
        fingerprint = hashlib.sha1(tree.sql(dialect=LOGICAL_DIALECT, normalize=True).encode()).hexdigest()
        try:
            return self._normalize(tree, fingerprint)
        except Exception as e:  # never fail a turn because of caching or memory
            log.warning("could not normalise SQL, falling back to its hash: %s", e)
            return Intent(None, False, None, fingerprint)

    # ---- implementation ----
    def _normalize(self, tree: exp.Expression, fingerprint: str) -> Intent:
        selects = list(tree.find_all(exp.Select))
        root = tree if isinstance(tree, exp.Select) else selects[0]
        simple = (isinstance(tree, exp.Select) and len(selects) == 1 and not tree.find(exp.Join) and not tree.find(exp.Window)
                  and not tree.args.get("having") and not tree.find(exp.With))

        metrics: list[str] = []
        column_metrics: dict[str, str] = {}
        exact = simple
        for select in selects:
            for proj in select.expressions:
                inner = proj.this if isinstance(proj, exp.Alias) else proj
                match = self._match_metric(inner, self._tables_of(select))
                if match and inner.find(exp.Cast, exp.TryCast, exp.Round):
                    exact = False  # CAST/ROUND change the values: not interchangeable with the plain metric, so never share its cache entry
                if match:
                    if match.id not in metrics:
                        metrics.append(match.id)
                    if select is root:
                        column_metrics[proj.alias_or_name] = match.id
        for name in root.named_selects:  # CTE pipelines: the final SELECT usually re-exposes a metric by its id
            if name in self.cat.metrics and name in metrics:
                column_metrics.setdefault(name, name)

        dims: list[str] = []
        grain, date_columns = TimeGrain.NONE, []
        for select in selects:
            for key in self._group_keys(select):
                if isinstance(key, _TRUNC):
                    unit = key.args["unit"].name.lower()
                    grain = TimeGrain(unit) if unit in {g.value for g in TimeGrain} else grain
                elif isinstance(key, exp.Column) and key.name in self._dim_by_column:
                    dim = self._dim_by_column[key.name]
                    if dim not in dims:
                        dims.append(dim)
        for proj in root.expressions:
            inner = proj.this if isinstance(proj, exp.Alias) else proj
            if isinstance(inner, _TRUNC):
                date_columns.append(proj.alias_or_name)

        filters: list[Filter] = []
        ranges: list[tuple[date, date]] = []
        understood = True
        for select in selects:
            fs, rng, ok = self._predicates(select.args.get("where"))
            understood &= ok
            for f in fs:
                if not any(x.dim == f.dim and x.values == f.values and x.negate == f.negate for x in filters):
                    filters.append(f)
            if rng:
                ranges.append(rng)
        period = None
        if ranges:
            period = Period(min(r[0] for r in ranges), max(r[1] for r in ranges))
            exact &= len(set(ranges)) == 1
        elif simple:
            period = self.resolver.resolve("all_time")

        order_by, order_desc = self._order(root, column_metrics)
        limit = self._limit(root)
        order = root.args.get("order")
        if root.args.get("offset") or (order and (len(order.expressions) != 1 or order_by is None)):
            exact = False  # OFFSET, multi-key or non-metric ordering (dimension/date) change which rows come back
        ir = None
        if metrics:
            ir = QueryIR(metrics=metrics, dimensions=dims, filters=filters, time_expr=self._time_expr(period), grain=grain,
                         order_by=order_by, order_desc=order_desc, limit=limit)
        exact = bool(exact and ir and understood and period is not None
                     and root.named_selects == self._canonical_columns(ir, grain) and len(self._tables_of(root)) == 1
                     and self._group_ok(root, ir))
        return Intent(ir, exact, period, fingerprint, column_metrics, date_columns)

    # ---- helpers ----
    @staticmethod
    def _metric_expr(metric: MetricSpec) -> exp.Expression:
        text = metric.expr if not metric.is_ratio else f"({metric.numerator}) / NULLIF({metric.denominator}, 0)"
        return sqlglot.parse_one(text, dialect=LOGICAL_DIALECT)

    @staticmethod
    def _canon(node: exp.Expression) -> str:
        """Strip presentation-only wrappers (casts, parentheses, ROUND, NULLIF(x, 0)) so equivalent formulas compare equal."""
        def strip(n: exp.Expression):
            if isinstance(n, (exp.Cast, exp.TryCast, exp.Paren, exp.Round)):
                return n.this
            if isinstance(n, exp.Column) and n.table:  # `s.net_gmv` and `net_gmv` are the same column
                return exp.column(n.name)
            if isinstance(n, exp.Nullif) and isinstance(n.expression, exp.Literal) and n.expression.name == "0":
                return n.this
            return n
        return node.copy().transform(strip).sql(dialect=LOGICAL_DIALECT, normalize=True)

    def _match_metric(self, node: exp.Expression, tables: list[str]) -> MetricSpec | None:
        candidates = self._metric_by_canon.get(self._canon(node), [])
        return next((m for m in candidates if m.table in tables), None)

    @staticmethod
    def _tables_of(select: exp.Select) -> list[str]:
        return [t.name.lower() for t in select.find_all(exp.Table) if t.find_ancestor(exp.Select) is select]

    @staticmethod
    def _group_keys(select: exp.Select) -> list[exp.Expression]:
        group = select.args.get("group")
        keys = []
        for e in (group.expressions if group else []):
            if isinstance(e, exp.Literal) and e.is_int and 1 <= int(e.name) <= len(select.expressions):
                e = select.expressions[int(e.name) - 1]
            keys.append(e.this if isinstance(e, exp.Alias) else e)
        return keys

    def _predicates(self, where: exp.Where | None) -> tuple[list[Filter], tuple[date, date] | None, bool]:
        if where is None:
            return [], None, True
        filters: list[Filter] = []
        lo: date | None = None
        hi: date | None = None
        ok = True
        for p in self._conjuncts(where.this):
            negate = isinstance(p, exp.Not)
            node = p.this if negate else p
            col = node.this if isinstance(node, (exp.In, exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)) else None
            if not isinstance(col, exp.Column):
                ok = False
                continue
            if col.name in self._dim_by_column:
                values = self._literals(node)
                if values is None or isinstance(node, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)):
                    ok = False
                else:
                    filters.append(Filter(dim=self._dim_by_column[col.name], values=values, negate=negate != isinstance(node, exp.NEQ)))
            elif col.name in self._time_columns and not negate:
                bound = self._date_bound(node)
                if bound is None:
                    ok = False
                    continue
                start, end = bound
                lo = start if start and (lo is None or start > lo) else lo
                hi = end if end and (hi is None or end < hi) else hi
            else:
                ok = False
        return filters, (lo, hi) if lo and hi else None, ok and (lo is not None) == (hi is not None)

    @staticmethod
    def _conjuncts(node: exp.Expression) -> list[exp.Expression]:
        if isinstance(node, exp.And):
            return SqlNormalizer._conjuncts(node.left) + SqlNormalizer._conjuncts(node.right)
        if isinstance(node, exp.Paren) and isinstance(node.this, exp.And):
            return SqlNormalizer._conjuncts(node.this)
        return [node]

    @staticmethod
    def _literals(node: exp.Expression) -> list[str] | None:
        if isinstance(node, exp.In):
            lits = node.expressions
        elif isinstance(node, (exp.EQ, exp.NEQ)):
            lits = [node.expression]
        else:
            return None
        return [x.name for x in lits] if lits and all(isinstance(x, exp.Literal) and x.is_string for x in lits) else None

    @staticmethod
    def _as_date(node: exp.Expression | None) -> date | None:
        if isinstance(node, exp.Cast) and isinstance(node.this, exp.Literal):
            node = node.this
        if isinstance(node, exp.Literal) and node.is_string:
            try:
                return date.fromisoformat(node.name)
            except ValueError:
                return None
        return None

    def _date_bound(self, node: exp.Expression) -> tuple[date | None, date | None] | None:
        """(start, end_exclusive) contributed by one predicate on the time column, either side may be None."""
        one = timedelta(days=1)
        if isinstance(node, exp.Between):
            a, b = self._as_date(node.args.get("low")), self._as_date(node.args.get("high"))
            return (a, b + one) if a and b else None
        if not isinstance(node, (exp.GT, exp.GTE, exp.LT, exp.LTE)):
            return None
        d = self._as_date(node.expression)
        if d is None:
            return None
        return {exp.GTE: (d, None), exp.GT: (d + one, None), exp.LT: (None, d), exp.LTE: (None, d + one)}[type(node)]

    def _time_expr(self, period: Period | None) -> str:
        if period is None:
            return "all_time"
        if period.end == self.resolver.today and period.days >= 1:
            return "yesterday" if period.days == 1 else f"last_{period.days}_days"
        return period.as_expr()

    @staticmethod
    def _order(root: exp.Select, column_metrics: dict[str, str]) -> tuple[str | None, bool]:
        order = root.args.get("order")
        if not order or not order.expressions:
            return None, True
        first = order.expressions[0]
        key = first.this
        if isinstance(key, exp.Literal) and key.is_int and 1 <= int(key.name) <= len(root.expressions):
            key = root.expressions[int(key.name) - 1]
        name = key.alias_or_name if isinstance(key, (exp.Column, exp.Alias)) else ""
        return column_metrics.get(name), bool(first.args.get("desc"))

    @staticmethod
    def _limit(root: exp.Select) -> int | None:
        limit = root.args.get("limit")
        node = limit.expression if limit else None
        return min(int(node.name), MAX_LIMIT) if isinstance(node, exp.Literal) and node.is_int and int(node.name) >= 1 else None

    def _canonical_columns(self, ir: QueryIR, grain: TimeGrain) -> list[str]:
        """Column names/order the IR compiler would produce."""
        return ([DATE_ALIAS] if grain != TimeGrain.NONE else []) + [self.cat.dimension(d).column for d in ir.dimensions] + list(ir.metrics)

    def _group_ok(self, root: exp.Select, ir: QueryIR) -> bool:
        keys = self._group_keys(root)
        wanted = len(ir.dimensions) + (1 if ir.grain != TimeGrain.NONE else 0)
        return len(keys) == wanted and all(isinstance(k, (exp.Column, _TRUNC)) for k in keys)
