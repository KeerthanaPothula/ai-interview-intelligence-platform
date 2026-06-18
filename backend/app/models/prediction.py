from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.interview import InterviewSession


class InterviewPrediction(Base):
    __tablename__ = "interview_predictions"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_interview_predictions_session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    success_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentile_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    feature_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession", back_populates="prediction"
    )


class CoachingPlan(Base):
    __tablename__ = "coaching_plans"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_coaching_plans_session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    plan_7_day: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_14_day: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_30_day: Mapped[str | None] = mapped_column(Text, nullable=True)
    focus_areas: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[InterviewSession] = relationship(
        "InterviewSession", back_populates="coaching_plan"
    )
