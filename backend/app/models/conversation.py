from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User

_STATUS_ACTIVE = "active"
_STATUS_COMPLETED = "completed"

LIVE_SESSION_STATUS_ACTIVE = _STATUS_ACTIVE
LIVE_SESSION_STATUS_COMPLETED = _STATUS_COMPLETED


class LiveInterviewSession(Base):
    __tablename__ = "live_interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed')",
            name="ck_live_interview_sessions_status",
        ),
        CheckConstraint(
            "current_turn >= 0 AND current_turn <= max_turns",
            name="ck_live_interview_sessions_turn",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    job_role: Mapped[str] = mapped_column(String(200), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=_STATUS_ACTIVE
    )
    current_turn: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship("User", back_populates="live_interview_sessions")
    turns: Mapped[list[ConversationTurn]] = relationship(
        "ConversationTurn",
        back_populates="live_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ConversationTurn.turn_number",
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"
    __table_args__ = (
        Index("ix_conversation_turns_audio_response_id", "audio_response_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    live_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("live_interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_response_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "audio_responses.id",
            ondelete="SET NULL",
            name="fk_conversation_turns_audio_response_id",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    live_session: Mapped[LiveInterviewSession] = relationship(
        "LiveInterviewSession", back_populates="turns"
    )
