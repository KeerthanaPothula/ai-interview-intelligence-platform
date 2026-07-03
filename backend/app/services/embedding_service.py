"""Sentence embedding service — lazy-loads sentence-transformers."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"

_model = None
_model_lock = threading.Lock()


def _get_model():
    """Lazy-load the SentenceTransformer model on first call (thread-safe).

    Double-checked locking prevents two concurrent callers from both loading
    the ~90 MB model when _model is None. Only the first caller acquires the
    lock and loads; all subsequent callers take the fast path (outer if is
    False) and return the already-loaded model without touching the lock.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer  # type: ignore

                _model = SentenceTransformer(_MODEL_NAME)
                logger.info("Loaded sentence-transformer model: %s", _MODEL_NAME)
    return _model


def encode_text(text: str) -> list[float]:
    """Encode text to a unit-normalised float embedding vector."""
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity of two pre-normalised embedding vectors.

    Both vectors are produced by encode_text with normalize_embeddings=True,
    so ||a|| = ||b|| = 1.0 always. For unit vectors, cosine similarity
    equals the dot product — the two sqrt calls are skipped entirely.
    """
    return sum(x * y for x, y in zip(a, b))


def retrieve_top_k(
    query_embedding: list[float],
    chunk_embeddings: list[tuple[str, list[float]]],
    k: int = 5,
) -> list[tuple[str, float]]:
    """Return top-k (chunk_text, score) pairs sorted by cosine similarity."""
    scored = [
        (text, cosine_similarity(query_embedding, emb))
        for text, emb in chunk_embeddings
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
