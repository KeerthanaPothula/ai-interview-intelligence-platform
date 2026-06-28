"""Structured security-event logging.

All security-relevant events route through the "app.security" logger
(a child of the root logger configured in app.main.configure_logging),
so they can be filtered or shipped to a SIEM independently of general
application logs by matching the logger name.

Every helper here logs only identifiers (user id, client IP, a fixed
reason code) — never passwords, raw tokens, secrets, or other personal
data. user_id is a UUID, not an email, specifically so these log lines
do not carry PII.
"""

from __future__ import annotations

import logging
import uuid

security_logger = logging.getLogger("app.security")


def log_login_failed(user_id: uuid.UUID | None, ip: str, reason: str) -> None:
    security_logger.warning(
        "event=login_failed user_id=%s ip=%s reason=%s", user_id, ip, reason
    )


def log_account_locked(user_id: uuid.UUID, ip: str, locked_until_minutes: int) -> None:
    security_logger.warning(
        "event=account_locked user_id=%s ip=%s duration_minutes=%s",
        user_id,
        ip,
        locked_until_minutes,
    )


def log_login_succeeded(user_id: uuid.UUID, ip: str) -> None:
    security_logger.info("event=login_succeeded user_id=%s ip=%s", user_id, ip)


def log_rate_limited(path: str, ip: str) -> None:
    security_logger.warning("event=rate_limited path=%s ip=%s", path, ip)


def log_token_refreshed(user_id: uuid.UUID, ip: str) -> None:
    security_logger.info("event=token_refreshed user_id=%s ip=%s", user_id, ip)


def log_token_refresh_rejected(ip: str, reason: str) -> None:
    security_logger.warning("event=token_refresh_rejected ip=%s reason=%s", ip, reason)


def log_logout(user_id: uuid.UUID, ip: str) -> None:
    security_logger.info("event=logout user_id=%s ip=%s", user_id, ip)


def log_permission_denied(user_id: uuid.UUID | None, ip: str, path: str) -> None:
    security_logger.warning(
        "event=permission_denied user_id=%s ip=%s path=%s", user_id, ip, path
    )


def log_upload_rejected(user_id: uuid.UUID | None, ip: str, reason: str) -> None:
    security_logger.warning(
        "event=upload_rejected user_id=%s ip=%s reason=%s", user_id, ip, reason
    )
