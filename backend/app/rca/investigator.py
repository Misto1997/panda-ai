"""Runbook-driven root-cause investigation. All numbers come from governed queries and exact attribution maths;
the LLM only narrates the resulting report."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.enums import ValueFormat
from app.core.logging import get_logger
from app.query.service import QueryService
from app.rca.checks import CheckContext, run_checks
from app.rca.decomposition import LogRatioDecomposer
from app.rca.drill import SegmentDriller
from app.rca.hypotheses import HypothesisContext, run_hypotheses
from app.rca.models import PeriodValue, RcaReport
from app.rca.reader import SegmentReader, relative_change
from app.semantic.catalog import Catalog
from app.semantic.models import PolicySpec, RcaTreeSpec

log = get_logger("rca")
SQL_SAMPLE = 3
READ_WORKERS = 8   # concurrent warehouse queries per investigation
PHASE_WORKERS = 3


class RcaInvestigator:
    def __init__(self, catalog: Catalog, service: QueryService) -> None:
        self._cat, self._service = catalog, service

    def investigate(self, metric_id: str, time_expr: str) -> RcaReport:
        metric = self._cat.metric(metric_id)
        tree = self._cat.tree_for(metric_id)
        policy = self._cat.policies[tree.policy] if tree else next(iter(self._cat.policies.values()))
        current = self._service.resolver.resolve(time_expr)
        baseline = current.previous()
        # Warehouse reads are 1-2 s round trips and mostly independent: fan them out (two pools, so a phase waiting on reads can never starve them).
        with ThreadPoolExecutor(READ_WORKERS, thread_name_prefix="rca-read") as reads, ThreadPoolExecutor(PHASE_WORKERS, thread_name_prefix="rca-phase") as phases:
            reader = SegmentReader(self._service, reads)
            checks_f = phases.submit(run_checks, tree.preflight, CheckContext(self._cat, reader, self._service.engine, current, baseline)) if tree else None
            decomp_f = phases.submit(LogRatioDecomposer(self._cat, reader).decompose, tree, current, baseline) if tree else None
            now, before = reader.value(metric, current), reader.value(metric, baseline)
            rel = relative_change(now, before)
            decomposition = decomp_f.result() if decomp_f else []

            driver = self._cat.metric(decomposition[0].component) if decomposition else metric
            drill_dims = tree.drill_dimensions if tree else metric.dimensions[:2]
            drill = SegmentDriller(self._cat, reader).drill(
                driver, drill_dims, tree.marginal_dimensions if tree else [], current, baseline,
                top_k=int(policy.value("top_k_drivers")), min_share=policy.value("min_segment_share"))
            top = drill.cells[0] if drill.cells else None
            hypotheses = run_hypotheses(tree.hypotheses, HypothesisContext(self._cat, reader, current, baseline, top), reads) if tree else []
            checks = checks_f.result() if checks_f else []

        log.info("rca %s: rel=%s driver=%s top=%s queries=%d", metric_id, rel, driver.id, top.segment if top else None, len(reader.queries))
        return RcaReport(
            metric=metric.id, title=metric.title, format=metric.format, tree=tree.id if tree else None,
            current=PeriodValue(start=str(current.start), end=str(current.last_day), value=now),
            baseline=PeriodValue(start=str(baseline.start), end=str(baseline.last_day), value=before),
            rel=rel, material=rel is not None and abs(rel) >= policy.value("materiality"),
            checks=checks, decomposition=decomposition, drill_metric=driver.id, drill=drill, hypotheses=hypotheses,
            queries_run=len(reader.queries), sql_sample=reader.queries[:SQL_SAMPLE])
