from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Protocol

import numpy as np

from app.core.config import Settings
from app.core.enums import EmbeddingProvider, LlmProvider
from app.core.errors import LlmError
from app.core.logging import get_logger
from app.llm.vertex import client_options

_TOKEN = re.compile(r"[a-z0-9]+")
log = get_logger("llm.embeddings")


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


def is_rate_limited(error: Exception) -> bool:
    text = str(error).lower()
    return any(m in text for m in ("429", "resource exhausted", "resource_exhausted", "rate limit", "quota", "503", "unavailable"))


class GeminiEmbedder:
    BATCH = 10            # conservative: some embedding endpoints accept few inputs per request
    PAUSE_S = 1.0         # pace batch calls: sharp bursts trip the pay-as-you-go acceleration limits on new projects
    INDEX_ATTEMPTS = 6    # bulk indexing is an offline job: it can afford to wait out a 429 (4, 8, 16, 32, 64 s)
    QUERY_ATTEMPTS = 2    # a user is waiting: retry once quickly, then let hybrid search fall back to lexical-only

    def __init__(self, settings: Settings) -> None:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        self.dim = settings.embedding_dim
        self._client = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, output_dimensionality=settings.embedding_dim,
                                                  **client_options(settings, settings.embedding_location))

    def _call(self, fn, *args, attempts: int, base_delay: float):
        """Truncated exponential backoff on 429 / quota / unavailable; any other error is raised at once."""
        for attempt in range(1, attempts + 1):
            try:
                return fn(*args)
            except Exception as e:
                if not is_rate_limited(e) or attempt == attempts:
                    raise LlmError(f"embedding call failed: {e}") from e
                delay = base_delay * 2 ** (attempt - 1)
                log.warning("embedding call rate limited (attempt %d/%d), retrying in %.0fs: %s", attempt, attempts, delay, str(e)[:160])
                time.sleep(delay)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            chunk = texts[i:i + self.BATCH]
            if i:
                time.sleep(self.PAUSE_S)
            try:
                vectors += self._call(self._client.embed_documents, chunk, attempts=self.INDEX_ATTEMPTS, base_delay=4.0)
            except LlmError as batch_error:
                if len(chunk) == 1 or is_rate_limited(batch_error.__cause__ or batch_error):
                    raise  # never turn a rate limit into a burst of single calls
                # an endpoint that only accepts one input per request: retry one by one, paced
                for text in chunk:
                    vectors += self._call(self._client.embed_documents, [text], attempts=self.INDEX_ATTEMPTS, base_delay=4.0)
                    time.sleep(self.PAUSE_S)
        arr = np.array(vectors, dtype=np.float32)
        return arr / np.linalg.norm(arr, axis=1, keepdims=True)

    def embed_query(self, text: str) -> np.ndarray:
        vec = np.array(self._call(self._client.embed_query, text, attempts=self.QUERY_ATTEMPTS, base_delay=1.0), dtype=np.float32)
        return vec / np.linalg.norm(vec)


def create_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider
    if provider == EmbeddingProvider.AUTO:
        provider = EmbeddingProvider.GEMINI if settings.llm_provider == LlmProvider.GEMINI else EmbeddingProvider.HASH
    return GeminiEmbedder(settings) if provider == EmbeddingProvider.GEMINI else HashEmbedder(settings.embedding_dim)
