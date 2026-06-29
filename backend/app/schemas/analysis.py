from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResponseStatus = Literal["uploaded", "processing", "completed", "failed"]


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AudioResponseCreate(BaseModel):
    """Form metadata for POST /interviews/{session_id}/responses.

    The audio file itself is received as a multipart UploadFile and is not
    part of this schema. This schema validates only the structured metadata
    that accompanies the upload.
    """

    question_id: uuid.UUID = Field(
        description=(
            "UUID of the Question this recording answers. "
            "Must belong to the same session as the upload endpoint's session_id."
        )
    )


class ProcessResponseRequest(BaseModel):
    """Request body for POST /api/v1/responses/{response_id}/process.

    Carries the UUID of the audio response to be submitted for processing.
    The router reads response_id from both the URL path parameter and this
    body. Future iterations may extend this schema with processing options
    (e.g. force_reprocess, model_override) without changing the endpoint URL.
    """

    response_id: uuid.UUID = Field(
        description="UUID of the audio response to submit for AI processing."
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
#
# Three storage fields are intentionally absent from all response schemas:
#
#   file_path   — leaks the server's upload directory structure and file-naming
#                 convention. A client that knows the path could probe file
#                 existence or, if a future route serves static files, attempt
#                 path traversal. The client references recordings by UUID, not
#                 by filesystem path.
#
#   file_size_bytes, mime_type — internal bookkeeping used by the Week 3 pipeline.
#                 Surfacing them in the API would lock the storage format into
#                 the public contract, making it harder to change later.
#
#   user_id, session_id — derivable from the JWT and the URL respectively;
#                 echoing them adds payload size with no client benefit.
#
# error_message is exposed only via AudioResponseStatusResponse (the status
# polling endpoint) because:
#   - It is always null at upload time (status is always 'uploaded' immediately
#     after a successful upload — the pipeline has not run yet).
#   - The status endpoint is the correct place to surface pipeline failures
#     because that is when status == 'failed' can first occur.
#   - Keeping error_message off AudioResponseResponse prevents callers from
#     writing error-handling logic against a field that is always null there.


class AudioResponseResponse(BaseModel):
    """Returned immediately after a successful audio upload (POST .../responses).

    Contains the fields the client needs to track the recording:
    - id: reference the response in future status polls and UI
    - question_id: confirm which question was answered
    - status: always 'uploaded' at creation; changes as the pipeline processes
    - created_at: timestamp for display and ordering

    Does not include error_message — see module docstring above.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique identifier for this audio response.")
    question_id: uuid.UUID = Field(
        description="UUID of the question this recording answers."
    )
    status: ResponseStatus = Field(
        description=(
            "Processing state: 'uploaded' → 'processing' → 'completed' or 'failed'. "
            "Always 'uploaded' immediately after creation."
        )
    )
    created_at: datetime = Field(description="UTC timestamp of upload.")


class AudioResponseStatusResponse(BaseModel):
    """Returned by the status polling endpoint (GET .../responses/{id}/status).

    Includes error_message so clients can surface pipeline failure details.
    This is the only context where status can be 'failed' and error_message
    can be non-null — the pipeline (Week 3) sets both fields together.

    Polling pattern:
        Client polls until status is 'completed' or 'failed'.
        On 'failed', error_message contains a human-readable reason.
        On 'completed', downstream results are available via the analysis
        endpoints added in Week 3.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique identifier for this audio response.")
    status: ResponseStatus = Field(
        description=(
            "Current processing state: 'uploaded', 'processing', "
            "'completed', or 'failed'."
        )
    )
    created_at: datetime = Field(description="UTC timestamp of upload.")
    error_message: str | None = Field(
        None,
        description=(
            "Human-readable failure reason set by the processing pipeline. "
            "Non-null only when status == 'failed'; null for all other states."
        ),
    )


class TranscriptResponse(BaseModel):
    """Returned by GET /api/v1/responses/{response_id}/transcript.

    Represents the Whisper transcription result for one audio response.
    Built directly from the Transcript ORM object via from_attributes=True.

    duration_seconds is the audio length in whole seconds (Integer at the DB
    level). word_count is the number of whitespace-separated tokens in text;
    zero is a valid value for silent recordings.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique identifier for this transcript.")
    audio_response_id: uuid.UUID = Field(
        description="UUID of the audio response this transcript belongs to."
    )
    text: str = Field(
        description=(
            "Full transcript text as returned by Whisper. "
            "Empty string for silent recordings."
        )
    )
    language: str | None = Field(
        None,
        description=(
            "BCP-47 language code detected by Whisper, e.g. 'en', 'fr'. "
            "Null if Whisper could not detect a language."
        ),
    )
    duration_seconds: int | None = Field(
        None,
        description=(
            "Duration of the audio in whole seconds. "
            "Null for silent recordings where Whisper returns no segments."
        ),
    )
    word_count: int = Field(
        description=(
            "Number of whitespace-separated tokens in the transcript text. "
            "Zero is a valid value for empty transcripts."
        )
    )
    created_at: datetime = Field(
        description="UTC timestamp when the transcript was created by the pipeline."
    )


class InterviewAnalysisResponse(BaseModel):
    """Returned by GET /api/v1/responses/{response_id}/analysis.

    Represents the Gemini AI evaluation for one audio response.
    Built directly from the InterviewAnalysis ORM object via from_attributes=True.

    All five score fields use Decimal to preserve NUMERIC(4,1) exact precision
    from the database. Scores are in the range [0.0, 10.0] with one decimal
    place, enforced by CHECK constraints at the DB level and round(v, 1)
    at the service layer.

    transcript_id may be null if the transcript was deleted after the analysis
    was created (ON DELETE SET NULL). The analysis scores remain valid in
    this state — the transcript text is not needed to read the scores.

    strengths and weaknesses are stored in the DB as JSON-encoded text and
    are returned as raw strings from this schema. The client is responsible
    for parsing them as JSON arrays if structured data is needed; a future
    schema version may expose them as list[str] directly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique identifier for this analysis.")
    audio_response_id: uuid.UUID = Field(
        description="UUID of the audio response this analysis evaluates."
    )
    transcript_id: uuid.UUID | None = Field(
        None,
        description=(
            "UUID of the transcript used for this evaluation. "
            "Null if the transcript was deleted after the analysis was created."
        ),
    )
    # ── Scores ─────────────────────────────────────────────────────────
    # Decimal preserves exact NUMERIC(4,1) precision from the DB.
    # Serialised as strings in JSON (e.g. "7.5") by Pydantic v2 default.
    overall_score: Decimal = Field(
        description="Overall interview performance score from 0.0 to 10.0."
    )
    communication_score: Decimal = Field(
        description="Communication clarity and articulation score from 0.0 to 10.0."
    )
    technical_score: Decimal = Field(
        description="Technical accuracy and depth score from 0.0 to 10.0."
    )
    problem_solving_score: Decimal = Field(
        description="Structured reasoning and problem-solving score from 0.0 to 10.0."
    )
    confidence_score: Decimal = Field(
        description="Confidence and delivery score from 0.0 to 10.0."
    )
    # ── Narrative ───────────────────────────────────────────────────────
    strengths: str | None = Field(
        None,
        description=(
            "JSON-encoded array of identified strengths, "
            'e.g. \'["Clear structure", "Technical depth"]\'. '
            "Null if the pipeline did not produce this field."
        ),
    )
    weaknesses: str | None = Field(
        None,
        description=(
            "JSON-encoded array of identified areas for improvement. "
            "Null if the pipeline did not produce this field."
        ),
    )
    detailed_feedback: str | None = Field(
        None,
        description=(
            "Free-text narrative feedback from the AI evaluator. "
            "Null if the pipeline did not produce this field."
        ),
    )
    model_used: str | None = Field(
        None,
        description=(
            "Identifier of the Gemini model that produced this evaluation, "
            "e.g. 'gemini-2.0-flash'. Null for rows created by test fixtures."
        ),
    )
    created_at: datetime = Field(
        description="UTC timestamp when the analysis was created by the pipeline."
    )


class ProcessingStatusResponse(BaseModel):
    """Returned by POST /api/v1/responses/{response_id}/process on 202 Accepted.

    Aggregates the current processing state of an audio response alongside
    the IDs of any child records that have been created. Constructed manually
    in the router from the AudioResponse ORM object and its related records —
    not built from a single ORM object, so no from_attributes config is used.

    The client can use transcript_id and analysis_id to call the corresponding
    GET endpoints without a separate status poll:
        GET /api/v1/responses/{response_id}/transcript
        GET /api/v1/responses/{response_id}/analysis
    """

    response_id: uuid.UUID = Field(
        description="UUID of the audio response being processed."
    )
    status: str = Field(
        description=(
            "Current processing state of the response: "
            "'uploaded', 'processing', 'completed', or 'failed'."
        )
    )
    transcript_id: uuid.UUID | None = Field(
        None,
        description=(
            "UUID of the transcript if transcription has completed. "
            "Null while status is 'uploaded' or 'processing'."
        ),
    )
    analysis_id: uuid.UUID | None = Field(
        None,
        description=(
            "UUID of the analysis if evaluation has completed. "
            "Null while status is not yet 'completed'."
        ),
    )
    error_message: str | None = Field(
        None,
        description=(
            "Human-readable failure reason. " "Non-null only when status == 'failed'."
        ),
    )
