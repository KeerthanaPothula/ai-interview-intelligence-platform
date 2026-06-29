"""Add Phase 3 security columns to users and the refresh_tokens table.

Revision ID: f1a2b3c4d5e6
Revises: e9a1c3f5b2d4
Create Date: 2026-06-27 00:06:00.000000

Phase 3 (Production Security Hardening):

  Upgrade:
    1. users gains four columns supporting login protection and JWT
       token versioning:
         - failed_login_attempts (Integer, NOT NULL, default 0)
         - locked_until (TIMESTAMPTZ, nullable)
         - lockout_count (Integer, NOT NULL, default 0)
         - token_version (Integer, NOT NULL, default 0)
    2. A new refresh_tokens table is created to support refresh token
       issuance, rotation, and revocation. Only a SHA-256 hash of each
       token is stored — never the raw value.

  Downgrade: drop refresh_tokens, then drop the four new users columns,
  in reverse order.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e9a1c3f5b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. users — login protection + token versioning columns
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("lockout_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )

    # ------------------------------------------------------------------
    # 2. refresh_tokens table
    # ------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaces_token_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaces_token_id"], ["refresh_tokens.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_column("users", "token_version")
    op.drop_column("users", "lockout_count")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
