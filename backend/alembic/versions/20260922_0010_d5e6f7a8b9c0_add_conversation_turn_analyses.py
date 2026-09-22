"""Add conversation_turn_analyses table.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-22 00:10:00.000000

Purely additive: one new table, no changes to any existing table. Stores
per-answer Gemini evaluation scores for live-interview ConversationTurns —
the live-interview analogue of interview_analyses, produced by the same
evaluation_service.generate_evaluation(), but keyed to conversation_turns
instead of audio_responses. See app.models.conversation.ConversationTurnAnalysis
and app.services.interview_service.score_and_store_conversation_turn.

interview_analyses itself is untouched: its audio_response_id stays
NOT NULL + UNIQUE, and the entire upload/audio pipeline keeps working
exactly as before.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_turn_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_turn_id", sa.Uuid(), nullable=False),
        sa.Column("overall_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("communication_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("technical_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("problem_solving_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("confidence_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("weaknesses", sa.Text(), nullable=True),
        sa.Column("detailed_feedback", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "overall_score >= 0.0 AND overall_score <= 10.0",
            name="ck_turn_analyses_overall_score",
        ),
        sa.CheckConstraint(
            "communication_score >= 0.0 AND communication_score <= 10.0",
            name="ck_turn_analyses_communication_score",
        ),
        sa.CheckConstraint(
            "technical_score >= 0.0 AND technical_score <= 10.0",
            name="ck_turn_analyses_technical_score",
        ),
        sa.CheckConstraint(
            "problem_solving_score >= 0.0 AND problem_solving_score <= 10.0",
            name="ck_turn_analyses_problem_solving_score",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 10.0",
            name="ck_turn_analyses_confidence_score",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_turn_id"],
            ["conversation_turns.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_turn_id", name="uq_conversation_turn_analyses_turn_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("conversation_turn_analyses")
