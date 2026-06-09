"""add interview tables

Revision ID: a4f2e9b1c8d7
Revises: e3d9c8b7a6f5
Create Date: 2026-06-07 00:01:00.000000

Creates three tables in dependency order:
  1. interview_sessions  (FK → users)
  2. questions           (FK → interview_sessions)
  3. audio_responses     (FK → interview_sessions, questions, users)

All foreign keys carry ON DELETE CASCADE so that removing a parent row
at the DB level (e.g. via a bulk DELETE that bypasses the ORM) also
removes child rows without raising a constraint violation.

Status and source columns carry server-level defaults so that direct SQL
inserts (migrations, admin scripts) produce valid rows without specifying
every column. Alembic autogenerate does not compare server defaults
(compare_server_default is not enabled in env.py), so these defaults do
not cause phantom ALTER COLUMN migrations.

The onupdate=func.now() behaviour for updated_at is ORM-only and has no
DDL representation — it is not emitted here.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4f2e9b1c8d7"
down_revision: Union[str, None] = "e3d9c8b7a6f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. interview_sessions
    #
    # Root of the interview data model. FK to users.id with ON DELETE
    # CASCADE so deleting a user account automatically removes all their
    # sessions at the DB level.
    # ------------------------------------------------------------------
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("job_role", sa.String(255), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        # server_default provides a sensible value for direct SQL inserts.
        # The ORM uses its Python-side default= instead, so these two paths
        # are independent.
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # updated_at: server_default handles INSERT. The ORM's onupdate=func.now()
        # keeps this column current on UPDATE. There is no DB trigger — the ORM
        # is responsible for UPDATE-time stamping.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Index: speeds up the list-sessions query (WHERE user_id = ?)
    op.create_index(
        op.f("ix_interview_sessions_user_id"),
        "interview_sessions",
        ["user_id"],
        unique=False,
    )
    # Index: reserved for future status-filtered queries (e.g. admin dashboard)
    op.create_index(
        op.f("ix_interview_sessions_status"),
        "interview_sessions",
        ["status"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 2. questions
    #
    # Must be created after interview_sessions (FK dependency).
    # UniqueConstraint on (session_id, sequence_order) is defined inline
    # so no window exists where duplicates could be inserted between the
    # CREATE TABLE and a subsequent ALTER TABLE ADD CONSTRAINT.
    # ------------------------------------------------------------------
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        # SMALLINT: sequence positions 1-20 fit easily; saves 2 bytes per row
        # vs INTEGER and signals that large values are not expected.
        sa.Column("sequence_order", sa.SmallInteger(), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column(
            "source",
            sa.String(20),
            server_default=sa.text("'ai_generated'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        # Guarantees no two questions occupy the same position in a session.
        # Named explicitly so downgrade can reference it via constraint name
        # if a future migration needs to alter rather than drop the table.
        sa.UniqueConstraint(
            "session_id",
            "sequence_order",
            name="uq_question_session_order",
        ),
    )

    # ------------------------------------------------------------------
    # 3. audio_responses
    #
    # Must be created last: has FKs to interview_sessions, questions, and
    # users — all of which must exist before this table can be created.
    #
    # Three separate ON DELETE CASCADE constraints ensure that removing any
    # parent (user, session, or question) cascades to this table at the DB
    # level. This is critical for question regeneration: bulk-deleting
    # questions via SQL (not ORM) fires the DB cascade on question_id here
    # without the ORM needing to load any AudioResponse objects.
    # ------------------------------------------------------------------
    op.create_table(
        "audio_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # Relative path under settings.UPLOAD_DIR, e.g. "{session_id}/{id}.webm".
        # TEXT avoids any length ceiling on path strings.
        sa.Column("file_path", sa.Text(), nullable=False),
        # Nullable: populated after a successful write; allows a row to
        # exist in 'failed' status even when no file was written.
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'uploaded'"),
            nullable=False,
        ),
        # Populated by the Week 3 pipeline on processing failure.
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Index: speeds up list-responses queries (WHERE session_id = ?)
    op.create_index(
        op.f("ix_audio_responses_session_id"),
        "audio_responses",
        ["session_id"],
        unique=False,
    )
    # Index: used by the Week 3 pipeline to poll (WHERE status = 'uploaded')
    op.create_index(
        op.f("ix_audio_responses_status"),
        "audio_responses",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    # Drop in strict reverse dependency order.
    # Dropping a table implicitly drops all its indexes, FK constraints, and
    # the UniqueConstraint on questions — no explicit drop_constraint needed.
    # Indexes are dropped explicitly before their table for readability and
    # consistency with the Week 1 migration style.

    # 3 → audio_responses (most dependent: references all three parent tables)
    op.drop_index(op.f("ix_audio_responses_status"), table_name="audio_responses")
    op.drop_index(op.f("ix_audio_responses_session_id"), table_name="audio_responses")
    op.drop_table("audio_responses")

    # 2 → questions (depends on interview_sessions)
    # UniqueConstraint uq_question_session_order is dropped implicitly.
    op.drop_table("questions")

    # 1 → interview_sessions (depends only on users, which is not touched)
    op.drop_index(op.f("ix_interview_sessions_status"), table_name="interview_sessions")
    op.drop_index(
        op.f("ix_interview_sessions_user_id"), table_name="interview_sessions"
    )
    op.drop_table("interview_sessions")
