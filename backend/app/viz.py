"""Pick a chart (Vega-Lite spec) for a tabular result."""
from __future__ import annotations

from app.semantic.catalog import Catalog

_AXIS = {"percent": ".1%", "currency": "$~s", "number": "~s"}


def chart_for(columns: list[str], rows: list[list], cat: Catalog, title: str = "") -> dict | None:
    metrics = [c for c in columns if c in cat.metrics]
    dims = [c for c in columns if c not in cat.metrics and c != "date"]
    if not metrics or len(rows) < 2:
        return None
    values = [dict(zip(columns, r)) for r in rows]
    m = cat.metrics[metrics[0]]
    y = {"field": m.id, "type": "quantitative", "title": m.title, "axis": {"format": _AXIS.get(m.format, "~s")}}
    base = {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "title": title or m.title,
            "data": {"values": values}, "width": "container", "height": 260}
    if "date" in columns:
        enc = {"x": {"field": "date", "type": "temporal", "title": None}, "y": y}
        if dims:
            enc["color"] = {"field": dims[0], "type": "nominal"}
        return {**base, "mark": {"type": "line", "point": len(rows) < 40, "tooltip": True}, "encoding": enc}
    if dims:
        return {**base, "mark": {"type": "bar", "tooltip": True},
                "encoding": {"x": {"field": dims[0], "type": "nominal", "sort": "-y", "title": None}, "y": y}}
    return None
