from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.features import VoiceAnalysis
    from app.models.interview import InterviewSession, Question
    from app.models.user import User

# ---------------------------------------------------------------------------
# Status constants — AudioResponse.status
# Import and use these in services; never compare against raw string literals.
#
# Lifecycle:
#   uploaded → processing → completed
#                        ↘ failed
# ---------------------------------------------------------------------------
RESPONSE_STATUS_UPLOADED = "uploaded"
RESPONSE_STATUS_PROCESSING = "processing"
RESPONSE_STATUS_COMPLETED = "completed"
RESPONSE_STATUS_FAILED = "failed"

VALID_RESPONSE_STATUSES = {
    RESPONSE_STATUS_UPLOADED,
    RESPONSE_STATUS_PROCESSING,
    RESPONSE_STATUS_COMPLETED,
    RESPONSE_STATUS_FAILED,
}


class AudioResponse(Base):
    """
    ORM model for the `audio_responses` table.

    Stores one uploaded audio file per question per interview session.
    Week 2 creates rows with status='uploaded'. The AI pipeline (Week 3)
    transitions rows to 'processing' → 'completed' or 'failed'.

    Three separate ON DELETE CASCADE foreign keys ensure that removing a
    user, session, or question at the DB level cleans up all associated
    audio response rows without requiring the ORM to load them first.

    file_path stores a path relative to settings.UPLOAD_DIR (e.g.
    "{session_id}/{response_id}.webm") so that moving the upload directory
    does not invalidate stored rows.

    Week 3 additions:
      processing_started_at / processing_completed_at record wall-clock
      timing for the Whisper + Gemini pipeline. Both are nullable because
      they are populated asynchronously after the initial upload.

      transcript / analysis are one-to-one relationships to child rows
      created by the pipeline. passive_deletes=True on both: the FK in
      each child table is NOT NULL with ON DELETE CASCADE, so SQLAlchemy
      must not emit a pre-delete SET NULL — the DB cascade handles cleanup.
    """

    __tablename__ = "audio_responses"
    __table_args__ = (
        Index("ix_audio_responses_session_id", "session_id"),
        Index("ix_audio_responses_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # ── Foreign keys — all with ON DELETE CASCADE ────────────────────────
    #
    # session_id CASCADE: deleting a session removes all its responses.
    # question_id CASCADE: required because question regeneration issues a
    #   bulk SQL DELETE on questions (bypassing ORM). Without DB-level CASCADE,
    #   that bulk DELETE would raise a FK violation. ORM-level cascade alone
    #   is insufficient for the bulk-delete path.
    # user_id CASCADE: deleting an account removes all their uploaded audio.

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── File metadata ────────────────────────────────────────────────────

    # Relative path under settings.UPLOAD_DIR, e.g. "{session_id}/{id}.webm".
    # Using a relative path decouples the DB row from the physical mount point
    # of the upload directory — safe to move the volume without a data migration.
    file_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Populated by upload_service after reading the file bytes.
    # Nullable: if the upload fails mid-write, we still want a row for audit.
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Content-Type header sent by the client, e.g. "audio/webm".
    # Nullable for same reason as file_size_bytes.
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Processing state ─────────────────────────────────────────────────

    # VARCHAR(20) rather than a PostgreSQL ENUM: ALTER TYPE ... ADD VALUE
    # acquires a catalog lock that blocks concurrent reads on busy tables.
    # Service-layer enforcement with string constants is zero-cost at the DB.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RESPONSE_STATUS_UPLOADED
    )

    # Populated by the Week 3 pipeline on failure; NULL when status != 'failed'.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Week 3: pipeline timing columns ──────────────────────────────────
    #
    # Both are nullable: rows created at upload time have neither timestamp.
    # processing_started_at is set atomically in the same UPDATE that claims
    # the job (status 'uploaded' → 'processing') in processing_service.py.
    # processing_completed_at is set in Transaction 3 when the pipeline
    # writes the analysis row and sets status 'completed' or 'failed'.

    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ────────────────────────────────────────────────────
    # from __future__ import annotations makes all annotations lazy strings,
    # so InterviewSession, Question, and User are resolved at mapper
    # configuration time without circular imports.

    # Completes InterviewSession.audio_responses back_populates declared
    # in interview.py.
    session: Mapped[InterviewSession] = relationship(
        "InterviewSession", back_populates="audio_responses"
    )

    # Completes Question.audio_responses back_populates declared in interview.py.
    question: Mapped[Question] = relationship(
        "Question", back_populates="audio_responses"
    )

    # No back_populates on User: MVP routes never navigate user → audio_responses.
    # The FK (user_id) is sufficient for ownership checks in the service layer.
    user: Mapped[User] = relationship("User")

    # ── Week 3: one-to-one child relationships ────────────────────────────
    #
    # uselist=False: enforces one-to-one semantics at the ORM layer.
    #   Accessing response.transcript returns a single Transcript object
    #   (or None), not a list.
    #
    # passive_deletes=True: required because both child FKs are NOT NULL
    #   with ON DELETE CASCADE. Without this flag SQLAlchemy emits a pre-
    #   delete UPDATE to SET the FK to NULL, which violates NOT NULL.
    #   passive_deletes=True tells SQLAlchemy to trust the DB CASCADE and
    #   skip the pre-delete UPDATE entirely.
    #
    # Transcript and InterviewAnalysis are defined later in this file.
    # from __future__ import annotations makes the forward references valid.

    transcript: Mapped[Transcript | None] = relationship(
        "Transcript",
        back_populates="audio_response",
        uselist=False,
        passive_deletes=True,
    )

    analysis: Mapped[InterviewAnalysis | None] = relationship(
        "InterviewAnalysis",
        back_populates="audio_response",
        uselist=False,
        passive_deletes=True,
    )

    voice_analysis: Mapped[VoiceAnalysis | None] = relationship(
        "VoiceAnalysis",
        back_populates="audio_response",
        uselist=False,
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AudioResponse id={self.id} "
            f"status={self.status!r} session_id={self.session_id}>"
        )


class Transcript(Base):
    """
    ORM model for the `transcripts` table.

    Stores the raw Whisper transcription result for one AudioResponse.
    The UNIQUE constraint on audio_response_id enforces the one-to-one
    relationship at the DB level and prevents duplicate transcriptions.

    The FK is NOT NULL with ON DELETE CASCADE: deleting an AudioResponse
    (directly or via session/user cascade) removes the transcript row
    automatically without requiring the ORM to load it first.

    duration_seconds is Integer (whole seconds). Whisper's raw segment
    end-times are fractional floats; the transcription service truncates
    to int via int() before storing. See architecture-change request
    ACR-001 if sub-second precision is required in a future iteration.

    word_count=0 is a valid result for silent or near-silent audio
    that Whisper transcribes as an empty or whitespace-only string.
    The service layer writes len(text.split()) which returns 0 for "".
    """

    __tablename__ = "transcripts"
    __table_args__ = (
        # Named UniqueConstraint: creates a B-tree unique index in both
        # PostgreSQL and SQLite. No separate Index is declared for
        # audio_response_id because the UniqueConstraint already serves
        # as the index — a duplicate Index would waste storage.
        UniqueConstraint(
            "audio_response_id",
            name="uq_transcripts_audio_response_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # NOT NULL + UNIQUE: one transcript per audio response, enforced at DB level.
    # ON DELETE CASCADE: removing the AudioResponse removes this row.
    audio_response_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audio_responses.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Full transcript text as returned by Whisper, stripped of leading/trailing
    # whitespace. May be empty string for silent recordings (word_count=0).
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # BCP-47 language code detected by Whisper, e.g. "en", "fr", "zh".
    # Nullable: Whisper may not detect language for very short recordings.
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Duration of the audio in whole seconds.
    # Derived from result["segments"][-1]["end"] (a Whisper float); the
    # transcription service truncates to int before storing.
    # Nullable: None when Whisper returns an empty segments list (silent audio).
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Number of whitespace-separated tokens in text. 0 is valid (empty text).
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ────────────────────────────────────────────────────

    # Completes AudioResponse.transcript back_populates.
    audio_response: Mapped[AudioResponse] = relationship(
        "AudioResponse",
        back_populates="transcript",
    )

    # One transcript may have zero or one analysis (it may not have been
    # evaluated yet, or evaluation may have failed after transcription).
    #
    # passive_deletes=True: when this Transcript is deleted, do not emit
    #   UPDATE interview_analyses SET transcript_id=NULL beforehand.
    #   The DB's ON DELETE SET NULL on interview_analyses.transcript_id
    #   handles nullification. Without this flag SQLAlchemy would issue a
    #   redundant UPDATE (which would succeed since transcript_id IS nullable,
    #   but creates an unnecessary round-trip).
    analysis: Mapped[InterviewAnalysis | None] = relationship(
        "InterviewAnalysis",
        back_populates="transcript",
        uselist=False,
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Transcript id={self.id} "
            f"audio_response_id={self.audio_response_id} "
            f"word_count={self.word_count}>"
        )


class InterviewAnalysis(Base):
    """
    ORM model for the `interview_analyses` table.

    Stores the Gemini AI evaluation for one AudioResponse. Each row
    contains five numeric scores and three free-text narrative fields.

    Score columns use NUMERIC(4,1) for exact decimal storage — IEEE 754
    float arithmetic can produce values like 7.333333334 where the
    intended value is 7.3. NUMERIC avoids this in aggregate queries.
    The service layer rounds every score to one decimal place before
    INSERT via round(value, 1), then converts to Decimal(str(rounded))
    to prevent the Decimal constructor from inheriting float imprecision.

    CHECK constraints on all five scores are named for future migration
    maintainability. Named constraints can be referenced unambiguously
    in ALTER TABLE statements across environments — system-generated
    names differ between PostgreSQL installations.

    transcript_id is nullable with ON DELETE SET NULL: the analysis
    row survives if its transcript is deleted independently. In practice
    this only happens via direct Transcript deletion; AudioResponse
    deletion removes both rows simultaneously via their own CASCADE FKs.

    strengths and weaknesses are stored as JSON-encoded text rather than
    PostgreSQL JSONB to preserve SQLite compatibility for the test suite.
    The schema layer (Pydantic, File 05) deserialises them into lists.
    """

    __tablename__ = "interview_analyses"
    __table_args__ = (
        # ── Named CHECK constraints ───────────────────────────────────────
        # Score fields are NOT NULL so no IS NULL guard is needed.
        # SQLite enforces CHECK constraints from version 3.25.0 (2018),
        # which ships with Python 3.12+. Constraint names follow
        # ck_{table_short}_{column} convention used across this schema.
        CheckConstraint(
            "overall_score >= 0.0 AND overall_score <= 10.0",
            name="ck_analyses_overall_score",
        ),
        CheckConstraint(
            "communication_score >= 0.0 AND communication_score <= 10.0",
            name="ck_analyses_communication_score",
        ),
        CheckConstraint(
            "technical_score >= 0.0 AND technical_score <= 10.0",
            name="ck_analyses_technical_score",
        ),
        CheckConstraint(
            "problem_solving_score >= 0.0 AND problem_solving_score <= 10.0",
            name="ck_analyses_problem_solving_score",
        ),
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 10.0",
            name="ck_analyses_confidence_score",
        ),
        # ── Uniqueness ────────────────────────────────────────────────────
        # One analysis per AudioResponse. Named so future migrations can
        # reference it without guessing the system-generated constraint name.
        # The UniqueConstraint implicitly creates a B-tree index — no
        # separate Index is declared for audio_response_id.
        UniqueConstraint(
            "audio_response_id",
            name="uq_interview_analyses_audio_response_id",
        ),
        # ── Non-unique index ──────────────────────────────────────────────
        # created_at: supports time-range queries and dashboard ordering
        # without a full table scan. audio_response_id is covered above.
        Index("ix_interview_analyses_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # NOT NULL + UNIQUE (via UniqueConstraint above).
    # ON DELETE CASCADE: deleting the AudioResponse removes this row.
    audio_response_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audio_responses.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Nullable: may become NULL if the Transcript is deleted after the
    # analysis was created (ON DELETE SET NULL on the FK below).
    # The analysis remains usable — scores and feedback are self-contained.
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("transcripts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── AI evaluation scores ──────────────────────────────────────────────
    # Mapped[Decimal] pairs with Numeric(4,1) in SQLAlchemy's type system.
    # Decimal(str(float)) must be used when constructing values to avoid
    # IEEE 754 imprecision entering the Decimal constructor.

    overall_score: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    communication_score: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    technical_score: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    problem_solving_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), nullable=False
    )
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)

    # ── Evaluation narrative ──────────────────────────────────────────────
    # Stored as JSON-serialised text (e.g. '["strength 1", "strength 2"]').
    # Using Text rather than PostgreSQL JSONB preserves SQLite compatibility
    # for the test suite. The Pydantic schema (File 05) deserialises these
    # into list[str] when building API responses.
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    weaknesses: Mapped[str | None] = mapped_column(Text, nullable=True)
    detailed_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Gemini model identifier recorded at evaluation time, e.g.
    # "gemini-2.0-flash". Nullable: populated by evaluation_service,
    # absent if the analysis row is created by a test fixture directly.
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ────────────────────────────────────────────────────

    # Completes AudioResponse.analysis back_populates.
    audio_response: Mapped[AudioResponse] = relationship(
        "AudioResponse",
        back_populates="analysis",
    )

    # Completes Transcript.analysis back_populates.
    # transcript_id is nullable so this may be None after ON DELETE SET NULL.
    transcript: Mapped[Transcript | None] = relationship(
        "Transcript",
        back_populates="analysis",
    )

    def __repr__(self) -> str:
        return (
            f"<InterviewAnalysis id={self.id} "
            f"audio_response_id={self.audio_response_id} "
            f"overall_score={self.overall_score}>"
        )
