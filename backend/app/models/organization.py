from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Organization(Base):
    """
    ORM model for the `organizations` table — the tenant boundary for the
    multi-tenant RBAC model.

    Recruiters and Admins belong to exactly one organization. Candidates
    belong to at most one, and only when explicitly invited — otherwise
    User.organization_id is NULL (see app.models.user.User). Recruiters can
    only see candidates whose organization_id matches their own
    (app.services.recruiter_service); Super Admins see every organization
    regardless of membership.
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique organization identifier.",
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Organization display name, e.g. 'Google'. Unique platform-wide.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Deactivated by an Admin/Super Admin — hides the org and its "
        "recruiters from active flows without deleting historical data.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC timestamp the organization was created.",
    )

    members: Mapped[list["User"]] = relationship("User", back_populates="organization")

    def __repr__(self) -> str:
        return f"<Organization id={self.id} name={self.name!r}>"
