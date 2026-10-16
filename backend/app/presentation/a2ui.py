"""Builds an A2UI v0.9 surface (https://github.com/google/A2UI) from a ChatResult payload. Pure: no I/O.

The surface uses the PANDA catalog (a2ui_catalog.json). Data lives in the surface data model and components bind to it
with {"path": "/json/pointer"} so the structure stays small and the data can be updated independently."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.core.enums import A2uiComponent as C
from app.core.enums import A2uiMessage, CacheStatus, ResponseType
from app.presentation.formatting import format_value

CATALOG_PATH = Path(__file__).with_name("a2ui_catalog.json")
VERSION = "v0.9"
ROOT = "root"
MIN_TABLE_ROWS = 2  # a single-row table is shown as KPIs instead


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text())


def catalog_id() -> str:
    return load_catalog()["catalogId"]


def _bind(path: str) -> dict:
    return {"path": path}


def _kpis(result: dict) -> list[dict]:
    rca, table = result.get("rca"), result.get("table")
    if rca:
        cur, base, rel = rca["current"]["value"], rca["baseline"]["value"], rca.get("rel")
        return [{"label": rca["title"], "value": format_value(cur, rca["format"]), "delta": rel,
                 "caption": f"vs {format_value(base, rca['format'])} baseline", "tone": _tone(rel, rca.get("direction"))}]
    if table and len(table["rows"]) == 1:
        row = dict(zip(table["columns"], table["rows"][0]))
        return [{"label": table["titles"].get(c, c), "value": format_value(v, table["formats"].get(c, "number")) if isinstance(v, (int, float)) else str(v)}
                for c, v in row.items()]
    return []


def _provenance(result: dict) -> list[dict]:
    m = result.get("meta", {})
    chips: list[dict] = []

    def add(label: str, value: Any, tone: str | None = None) -> None:
        if value not in (None, "", []):
            chips.append({"label": label, "value": str(value), **({"tone": tone} if tone else {})})

    add("engine", m.get("engine"))
    if m.get("sources"):
        tables = ", ".join(m["sources"].values())
        add("source", tables, "good" if next(iter(m["sources"].values())).startswith("agg_") else "warn")
    if m.get("elapsed_ms") is not None:
        add("query", f"{m['elapsed_ms']} ms")
    if m.get("cache") and m["cache"] != CacheStatus.OFF:
        add("cache", m["cache"], "good" if m["cache"] == CacheStatus.HIT else None)
    if m.get("bytes_processed") is not None:
        add("scanned", f"{m['bytes_processed'] / 1e6:.1f} MB")
    add("path", m.get("path"))
    add("sql attempts", m.get("sql_attempts"))
    add("queries", m.get("queries"))
    if m.get("total_ms") is not None:
        add("total", f"{m['total_ms']} ms")
    add("llm", m.get("llm"))
    return chips


RED, GREEN, GREY = "#dc2626", "#16a34a", "#9ca3af"
MAX_SEGMENT_BARS = 8
MAX_FINDINGS = 5


def _segment_label(segment: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in (segment or {}).items())


def _tone(change: float | None, direction: str | None) -> str:
    """good / bad / neutral for a change in the analysed metric, from the metric's polarity (a rising cancellation rate is bad)."""
    if not change or direction not in ("up_is_good", "down_is_good"):
        return "neutral"
    return "good" if (change > 0) == (direction == "up_is_good") else "bad"


def _pct(v: float | None, signed: bool = True) -> str:
    return "n/a" if v is None else f"{'+' if signed and v >= 0 else ''}{v * 100:.1f}%"


def _range(period: dict) -> str:
    """Half-open [start, end) shown as an inclusive range."""
    start, end = period.get("start"), period.get("end")
    try:
        end = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
    except (TypeError, ValueError):
        pass
    return f"{start} to {end}" if start and end else ""


