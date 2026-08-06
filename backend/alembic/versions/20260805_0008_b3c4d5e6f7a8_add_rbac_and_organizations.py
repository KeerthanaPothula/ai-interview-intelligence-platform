"""Add RBAC roles and multi-tenant organizations.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-05 00:08:00.000000

Adds:
  - organizations table (the tenant boundary).
  - users.role (NOT NULL, server_default 'candidate' — every existing user
    becomes CANDIDATE automatically, no data loss, no manual backfill step).
  - users.organization_id (nullable FK -> organizations.id, ON DELETE SET
    NULL — candidates are unaffiliated until invited; deleting/deactivating
    an org must never cascade-delete its former members).
  - users.is_active (NOT NULL, server_default true).
  - interview_sessions.recruiter_status (nullable — only ever set once a
    session has already reached the recruiter pipeline; see the column's
    comment in app.models.interview).

ck_users_role enforces the same four values as app.models.role.Role at the
database level, independent of the application layer.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            comment="Unique organization identifier.",
        ),
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
            comment="Organization display name, e.g. 'Google'. Unique platform-wide.",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="Deactivated by an Admin/Super Admin — hides the org and its "
            "recruiters from active flows without deleting historical data.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="UTC timestamp the organization was created.",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_organizations_name"), "organizations", ["name"], unique=True
    )

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(20),
            server_default="candidate",
            nullable=False,
            comment="One of Role's values. Assigned CANDIDATE at registration; "
            "changed only by a Super Admin thereafter.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "organization_id",
            sa.Uuid(),
            nullable=True,
            comment="NULL for an unaffiliated candidate. Required in practice for "
            "RECRUITER/ADMIN accounts, which are always created already assigned "
            "to an organization.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="Deactivated accounts (e.g. an offboarded recruiter) fail "
            "authorization even with a valid, unexpired JWT.",
        ),
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('admin', 'candidate', 'recruiter', 'super_admin')",
    )
    op.create_foreign_key(
        "fk_users_organization_id",
        "users",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_users_organization_id"), "users", ["organization_id"], unique=False
    )

    op.add_column(
        "interview_sessions",
        sa.Column(
            "recruiter_status",
            sa.String(20),
            nullable=True,
            comment="Recruiter pipeline status (applied/reviewing/interviewed/"
            "shortlisted/rejected/hired). NULL until the session first "
            "surfaces in a recruiter's candidate list.",
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "recruiter_status")

    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "is_active")
    op.drop_column("users", "organization_id")
    op.drop_column("users", "role")

    op.drop_index(op.f("ix_organizations_name"), table_name="organizations")
    op.drop_table("organizations")
