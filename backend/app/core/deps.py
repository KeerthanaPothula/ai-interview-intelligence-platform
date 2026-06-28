from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User

# tokenUrl must match the login endpoint path exactly so that
# FastAPI's /docs UI can locate it and issue tokens automatically.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_V1_PREFIX}/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency that resolves the Bearer token to a User row.

    Raises HTTP 401 if:
      - the token is missing or malformed
      - the token signature is invalid or expired
      - the email in the token does not match any user in the database

    Usage:
      @router.get("/me")
      def me(current_user: User = Depends(get_current_user)):
          ...
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    email: str | None = payload.get("sub")
    if not email:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    # Token versioning: a token issued before "ver" claims existed has no
    # "ver" key, which is treated as version 0 — matching the default
    # token_version=0 every existing user starts with, so pre-Phase-3
    # tokens keep working unchanged. Bumping token_version (logout-all,
    # password change) instantly invalidates every token signed with an
    # older version, without needing a blacklist store.
    token_version = payload.get("ver", 0)
    if token_version != user.token_version:
        raise credentials_exception

    return user
