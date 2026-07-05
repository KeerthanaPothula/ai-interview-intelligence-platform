from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.deps import get_current_user
from app.core.rate_limit import enforce_login_rate_limit
from app.core.security import create_access_token, generate_refresh_token
from app.core.security_logging import (
    log_account_locked,
    log_login_failed,
    log_login_succeeded,
    log_logout,
    log_token_refreshed,
    log_token_refresh_rejected,
)
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    DetailResponse,
    ForgotPasswordRequest,
    RefreshRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _issue_token_pair(db: Session, user: User) -> Token:
    """Create a fresh access token + refresh token pair for `user`."""
    access_token = create_access_token(
        data={"sub": user.email, "ver": user.token_version}
    )
    raw_refresh_token = generate_refresh_token()
    auth_service.issue_refresh_token(db, user, raw_refresh_token)
    return Token(access_token=access_token, refresh_token=raw_refresh_token)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    return auth_service.register_user(db, user_data)


@router.post(
    "/login",
    response_model=Token,
    summary="Exchange email + password for a JWT access token + refresh token",
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """
    Accepts standard OAuth2 form fields:
      - username  (we treat this as the email address)
      - password

    Returns a Bearer access token (ACCESS_TOKEN_EXPIRE_MINUTES lifetime)
    and a refresh token (REFRESH_TOKEN_EXPIRE_DAYS lifetime). The /docs UI
    uses this endpoint automatically to issue tokens.

    Rate limited per client IP (see enforce_login_rate_limit) and subject
    to per-account lockout with progressive backoff after repeated failed
    attempts (see auth_service.record_failed_login).
    """
    ip = _client_ip(request)
    user = auth_service.get_user_by_email(db, form_data.username)

    if user is not None and auth_service.is_account_locked(user):
        log_login_failed(user.id, ip, "account_locked")
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "Account temporarily locked due to multiple failed login "
                "attempts. Please try again later."
            ),
        )

    authenticated = auth_service.authenticate_user(
        db, form_data.username, form_data.password
    )
    if authenticated is None:
        if user is not None:
            locked_now = auth_service.record_failed_login(db, user)
            if locked_now:
                log_account_locked(user.id, ip, user.lockout_count)
            else:
                log_login_failed(user.id, ip, "bad_password")
        else:
            log_login_failed(None, ip, "unknown_email")

        # Intentionally vague — do not reveal whether the email exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service.record_successful_login(db, authenticated)
    log_login_succeeded(authenticated.id, ip)
    return _issue_token_pair(db, authenticated)


@router.post(
    "/refresh",
    response_model=Token,
    summary="Exchange a refresh token for a new access token + rotated refresh token",
    dependencies=[Depends(enforce_login_rate_limit)],
)
def refresh(
    request: Request,
    body: RefreshRequest,
    db: Session = Depends(get_db),
) -> Token:
    """
    Refresh token rotation: the submitted refresh token is revoked and a
    new one is issued in the same call. A refresh token can therefore only
    ever be redeemed once — replaying an already-used token revokes every
    other active token for that account (see
    auth_service.get_refresh_token_for_use) as a defensive response to
    suspected token theft. Does not require re-entering a password, and
    does not affect the existing password-based login flow.
    """
    ip = _client_ip(request)
    try:
        old_row = auth_service.get_refresh_token_for_use(db, body.refresh_token)
    except HTTPException:
        log_token_refresh_rejected(ip, "invalid_or_reused")
        raise

    user = db.get(User, old_row.user_id)
    if user is None:
        log_token_refresh_rejected(ip, "user_not_found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    raw_new_token = generate_refresh_token()
    auth_service.rotate_refresh_token(db, old_row, raw_new_token)

    access_token = create_access_token(
        data={"sub": user.email, "ver": user.token_version}
    )
    log_token_refreshed(user.id, ip)
    return Token(access_token=access_token, refresh_token=raw_new_token)


@router.post(
    "/logout",
    response_model=DetailResponse,
    summary="Revoke a refresh token",
)
def logout(
    body: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> DetailResponse:
    """
    Revokes the submitted refresh token so it can no longer be redeemed via
    /auth/refresh. Does not revoke the caller's current access token —
    that token remains valid until it expires (ACCESS_TOKEN_EXPIRE_MINUTES),
    consistent with stateless JWT access tokens. Logging out of all
    devices (revoking every access token immediately) is achieved by
    bumping the user's token_version, which this endpoint does not do.
    """
    ip = _client_ip(request)
    row = auth_service.get_refresh_token_for_use(db, body.refresh_token)
    auth_service.revoke_refresh_token(db, row)
    log_logout(row.user_id, ip)
    return DetailResponse(detail="Logged out successfully.")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the currently authenticated user",
)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post(
    "/forgot-password",
    response_model=DetailResponse,
    summary="Request a password-reset link",
)
def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DetailResponse:
    """Issue a one-time password-reset token for the given email.

    Always returns HTTP 200 with the same message regardless of whether the
    email is registered — this prevents user enumeration attacks.

    In production, configure SMTP via the SMTP_* environment variables and the
    token will be sent as an email link. Without SMTP config, the raw token is
    logged at WARNING level so it can be retrieved from server logs during
    development/testing.
    """
    import logging

    logger = logging.getLogger(__name__)

    raw_token = auth_service.create_password_reset_token(db, body.email)

    if raw_token is not None:
        reset_url = f"{settings.FRONTEND_URL}/reset-password/{raw_token}"
        _send_reset_email(body.email, reset_url, logger, settings)

    return DetailResponse(
        detail="If an account with that email exists, a password-reset link has been sent."
    )


@router.post(
    "/reset-password",
    response_model=DetailResponse,
    summary="Set a new password using a reset token",
)
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> DetailResponse:
    """Consume a password-reset token and update the user's password.

    The token must be unused and not expired (30-minute window). On success,
    all existing access tokens and refresh tokens for the user are invalidated.
    Returns HTTP 400 on any invalid/expired/reused token — the error message
    is deliberately generic to avoid leaking token validity information.
    """
    success = auth_service.redeem_password_reset_token(db, body.token, body.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Please request a new one.",
        )
    return DetailResponse(detail="Password updated successfully. You can now log in.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _send_reset_email(email: str, reset_url: str, logger: object, settings: Settings) -> None:
    """Send a password-reset email, or log the URL if SMTP is not configured."""
    import logging
    import smtplib
    from email.message import EmailMessage

    _logger = logger if isinstance(logger, logging.Logger) else logging.getLogger(__name__)

    smtp_host = getattr(settings, "SMTP_HOST", None)
    if not smtp_host:
        _logger.warning(
            "SMTP not configured — password reset URL for %s: %s",
            email,
            reset_url,
        )
        return

    try:
        smtp_port = getattr(settings, "SMTP_PORT", 587)
        smtp_user = getattr(settings, "SMTP_USER", "")
        smtp_password = getattr(settings, "SMTP_PASSWORD", "")
        from_email = getattr(settings, "SMTP_FROM", smtp_user)

        msg = EmailMessage()
        msg["Subject"] = "Reset your password — AI Interview Intelligence Platform"
        msg["From"] = from_email
        msg["To"] = email
        msg.set_content(
            f"You requested a password reset.\n\n"
            f"Click the link below to set a new password (valid for 30 minutes):\n\n"
            f"{reset_url}\n\n"
            f"If you did not request this, you can safely ignore this email."
        )

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
    except Exception as exc:
        _logger.error("Failed to send password-reset email to %s: %s", email, exc)
