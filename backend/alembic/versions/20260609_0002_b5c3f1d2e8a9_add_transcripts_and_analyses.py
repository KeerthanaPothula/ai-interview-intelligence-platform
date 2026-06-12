"""add transcripts and interview_analyses tables

Revision ID: b5c3f1d2e8a9
Revises: a4f2e9b1c8d7
Create Date: 2026-06-09 00:02:00.000000

Week 3 schema additions. Operations in dependency order:

  Upgrade:
    1. ALTER TABLE audio_responses — add two nullable timing columns.
       Non-destructive: existing rows receive NULL for both columns.
    2. CREATE TABLE transcripts — FK → audio_responses ON DELETE CASCADE.
       Must follow step 1 so the referenced table exists.
    3. CREATE TABLE interview_analyses — FK → audio_responses CASCADE,
       FK → transcripts SET NULL. Must follow step 2.

  Downgrade:
    3 → DROP TABLE interview_analyses (most dependent)
    2 → DROP TABLE transcripts
    1 → DROP COLUMN processing_started_at / processing_completed_at

Key design decisions recorded here:

  UNIQUE(audio_response_id) on both new tables: enforces the one-to-one
  relationship at the DB level. The unique constraint implicitly creates a
  B-tree index in PostgreSQL and SQLite — no separate CREATE INDEX needed
  for audio_response_id on either table.

  Named CHECK constraints on all five score columns: named constraints can
  be targeted by future ALTER TABLE DROP CONSTRAINT statements without
  relying on system-generated names that differ between PostgreSQL
  installations and pg_restore environments.

  NUMERIC(4,1) for scores: exact decimal storage prevents the IEEE 754
  precision drift that FLOAT produces in aggregate queries (e.g. AVG).
  The service layer rounds every value to one decimal place before INSERT;
  the CHECK constraints enforce the valid range [0.0, 10.0] at the DB level.

  ON DELETE SET NULL on interview_analyses.transcript_id: the analysis row
  survives independent transcript deletion. AudioResponse deletion removes
  both rows simultaneously via their own CASCADE FKs.

  server_default sa.text("now()") matches the convention used in migrations
  0000 and 0001. This is PostgreSQL-specific; Alembic migrations are run
  against PostgreSQL only — the test suite creates tables via
  Base.metadata.create_all() using func.now() which translates correctly
  for both PostgreSQL and SQLite.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c3f1d2e8a9"
down_revision: Union[str, None] = "a4f2e9b1c8d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Extend audio_responses with Week 3 timing columns
    #
    # Both columns are nullable — existing rows produced by Week 2 have
    # no processing timestamps and receive NULL. The pipeline sets
    # processing_started_at atomically when it claims a job (status →
    # 'processing') and processing_completed_at when it finishes
    # (status → 'completed' or 'failed').
    #
    # No server_default: NULL is the correct initial value for rows
    # that have not yet been processed. A server_default of now() would
    # backfill every existing row with the migration timestamp, which
    # would be misleading.
    # ------------------------------------------------------------------
    op.add_column(
        "audio_responses",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audio_responses",
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------------
    # 2. Create transcripts
    #
    # Dependency: audio_responses must exist (created in migration 0001).
    #
    # UNIQUE(audio_response_id): one transcript per audio response.
    # The unique constraint implicitly creates a B-tree index on
    # audio_response_id — no separate op.create_index needed for that
    # column. The constraint name follows the uq_{table}_{column}
    # convention used by migration 0001.
    #
    # ON DELETE CASCADE: deleting an AudioResponse automatically removes
    # its Transcript without requiring the ORM to load the child row.
    # This is required because processing_service deletes AudioResponse
    # objects via Session cascade (triggered by InterviewSession deletion)
    # which bypasses explicit ORM child management.
    # ------------------------------------------------------------------
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("audio_response_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["audio_response_id"],
            ["audio_responses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "audio_response_id",
            name="uq_transcripts_audio_response_id",
        ),
    )

    # ------------------------------------------------------------------
    # 3. Create interview_analyses
    #
    # Dependencies: both audio_responses and transcripts must exist.
    # Must be created last in upgrade; dropped first in downgrade.
    #
    # Named CHECK constraints on all five score columns: score fields are
    # NOT NULL so the CHECK expression needs no IS NULL guard.
    # Constraints are named with the ck_{table_short}_{column} convention
    # for future ALTER TABLE maintainability across environments.
    #
    # UNIQUE(audio_response_id): one analysis per audio response.
    # Implicitly creates a B-tree index — no separate CREATE INDEX needed.
    #
    # ix_interview_analyses_created_at: explicit non-unique index for
    # time-range queries and dashboard ordering. Separate from the unique
    # index on audio_response_id; both serve different query patterns.
    #
    # transcript_id FK ON DELETE SET NULL: the analysis survives if its
    # transcript is deleted independently. The column is nullable to
    # accommodate this; the service records transcript_id at the time of
    # evaluation but does not depend on it remaining populated.
    # ------------------------------------------------------------------
    op.create_table(
        "interview_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("audio_response_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_id", sa.Uuid(), nullable=True),
        # Scores: NUMERIC(4,1) — exact decimal, no IEEE 754 drift.
        # Range [0.0, 10.0] enforced by the named CHECK constraints below.
        sa.Column("overall_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("communication_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("technical_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("problem_solving_score", sa.Numeric(4, 1), nullable=False),
        sa.Column("confidence_score", sa.Numeric(4, 1), nullable=False),
        # Narrative fields: stored as JSON-encoded text for SQLite
        # compatibility; the Pydantic schema layer deserialises them.
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("weaknesses", sa.Text(), nullable=True),
        sa.Column("detailed_feedback", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Named CHECK constraints — score NOT NULL, so no IS NULL guard needed.
        sa.CheckConstraint(
            "overall_score >= 0.0 AND overall_score <= 10.0",
            name="ck_analyses_overall_score",
        ),
        sa.CheckConstraint(
            "communication_score >= 0.0 AND communication_score <= 10.0",
            name="ck_analyses_communication_score",
        ),
        sa.CheckConstraint(
            "technical_score >= 0.0 AND technical_score <= 10.0",
            name="ck_analyses_technical_score",
        ),
        sa.CheckConstraint(
            "problem_solving_score >= 0.0 AND problem_solving_score <= 10.0",
            name="ck_analyses_problem_solving_score",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 10.0",
            name="ck_analyses_confidence_score",
        ),
        sa.ForeignKeyConstraint(
            ["audio_response_id"],
            ["audio_responses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "audio_response_id",
            name="uq_interview_analyses_audio_response_id",
        ),
    )
    # Non-unique index on created_at: time-range and ordering queries.
    # audio_response_id is already covered by the UniqueConstraint above.
    op.create_index(
        op.f("ix_interview_analyses_created_at"),
        "interview_analyses",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Drop in strict reverse dependency order.
    # Dropping a table implicitly drops all its constraints and indexes
    # (PRIMARY KEY, UNIQUE, CHECK, FK). Only separately-created indexes
    # need an explicit drop_index call before drop_table.

    # 3 → interview_analyses (depends on audio_responses and transcripts)
    op.drop_index(
        op.f("ix_interview_analyses_created_at"),
        table_name="interview_analyses",
    )
    op.drop_table("interview_analyses")

    # 2 → transcripts (depends on audio_responses)
    # uq_transcripts_audio_response_id is dropped implicitly with the table.
    op.drop_table("transcripts")

    # 1 → audio_responses timing columns (table stays; only the two new
    # columns added in this migration are removed).
    # Drop in reverse-add order to keep the column history readable.
    op.drop_column("audio_responses", "processing_completed_at")
    op.drop_column("audio_responses", "processing_started_at")
