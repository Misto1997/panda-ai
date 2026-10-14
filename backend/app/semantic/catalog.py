"""Loads the file-based semantic layer (markdown + YAML frontmatter) into a typed catalog."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings

_FM = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)


@dataclass
class Doc:
    """One searchable chunk of the semantic layer."""
    id: str
    kind: str
    title: str
    text: str  # what gets indexed
    meta: dict = field(default_factory=dict)


@dataclass
class Metric:
    id: str
    title: str
    table: str
    aliases: list[str]
    description: str
    expr: str | None
    numerator: str | None
    denominator: str | None
    unit: str
    format: str
    direction: str
    dimensions: list[str]

    @property
    def is_ratio(self) -> bool:
        return self.numerator is not None


@dataclass
class Dimension:
    id: str
    title: str
    column: str
    tables: list[str]
    aliases: list[str]
    values: list[str]


@dataclass
class Table:
    id: str
    raw: str
    rollup: str
    time_column: str
    rollup_dimensions: list[str]


@dataclass
class Catalog:
    metrics: dict[str, Metric]
    dimensions: dict[str, Dimension]
    tables: dict[str, Table]
    trees: dict[str, dict]
    checks: dict[str, dict]
    policies: dict[str, dict]
    docs: list[Doc]

    def metric_by_name(self, name: str) -> Metric | None:
        n = name.strip().lower().replace(" ", "_")
        if n in self.metrics:
            return self.metrics[n]
        for m in self.metrics.values():
            if n in {a.lower().replace(" ", "_") for a in m.aliases} or n == m.title.lower().replace(" ", "_"):
                return m
        return None

    def tree_for(self, metric_id: str) -> dict | None:
        return next((t for t in self.trees.values() if t["root_metric"] == metric_id), None)


def _parse(path: Path) -> tuple[dict, str]:
    m = _FM.match(path.read_text())
    if not m:
        raise ValueError(f"{path}: missing frontmatter")
    return yaml.safe_load(m.group(1)), m.group(2).strip()


@lru_cache
def load_catalog(semantic_dir: str | None = None) -> Catalog:
    root = Path(semantic_dir or get_settings().semantic_dir)
    cat = Catalog({}, {}, {}, {}, {}, {}, [])
    for path in sorted(root.rglob("*.md")):
        fm, body = _parse(path)
        kind = fm["kind"]
        if kind == "metric":
            m = Metric(fm["id"], fm["title"], fm["table"], fm.get("aliases", []), fm["description"], fm.get("expr"),
                       fm.get("numerator"), fm.get("denominator"), fm.get("unit", ""), fm.get("format", "number"),
                       fm.get("direction", "neutral"), fm.get("dimensions", []))
            cat.metrics[m.id] = m
            text = f"{m.title}. Also called {', '.join(m.aliases)}. {m.description} {body} Dimensions: {', '.join(m.dimensions)}."
            cat.docs.append(Doc(m.id, "metric", m.title, text, {"dimensions": m.dimensions}))
        elif kind == "dimension":
            d = Dimension(fm["id"], fm["title"], fm["column"], fm.get("tables", []), fm.get("aliases", []), fm.get("values", []))
            cat.dimensions[d.id] = d
            text = f"{d.title}. Also called {', '.join(d.aliases)}. {fm['description']} Values: {', '.join(d.values)}."
            cat.docs.append(Doc(d.id, "dimension", d.title, text))
        elif kind == "table":
            t = Table(fm["id"], fm["raw"], fm["rollup"], fm["time_column"], fm.get("rollup_dimensions", []))
            cat.tables[t.id] = t
        elif kind == "glossary":
            for t in fm["terms"]:
                cat.docs.append(Doc(f"glossary:{t['term']}", "glossary", t["term"],
                                    f"{t['term']} ({t['full_form']}): {t['definition']}"))
        elif kind == "rca_tree":
            cat.trees[fm["id"]] = fm
            hyp = "; ".join(h["claim"] for h in fm.get("hypotheses", []))
            cat.docs.append(Doc(fm["id"], "rca_tree", fm["title"],
                                f"RCA runbook: {fm['title']}. Root metric {fm['root_metric']}. {body} Hypotheses: {hyp}."))
        elif kind == "rca_check":
            cat.checks[fm["id"]] = fm
            cat.docs.append(Doc(fm["id"], "rca_check", fm["title"], f"{fm['title']}: {fm['description']}"))
        elif kind == "rca_policy":
            cat.policies[fm["id"]] = fm
    return cat
