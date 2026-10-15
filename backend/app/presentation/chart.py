"""Chooses a Vega-Lite chart for a tabular result."""
from __future__ import annotations

from app.core.enums import ValueFormat
from app.semantic.catalog import Catalog

_AXIS_FORMAT = {ValueFormat.PERCENT: ".1%", ValueFormat.CURRENCY: "$~s", ValueFormat.NUMBER: "~s"}
SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"
MAX_CATEGORIES = 40


class ChartBuilder:
    def __init__(self, catalog: Catalog) -> None:
        self.cat = catalog

    def build(self, columns: list[str], rows: list[list]) -> dict | None:
        metrics = [c for c in columns if c in self.cat.metrics]
        dims = [c for c in columns if c not in self.cat.metrics and c != "date"]
        if not metrics or len(rows) < 2:
            return None
        metric = self.cat.metrics[metrics[0]]
        y = {"field": metric.id, "type": "quantitative", "title": metric.title,
             "axis": {"format": _AXIS_FORMAT.get(metric.format, "~s")}}
        spec = {"$schema": SCHEMA, "title": metric.title, "width": "container", "height": 260,
                "data": {"values": [dict(zip(columns, r)) for r in rows]}}
        if "date" in columns:
            encoding = {"x": {"field": "date", "type": "temporal", "title": None}, "y": y}
            if dims:
                encoding["color"] = {"field": dims[0], "type": "nominal"}
            return {**spec, "mark": {"type": "line", "point": len(rows) < 40, "tooltip": True}, "encoding": encoding}
        if dims and len(rows) <= MAX_CATEGORIES:
            return {**spec, "mark": {"type": "bar", "tooltip": True},
                    "encoding": {"x": {"field": dims[0], "type": "nominal", "sort": "-y", "title": None}, "y": y}}
        return None
