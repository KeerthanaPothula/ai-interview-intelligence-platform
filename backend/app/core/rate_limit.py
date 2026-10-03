"""In-memory rate limiters: per-IP for authentication, per-user for AI endpoints.

Single-process only — state lives in a module-level dict and is not
shared across multiple Uvicorn/Gunicorn workers or horizontally scaled
instances. That is an accepted trade-off for the current single-worker
deployment (see SECURITY.md for the multi-worker upgrade path: a
Redis-backed limiter using INCR + EXPIRE on the same key scheme used
here). It still fully protects a single-process deployment against
brute-force and credential-stuffing traffic from one IP.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from fastapi import Depends, HTTPException, Request, status

from app.config import get_settings
from app.core.client_ip import get_client_ip
from app.core.deps import get_current_user
from app.models.user import User


class InMemoryRateLimiter:
    """Fixed-window counter keyed by an arbitrary string."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Record one hit for `key` and report whether it is within `limit`.

        Returns (allowed, retry_after_seconds). retry_after_seconds is 0
        when allowed is True.
        """
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            cutoff = now - window_seconds
            while hits and hits[0] <= cutoff:
                hits.pop(0)

            if len(hits) >= limit:
                retry_after = max(int(hits[0] + window_seconds - now) + 1, 1)
                return False, retry_after

            hits.append(now)
            return True, 0

    def clear(self) -> None:
        """Discard all recorded hits. Test-only — not used by app code."""
        with self._lock:
            self._hits.clear()


# Single shared instance for all authentication endpoints in this process.
login_rate_limiter = InMemoryRateLimiter()


def enforce_login_rate_limit(request: Request) -> None:
    """FastAPI dependency: reject requests once an IP exceeds the login rate limit.

    Applied to /auth/login and /auth/refresh — the two endpoints an
    attacker would hammer for credential stuffing or refresh-token
    guessing. Keyed by client IP only (not by email), so it throttles an
    attacker probing many different email addresses from one source just
    as effectively as one repeatedly guessing a single account's password.
    """
    settings = get_settings()
    client_ip = get_client_ip(request)
    allowed, retry_after = login_rate_limiter.check(
        f"{request.url.path}:{client_ip}",
        settings.RATE_LIMIT_LOGIN_ATTEMPTS,
        settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


# Separate instance: AI usage must never eat into the login budget (or vice versa).
ai_rate_limiter = InMemoryRateLimiter()


def enforce_ai_rate_limit(current_user: User = Depends(get_current_user)) -> None:
    """FastAPI dependency: cap one user's requests to Gemini-backed endpoints.

    Keyed by the authenticated user's id, taken from the verified access
    token via get_current_user — never from anything the client sends — so
    a request without a valid token is rejected (401) before it reaches a
    bucket, and users behind one shared IP never throttle each other. One
    bucket per user across every AI endpoint caps their total AI cost.
    """
    settings = get_settings()
    allowed, retry_after = ai_rate_limiter.check(
        f"ai:{current_user.id}",
        settings.RATE_LIMIT_AI_REQUESTS,
        settings.RATE_LIMIT_AI_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You've made too many AI requests in a short time. "
            "Please wait a few minutes and try again.",
            headers={"Retry-After": str(retry_after)},
        )
