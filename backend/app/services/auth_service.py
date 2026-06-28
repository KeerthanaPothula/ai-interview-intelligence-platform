from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import get_password_hash, hash_refresh_token, verify_password
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import UserCreate


def _as_aware_utc(dt: datetime) -> datetime:
    """Treat a naive datetime read back from the database as UTC.

    SQLite (used by the test suite) does not reliably round-trip the
    timezone-awareness of DateTime(timezone=True) columns — values can come
    back naive even though they were written as UTC-aware. PostgreSQL
    (production) does not have this issue, but normalizing here is cheap
    and correct in both cases since every datetime this module writes is
    already UTC.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def get_user_by_email(db: Session, email: str) -> User | None:
    """Return the User row with the given email, or None."""
    return db.query(User).filter(User.email == email).first()


def register_user(db: Session, user_data: UserCreate) -> User:
    """
    Create a new user account.

    Raises HTTP 409 if the email is already registered.
    The plaintext password is hashed before storage — it is never written
    to the database.
    """
    if get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """
    Verify email + password and return the User if correct.

    Returns None on any mismatch — callers must not distinguish between
    "email not found" and "wrong password" to prevent user enumeration.

    Does NOT check account lockout — callers must call is_account_locked()
    on the looked-up user first (see app.routers.auth.login), because a
    locked account must reject *correct* passwords too, which this
    function alone cannot express while keeping its enumeration-safe
    contract simple.
    """
    user = get_user_by_email(db, email)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ---------------------------------------------------------------------------
# Login protection — brute-force lockout with progressive backoff
# ---------------------------------------------------------------------------


def is_account_locked(user: User) -> bool:
    """Return True if `user` is currently within an active lockout window."""
    if user.locked_until is None:
        return False
    return _as_aware_utc(user.locked_until) > datetime.now(timezone.utc)


def _lockout_duration_minutes(lockout_count: int) -> int:
    """Progressive backoff: duration doubles with each successive lockout.

    lockout_count is the number of times this account has been locked
    *before* this one, so the first lockout uses the base duration, the
    second uses 2x, the third 4x, capped at ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES.
    """
    settings = get_settings()
    duration = settings.ACCOUNT_LOCKOUT_DURATION_MINUTES * (2**lockout_count)
    return min(duration, settings.ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES)


def record_failed_login(db: Session, user: User) -> bool:
    """Increment the failed-attempt counter and lock the account if the
    configured threshold is reached.

    Returns True if this call triggered a new lockout (so the caller can
    log/report it distinctly from an ordinary failed attempt).
    """
    settings = get_settings()
    user.failed_login_attempts += 1

    locked_now = False
    if user.failed_login_attempts >= settings.ACCOUNT_LOCKOUT_THRESHOLD:
        duration = _lockout_duration_minutes(user.lockout_count)
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=duration)
        user.lockout_count += 1
        user.failed_login_attempts = 0
        locked_now = True

    db.commit()
    return locked_now


def record_successful_login(db: Session, user: User) -> None:
    """Reset the failed-attempt counter after a successful login.

    lockout_count (the historical count of lockouts) is intentionally not
    reset — it keeps driving progressive backoff for any future lockout.
    """
    if user.failed_login_attempts != 0:
        user.failed_login_attempts = 0
        db.commit()


# ---------------------------------------------------------------------------
# Refresh tokens — issuance, rotation, revocation
# ---------------------------------------------------------------------------


def issue_refresh_token(
    db: Session,
    user: User,
    raw_token: str,
    replaces_token_id: uuid.UUID | None = None,
) -> RefreshToken:
    """Persist a new refresh token row (hashed) for `user` and return it."""
    settings = get_settings()
    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        replaces_token_id=replaces_token_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_refresh_token_for_use(db: Session, raw_token: str) -> RefreshToken:
    """Validate a refresh token for redemption (refresh or logout).

    Raises HTTP 401 if the token is unknown, expired, or already revoked.
    Presenting an already-revoked-but-known token is treated as reuse of a
    rotated-away token — a signal of token theft or a stale client — and
    revokes every other active token for that user as a defensive measure.
    """
    token_hash = hash_refresh_token(raw_token)
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token.",
    )

    if row is None:
        raise invalid

    if row.revoked_at is not None:
        revoke_all_refresh_tokens_for_user(db, row.user_id)
        raise invalid

    if _as_aware_utc(row.expires_at) < datetime.now(timezone.utc):
        raise invalid

    return row


def rotate_refresh_token(
    db: Session, old_row: RefreshToken, raw_new_token: str
) -> RefreshToken:
    """Revoke `old_row` and issue a new token chained to it. Single commit."""
    old_row.revoked_at = datetime.now(timezone.utc)
    settings = get_settings()
    new_row = RefreshToken(
        user_id=old_row.user_id,
        token_hash=hash_refresh_token(raw_new_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        replaces_token_id=old_row.id,
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


def revoke_refresh_token(db: Session, row: RefreshToken) -> None:
    """Mark a single refresh token row revoked (used by /auth/logout)."""
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()


def revoke_all_refresh_tokens_for_user(db: Session, user_id: uuid.UUID) -> None:
    """Revoke every currently-active refresh token belonging to a user.

    Used both for reuse-detection (see get_refresh_token_for_use) and as
    the basis for a future "log out of all devices" action.
    """
    now = datetime.now(timezone.utc)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": now})
    db.commit()
