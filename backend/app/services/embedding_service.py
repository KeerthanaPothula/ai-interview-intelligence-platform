"""Sentence embedding service — lazy-loads sentence-transformers."""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

_model = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model():
    """Lazy-load the SentenceTransformer model on first call."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Loaded sentence-transformer model: %s", _MODEL_NAME)
    return _model


def encode_text(text: str) -> list[float]:
    """Encode text to a float embedding vector."""
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two normalised vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


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
