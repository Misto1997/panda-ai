"""Hypothesis tests (Strategy pattern, one class per HypothesisTest). New test types register in TESTERS;
runbooks in semantic/rca/trees reference them by name and carry the thresholds."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.enums import HypothesisStatus, HypothesisTest, Movement, Scope
from app.core.errors import CatalogError
from app.presentation.formatting import format_value
from app.query.ir import Filter
from app.query.period import Period
from app.rca.models import HypothesisOutcome, SegmentContribution
from app.rca.reader import SegmentReader, relative_change
from app.semantic.catalog import Catalog
from app.semantic.models import HypothesisSpec


@dataclass
class HypothesisContext:
    catalog: Catalog
    reader: SegmentReader
    current: Period
    baseline: Period
    top_cell: SegmentContribution | None

    def filters_for(self, spec: HypothesisSpec, metric_ids: list[str], exclude: set[str] = frozenset()) -> tuple[list[Filter], str]:
        """TOP_CELL scope: restrict to the top segment, keeping only dimensions every involved metric supports."""
        if spec.scope != Scope.TOP_CELL or self.top_cell is None:
            return [], "overall"
        usable = set.intersection(*(set(self.catalog.metric(m).dimensions) for m in metric_ids)) - exclude
        seg = {d: v for d, v in self.top_cell.segment.items() if d in usable}
        return [Filter(dim=d, values=[v]) for d, v in seg.items()], ", ".join(seg.values()) or "overall"

    def outcome(self, spec: HypothesisSpec, status: HypothesisStatus, evidence: str) -> HypothesisOutcome:
        return HypothesisOutcome(id=spec.id, claim=spec.claim, test=spec.test, status=status, evidence=evidence)


def where(scope: str) -> str:
    return scope if scope == "overall" else f"in {scope}"


def movement_met(rel: float, direction: Movement, threshold: float) -> bool:
    return {Movement.DOWN: rel <= -threshold, Movement.UP: rel >= threshold, Movement.ANY: abs(rel) >= threshold}[direction]


class HypothesisTester(ABC):
    test: HypothesisTest

    @abstractmethod
    def run(self, spec: HypothesisSpec, ctx: HypothesisContext) -> HypothesisOutcome: ...

    @staticmethod
    def _rel(ctx: HypothesisContext, metric_id: str, filters: list[Filter]) -> tuple[float | None, float | None, float | None]:
        metric = ctx.catalog.metric(metric_id)
        now, before = ctx.reader.value(metric, ctx.current, filters), ctx.reader.value(metric, ctx.baseline, filters)
        return now, before, relative_change(now, before)


class MetricShiftTester(HypothesisTester):
    test = HypothesisTest.METRIC_SHIFT

    def run(self, spec: HypothesisSpec, ctx: HypothesisContext) -> HypothesisOutcome:
        filters, scope = ctx.filters_for(spec, [spec.metric])
        now, before, rel = self._rel(ctx, spec.metric, filters)
        if rel is None:
            return ctx.outcome(spec, HypothesisStatus.INCONCLUSIVE, f"no baseline for {spec.metric} ({scope})")
        fmt = ctx.catalog.metric(spec.metric).format
        status = HypothesisStatus.CONFIRMED if movement_met(rel, spec.direction, spec.threshold) else HypothesisStatus.REJECTED
        return ctx.outcome(spec, status, f"{spec.metric} {where(scope)}: {rel:+.1%} ({format_value(before, fmt)} to {format_value(now, fmt)}); "
                                         f"needs {spec.direction.value} >= {spec.threshold:.0%}")


class DivergenceTester(HypothesisTester):
    test = HypothesisTest.DIVERGENCE

    def run(self, spec: HypothesisSpec, ctx: HypothesisContext) -> HypothesisOutcome:
        filters, scope = ctx.filters_for(spec, [spec.metric, spec.other_metric])
        _, _, rel_a = self._rel(ctx, spec.metric, filters)
        _, _, rel_b = self._rel(ctx, spec.other_metric, filters)
        if rel_a is None or rel_b is None:
            return ctx.outcome(spec, HypothesisStatus.INCONCLUSIVE, f"no baseline {where(scope)}")
        met = movement_met(rel_a, spec.direction, spec.threshold) and abs(rel_b) <= spec.stable_threshold
        return ctx.outcome(spec, HypothesisStatus.CONFIRMED if met else HypothesisStatus.REJECTED,
                           f"{where(scope)}: {spec.metric} {rel_a:+.1%} while {spec.other_metric} {rel_b:+.1%} "
                           f"(needs {spec.metric} {spec.direction.value} >= {spec.threshold:.0%} and {spec.other_metric} within {spec.stable_threshold:.0%})")


class ConcentrationTester(HypothesisTester):
    test = HypothesisTest.CONCENTRATION

    def run(self, spec: HypothesisSpec, ctx: HypothesisContext) -> HypothesisOutcome:
        cell = ctx.top_cell
        if cell is None or cell.share_of_change is None:
            return ctx.outcome(spec, HypothesisStatus.INCONCLUSIVE, "no segment stands out")
        share = abs(cell.share_of_change)
        label = ", ".join(f"{k}={v}" for k, v in cell.segment.items())
        return ctx.outcome(spec, HypothesisStatus.CONFIRMED if share >= spec.threshold else HypothesisStatus.REJECTED,
                           f"{label} explains {share:.0%} of the change (needs {spec.threshold:.0%})")


class MixShiftTester(HypothesisTester):
    test = HypothesisTest.MIX_SHIFT

    def run(self, spec: HypothesisSpec, ctx: HypothesisContext) -> HypothesisOutcome:
        metric = ctx.catalog.metric(spec.metric)
        filters, scope = ctx.filters_for(spec, [spec.metric], exclude={spec.dimension})
        now, before = (ctx.reader.segments(metric, [spec.dimension], p, filters) for p in (ctx.current, ctx.baseline))
        total_now, total_before = sum(c.num for c in now.values()), sum(c.num for c in before.values())
        if not total_now or not total_before:
            return ctx.outcome(spec, HypothesisStatus.INCONCLUSIVE, f"no {spec.metric} volume {where(scope)}")
        share = lambda cells, total, key: cells[key].num / total if key in cells else 0.0
        shifts = {k[0]: share(now, total_now, k) - share(before, total_before, k) for k in set(now) | set(before)}
        biggest = max(shifts, key=lambda k: abs(shifts[k]))
        met = abs(shifts[biggest]) >= spec.threshold
        return ctx.outcome(spec, HypothesisStatus.CONFIRMED if met else HypothesisStatus.REJECTED,
                           f"{spec.dimension} share of {spec.metric} {where(scope)}: {biggest} {shifts[biggest] * 100:+.1f} pp "
                           f"(needs {spec.threshold * 100:.0f} pp)")


TESTERS: dict[HypothesisTest, HypothesisTester] = {t.test: t for t in (MetricShiftTester(), DivergenceTester(), ConcentrationTester(), MixShiftTester())}


def run_hypotheses(specs: list[HypothesisSpec], ctx: HypothesisContext) -> list[HypothesisOutcome]:
    out = []
    for spec in specs:
        tester = TESTERS.get(spec.test)
        if tester is None:
            raise CatalogError(f"no tester registered for {spec.test}")
        out.append(tester.run(spec, ctx))
    return out
