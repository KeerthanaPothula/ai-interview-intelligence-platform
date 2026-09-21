"""Application-level request body size limits (pure ASGI middleware).

Why this exists
---------------
Starlette (0.47.x) does not bound the size of an ``application/x-www-form-urlencoded``
body (PYSEC-2026-249), and FastAPI reads and parses the body *before* dependencies
such as authentication and the login rate limiter run. Parsing a urlencoded body full
of tiny fields is roughly quadratic: about 0.1 s for 16 KiB but ~17 s of event-loop
time for 1 MiB. This middleware rejects oversized bodies with HTTP 413 before any
parser sees them, independent of what the hosting platform enforces.

Which limit applies (chosen per request, so a large upload allowance is never
available to an ordinary endpoint):

* ``multipart/form-data`` on one of the two upload routes (``UPLOAD_ROUTES``):
  the endpoint's own per-file cap plus ``_MULTIPART_OVERHEAD_BYTES`` for boundaries
  and form fields. The endpoint still enforces its exact per-file limit and message.
* ``application/x-www-form-urlencoded`` anywhere: ``MAX_FORM_BODY_KB`` (login is the
  only such endpoint and sends ~170 bytes).
* anything else (JSON, multipart at a non-upload path, ...): ``MAX_REQUEST_BODY_KB``.

How it rejects
--------------
* ``Content-Length`` above the limit: 413 immediately, without reading the body.
* No/understated ``Content-Length`` (chunked): bytes are counted as the app reads
  them, and reading stops with 413 once the limit is crossed — at most one chunk
  beyond the limit is ever held, never the whole body.

The middleware is added *innermost* (before CORS), so its 413 responses still get
CORS, security and request-ID headers from the outer layers.
"""

from __future__ import annotations

import logging
import re

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings

logger = logging.getLogger(__name__)

TOO_LARGE_DETAIL = "Request body too large."

_MB = 1024 * 1024
# Multipart framing (boundaries, part headers, the small form fields that travel
# with the file). The endpoint checks the file's exact size itself.
_MULTIPART_OVERHEAD_BYTES = _MB

# The ONLY routes that accept file uploads: (method, path pattern, setting holding
# the per-file cap in MB). A new upload endpoint must be added here — a test fails
# if a route takes a file that is not listed.
UPLOAD_ROUTES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("POST", re.compile(r"^/api/v1/interviews/[^/]+/responses$"), "MAX_UPLOAD_SIZE_MB"),
    (
        "POST",
        re.compile(r"^/api/v1/documents/resume/upload$"),
        "MAX_RESUME_UPLOAD_SIZE_MB",
    ),
)


def body_limit_bytes(method: str, path: str, content_type: str, settings) -> int:
    """Return the maximum request body size, in bytes, for this request."""
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type == "multipart/form-data":
        for upload_method, pattern, setting in UPLOAD_ROUTES:
            if method == upload_method and pattern.match(path):
                return getattr(settings, setting) * _MB + _MULTIPART_OVERHEAD_BYTES
    if media_type == "application/x-www-form-urlencoded":
        return settings.MAX_FORM_BODY_KB * 1024
    return settings.MAX_REQUEST_BODY_KB * 1024


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        limit = body_limit_bytes(
            scope["method"],
            scope["path"],
            headers.get("content-type", ""),
            get_settings(),
        )

        declared = headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            logger.warning(
                "Rejected oversized request body: %s %s declared=%s limit=%d",
                scope["method"],
                scope["path"],
                declared,
                limit,
            )
            response = JSONResponse(
                {"detail": TOO_LARGE_DETAIL},
                status_code=413,
                # The body was not read: tell the client to stop sending it.
                headers={"Connection": "close"},
            )
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    logger.warning(
                        "Rejected oversized streamed request body: %s %s limit=%d",
                        scope["method"],
                        scope["path"],
                        limit,
                    )
                    # Must be an HTTPException: FastAPI's body parsing re-raises
                    # those (-> a clean 413 via the app's exception handling) but
                    # turns any other exception into a 400 "error parsing the body".
                    raise HTTPException(status_code=413, detail=TOO_LARGE_DETAIL)
            return message

        await self.app(scope, limited_receive, send)
