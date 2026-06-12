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
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import SessionLocal
from app.routers.auth import router as auth_router
from app.routers.interviews import router as interviews_router
from app.routers.processing import router as processing_router
from app.routers.responses import router as responses_router
from app.services import processing_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings — loaded once at startup via @lru_cache.
# If any required env var is missing or invalid, pydantic raises ValidationError
# here — the process exits immediately rather than serving broken requests.
# ---------------------------------------------------------------------------
settings = get_settings()

_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Lifespan — startup recovery
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
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = SessionLocal()
    try:
        recovered = processing_service.recover_stuck_jobs(db)
    finally:
        db.close()
    logger.info("Startup recovery: %d job(s) recovered", recovered)
    yield


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
# Week 2: wildcard origins allow the frontend dev server (any port) and
# Postman/curl to call the API without CORS preflight failures.
#
# Week 5: replace allow_origins=["*"] with the specific frontend domain
# (e.g. ["https://app.example.com"]) before production deployment.
# Wildcard origins with allow_credentials=True is accepted by browsers only
# when the server's response does NOT include Access-Control-Allow-Credentials;
# many browsers silently drop credentials in that case — revisit before launch.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

# auth_router has prefix="/auth"; adding "/api/v1" here → /api/v1/auth/...
app.include_router(auth_router, prefix="/api/v1")

# interviews_router already has prefix="/api/v1/interviews" — no extra prefix.
app.include_router(interviews_router)

# responses_router already has prefix="/api/v1" — no extra prefix.
app.include_router(responses_router)

# processing_router already has prefix="/api/v1" — no extra prefix.
app.include_router(processing_router)

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
