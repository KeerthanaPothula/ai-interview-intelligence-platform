from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class PasswordResetToken(Base):
    """ORM model for the `password_reset_tokens` table.

    One row per password-reset request. Only a SHA-256 hash of the raw
    token is stored — the raw token is sent to the user via email and is
    never written to the database, so a leaked dump cannot be replayed.

    Tokens expire after 30 minutes and are single-use: used_at is set when
    the token is redeemed, and any attempt to reuse it is rejected.

    Invalidation: issuing a new reset token invalidates all previous tokens
    for the same user (previous rows remain in the DB with used_at set).
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique row identifier.",
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
        comment="SHA-256 hash of the raw reset token. The raw value is never stored.",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC expiry. Expired tokens are rejected even if not used.",
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Set when the token is successfully redeemed. Null means unused.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="UTC timestamp this token row was created.",
    )

    user: Mapped["User"] = relationship("User", back_populates="password_reset_tokens")

    def __repr__(self) -> str:
        return f"<PasswordResetToken id={self.id} user_id={self.user_id} used={self.used_at is not None}>"
