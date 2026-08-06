from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.security import decode_access_token
from app.database import get_db
from app.models.role import Role
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

    # Deactivation (e.g. an Admin offboarding a recruiter, or deactivating
    # an organization) must block access immediately, even with a
    # still-valid, unexpired JWT — checked here rather than only in
    # role-gated routes so it applies uniformly to every endpoint,
    # including plain get_current_user usages that predate RBAC.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    return user


def require_role(role: Role) -> Callable[[User], User]:
    """FastAPI dependency factory: only `role` may proceed.

    Usage:
        @router.get("/admin/organizations")
        def list_organizations(
            current_user: User = Depends(require_role(Role.SUPER_ADMIN)),
        ):
            ...

    The check is always against `current_user.role` as freshly loaded from
    the database inside get_current_user on *this* request — never against
    a `role` claim decoded out of the JWT itself. A JWT is only valid for
    up to ACCESS_TOKEN_EXPIRE_MINUTES; if an admin changes a user's role
    mid-lifetime, the very next request already sees the new role, with no
    separate cache-invalidation step required. This is what actually
    prevents privilege escalation via a stale or hand-crafted token: the
    role in the token payload (if present at all) is informational only
    and is never trusted for the authorization decision.
    """

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{role.value}' role.",
            )
        return current_user

    return _dependency


def require_any_role(*roles: Role) -> Callable[[User], User]:
    """FastAPI dependency factory: any one of `roles` may proceed.

    Usage:
        @router.get("/admin/overview")
        def overview(
            current_user: User = Depends(
                require_any_role(Role.ADMIN, Role.SUPER_ADMIN)
            ),
        ):
            ...

    Same DB-sourced-role guarantee as require_role — see its docstring.
    """
    allowed = {r.value for r in roles}

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _dependency
