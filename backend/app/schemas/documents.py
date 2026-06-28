from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ResumeDocumentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    extracted_text: str | None
    created_at: datetime
    chunk_count: int = 0

    model_config = {"from_attributes": True}


class RAGQuestionsRequest(BaseModel):
    # Bounded the same as MAX_QUESTIONS_PER_SESSION (app/config.py): an
    # unbounded count would let a caller force an arbitrarily large Gemini
    # prompt/response, inflating token usage and latency.
    count: int = Field(default=5, ge=1, le=20)


class RAGQuestionItem(BaseModel):
    body: str
    category: str
    sequence_order: int


class RAGQuestionsResponse(BaseModel):
    session_id: uuid.UUID
    questions: list[RAGQuestionItem]
    resume_context_used: bool
    chunks_retrieved: int
