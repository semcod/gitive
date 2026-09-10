"""Embeddings.

Design note worth reading before you change this:

OpenRouter is a *chat completion* router; it does not reliably expose embedding
models. If we made embeddings a hard dependency on OpenRouter, the loop would be
dead on arrival for most users. So the chain is:

    INTUITION_EMBED_MODEL set  ->  litellm.embedding(...)   (any provider)
    otherwise / on failure     ->  HashingEmbedder          (offline, deterministic)

The hashing embedder is signed feature hashing over character 4-grams and word
tokens, L2-normalised. It is not semantic, but every quantity the model actually
needs -- cosine against the tension vector, redundancy against past tasks, decay
weighted centroid -- degrades gracefully into lexical similarity. That is enough
to run the loop; swap in a real embedding provider for better task ranking.
"""
from __future__ import annotations

import hashlib
import re

import numpy as np

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|\d+")


def _tokens(text: str) -> list[str]:
    t = text.lower()
    words = _WORD.findall(t)
    grams = [t[i : i + 4] for i in range(0, max(0, len(t) - 3), 2)][:4000]
    return words + grams


class HashingEmbedder:
    """Deterministic, dependency-free, offline."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _one(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in _tokens(text):
            h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            v[idx] += sign
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v

    def __call__(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._one(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)


class Embedder:
    def __init__(self, model: str = "", dim: int = 512) -> None:
        self.model = model
        self.dim = dim
        self._fallback = HashingEmbedder(dim)
        self._degraded = not model

    def __call__(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        if self.model and not self._degraded:
            try:
                import litellm  # imported lazily: package stays usable offline

                resp = litellm.embedding(model=self.model, input=texts)
                vecs = np.array([d["embedding"] for d in resp["data"]], dtype=np.float32)
                norms = np.linalg.norm(vecs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self.dim = vecs.shape[1]
                return vecs / norms
            except Exception as exc:  # provider missing, no key, rate limit, ...
                print(f"[intuition] embedding provider failed ({exc}); using hashing fallback")
                self._degraded = True
        return self._fallback(texts)

    @property
    def degraded(self) -> bool:
        return self._degraded
