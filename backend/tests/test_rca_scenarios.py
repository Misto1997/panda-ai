"""One test per planted anomaly. These guard the planted-anomaly scenarios: if the data generator changes, each scenario must stay findable."""
import pytest

from app.core.enums import HypothesisStatus as S
from app.rca.investigator import RcaInvestigator

C, R = S.CONFIRMED, S.REJECTED


def investigate(container, metric):
    return RcaInvestigator(container.catalog, container.query_service).investigate(metric, "last_14_days")


@pytest.mark.parametrize("metric, top_segment, expected", [
    ("net_gmv", {"marketplace": "Acme Express", "zone": "South"},
     {"h_cancellation_spike": C, "h_demand_drop": R, "h_basket_shrink": R, "h_tracking_artifact": R, "h_localized_movement": C}),
    ("visits", {"marketplace": "Acme Mall", "zone": "East"},
     {"h_localized_outage": C, "h_tracking_loss": C, "h_bu_visits_consistent": C, "h_conversion_artifact": C, "h_demand_decline": R}),
    ("asp", {"marketplace": "Acme Wholesale", "zone": "North"},
     {"h_bu_mix_shift": C, "h_localized_movement": C, "h_cancellation_bias": R, "h_gross_price_drop": C}),
    ("conversion_rate", {"marketplace": "Acme Mall", "zone": "East"},
     {"h_visit_denominator": C, "h_localized_movement": C, "h_orders_dropped": R}),
])
def test_scenario(container, metric, top_segment, expected):
    report = investigate(container, metric)
    assert report.material
    assert report.drill.cells[0].segment == top_segment
    got = {h.id: h.status for h in report.hypotheses}
    assert {k: got[k] for k in expected} == expected


def test_decomposition_sums_to_the_change_and_finds_cancellations(container):
    r = investigate(container, "net_gmv")
    assert r.decomposition[0].component == "net_realization_rate"
    assert sum(d.contribution for d in r.decomposition) == pytest.approx(r.current.value - r.baseline.value, rel=1e-6)
    assert sum(c.contribution for c in r.drill.cells) == pytest.approx(r.drill.total_change, rel=0.05)  # top-k cells cover almost all of it


def test_metric_without_runbook_still_gets_a_drill(container):
    r = investigate(container, "gross_units")
    assert r.tree is None and r.hypotheses == [] and r.drill.cells


def test_rca_reads_run_concurrently(container, monkeypatch):
    """Warehouse reads are the RCA bottleneck on BigQuery (1-2 s each): with 50 ms per query the parallel run must beat a serial one clearly."""
    import time

    engine, real = container.query_service.engine, container.query_service.engine.run

    def slow(sql, timeout_s):
        time.sleep(0.05)
        return real(sql, timeout_s)

    monkeypatch.setattr(engine, "run", slow)
    started = time.perf_counter()
    report = investigate(container, "net_gmv")
    elapsed = time.perf_counter() - started
    assert report.queries_run >= 15 and report.hypotheses and elapsed < report.queries_run * 0.05 * 0.6, (elapsed, report.queries_run)
