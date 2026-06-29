"""Per-request observability: request IDs, timing, slow-request logging,
and HTTP metrics — all in a single middleware pass to avoid stacking
multiple ASGI layers for what is fundamentally one concern (wrapping a
request/response cycle).
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings
from app.core.request_context import reset_request_id, set_request_id

logger = logging.getLogger("app.request")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a request ID, times the request, logs slow
    requests, and (if enabled) records Prometheus HTTP metrics.

    `settings` is captured once at construction (process lifetime), same
    as SecurityHeadersMiddleware — these are deployment-time toggles, not
    per-request values.
    """

    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        header_name = self._settings.REQUEST_ID_HEADER
        request_id = request.headers.get(header_name) or uuid.uuid4().hex
        token = set_request_id(request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers[header_name] = request_id

        route = request.scope.get("route")
        path_template = route.path if route is not None else request.url.path

        log_fields = {
            "method": request.method,
            "path": path_template,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "request_id": request_id,
        }
        if duration_ms > self._settings.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning("Slow request", extra=log_fields)
        else:
            logger.info("Request completed", extra=log_fields)

        if self._settings.ENABLE_METRICS:
            from app.core.metrics import observe_http_request

            observe_http_request(
                method=request.method,
                path=path_template,
                status_code=response.status_code,
                duration_seconds=duration_ms / 1000,
            )

        return response
