"""AI Interview Intelligence Platform — FastAPI application entry point.

This module wires together all routers and middleware into a single ASGI
application consumed by Uvicorn (or Gunicorn + Uvicorn workers in production).

Router registration:
    auth_router     — included with prefix="/api/v1" (router has prefix="/auth")
                      → routes land at /api/v1/auth/...

    interviews_router — included WITHOUT extra prefix because the router already
                        carries prefix="/api/v1/interviews"
                        → routes land at /api/v1/interviews/...

    responses_router  — included WITHOUT extra prefix because the router already
                        carries prefix="/api/v1"
                        → routes land at /api/v1/interviews/{id}/responses/...
                                     and /api/v1/responses/{id}/status

    processing_router — included WITHOUT extra prefix because the router already
                        carries prefix="/api/v1"
                        → routes land at /api/v1/responses/{id}/process
                                     and /api/v1/responses/{id}/processing-status

    Adding an extra prefix="/api/v1" when including interviews_router or
    responses_router would produce doubled paths like:
        /api/v1/api/v1/interviews/...  ← wrong

Why docs are disabled in production:
    Exposing /docs and /redoc in production reveals the full API schema,
    endpoint paths, parameter names, and example payloads to anyone with a
    browser. Disabling them (docs_url=None, redoc_url=None, openapi_url=None)
    also prevents FastAPI from serving the /openapi.json spec, so automated
    scanners cannot enumerate the API surface.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.responses import Response

from app.config import get_settings
from app.core.constants import API_V1_PREFIX
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.middleware import ObservabilityMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.tracing import configure_tracing
from app.database import SessionLocal, engine
from app.routers.admin import router as admin_router
from app.routers.analytics import router as analytics_router
from app.routers.auth import router as auth_router
from app.routers.documents import router as documents_router
from app.routers.follow_up import router as follow_up_router
from app.routers.interviews import router as interviews_router
from app.routers.live_interview import router as live_interview_router
from app.routers.prediction import router as prediction_router
from app.routers.processing import router as processing_router
from app.routers.recruiter import router as recruiter_router
from app.routers.reports import router as reports_router
from app.routers.responses import router as responses_router
from app.services import processing_service

# ---------------------------------------------------------------------------
# Settings — loaded once at startup via @lru_cache.
# If any required env var is missing or invalid, pydantic raises ValidationError
# here — the process exits immediately rather than serving broken requests.
# ---------------------------------------------------------------------------
settings = get_settings()

# ---------------------------------------------------------------------------
# Logging configuration
#
# configure_logging() attaches a single StreamHandler to the root logger,
# formatted as structured JSON by default (settings.LOG_FORMAT) so log
# aggregation tools can parse every line, with every record tagged with
# the current request ID (see app.core.request_context) for correlation.
# Idempotent — calling it more than once just replaces the handler.
# ---------------------------------------------------------------------------
configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

logger = logging.getLogger(__name__)

_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Lifespan — startup diagnostics, recovery, and shutdown
#
# Before recovery runs, a handful of logger.info() calls record the
# process's effective configuration (version, environment, debug flag,
# audio-processing flag, Whisper model, upload directory) once per process
# start — useful for confirming what a given deploy is actually running
# with, directly from the log stream, without inspecting environment
# variables.
#
# recover_stuck_jobs() issues a single conditional UPDATE ... WHERE
# status='processing' and commits. No Whisper, no Gemini, no
# BackgroundTasks — it runs synchronously and adds negligible latency to
# startup regardless of how many rows it touches.
#
# If recover_stuck_jobs() raises (e.g. the database is unreachable), the
# exception propagates out of this function and Uvicorn aborts startup —
# the same fail-fast behavior as `settings = get_settings()` above, which
# exits immediately on invalid configuration rather than serving requests
# against a broken database.
#
# The code after `yield` runs once on graceful shutdown (e.g. SIGTERM),
# logging a single line so a process stop is visible in the log stream.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "Application startup: AI Interview Intelligence Platform API v%s (environment=%s)",
        _VERSION,
        settings.ENVIRONMENT,
    )
    logger.info(
        "Settings loaded: debug=%s, audio_processing_enabled=%s",
        settings.DEBUG,
        settings.ENABLE_AUDIO_PROCESSING,
    )
    logger.info("Whisper model configured: %s", settings.WHISPER_MODEL)
    logger.info("Upload directory: %s", settings.UPLOAD_DIR)

    db = SessionLocal()
    try:
        recovered = processing_service.recover_stuck_jobs(db)
        logger.info("Startup recovery: %d job(s) recovered", recovered)
    except Exception as exc:
        # Neon Free (and other serverless DBs) may be suspended at container
        # startup. A failed recovery is non-fatal: stuck jobs will be cleaned
        # up on the next successful startup. The app still starts and serves
        # traffic; the first real request wakes the DB.
        logger.warning("Startup recovery skipped — DB unavailable at boot: %s", exc)
    finally:
        db.close()

    yield

    logger.info("Application shutdown: AI Interview Intelligence Platform API")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI Interview Intelligence Platform API",
    description=(
        "**Week 1:** Authentication, JWT\n\n"
        "**Week 2:** Interview sessions, Gemini question generation, audio uploads"
    ),
    version=_VERSION,
    # Disable all API discovery endpoints in production.
    # In development (DEBUG=True) /docs, /redoc, and /openapi.json are
    # enabled so engineers can explore and test the API interactively.
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
#
# allow_origins is environment-driven (CORS_ORIGINS, see config.py) — a
# comma-separated list of exact frontend origins, e.g.
# "http://localhost:3000,http://localhost:5173" for local development or
# "https://your-frontend-domain.com" for production. No code change is
# needed to switch between environments.
#
# allow_credentials=True is only safe paired with explicit origins —
# allow_origins=["*"] with allow_credentials=True is rejected by browsers
# (or silently strips credentials) because the spec forbids combining a
# wildcard origin with Access-Control-Allow-Credentials: true. Gating
# allow_credentials on CORS_ORIGINS being non-empty means an unconfigured
# deployment fails closed (no allowed origins, no credentialed CORS) rather
# than falling back to an insecure wildcard.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=bool(settings.CORS_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Security headers
#
# Adds Content-Security-Policy, X-Frame-Options, X-Content-Type-Options,
# Referrer-Policy, and Permissions-Policy to every response.
# Strict-Transport-Security is added only when ENVIRONMENT == "production"
# (see SecurityHeadersMiddleware) — sending HSTS over plain-HTTP local
# development would tell browsers to force HTTPS against a server that
# does not serve it.
# ---------------------------------------------------------------------------
app.add_middleware(SecurityHeadersMiddleware, settings=settings)

# ---------------------------------------------------------------------------
# Observability
#
# Assigns/propagates a request ID (header configurable via
# REQUEST_ID_HEADER), times every request, logs slow requests, and records
# Prometheus HTTP metrics. Added last so it is the outermost middleware —
# its timing covers CORS and security-header processing too.
# ---------------------------------------------------------------------------
app.add_middleware(ObservabilityMiddleware, settings=settings)

# ---------------------------------------------------------------------------
# Tracing
#
# No-op unless ENABLE_TRACING is set — see app.core.tracing.
# ---------------------------------------------------------------------------
configure_tracing(app, engine, settings)

# ---------------------------------------------------------------------------
# Global exception handling
#
# Registers handlers for AppException (and its subclasses — ResourceNotFound,
# UnauthorizedAccess, ValidationError, AIServiceError, FileValidationError),
# RequestValidationError, and a catch-all Exception handler that logs the
# full traceback and returns a generic 500. FastAPI/Starlette dispatch to the
# most specific registered handler, so existing `raise HTTPException(...)`
# call sites throughout the routers are unaffected and keep using FastAPI's
# built-in HTTPException handler.
# ---------------------------------------------------------------------------
register_exception_handlers(app)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

# auth_router has prefix="/auth"; adding API_V1_PREFIX here → /api/v1/auth/...
app.include_router(auth_router, prefix=API_V1_PREFIX)

# interviews_router already has prefix="/api/v1/interviews" — no extra prefix.
app.include_router(interviews_router)

# responses_router already has prefix="/api/v1" — no extra prefix.
app.include_router(responses_router)

# processing_router already has prefix="/api/v1" — no extra prefix.
app.include_router(processing_router)

# analytics_router already has prefix="/api/v1/analytics" — no extra prefix.
app.include_router(analytics_router)

# follow_up_router already has prefix="/api/v1/interviews" — no extra prefix.
app.include_router(follow_up_router)

# reports_router already has prefix="/api/v1/interviews" — no extra prefix.
app.include_router(reports_router)

# live_interview_router already has prefix="/api/v1/live-interviews" — no extra prefix.
app.include_router(live_interview_router)

# documents_router already has prefix="/api/v1/documents" — no extra prefix.
app.include_router(documents_router)

# prediction_router uses full /api/v1/... paths inline — no extra prefix.
app.include_router(prediction_router)

# recruiter_router already has prefix="/api/v1/recruiter" — no extra prefix.
app.include_router(recruiter_router)

# admin_router already has prefix="/api/v1/admin" — no extra prefix.
app.include_router(admin_router)

# ---------------------------------------------------------------------------
# Health check
#
# No database call — intentional. The health check must succeed even when the
# DB is temporarily unreachable (e.g. during a rolling restart). Docker Compose
# and load balancers use this endpoint to confirm the process is alive.
# A separate readiness probe (not implemented in Week 2) would test DB
# connectivity for orchestration systems that distinguish live from ready.
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"], summary="Process liveness check")
def health_check() -> dict[str, str | bool]:
    """Return process health, runtime environment, API version, and pipeline flags.

    Always returns HTTP 200. Does not query the database.
    """
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": _VERSION,
        "audio_processing_enabled": settings.ENABLE_AUDIO_PROCESSING,
    }


# ---------------------------------------------------------------------------
# Readiness check
#
# Unlike /health, this verifies the dependencies the app actually needs to
# serve traffic correctly: a reachable database, and (non-blocking) that
# the Gemini API key is configured. Orchestrators (Kubernetes, Render, ECS)
# use this to decide whether to route traffic to an instance — a process
# can be alive (/health == 200) while not yet ready (/ready == 503), e.g.
# during a transient DB outage.
#
# The DB check runs a trivial "SELECT 1" in a worker thread with a hard
# timeout (READINESS_DB_TIMEOUT_SECONDS) so a hanging connection can never
# make the readiness probe itself hang past the orchestrator's own timeout.
# ---------------------------------------------------------------------------

_readiness_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="readiness")


def _check_database() -> tuple[bool, str | None]:
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return True, None
    except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
        return False, str(exc)


@app.get("/ready", tags=["Health"], summary="Readiness check")
def readiness_check(response: Response) -> dict[str, object]:
    """Verify dependencies required to serve traffic.

    Returns HTTP 200 when ready, HTTP 503 otherwise. Checks:
      - Database connectivity (a real query, bounded by a timeout).
      - AI provider configuration presence (non-blocking — checks that
        GEMINI_API_KEY is set, does not call the Gemini API).
    """
    future = _readiness_executor.submit(_check_database)
    try:
        db_ok, db_error = future.result(timeout=settings.READINESS_DB_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        db_ok, db_error = False, "Database check timed out."

    ai_configured = bool(settings.GEMINI_API_KEY)

    checks = {
        "database": {"ok": db_ok, "error": db_error},
        "ai_provider_configured": {"ok": ai_configured},
    }
    ready = db_ok and ai_configured

    response.status_code = 200 if ready else 503
    return {"status": "ready" if ready else "not_ready", "checks": checks}


# ---------------------------------------------------------------------------
# Metrics
#
# Prometheus text-format scrape endpoint. Disabled (404) when
# ENABLE_METRICS is False, matching ObservabilityMiddleware which skips
# recording metrics in that case too.
# ---------------------------------------------------------------------------

if settings.ENABLE_METRICS:

    @app.get("/metrics", tags=["Health"], summary="Prometheus metrics")
    def metrics() -> Response:
        from app.core.metrics import render_metrics

        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)
