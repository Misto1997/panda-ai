"""Zero-infrastructure backend: BM25 for lexical ranking, brute-force cosine for vectors."""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

from app.llm.embeddings import Embedder
from app.semantic.models import Doc

_TOKEN = re.compile(r"[a-z0-9]+")
K1, B = 1.5, 0.75


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class MemoryBackend:
    name = "memory(bm25+vector)"

    def __init__(self, docs: list[Doc], embedder: Embedder) -> None:
        self._docs, self._embedder = docs, embedder
        self._tokens = [tokenize(f"{d.title} {d.id} {d.text}") for d in docs]
        self._df = Counter(t for toks in self._tokens for t in set(toks))
        self._avg_len = sum(map(len, self._tokens)) / max(1, len(docs))
        self._vectors = embedder.embed([d.text for d in docs])

    def lexical(self, query: str, limit: int) -> list[str]:
        n_docs, scores = len(self._docs), []
        for toks in self._tokens:
            tf, score = Counter(toks), 0.0
            for term in tokenize(query):
                if term in tf:
                    idf = math.log(1 + (n_docs - self._df[term] + 0.5) / (self._df[term] + 0.5))
                    score += idf * tf[term] * (K1 + 1) / (tf[term] + K1 * (1 - B + B * len(toks) / self._avg_len))
            scores.append(score)
        order = np.argsort(scores)[::-1][:limit]
        return [self._docs[i].id for i in order if scores[i] > 0]

    def vector(self, query: str, limit: int) -> list[str]:
        sims = self._vectors @ self._embedder.embed_query(query)
        return [self._docs[i].id for i in np.argsort(sims)[::-1][:limit]]
