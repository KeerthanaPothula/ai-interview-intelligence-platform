from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.analysis import AudioResponse
    from app.models.user import User

# ---------------------------------------------------------------------------
# Status constants — InterviewSession.status
# Import and use these in services; never compare against raw string literals.
# ---------------------------------------------------------------------------
SESSION_STATUS_DRAFT = "draft"
SESSION_STATUS_IN_PROGRESS = "in_progress"
SESSION_STATUS_PROCESSING = "processing"
SESSION_STATUS_COMPLETED = "completed"

VALID_SESSION_STATUSES = {
    SESSION_STATUS_DRAFT,
    SESSION_STATUS_IN_PROGRESS,
    SESSION_STATUS_PROCESSING,
    SESSION_STATUS_COMPLETED,
}

# ---------------------------------------------------------------------------
# Source and category constants — Question
# ---------------------------------------------------------------------------
QUESTION_SOURCE_AI_GENERATED = "ai_generated"
QUESTION_SOURCE_MANUAL = "manual"

QUESTION_CATEGORY_BEHAVIORAL = "behavioral"
QUESTION_CATEGORY_TECHNICAL = "technical"
QUESTION_CATEGORY_SITUATIONAL = "situational"

VALID_QUESTION_CATEGORIES = {
    QUESTION_CATEGORY_BEHAVIORAL,
    QUESTION_CATEGORY_TECHNICAL,
    QUESTION_CATEGORY_SITUATIONAL,
}


class InterviewSession(Base):
    """
    ORM model for the `interview_sessions` table.

    One session belongs to one user and contains many questions (Gemini-
    generated) and many audio responses (recorded answers).

    Status lifecycle enforced at the service layer, not via a DB ENUM:
        draft → in_progress → processing → completed

    Using VARCHAR + service validation avoids the exclusive lock required
    by ALTER TYPE ... ADD VALUE when new statuses are introduced later.
    """

    __tablename__ = "interview_sessions"
    __table_args__ = (
        # Explicit Index objects keep all DDL declarations for this table
        # in one place rather than scattered across mapped_column calls.
        Index("ix_interview_sessions_user_id", "user_id"),
        Index("ix_interview_sessions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # ForeignKey ondelete="CASCADE": if the parent User row is deleted,
    # PostgreSQL cascades the delete to all their sessions without requiring
    # the ORM to load and individually delete each one.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    job_role: Mapped[str] = mapped_column(String(255), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)

    # String(20) — longest current value is "in_progress" (11 chars).
    # Default applied by Python ORM on INSERT; no server_default needed
    # since all inserts go through the ORM.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SESSION_STATUS_DRAFT
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # server_default handles INSERT; onupdate causes SQLAlchemy to include
    # `SET updated_at = NOW()` in every UPDATE statement it emits for this
    # row. This fires only when the ORM issues an UPDATE — not for direct SQL.
    # Alembic does not emit onupdate in migrations (it is ORM-only, not DDL).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────────────
    # All type annotations use forward-reference strings (resolved lazily
    # by SQLAlchemy at mapper configuration time, not at class definition).
    # from __future__ import annotations makes all annotations strings,
    # so cross-module references like User and AudioResponse do not require
    # runtime imports and cannot cause circular import errors.

    # Requires User.sessions in user.py — see companion diff applied with
    # File 4. Without it, Base.metadata.create_all() raises InvalidRequestError.
    user: Mapped[User] = relationship("User", back_populates="sessions")

    # order_by on the relationship embeds ORDER BY sequence_order in every
    # JOIN or subquery that loads this collection — callers never need to
    # sort manually.
    questions: Mapped[list[Question]] = relationship(
        "Question",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Question.sequence_order",
    )

    # back_populates="session" is completed in analysis.py (File 5).
    # passive_deletes=True: skip the ORM NULL-update on child rows and let
    # the DB's ON DELETE CASCADE on audio_responses.session_id fire instead.
    audio_responses: Mapped[list[AudioResponse]] = relationship(
        "AudioResponse",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<InterviewSession id={self.id} "
            f"status={self.status!r} user_id={self.user_id}>"
        )


class Question(Base):
    """
    ORM model for the `questions` table.

    Questions are generated by Gemini and belong to one InterviewSession.
    sequence_order is assigned by the application (index + 1 from the parsed
    Gemini response) — Gemini's own sequence_order field is discarded to
    prevent duplicate values that would violate the UniqueConstraint.
    """

    __tablename__ = "questions"
    __table_args__ = (
        # DB-level guarantee: no two questions in the same session share a
        # slot. If concurrent generation requests race past the service-layer
        # delete, the second INSERT will raise IntegrityError rather than
        # silently producing duplicate sequence numbers.
        UniqueConstraint(
            "session_id", "sequence_order", name="uq_question_session_order"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # CASCADE: deleting a session bulk-deletes its questions at the DB level
    # without loading each Question ORM object into memory.
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)

    # SMALLINT (range −32768 to 32767) — sequence positions 1–20 fit easily.
    # Signals intentionally small values and saves 2 bytes per row vs INTEGER.
    sequence_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # NULL is valid — Gemini may not categorise every question.
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ai_generated is the only source in Week 2.
    # manual reserved for Week 4+ interviewer-added questions.
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default=QUESTION_SOURCE_AI_GENERATED
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ────────────────────────────────────────────────────

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession", back_populates="questions"
    )

    # back_populates="question" completed in analysis.py (File 5).
    # passive_deletes=True: when a Question ORM object is deleted (e.g. via
    # the InterviewSession.questions cascade), SQLAlchemy would otherwise try
    # to SET audio_responses.question_id = NULL before the DELETE — which fails
    # because question_id is NOT NULL. passive_deletes=True suppresses that
    # UPDATE and lets the DB's ON DELETE CASCADE on question_id handle cleanup.
    audio_responses: Mapped[list[AudioResponse]] = relationship(
        "AudioResponse",
        back_populates="question",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Question id={self.id} "
            f"seq={self.sequence_order} session_id={self.session_id}>"
        )