def _bar_spec(title: str, rows: list[dict], value_title: str) -> dict:
    rows = sorted(rows, key=lambda r: abs(r["value"]), reverse=True)
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": {"text": title, "anchor": "start", "fontSize": 13},
        "width": "container", "height": {"step": 26},
        "data": {"values": rows},
        "mark": {"type": "bar", "cornerRadiusEnd": 3},
        "encoding": {
            "y": {"field": "label", "type": "nominal", "sort": [r["label"] for r in rows], "axis": {"title": None, "labelLimit": 220}},
            "x": {"field": "value", "type": "quantitative", "axis": {"title": value_title}},
            "color": {"field": "tone", "type": "nominal", "scale": {"domain": ["bad", "good", "neutral"], "range": [RED, GREEN, GREY]}, "legend": None},
            "tooltip": [{"field": "label", "title": "Segment"}, {"field": "shown", "title": value_title}],
        },
    }


def _verdict(rca: dict) -> dict:
    rel, fmt = rca.get("rel"), rca["format"]
    return {"title": rca["title"], "delta": _pct(rel) if rel is not None else "n/a",
            "tone": _tone(rel, rca.get("direction")),
            "current": {"label": "Current", "value": format_value(rca["current"]["value"], fmt), "range": _range(rca["current"])},
            "baseline": {"label": "Baseline", "value": format_value(rca["baseline"]["value"], fmt), "range": _range(rca["baseline"])},
            "material": bool(rca.get("material")), "materialLabel": "Material change" if rca.get("material") else "Below threshold"}


def _findings(rca: dict, decomposition: list[dict], cells: list[dict]) -> list[str]:
    rel, fmt = rca.get("rel"), rca["format"]
    out: list[str] = []
    if rel is not None:
        out.append(f"**{rca['title']}** {'fell' if rel < 0 else 'rose'} {_pct(abs(rel), signed=False)} "
                   f"({format_value(rca['baseline']['value'], fmt)} to {format_value(rca['current']['value'], fmt)}).")
    if decomposition:
        d = max(decomposition, key=lambda r: abs(r.get("contribution") or 0))
        out.append(f"Biggest driver: **{d['title']}** ({_pct(d.get('rel'))}, contribution {format_value(d['contribution'], fmt)}).")
    if cells:
        c = max(cells, key=lambda r: abs(r["share"] or 0))
        if c["share"] is not None:
            out.append(f"Hottest segment: **{c['label']}** accounts for {c['share'] * 100:.0f}% of the change.")
    confirmed = [h for h in rca["hypotheses"] if h.get("status") == "confirmed"]
    if confirmed:
        out.append(f"{len(confirmed)} hypothesis(es) confirmed: " + "; ".join(h["claim"] for h in confirmed[:2]) + ("; ..." if len(confirmed) > 2 else ""))
    cautions = [c["title"] for c in rca["checks"] if c["fired"]]
    if cautions:
        out.append("Caution: " + ", ".join(cautions) + " flagged, so read the numbers with care.")
    elif not rca.get("material"):
        out.append("Caution: the movement is below the materiality threshold and may be noise.")
    return out[:MAX_FINDINGS]


def _rca_model(rca: dict) -> dict:
    cells = [{"label": _segment_label(c["segment"]), "share": c["share_of_change"], "rel": c["rel"], "tone": _tone(c["contribution"], rca.get("direction"))}
             for c in rca["drill"]["cells"]]
    marginals = [{"label": dim.replace("_", " "), "value": f"{m['segment'].get(dim, '')} · "
                  f"{'' if m['share_of_change'] is None else format(m['share_of_change'] * 100, '.0f') + '%'}"}
                 for dim, m in rca["drill"]["marginals"].items()]
    fired = [{"label": c["title"], "value": c["detail"], "tone": "warn"} for c in rca["checks"] if c["fired"]]
    fmt = rca["format"]
    driver_rows = [{"label": d["title"], "value": d["contribution"], "shown": format_value(d["contribution"], fmt),
                    "tone": _tone(d["contribution"], rca.get("direction"))} for d in rca["decomposition"] if d.get("contribution") is not None]
    seg_rows = [{"label": c["label"], "value": c["share"] * 100, "shown": f"{c['share'] * 100:.0f}% of change · {_pct(c['rel'])}",
                 "tone": c["tone"]} for c in cells if c["share"] is not None]
    seg_rows = sorted(seg_rows, key=lambda r: abs(r["value"]), reverse=True)[:MAX_SEGMENT_BARS]
    return {"title": rca["title"], "format": fmt, "drillMetric": rca["drill_metric"], "decomposition": rca["decomposition"],
            "cells": cells, "marginals": marginals, "hypotheses": rca["hypotheses"], "checks": fired,
            "verdict": _verdict(rca), "findings": _findings(rca, rca["decomposition"], cells),
            "driverChart": _bar_spec("What drove the change", driver_rows, f"Contribution to {rca['title']}") if driver_rows else None,
            "segmentChart": _bar_spec("Where it happened", seg_rows, "% of total change") if seg_rows else None,
            "footer": f"Runbook {rca.get('tree')} · {rca['queries_run']} governed queries · baseline {rca['baseline']['start']}..{rca['baseline']['end']}"}


