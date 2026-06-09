from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    """Request body for POST /interviews."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Short name for this session, e.g. 'Google SWE Round 1'.",
    )
    job_role: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Role being interviewed for, e.g. 'Software Engineer Intern'.",
    )
    job_description: str = Field(
        ...,
        min_length=20,
        description=(
            "Full job description text used by Gemini to generate relevant "
            "questions. Must be at least 20 characters so Gemini has enough "
            "context to produce meaningful questions."
        ),
    )


class SessionUpdate(BaseModel):
    """Request body for PATCH /interviews/{id}.

    All fields are optional — send only what you want to change (PATCH
    semantics). The service inspects `model_fields_set` to skip columns
    that were not included in the request body, so an absent field is
    treated as 'no change', not as an explicit null.

    Validation still applies to fields that *are* sent: an empty title
    string is rejected even though the field is optional.
    """

    title: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="New session title. Omit to leave unchanged.",
    )
    job_role: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="New job role. Omit to leave unchanged.",
    )
    job_description: str | None = Field(
        None,
        min_length=20,
        description="New job description. Omit to leave unchanged.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
#
# from_attributes=True (ConfigDict) tells Pydantic v2 to read field values
# from ORM object attributes (e.g. `session.title`) rather than only from
# dict keys. FastAPI calls `ResponseModel.model_validate(orm_object)` when
# serialising a route's response_model — without from_attributes=True this
# raises PydanticUserError because ORM objects are not dicts.
#
# Nested schemas (QuestionResponse inside SessionDetailResponse) also require
# from_attributes=True because Pydantic validates each element in the
# `questions` list by calling QuestionResponse.model_validate(question_orm).


class QuestionResponse(BaseModel):
    """Serialised representation of one Question ORM row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique question identifier.")
    body: str = Field(description="Full text of the interview question.")
    sequence_order: int = Field(
        description="1-based position of this question in the session."
    )
    category: str | None = Field(
        None,
        description=(
            "Question category assigned by Gemini: 'behavioral', 'technical', "
            "or 'situational'. Null if Gemini did not categorise the question."
        ),
    )
    source: str = Field(
        description="How the question was created: 'ai_generated' or 'manual'."
    )
    created_at: datetime = Field(description="UTC timestamp of question creation.")


class SessionListResponse(BaseModel):
    """One item in the list returned by GET /interviews.

    Excludes job_description — list payloads can contain 50+ sessions and
    job descriptions can be several kilobytes each. The detail endpoint
    includes job_description for the single-session view.

    Excludes nested questions and audio responses — callers use the detail
    endpoint to retrieve those.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique session identifier.")
    title: str = Field(description="Session title.")
    job_role: str = Field(description="Role being interviewed for.")
    status: str = Field(
        description=(
            "Session lifecycle state: 'draft', 'in_progress', 'processing', "
            "or 'completed'."
        )
    )
    created_at: datetime = Field(description="UTC timestamp of session creation.")
    updated_at: datetime = Field(description="UTC timestamp of last modification.")


class SessionDetailResponse(BaseModel):
    """Full session returned by GET /interviews/{id}.

    Includes job_description (omitted from the list view), the ordered list
    of generated questions, and a count of submitted audio responses.

    response_count vs raw AudioResponse rows
    ----------------------------------------
    Exposing raw AudioResponse objects would leak internal storage metadata
    (file paths, MIME types, upload directory layout). response_count gives
    the client what it needs to render UI state ('3 of 5 answers recorded')
    without exposing storage internals. The full response list is available
    only via GET /interviews/{id}/responses, which applies its own
    serialisation boundary (backend/app/schemas/analysis.py).

    Service usage note
    ------------------
    `response_count` is not an ORM column — Pydantic cannot derive it from
    the InterviewSession object alone. The service or route handler must
    supply it explicitly:

        SessionDetailResponse.model_validate(
            session,
            update={"response_count": len(session.audio_responses)},
        )

    or equivalently via keyword argument if constructing directly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique session identifier.")
    title: str = Field(description="Session title.")
    job_role: str = Field(description="Role being interviewed for.")
    job_description: str = Field(
        description="Full job description used for question generation."
    )
    status: str = Field(
        description=(
            "Session lifecycle state: 'draft', 'in_progress', 'processing', "
            "or 'completed'."
        )
    )
    created_at: datetime = Field(description="UTC timestamp of session creation.")
    updated_at: datetime = Field(description="UTC timestamp of last modification.")
    questions: list[QuestionResponse] = Field(
        description=(
            "Ordered list of interview questions (ascending sequence_order). "
            "Empty list when no questions have been generated yet."
        )
    )
    response_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of audio responses submitted for this session. "
            "Provided by the service layer — not a DB column."
        ),
    )
