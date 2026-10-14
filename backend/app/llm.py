"""Thin LLM/embedding abstraction. `mock` runs offline with rule-based behaviour so the whole
pipeline (and the demo fallback) works without credentials; `gemini` uses Google models."""
from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol, TypeVar

import numpy as np
from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    name: str

    def structured(self, schema: type[T], system: str, user: str, hints: dict | None = None) -> T: ...
    def text(self, system: str, user: str, hints: dict | None = None, pro: bool = False) -> str: ...


class GeminiLLM:
    name = "gemini"

    def __init__(self) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        s = get_settings()
        self._flash = ChatGoogleGenerativeAI(model=s.gemini_model, temperature=0)
        self._pro = ChatGoogleGenerativeAI(model=s.gemini_pro_model, temperature=0.2)

    def structured(self, schema: type[T], system: str, user: str, hints: dict | None = None) -> T:
        return self._flash.with_structured_output(schema).invoke([("system", system), ("human", user)])

    def text(self, system: str, user: str, hints: dict | None = None, pro: bool = False) -> str:
        out = (self._pro if pro else self._flash).invoke([("system", system), ("human", user)]).content
        return out if isinstance(out, str) else "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in out)


@lru_cache
def get_llm() -> LLM:
    if get_settings().llm_provider == "gemini":
        return GeminiLLM()
    from app.mock_llm import MockLLM
    return MockLLM()


# ---------- embeddings ----------
_TOKEN = re.compile(r"[a-z0-9]+")


def _hash_embed(text: str, dim: int) -> np.ndarray:
    """Offline fallback: signed feature hashing of word unigrams/bigrams + char trigrams."""
    v = np.zeros(dim, dtype=np.float32)
    toks = _TOKEN.findall(text.lower())
    feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])] + [w[i:i + 3] for w in toks for i in range(max(1, len(w) - 2))]
    for f in feats:
        h = int(hashlib.md5(f.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 64) & 1 else -1.0
    n = math.sqrt(float((v * v).sum())) or 1.0
    return v / n


def embed(texts: list[str]) -> np.ndarray:
    s = get_settings()
    if s.llm_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        emb = GoogleGenerativeAIEmbeddings(model=s.embedding_model, output_dimensionality=s.embedding_dim)
        arr = np.array(emb.embed_documents(texts), dtype=np.float32)
        return arr / np.linalg.norm(arr, axis=1, keepdims=True)
    return np.stack([_hash_embed(t, s.embedding_dim) for t in texts])
