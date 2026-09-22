"""Add live_session_id to interview_sessions.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-22 00:09:00.000000

Links a completed LiveInterviewSession to a mirrored InterviewSession so
that live conversational interviews appear in the existing /interviews
list and dashboard analytics, both of which only ever query
interview_sessions. See app.services.interview_service.mirror_completed_live_session.

live_session_id is nullable (upload/audio sessions never set it) and
UNIQUE (not NOT NULL) — the unique constraint is what makes mirroring
idempotent: a session already mirrored for a given live interview is
found by this column rather than inserted twice. ON DELETE SET NULL
because deleting a LiveInterviewSession (no endpoint does this today,
but the FK must define a policy regardless) must not cascade-delete the
candidate's already-completed interview history — only drop the
traceability link.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column(
            "live_session_id",
            sa.Uuid(),
            nullable=True,
            comment="Set when this session mirrors a completed "
            "LiveInterviewSession. NULL for the normal upload/audio flow.",
        ),
    )
    op.create_foreign_key(
        "fk_interview_sessions_live_session_id",
        "interview_sessions",
        "live_interview_sessions",
        ["live_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_interview_sessions_live_session_id",
        "interview_sessions",
        ["live_session_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_interview_sessions_live_session_id",
        "interview_sessions",
        type_="unique",
    )
    op.drop_constraint(
        "fk_interview_sessions_live_session_id",
        "interview_sessions",
        type_="foreignkey",
    )
    op.drop_column("interview_sessions", "live_session_id")
