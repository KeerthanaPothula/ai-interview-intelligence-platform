from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """ORM model for the `refresh_tokens` table.

    One row per refresh token ever issued. Rows are never deleted on
    rotation or logout — they are marked revoked_at instead, preserving an
    audit trail of the full rotation chain for a user.

    Only a SHA-256 hash of the token is stored (token_hash), never the
    raw token value. A leaked database dump therefore cannot be replayed
    as a valid refresh token, mirroring how hashed_password is stored on
    User.

    Rotation: when a refresh token is redeemed for a new access token, the
    old row is marked revoked_at and a new row is inserted with
    replaces_token_id pointing at the old row's id. If a revoked token is
    ever presented again (token reuse — a signal of theft), the entire
    chain rooted at that token should be revoked; see
    auth_service.revoke_token_family.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique refresh token row identifier.",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user. Cascade-deleted with the user.",
    )

    # SHA-256 hex digest is always 64 characters.
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA-256 hash of the raw refresh token. The raw value is never stored.",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC expiry. Expired tokens are rejected even if not revoked.",
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when the token is rotated, logged out, or explicitly revoked.",
    )

    replaces_token_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
        comment="Predecessor token in the rotation chain, if this token was issued via rotation.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="UTC timestamp this token row was created.",
    )

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.revoked_at is not None}>"
