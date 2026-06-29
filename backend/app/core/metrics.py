"""Prometheus metrics.

All metrics are registered against the default prometheus_client registry
on import. Label values are kept low-cardinality on purpose (route
template, not raw path; provider/operation name, not request content) so
the /metrics endpoint stays cheap to scrape regardless of traffic shape.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests received.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)

AI_REQUESTS_TOTAL = Counter(
    "ai_requests_total",
    "Total AI provider requests, by provider/operation/outcome.",
    ["provider", "operation", "status"],
)

AI_REQUEST_DURATION_SECONDS = Histogram(
    "ai_request_duration_seconds",
    "AI provider request duration in seconds.",
    ["provider", "operation"],
)

DB_QUERY_DURATION_SECONDS = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds.",
)

BACKGROUND_TASKS_TOTAL = Counter(
    "background_tasks_total",
    "Total background processing tasks, by task type and outcome.",
    ["task_type", "status"],
)

HTTP_ERRORS_TOTAL = Counter(
    "http_errors_total",
    "Total HTTP responses with a 4xx or 5xx status code.",
    ["method", "path", "status_code"],
)


def observe_http_request(
    *, method: str, path: str, status_code: int, duration_seconds: float
) -> None:
    """Record one completed HTTP request."""
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=status_code).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(
        duration_seconds
    )
    if status_code >= 400:
        HTTP_ERRORS_TOTAL.labels(
            method=method, path=path, status_code=status_code
        ).inc()


def observe_ai_request(
    *, provider: str, operation: str, status: str, duration_seconds: float
) -> None:
    """Record one AI provider call (e.g. Gemini, Whisper)."""
    AI_REQUESTS_TOTAL.labels(
        provider=provider, operation=operation, status=status
    ).inc()
    AI_REQUEST_DURATION_SECONDS.labels(provider=provider, operation=operation).observe(
        duration_seconds
    )


def observe_db_query(duration_seconds: float) -> None:
    """Record one database query's duration."""
    DB_QUERY_DURATION_SECONDS.observe(duration_seconds)


def observe_background_task(*, task_type: str, status: str) -> None:
    """Record one completed background processing task (e.g. the
    transcription + evaluation pipeline triggered by POST /process)."""
    BACKGROUND_TASKS_TOTAL.labels(task_type=task_type, status=status).inc()


def render_metrics() -> tuple[bytes, str]:
    """Return the current metrics snapshot and its content type."""
    return generate_latest(), CONTENT_TYPE_LATEST
