from app.llm.base import Term, Vocabulary
from app.semantic.catalog import Catalog


def build_vocabulary(catalog: Catalog) -> Vocabulary:
    return Vocabulary(
        metrics=[Term(m.id, [m.id.replace("_", " "), m.title, *m.aliases]) for m in catalog.metrics.values()],
        dimensions=[Term(d.id, [d.id.replace("_", " "), d.title, *d.aliases], d.values)
                    for d in catalog.dimensions.values() if d.id != "date"])
