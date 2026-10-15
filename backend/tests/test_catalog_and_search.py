import shutil

import pytest

from app.core.config import get_settings
from app.core.enums import DocKind
from app.core.errors import CatalogError
from app.search.hybrid import reciprocal_rank_fusion
from app.semantic.loader import load_catalog


def test_catalog_references_are_consistent(container):
    cat = container.catalog
    assert {"net_gmv", "gross_gmv", "net_units", "gross_units", "visits", "bu_visits"} <= set(cat.metrics)
    assert {"marketplace", "business_unit", "zone", "region", "state", "city"} <= set(cat.dimensions)
    assert len(cat.dimensions["city"].hierarchy) == 32 and all(len(t.hypotheses) >= 4 for t in cat.trees.values())


def test_broken_reference_fails_at_load(tmp_path):
    shutil.copytree(get_settings().semantic_dir, tmp_path / "semantic")
    (tmp_path / "semantic/metrics/asp.md").write_text((tmp_path / "semantic/metrics/asp.md").read_text().replace("table: sales", "table: ghost"))
    with pytest.raises(CatalogError, match="unknown table ghost"):
        load_catalog(tmp_path / "semantic")


def test_rrf_prefers_agreement():
    assert max(reciprocal_rank_fusion([["a", "b"], ["b", "c"]]).items(), key=lambda kv: kv[1])[0] == "b"


def test_hybrid_search_maps_synonyms_and_expands_dimensions(container):
    hits = container.search.search("revenue", 5, {DocKind.METRIC})
    assert hits[0].id == "net_gmv"  # "revenue" is an alias of Net GMV
    assert {"marketplace", "zone"} <= {d.id for d in hits}  # graph expansion pulled the allowed dimensions
