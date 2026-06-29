"""RAG (Retrieval-Augmented Generation) service for personalised question generation."""

from __future__ import annotations

import json
import logging
import uuid

import google.genai as genai
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.ai_reliability import call_gemini_with_retry, parse_json_response
from app.core.tracing import get_tracer
from app.models.documents import DocumentChunk
from app.services import embedding_service

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={"timeout": settings.GEMINI_TIMEOUT_SECONDS},
        )
    return _client


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split text into overlapping word-count chunks."""
    settings = get_settings()
    chunk_size = chunk_size if chunk_size is not None else settings.RAG_CHUNK_SIZE
    overlap = overlap if overlap is not None else settings.RAG_CHUNK_OVERLAP

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
            logger.warning(
                "Embedding failed for chunk %d — storing without embedding", idx
            )
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
    with tracer.start_as_current_span("rag.retrieve_relevant_chunks") as span:
        span.set_attribute("rag.k", k)

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
            top_k = embedding_service.retrieve_top_k(
                query_embedding, chunk_embeddings, k=k
            )
            return [text for text, _ in top_k]
        except Exception:
            logger.warning(
                "RAG retrieval embedding failed — returning first %d chunks", k
            )
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

    context = "\n\n".join(
        f"[Resume excerpt {i + 1}]: {chunk}" for i, chunk in enumerate(relevant_chunks)
    )

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

    settings = get_settings()
    response = call_gemini_with_retry(
        lambda: client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=prompt
        ),
        operation="RAG question generation",
    )
    questions = parse_json_response(
        response.text, operation="RAG question generation", expect=list
    )
    for i, q in enumerate(questions):
        q["sequence_order"] = i + 1
        q.setdefault("category", "behavioral")
    return questions[:count]
