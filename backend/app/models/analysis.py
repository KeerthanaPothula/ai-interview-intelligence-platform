from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
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

    def __repr__(self) -> str:
        return (
            f"<AudioResponse id={self.id} "
            f"status={self.status!r} session_id={self.session_id}>"
        )
