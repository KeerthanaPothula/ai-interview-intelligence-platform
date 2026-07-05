"""Add password_reset_tokens table.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-04 00:07:00.000000

Adds the `password_reset_tokens` table to support the forgot-password /
reset-password flow.

  Upgrade:
    Creates `password_reset_tokens` with:
      - id (UUID, PK)
      - user_id (UUID, FK → users.id ON DELETE CASCADE, indexed)
      - token_hash (VARCHAR(64), unique, indexed) — SHA-256 of raw token
      - expires_at (TIMESTAMPTZ, NOT NULL)
      - used_at (TIMESTAMPTZ, nullable) — set on redemption
      - created_at (TIMESTAMPTZ, server default NOW())

  Downgrade: drop the table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), nullable=False, comment="Unique row identifier."),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
            comment="Owning user. Cascade-deleted with the user.",
        ),
        sa.Column(
            "token_hash",
            sa.String(64),
            nullable=False,
            comment="SHA-256 hash of the raw reset token. The raw value is never stored.",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC expiry. Expired tokens are rejected even if not used.",
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Set when the token is successfully redeemed. Null means unused.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="UTC timestamp this token row was created.",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"),
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_token_hash"),
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_password_reset_tokens_token_hash"),
        table_name="password_reset_tokens",
    )
    op.drop_index(
        op.f("ix_password_reset_tokens_user_id"),
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")