def build_surface(result: dict, surface_id: str) -> list[dict]:
    """Returns [createSurface, updateComponents, updateDataModel] for one answer card."""
    components: list[dict] = []
    children: list[str] = []
    model: dict[str, Any] = {"text": result.get("text", ""), "provenance": _provenance(result)}

    def add(cid: str, component: C, top: bool = True, **props: Any) -> None:
        components.append({"id": cid, "component": component.value, **props})
        if top:
            children.append(cid)

    rca_result = result.get("rca")
    if not rca_result:
        add("answer", C.TEXT, text=_bind("/text"))
    if kpis := ([] if rca_result else _kpis(result)):
        model["kpis"] = kpis
        add("kpis", C.KPI_ROW, items=_bind("/kpis"))
    if suggestions := (result.get("meta") or {}).get("suggestions"):
        model["suggestions"] = list(suggestions)
        add("suggestions", C.SUGGESTION_CHIPS, items=_bind("/suggestions"))
    if result.get("chart"):
        model["chart"] = result["chart"]
        add("chart", C.VEGA_LITE_CHART, spec=_bind("/chart"))
    if rca_result:
        rca = _rca_model(rca_result)
        model["rca"] = rca
        add("rca_verdict", C.VERDICT_HEADER, verdict=_bind("/rca/verdict"))
        if rca["findings"]:
            add("rca_findings", C.BULLET_LIST, title="Key findings", items=_bind("/rca/findings"))
        if rca["checks"]:
            add("rca_checks", C.CALLOUTS, items=_bind("/rca/checks"))
        charts = [(cid, key) for cid, key in (("rca_driver_chart", "driverChart"), ("rca_segment_chart", "segmentChart")) if rca[key]]
        for cid, key in charts:
            add(cid, C.VEGA_LITE_CHART, top=False, spec=_bind(f"/rca/{key}"))
        if charts:
            add("rca_charts", C.GRID, children=[cid for cid, _ in charts])
        if rca["decomposition"]:
            add("rca_decomposition", C.DECOMPOSITION_TABLE, rows=_bind("/rca/decomposition"), title=_bind("/rca/title"), format=_bind("/rca/format"))
        if rca["marginals"]:
            add("rca_marginals", C.CHIP_ROW, chips=_bind("/rca/marginals"))
        if rca["hypotheses"]:
            add("rca_hypotheses", C.HYPOTHESIS_LIST, items=_bind("/rca/hypotheses"))
        add("answer_heading", C.HEADING, text="Analyst summary")
        add("answer", C.TEXT, text=_bind("/text"))
        add("rca_footer", C.TEXT, text=_bind("/rca/footer"))
    table = result.get("table")
    if table and len(table["rows"]) >= MIN_TABLE_ROWS:
        model["table"] = table
        add("table", C.DATA_TABLE, table=_bind("/table"))
    if result.get("sql"):
        model["sql"] = result["sql"]
        add("sql", C.SQL_BLOCK, sql=_bind("/sql"))
    add("provenance", C.CHIP_ROW, chips=_bind("/provenance"))

    components.insert(0, {"id": ROOT, "component": C.COLUMN.value, "children": list(children)})
    variant = "error" if result.get("type") == ResponseType.ERROR else "default"
    return [
        {"version": VERSION, A2uiMessage.CREATE_SURFACE.value: {"surfaceId": surface_id, "catalogId": catalog_id(), "theme": {"variant": variant}}},
        {"version": VERSION, A2uiMessage.UPDATE_COMPONENTS.value: {"surfaceId": surface_id, "components": components}},
        {"version": VERSION, A2uiMessage.UPDATE_DATA_MODEL.value: {"surfaceId": surface_id, "path": "/", "value": model}},
    ]
