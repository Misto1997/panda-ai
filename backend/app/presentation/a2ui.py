"""Builds an A2UI v0.9 surface (https://github.com/google/A2UI) from a ChatResult payload. Pure: no I/O.

The surface uses the PANDA catalog (a2ui_catalog.json). Data lives in the surface data model and components bind to it
with {"path": "/json/pointer"} so the structure stays small and the data can be updated independently."""
from __future__ import annotations

import json
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
                 "caption": f"vs {format_value(base, rca['format'])} baseline", "tone": "bad" if rel and rel < 0 else "good"}]
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


def _rca_model(rca: dict) -> dict:
    cells = [{"label": ", ".join(f"{k}={v}" for k, v in c["segment"].items()), "share": c["share_of_change"], "rel": c["rel"]}
             for c in rca["drill"]["cells"]]
    marginals = [{"label": dim.replace("_", " "), "value": f"{m['segment'].get(dim, '')} · "
                  f"{'' if m['share_of_change'] is None else format(m['share_of_change'] * 100, '.0f') + '%'}"}
                 for dim, m in rca["drill"]["marginals"].items()]
    fired = [{"label": c["title"], "value": c["detail"], "tone": "warn"} for c in rca["checks"] if c["fired"]]
    return {"title": rca["title"], "format": rca["format"], "drillMetric": rca["drill_metric"], "decomposition": rca["decomposition"],
            "cells": cells, "marginals": marginals, "hypotheses": rca["hypotheses"], "checks": fired,
            "footer": f"Runbook {rca.get('tree')} · {rca['queries_run']} governed queries · baseline {rca['baseline']['start']}..{rca['baseline']['end']}"}


def build_surface(result: dict, surface_id: str) -> list[dict]:
    """Returns [createSurface, updateComponents, updateDataModel] for one answer card."""
    components: list[dict] = []
    children: list[str] = []
    model: dict[str, Any] = {"text": result.get("text", ""), "provenance": _provenance(result)}

    def add(cid: str, component: C, **props: Any) -> None:
        components.append({"id": cid, "component": component.value, **props})
        children.append(cid)

    add("answer", C.TEXT, text=_bind("/text"))
    if kpis := _kpis(result):
        model["kpis"] = kpis
        add("kpis", C.KPI_ROW, items=_bind("/kpis"))
    if result.get("chart"):
        model["chart"] = result["chart"]
        add("chart", C.VEGA_LITE_CHART, spec=_bind("/chart"))
    if result.get("rca"):
        rca = _rca_model(result["rca"])
        model["rca"] = rca
        if rca["checks"]:
            add("rca_checks", C.CHIP_ROW, chips=_bind("/rca/checks"))
        if rca["decomposition"]:
            add("rca_decomposition", C.DECOMPOSITION_TABLE, rows=_bind("/rca/decomposition"), title=_bind("/rca/title"), format=_bind("/rca/format"))
        add("rca_segments", C.SEGMENT_BARS, cells=_bind("/rca/cells"), metric=_bind("/rca/drillMetric"))
        if rca["marginals"]:
            add("rca_marginals", C.CHIP_ROW, chips=_bind("/rca/marginals"))
        add("rca_hypotheses", C.HYPOTHESIS_LIST, items=_bind("/rca/hypotheses"))
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
