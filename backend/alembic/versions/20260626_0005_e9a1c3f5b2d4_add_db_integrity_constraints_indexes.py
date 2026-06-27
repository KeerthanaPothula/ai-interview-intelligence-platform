"""Add missing FK constraint and indexes for database integrity.

Revision ID: e9a1c3f5b2d4
Revises: d8e5f3a2b1c0
Create Date: 2026-06-26 00:05:00.000000

Phase 2 (Backend Refactor & Critical Fixes) integrity fixes:

  Upgrade:
    1. conversation_turns.audio_response_id was a plain UUID column with no
       FK — add ForeignKeyConstraint to audio_responses.id ON DELETE SET
       NULL (matches the existing follow_up_questions.parent_audio_response_id
       pattern) plus a supporting index.
    2. document_chunks.resume_document_id has a FK but no index — add one.
    3. follow_up_questions.session_id, .original_question_id, and
       .parent_audio_response_id all have FKs but no indexes — add them.

  No soft deletes are introduced in this migration.

  Downgrade: drop everything created above, in reverse order.
"""

from __future__ import annotations

from alembic import op

revision = "e9a1c3f5b2d4"
down_revision = "d8e5f3a2b1c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. conversation_turns.audio_response_id
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "fk_conversation_turns_audio_response_id",
        "conversation_turns",
        "audio_responses",
        ["audio_response_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversation_turns_audio_response_id",
        "conversation_turns",
        ["audio_response_id"],
    )

    # ------------------------------------------------------------------
    # 2. document_chunks.resume_document_id
    # ------------------------------------------------------------------
    op.create_index(
        "ix_document_chunks_resume_document_id",
        "document_chunks",
        ["resume_document_id"],
    )

    # ------------------------------------------------------------------
    # 3. follow_up_questions FK columns
    # ------------------------------------------------------------------
    op.create_index(
        "ix_follow_up_questions_session_id",
        "follow_up_questions",
        ["session_id"],
    )
    op.create_index(
        "ix_follow_up_questions_original_question_id",
        "follow_up_questions",
        ["original_question_id"],
    )
    op.create_index(
        "ix_follow_up_questions_parent_audio_response_id",
        "follow_up_questions",
        ["parent_audio_response_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_follow_up_questions_parent_audio_response_id",
        table_name="follow_up_questions",
    )
    op.drop_index(
        "ix_follow_up_questions_original_question_id",
        table_name="follow_up_questions",
    )
    op.drop_index("ix_follow_up_questions_session_id", table_name="follow_up_questions")
    op.drop_index("ix_document_chunks_resume_document_id", table_name="document_chunks")
    op.drop_index(
        "ix_conversation_turns_audio_response_id", table_name="conversation_turns"
    )
    op.drop_constraint(
        "fk_conversation_turns_audio_response_id",
        "conversation_turns",
        type_="foreignkey",
    )
