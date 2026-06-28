import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


def generate_refresh_token() -> str:
    """Return a new cryptographically random refresh token (256 bits, URL-safe)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Return the SHA-256 hex digest of a refresh token.

    Refresh tokens are persisted only in this hashed form (see
    RefreshToken.token_hash) — never the raw value — so a database leak
    cannot be replayed as a valid token, mirroring how passwords are
    stored via get_password_hash/verify_password.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plain_password matches the stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    """Hash a plaintext password with bcrypt. Never store the plain value."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    Encode a JWT access token.

    `data` must include a "sub" key (the subject — we use email).
    The token is signed with JWT_SECRET_KEY and expires after
    ACCESS_TOKEN_EXPIRE_MINUTES (or the provided expires_delta).

    Includes a random "jti" claim so that two tokens issued for the same
    user within the same second (exp has whole-second granularity) are
    still distinct values — relevant for refresh/rotation flows where a
    new access token is minted immediately after the previous one.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    to_encode["jti"] = secrets.token_hex(8)
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    Decode and verify a JWT access token.

    Returns the payload dict on success, None if the token is invalid,
    expired, or tampered with. Callers must treat None as an auth failure.
    """
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return None
