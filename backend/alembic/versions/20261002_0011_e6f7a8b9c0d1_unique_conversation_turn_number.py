"""Make (live_session_id, turn_number) unique on conversation_turns.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-02 00:11:00.000000

Two concurrent next-question requests for the same turn could each insert
the following turn. With this constraint the second insert fails, and
live_interview.next_question answers that request as a retry instead.

Rows duplicated before this fix are candidate data, so this migration
never deletes them: it stops with the affected session ids, to be
resolved by hand, and the constraint is added once none remain.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT DISTINCT live_session_id FROM conversation_turns "
                "GROUP BY live_session_id, turn_number HAVING COUNT(*) > 1"
            )
        )
        .scalars()
        .all()
    )
    if duplicates:
        raise RuntimeError(
            "conversation_turns has duplicate turn numbers in live sessions "
            f"{[str(d) for d in duplicates]}; resolve them before upgrading."
        )
    op.create_unique_constraint(
        "uq_conversation_turns_session_turn",
        "conversation_turns",
        ["live_session_id", "turn_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_conversation_turns_session_turn",
        "conversation_turns",
        type_="unique",
    )
