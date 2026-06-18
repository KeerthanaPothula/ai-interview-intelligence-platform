"""add voice_analyses, follow_up_questions, session_reports tables

Revision ID: c7d4e2f1a9b8
Revises: b5c3f1d2e8a9
Create Date: 2026-06-18 00:03:00.000000

Phase 16 schema additions. Operations in dependency order:

  Upgrade:
    1. CREATE TABLE voice_analyses — FK → audio_responses ON DELETE CASCADE.
       One-to-one with AudioResponse (UNIQUE on audio_response_id).
    2. CREATE TABLE follow_up_questions — FK → interview_sessions CASCADE,
       FK → questions CASCADE, FK → audio_responses SET NULL.
    3. CREATE TABLE session_reports — FK → interview_sessions CASCADE.
       One-to-one with InterviewSession (UNIQUE on session_id).

  Downgrade:
    3 → DROP TABLE session_reports
    2 → DROP TABLE follow_up_questions
    1 → DROP TABLE voice_analyses
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c7d4e2f1a9b8"
down_revision = "b5c3f1d2e8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. voice_analyses
    # ------------------------------------------------------------------
    op.create_table(
        "voice_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("audio_response_id", sa.Uuid(), nullable=False),
        sa.Column("speaking_rate", sa.Float(), nullable=True),
        sa.Column("average_pause_duration", sa.Float(), nullable=True),
        sa.Column("total_pause_time", sa.Float(), nullable=True),
        sa.Column("long_pause_count", sa.Integer(), nullable=True),
        sa.Column("filler_word_count", sa.Integer(), nullable=True),
        sa.Column("energy_consistency", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name="ck_voice_analyses_confidence_score",
        ),
        sa.CheckConstraint(
            "energy_consistency >= 0.0 AND energy_consistency <= 1.0",
            name="ck_voice_analyses_energy_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["audio_response_id"],
            ["audio_responses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "audio_response_id",
            name="uq_voice_analyses_audio_response_id",
        ),
    )

    # ------------------------------------------------------------------
    # 2. follow_up_questions
    # ------------------------------------------------------------------
    op.create_table(
        "follow_up_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("original_question_id", sa.Uuid(), nullable=False),
        sa.Column("parent_audio_response_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["original_question_id"],
            ["questions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_audio_response_id"],
            ["audio_responses.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # 3. session_reports
    # ------------------------------------------------------------------
    op.create_table(
        "session_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("overall_performance", sa.Text(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("communication_score", sa.Float(), nullable=True),
        sa.Column("technical_score", sa.Float(), nullable=True),
        sa.Column("problem_solving_score", sa.Float(), nullable=True),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("weaknesses", sa.Text(), nullable=True),
        sa.Column("improvement_plan", sa.Text(), nullable=True),
        sa.Column("readiness_level", sa.String(50), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            name="uq_session_reports_session_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("session_reports")
    op.drop_table("follow_up_questions")
    op.drop_table("voice_analyses")
