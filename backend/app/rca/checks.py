"""Preflight checks (Strategy pattern, one class per CheckKind). A fired check annotates the report; it never aborts it."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.enums import CheckKind
from app.core.errors import CatalogError
from app.engines.base import QueryEngine
from app.query.period import Period
from app.rca.models import CheckOutcome
from app.rca.reader import SegmentReader, relative_change
from app.semantic.catalog import Catalog
from app.semantic.models import CheckSpec


@dataclass
class CheckContext:
    catalog: Catalog
    reader: SegmentReader
    engine: QueryEngine
    current: Period
    baseline: Period


class Check(ABC):
    kind: CheckKind

    @abstractmethod
    def run(self, spec: CheckSpec, ctx: CheckContext) -> CheckOutcome: ...


class FreshnessCheck(Check):
    kind = CheckKind.FRESHNESS

    def run(self, spec: CheckSpec, ctx: CheckContext) -> CheckOutcome:
        table = ctx.catalog.anchor_table()
        latest = ctx.engine.max_date(table.rollup, table.time_column)
        return CheckOutcome(id=spec.id, title=spec.title, fired=latest < ctx.current.last_day, detail=f"latest loaded date {latest}")


class MetricShiftCheck(Check):
    kind = CheckKind.METRIC_SHIFT

    def run(self, spec: CheckSpec, ctx: CheckContext) -> CheckOutcome:
        if spec.metric is None or spec.threshold is None:
            raise CatalogError(f"check {spec.id} needs metric and threshold")
        metric = ctx.catalog.metric(spec.metric)
        rel = relative_change(ctx.reader.value(metric, ctx.current), ctx.reader.value(metric, ctx.baseline))
        if rel is None:
            return CheckOutcome(id=spec.id, title=spec.title, fired=False, detail="no baseline to compare")
        fired = rel <= spec.threshold if spec.threshold < 0 else rel >= spec.threshold
        return CheckOutcome(id=spec.id, title=spec.title, fired=fired, detail=f"{metric.id} changed {rel:+.1%}")


CHECKS: dict[CheckKind, Check] = {c.kind: c for c in (FreshnessCheck(), MetricShiftCheck())}


def run_checks(ids: list[str], ctx: CheckContext) -> list[CheckOutcome]:
    return [CHECKS[ctx.catalog.checks[i].check].run(ctx.catalog.checks[i], ctx) for i in ids]
