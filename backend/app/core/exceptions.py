"""Centralized application exception hierarchy and global FastAPI handlers.

Every handler returns the same JSON shape FastAPI's default HTTPException
handler already returns — ``{"detail": <str>}`` — so existing tests and
frontend error handling keep working unmodified. ``AppException`` subclasses
let services/routers raise typed errors without constructing an
``HTTPException`` (and its status code) inline at every call site.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.security_headers import apply_security_headers

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base class for all typed application errors.

    Carries the HTTP status code that should be returned, so a single
    exception handler can serialize any subclass without per-type branching.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail)


class ResourceNotFound(AppException):
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, detail: str = "Resource not found.") -> None:
        super().__init__(detail)


class UnauthorizedAccess(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self, detail: str = "Could not validate credentials.") -> None:
        super().__init__(detail)


class ValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(self, detail: str = "Validation failed.") -> None:
        super().__init__(detail)


class AIServiceError(AppException):
    """Raised when an upstream AI provider (Gemini) call fails or times out."""

    status_code = status.HTTP_502_BAD_GATEWAY

    def __init__(
        self,
        detail: str = "AI service is currently unavailable. Please try again.",
        status_code: int = status.HTTP_502_BAD_GATEWAY,
    ) -> None:
        super().__init__(detail, status_code=status_code)


class FileValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    def __init__(
        self,
        detail: str = "Uploaded file failed validation.",
        status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY,
    ) -> None:
        super().__init__(detail, status_code=status_code)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers. Call once during app construction."""

    @app.exception_handler(AppException)
    async def _handle_app_exception(
        _request: Request, exc: AppException
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )
        _apply_bypassed_middleware_headers(request, response)
        return response


def _apply_bypassed_middleware_headers(request: Request, response: JSONResponse) -> None:
    """Hand-apply what CORSMiddleware and SecurityHeadersMiddleware would
    normally add, because neither runs for this response.

    Starlette routes a handler registered for the base ``Exception`` class
    through ``ServerErrorMiddleware``, which — unlike handlers registered
    for ``HTTPException``/``AppException``/``RequestValidationError``, which
    go through ``ExceptionMiddleware`` — wraps the *entire* app, including
    every layer added via ``app.add_middleware()`` (see Starlette's
    ``Router.build_middleware_stack``). A response built here never passes
    back through CORSMiddleware, so a genuine backend bug (e.g. a query
    against a column missing from the database) produces a 500 with no
    ``Access-Control-Allow-Origin`` header. The browser's CORS check then
    fails, and `fetch()` raises a generic network-level error instead of
    ever exposing the 500 — the frontend's fetch wrapper reports this as
    "cannot connect to the backend", masking the real error entirely.
    """
    settings = get_settings()
    origin = request.headers.get("origin")
    if origin and origin in settings.CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"

    apply_security_headers(response, settings)
