from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import numpy as np

from app.core.config import Settings
from app.core.enums import LlmProvider
from app.core.errors import LlmError
from app.llm.vertex import client_options

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashEmbedder:
    """Offline fallback: signed feature hashing of word unigrams/bigrams and char trigrams. Unit-normalised."""

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._one(t) for t in texts])

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = _TOKEN.findall(text.lower())
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])] + [w[i:i + 3] for w in tokens for i in range(max(1, len(w) - 2))]
        for f in features:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        return vec / (math.sqrt(float((vec * vec).sum())) or 1.0)


class GeminiEmbedder:
    def __init__(self, settings: Settings) -> None:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        self.dim = settings.embedding_dim
        self._client = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, output_dimensionality=settings.embedding_dim,
                                                  **client_options(settings, settings.embedding_location))

    def embed(self, texts: list[str]) -> np.ndarray:
        try:
            arr = np.array(self._client.embed_documents(texts), dtype=np.float32)
        except Exception as e:
            raise LlmError(f"embedding call failed: {e}") from e
        return arr / np.linalg.norm(arr, axis=1, keepdims=True)


def create_embedder(settings: Settings) -> Embedder:
    return GeminiEmbedder(settings) if settings.llm_provider == LlmProvider.GEMINI else HashEmbedder(settings.embedding_dim)
