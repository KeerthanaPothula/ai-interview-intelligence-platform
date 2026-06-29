"""Add live interview sessions, document chunks, and prediction tables.

Revision ID: d8e5f3a2b1c0
Revises: c7d4e2f1a9b8
Create Date: 2026-06-18 12:00:00.000000

Phase 17-19 tables:
    live_interview_sessions — multi-turn conversational AI interview sessions
    conversation_turns      — individual Q&A turns within a live session
    resume_documents        — uploaded PDF/DOCX resumes with extracted text
    document_chunks         — chunked + embedded text segments for RAG retrieval
    interview_predictions   — ML success probability + percentile per session
    coaching_plans          — Gemini-generated 7/14/30 day improvement plans
"""

from alembic import op
import sqlalchemy as sa

revision = "d8e5f3a2b1c0"
down_revision = "c7d4e2f1a9b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── live_interview_sessions ──────────────────────────────────────────────
    op.create_table(
        "live_interview_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_role", sa.String(200), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("current_turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_turns", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'completed')",
            name="ck_live_interview_sessions_status",
        ),
        sa.CheckConstraint(
            "current_turn >= 0 AND current_turn <= max_turns",
            name="ck_live_interview_sessions_turn",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_live_interview_sessions_user_id",
        "live_interview_sessions",
        ["user_id"],
    )

    # ── conversation_turns ───────────────────────────────────────────────────
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("live_session_id", sa.Uuid(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("difficulty_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("audio_response_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["live_session_id"],
            ["live_interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_turns_live_session_id",
        "conversation_turns",
        ["live_session_id"],
    )

    # ── resume_documents ─────────────────────────────────────────────────────
    op.create_table(
        "resume_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resume_documents_user_id", "resume_documents", ["user_id"])

    # ── document_chunks ──────────────────────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resume_document_id", sa.Uuid(), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "source_type", sa.String(50), nullable=False, server_default="resume"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resume_document_id"],
            ["resume_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_chunks_user_id", "document_chunks", ["user_id"])

    # ── interview_predictions ────────────────────────────────────────────────
    op.create_table(
        "interview_predictions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("success_probability", sa.Float(), nullable=True),
        sa.Column("percentile_rank", sa.Float(), nullable=True),
        sa.Column("predicted_outcome", sa.String(50), nullable=True),
        sa.Column("feature_vector", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_interview_predictions_session_id"),
    )

    # ── coaching_plans ───────────────────────────────────────────────────────
    op.create_table(
        "coaching_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("plan_7_day", sa.Text(), nullable=True),
        sa.Column("plan_14_day", sa.Text(), nullable=True),
        sa.Column("plan_30_day", sa.Text(), nullable=True),
        sa.Column("focus_areas", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_coaching_plans_session_id"),
    )


def downgrade() -> None:
    op.drop_table("coaching_plans")
    op.drop_table("interview_predictions")
    op.drop_index("ix_document_chunks_user_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_resume_documents_user_id", table_name="resume_documents")
    op.drop_table("resume_documents")
    op.drop_index(
        "ix_conversation_turns_live_session_id", table_name="conversation_turns"
    )
    op.drop_table("conversation_turns")
    op.drop_index(
        "ix_live_interview_sessions_user_id", table_name="live_interview_sessions"
    )
    op.drop_table("live_interview_sessions")
