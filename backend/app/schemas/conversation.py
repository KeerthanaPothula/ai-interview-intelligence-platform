from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class StartLiveInterviewRequest(BaseModel):
    job_role: str = Field(..., min_length=2, max_length=200)
    job_description: str = Field(..., min_length=20, max_length=10000)
    max_turns: int = Field(default=5, ge=3, le=10)


class ConversationTurnResponse(BaseModel):
    id: uuid.UUID
    live_session_id: uuid.UUID
    turn_number: int
    question_text: str
    difficulty_level: int
    response_text: str | None
    audio_response_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NextQuestionRequest(BaseModel):
    response_text: str | None = Field(default=None, max_length=5000)
    audio_response_id: uuid.UUID | None = None


class LiveInterviewSessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    job_role: str
    job_description: str
    status: str
    current_turn: int
    max_turns: int
    created_at: datetime
    completed_at: datetime | None
    turns: list[ConversationTurnResponse] = []
    current_question: ConversationTurnResponse | None = None

    model_config = {"from_attributes": True}


class EndInterviewResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    total_turns: int
    summary: str
    turns: list[ConversationTurnResponse]
