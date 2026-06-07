from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth

settings = get_settings()

app = FastAPI(
    title="AI Interview Intelligence Platform",
    description="Backend API for recording, transcribing, and evaluating interviews.",
    version="1.0.0",
    # Disable interactive docs in production so internal API structure
    # is not publicly browsable.
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ---------------------------------------------------------------------------
# CORS
# Allow the React dev server (port 5173) to call the API.
# In production this list should be restricted to the actual frontend domain.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# All routes live under /api/v1 so the path prefix is clear and versioning
# is baked in from day one.
# ---------------------------------------------------------------------------
app.include_router(auth.router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Health check
# Used by Docker Compose and any future load balancer to confirm the process
# is alive. Returns immediately with no database call — intentional, so that
# the check does not fail when the DB is temporarily unreachable.
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
