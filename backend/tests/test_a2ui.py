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
