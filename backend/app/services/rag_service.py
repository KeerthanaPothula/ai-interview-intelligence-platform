"""RAG (Retrieval-Augmented Generation) service for personalised question generation."""

from __future__ import annotations

import json
import logging
import uuid

import google.genai as genai
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.documents import DocumentChunk
from app.services import embedding_service

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.0-flash"
_CHUNK_SIZE = 200
_CHUNK_OVERLAP = 50
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={"timeout": 30},
        )
    return _client


def chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping word-count chunks."""
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def store_chunks(
    *,
    user_id: uuid.UUID,
    chunks: list[str],
    source_type: str,
    resume_document_id: uuid.UUID | None,
    db: Session,
) -> int:
    """Embed and persist text chunks. Returns the number of chunks stored."""
    stored = 0
    for idx, chunk_text_str in enumerate(chunks):
        try:
            embedding = embedding_service.encode_text(chunk_text_str)
            embedding_json = json.dumps(embedding)
        except Exception:
            logger.warning("Embedding failed for chunk %d — storing without embedding", idx)
            embedding_json = None

        chunk = DocumentChunk(
            user_id=user_id,
            resume_document_id=resume_document_id,
            chunk_text=chunk_text_str,
            embedding_json=embedding_json,
            chunk_index=idx,
            source_type=source_type,
        )
        db.add(chunk)
        stored += 1

    db.flush()
    return stored


def retrieve_relevant_chunks(
    *,
    query_text: str,
    user_id: uuid.UUID,
    db: Session,
    k: int = 5,
) -> list[str]:
    """Return top-k relevant chunk texts for a query from the user's stored chunks."""
    stmt = select(DocumentChunk).where(DocumentChunk.user_id == user_id)
    chunks = db.execute(stmt).scalars().all()

    if not chunks:
        return []

    chunk_embeddings = []
    for c in chunks:
        if c.embedding_json:
            try:
                emb = json.loads(c.embedding_json)
                chunk_embeddings.append((c.chunk_text, emb))
            except Exception:
                pass

    if not chunk_embeddings:
        return [c.chunk_text for c in chunks[:k]]

    try:
        query_embedding = embedding_service.encode_text(query_text)
        top_k = embedding_service.retrieve_top_k(query_embedding, chunk_embeddings, k=k)
        return [text for text, _ in top_k]
    except Exception:
        logger.warning("RAG retrieval embedding failed — returning first %d chunks", k)
        return [c.chunk_text for c in chunks[:k]]


def generate_rag_questions(
    *,
    job_role: str,
    job_description: str,
    relevant_chunks: list[str],
    count: int = 5,
) -> list[dict]:
    """Generate personalised interview questions from retrieved resume context."""
    client = _get_client()

    context = "\n\n".join(f"[Resume excerpt {i + 1}]: {chunk}" for i, chunk in enumerate(relevant_chunks))

    prompt = (
        f"You are an expert technical interviewer hiring for a {job_role}.\n\n"
        f"Job Description:\n{job_description[:800]}\n\n"
        f"Candidate Resume Context:\n{context[:2000]}\n\n"
        f"Generate exactly {count} personalised interview questions that:\n"
        "- Reference specific experiences from the candidate's resume\n"
        "- Are relevant to the job requirements\n"
        "- Cover behavioral, technical, and situational aspects\n\n"
        "Return a JSON array only, no markdown fences:\n"
        '[{"body": "question text", "category": "technical|behavioral|situational", "sequence_order": 1}, ...]'
    )

    response = client.models.generate_content(model=_MODEL, contents=prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    questions = json.loads(raw)
    for i, q in enumerate(questions):
        q["sequence_order"] = i + 1
        q.setdefault("category", "behavioral")
    return questions[:count]
