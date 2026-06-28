"""Security response headers middleware.

Adds the standard OWASP-recommended hardening headers to every response.
Environment-aware: Strict-Transport-Security is only emitted in
production, because HSTS over plain HTTP in local development would
instruct browsers to force HTTPS against a dev server that does not
serve it, locking developers out of http://localhost.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        settings = self._settings
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = settings.CSP_POLICY
        response.headers["Permissions-Policy"] = settings.PERMISSIONS_POLICY

        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.HSTS_MAX_AGE_SECONDS}; includeSubDomains"
            )

        return response
