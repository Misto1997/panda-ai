"""Reads `semantic/**/*.md` (YAML frontmatter + markdown body) into a validated Catalog."""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from app.core.enums import DocKind
from app.core.errors import CatalogError
from app.core.logging import get_logger
from app.semantic.catalog import Catalog
from app.semantic.models import (CheckSpec, DimensionSpec, Doc, GlossarySpec, MetricSpec, PolicySpec, RcaTreeSpec, TableSpec)

log = get_logger("semantic.loader")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
_SPECS: dict[str, type[BaseModel]] = {
    "metric": MetricSpec, "dimension": DimensionSpec, "table": TableSpec, "glossary": GlossarySpec,
    "rca_tree": RcaTreeSpec, "rca_check": CheckSpec, "rca_policy": PolicySpec,
}


def _read(path: Path) -> tuple[dict, str]:
    match = _FRONTMATTER.match(path.read_text())
    if not match:
        raise CatalogError(f"{path}: missing YAML frontmatter")
    try:
        return yaml.safe_load(match.group(1)), match.group(2).strip()
    except yaml.YAMLError as e:
        raise CatalogError(f"{path}: invalid YAML: {e}") from e


def load_catalog(directory: str | Path) -> Catalog:
    root = Path(directory)
    if not root.is_dir():
        raise CatalogError(f"semantic directory not found: {root}")
    cat = Catalog()
    for path in sorted(root.rglob("*.md")):
        frontmatter, body = _read(path)
        spec_cls = _SPECS.get(frontmatter.get("kind", ""))
        if spec_cls is None:
            raise CatalogError(f"{path}: unknown kind '{frontmatter.get('kind')}'")
        try:
            spec = spec_cls.model_validate(frontmatter)
        except ValidationError as e:
            raise CatalogError(f"{path}: {e}") from e
        _register(cat, spec, body)
    cat.validate_references()
    log.info("catalog loaded: %d metrics, %d dimensions, %d tables, %d rca trees, %d docs",
             len(cat.metrics), len(cat.dimensions), len(cat.tables), len(cat.trees), len(cat.docs))
    return cat


def _register(cat: Catalog, spec: BaseModel, body: str) -> None:
    if isinstance(spec, MetricSpec):
        cat.metrics[spec.id] = spec
        text = (f"{spec.title}. Also called {', '.join(spec.aliases)}. {spec.description} {body} "
                f"Dimensions: {', '.join(spec.dimensions)}.")
        cat.docs.append(Doc(id=spec.id, kind=DocKind.METRIC, title=spec.title, text=text, related=spec.dimensions))
    elif isinstance(spec, DimensionSpec):
        cat.dimensions[spec.id] = spec
        sample = ", ".join(spec.values[:12]) + (" ..." if len(spec.values) > 12 else "")
        text = f"{spec.title}. Also called {', '.join(spec.aliases)}. {spec.description} Values: {sample}."
        cat.docs.append(Doc(id=spec.id, kind=DocKind.DIMENSION, title=spec.title, text=text))
    elif isinstance(spec, TableSpec):
        cat.tables[spec.id] = spec
    elif isinstance(spec, GlossarySpec):
        for t in spec.terms:
            cat.docs.append(Doc(id=f"glossary:{t.term}", kind=DocKind.GLOSSARY, title=t.term,
                                text=f"{t.term} ({t.full_form}): {t.definition}"))
    elif isinstance(spec, RcaTreeSpec):
        cat.trees[spec.id] = spec
        claims = "; ".join(h.claim for h in spec.hypotheses)
        text = f"RCA runbook: {spec.title}. Root metric {spec.root_metric}. {body} Hypotheses: {claims}."
        cat.docs.append(Doc(id=spec.id, kind=DocKind.RCA_TREE, title=spec.title, text=text))
    elif isinstance(spec, CheckSpec):
        cat.checks[spec.id] = spec
        cat.docs.append(Doc(id=spec.id, kind=DocKind.RCA_CHECK, title=spec.title, text=f"{spec.title}: {spec.description}"))
    elif isinstance(spec, PolicySpec):
        cat.policies[spec.id] = spec
