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
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )
