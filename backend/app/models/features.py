from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
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
    from app.models.interview import InterviewSession, Question


class VoiceAnalysis(Base):
    """
    ORM model for the `voice_analyses` table.

    Stores librosa-computed speaking metrics for one AudioResponse.
    One-to-one with AudioResponse: the UNIQUE constraint on
    audio_response_id enforces this at the DB level.
    """

    __tablename__ = "voice_analyses"
    __table_args__ = (
        UniqueConstraint(
            "audio_response_id",
            name="uq_voice_analyses_audio_response_id",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name="ck_voice_analyses_confidence_score",
        ),
        CheckConstraint(
            "energy_consistency >= 0.0 AND energy_consistency <= 1.0",
            name="ck_voice_analyses_energy_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    audio_response_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audio_responses.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Words per minute computed from transcript word_count / audio duration.
    speaking_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Mean duration of detected silence segments > 300 ms, in seconds.
    average_pause_duration: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Total silence time across the recording, in seconds.
    total_pause_time: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Number of pauses exceeding 2 seconds.
    long_pause_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Count of filler words (um, uh, like, you know, actually, basically).
    filler_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # RMS energy coefficient of variation normalised to [0, 1].
    # 1.0 = very consistent volume; 0.0 = highly variable.
    energy_consistency: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Weighted composite score [0, 100] derived from the metrics above.
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    audio_response: Mapped[AudioResponse] = relationship(
        "AudioResponse",
        back_populates="voice_analysis",
    )

    def __repr__(self) -> str:
        return (
            f"<VoiceAnalysis id={self.id} "
            f"audio_response_id={self.audio_response_id} "
            f"confidence_score={self.confidence_score}>"
        )


class FollowUpQuestion(Base):
    """
    ORM model for the `follow_up_questions` table.

    Records an AI-generated follow-up question produced by Gemini in
    response to a candidate's audio answer. Linked to the session (for
    history queries), the original question (for context), and the audio
    response that triggered generation.
    """

    __tablename__ = "follow_up_questions"
    __table_args__ = (
        Index("ix_follow_up_questions_session_id", "session_id"),
        Index("ix_follow_up_questions_original_question_id", "original_question_id"),
        Index(
            "ix_follow_up_questions_parent_audio_response_id",
            "parent_audio_response_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The original question this follow-up probes deeper on.
    original_question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The audio response that triggered generation (nullable: SET NULL on delete
    # so history survives if the response is removed).
    parent_audio_response_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("audio_responses.id", ondelete="SET NULL"),
        nullable=True,
    )

    # The follow-up question text.
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # How many levels deep: 1 = first follow-up on an original question.
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession",
        back_populates="follow_up_questions",
    )

    original_question: Mapped[Question] = relationship(
        "Question",
        back_populates="follow_up_questions",
    )

    def __repr__(self) -> str:
        return (
            f"<FollowUpQuestion id={self.id} "
            f"session_id={self.session_id} depth={self.depth}>"
        )


class SessionReport(Base):
    """
    ORM model for the `session_reports` table.

    Stores a Gemini-generated holistic report for a completed interview
    session. One-to-one with InterviewSession.
    """

    __tablename__ = "session_reports"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="uq_session_reports_session_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Gemini narrative summary of overall performance.
    overall_performance: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Aggregate score [0, 10] derived from all response analyses.
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Aggregate voice confidence score [0, 100] across all voice analyses.
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Category averages.
    communication_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    problem_solving_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # JSON-encoded list[str] — bullets of identified strengths.
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON-encoded list[str] — areas for improvement.
    weaknesses: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON-encoded list[str] — actionable improvement steps.
    improvement_plan: Mapped[str | None] = mapped_column(Text, nullable=True)

    # One of: Beginner / Developing / Interview Ready / Strong Candidate /
    # Highly Competitive
    readiness_level: Mapped[str | None] = mapped_column(String(50), nullable=True)

    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession",
        back_populates="report",
    )

    def __repr__(self) -> str:
        return (
            f"<SessionReport id={self.id} "
            f"session_id={self.session_id} "
            f"readiness_level={self.readiness_level!r}>"
        )
