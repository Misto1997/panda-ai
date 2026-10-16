from app.presentation.a2ui import build_surface, load_catalog


def _components(messages):
    return {c["id"]: c for c in messages[1]["updateComponents"]["components"]}


def test_surface_for_single_row_answer_uses_kpis_not_table():
    result = {"type": "answer", "text": "x", "meta": {"route": "qna", "engine": "duckdb", "cache": "hit", "sources": {"s": "agg_sales_daily"}, "elapsed_ms": 2.0},
              "table": {"columns": ["net_gmv"], "rows": [[1500000.0]], "formats": {"net_gmv": "currency"}, "titles": {"net_gmv": "Net GMV"}}}
    msgs = build_surface(result, "s1")
    comps = _components(msgs)
    assert msgs[0]["createSurface"]["surfaceId"] == "s1" and comps["root"]["children"][0] == "answer"
    assert "table" not in comps and msgs[2]["updateDataModel"]["value"]["kpis"][0]["value"] == "$1.50M"
    assert {"label": "cache", "value": "hit", "tone": "good"} in msgs[2]["updateDataModel"]["value"]["provenance"]
    catalog = load_catalog()["components"]
    assert all(c["component"] in catalog for c in comps.values())


def test_every_child_reference_exists():
    msgs = build_surface({"type": "info", "text": "hi", "meta": {"route": "help"}, "sql": "SELECT 1"}, "s2")
    comps = _components(msgs)
    assert all(c in comps for c in comps["root"]["children"]) and "sql" in comps


def test_suggestions_render_chips_below_text():
    msgs = build_surface({"type": "info", "text": "hi", "meta": {"route": "help", "suggestions": ["Net GMV last month?"]}}, "s3")
    comps = _components(msgs)
    assert comps["root"]["children"][:2] == ["answer", "suggestions"] and msgs[2]["updateDataModel"]["value"]["suggestions"] == ["Net GMV last month?"]


def test_rca_surface_has_verdict_findings_and_charts():
    rca = {"title": "Net GMV", "format": "currency", "direction": "up_is_good", "rel": -0.2, "material": True, "tree": "t", "queries_run": 3,
           "current": {"start": "2026-09-01", "end": "2026-10-01", "value": 800.0}, "baseline": {"start": "2026-08-01", "end": "2026-09-01", "value": 1000.0},
           "checks": [{"id": "c", "title": "Late data", "fired": True, "detail": "d"}],
           "decomposition": [{"component": "a", "title": "Orders", "format": "number", "baseline": 10, "current": 8, "rel": -0.2, "contribution": -200.0}],
           "drill_metric": "net_gmv", "drill": {"dims": ["zone"], "total_change": -200.0, "marginals": {},
                                                "cells": [{"segment": {"zone": "South"}, "baseline": 1, "current": 0, "rel": -0.5, "contribution": -100.0, "share_of_change": 0.5}]},
           "hypotheses": [{"id": "h", "claim": "Cancellations up", "test": "x", "status": "confirmed", "evidence": "e"}]}
    msgs = build_surface({"type": "rca", "text": "why", "meta": {"route": "rca"}, "rca": rca}, "s4")
    comps, model = _components(msgs), msgs[2]["updateDataModel"]["value"]["rca"]
    assert comps["root"]["children"][0] == "rca_verdict" and "rca_charts" in comps["root"]["children"] and "rca_driver_chart" not in comps["root"]["children"]
    assert model["verdict"]["tone"] == "bad" and model["verdict"]["current"]["range"] == "2026-09-01 to 2026-09-30"
    assert 3 <= len(model["findings"]) <= 5 and model["driverChart"]["encoding"]["y"]["sort"] == ["Orders"]
    assert all(c["component"] in load_catalog()["components"] for c in comps.values())
    rise = build_surface({"type": "rca", "text": "x", "meta": {"route": "rca"}, "rca": {**rca, "direction": "down_is_good", "rel": 0.3}}, "s5")
    assert rise[2]["updateDataModel"]["value"]["rca"]["verdict"]["tone"] == "bad"  # a rising cancellation rate is bad news
    assert build_surface({"type": "rca", "text": "x", "meta": {"route": "rca"}, "rca": {**rca, "direction": "neutral"}}, "s6")[2]["updateDataModel"]["value"]["rca"]["verdict"]["tone"] == "neutral"
