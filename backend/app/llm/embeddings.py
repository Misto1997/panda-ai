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
    def embed_query(self, text: str) -> np.ndarray: ...


class HashEmbedder:
    """Offline fallback: signed feature hashing of word unigrams/bigrams and char trigrams. Unit-normalised."""

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._one(t) for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._one(text)

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

    BATCH = 10  # conservative: some embedding endpoints accept few inputs per request

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            chunk = texts[i:i + self.BATCH]
            try:
                vectors += self._client.embed_documents(chunk)
            except Exception as batch_error:  # an endpoint that only accepts one input per request: retry one by one
                if len(chunk) == 1:
                    raise LlmError(f"embedding call failed: {batch_error}") from batch_error
                try:
                    vectors += [self._client.embed_documents([t])[0] for t in chunk]
                except Exception as e:
                    raise LlmError(f"embedding call failed: {e}") from e
        arr = np.array(vectors, dtype=np.float32)
        return arr / np.linalg.norm(arr, axis=1, keepdims=True)

    def embed_query(self, text: str) -> np.ndarray:
        try:
            vec = np.array(self._client.embed_query(text), dtype=np.float32)
        except Exception as e:
            raise LlmError(f"embedding call failed: {e}") from e
        return vec / np.linalg.norm(vec)


def create_embedder(settings: Settings) -> Embedder:
    return GeminiEmbedder(settings) if settings.llm_provider == LlmProvider.GEMINI else HashEmbedder(settings.embedding_dim)
