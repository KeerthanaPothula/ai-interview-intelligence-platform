"""Tests for the Phase 3 SecurityHeadersMiddleware (app/core/security_headers.py)."""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient as StarletteTestClient

from app.config import Settings
from app.core.security_headers import SecurityHeadersMiddleware


def _build_app(environment: str) -> Starlette:
    """Build a minimal throwaway Starlette app with the middleware attached.

    The real `app` (app.main) captures its Settings object once at module
    import time, before ENVIRONMENT is forced to "development" by
    conftest.py — that object never changes for the life of the test
    session, so the production (HSTS-enabled) branch cannot be exercised
    through the shared `client` fixture. Building an isolated app per test
    with a fresh Settings object lets both branches be tested directly.
    """

    async def homepage(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    settings = Settings(
        DATABASE_URL="sqlite://",
        JWT_SECRET_KEY="x" * 32,
        GEMINI_API_KEY="test-key",
        ENVIRONMENT=environment,
        DEBUG=(environment != "production"),
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    return app


class TestSecurityHeadersMiddleware:
    def test_standard_headers_present_in_development(self):
        app = _build_app("development")
        with StarletteTestClient(app) as c:
            response = c.get("/")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in response.headers
        assert "Permissions-Policy" in response.headers

    def test_hsts_absent_in_development(self):
        app = _build_app("development")
        with StarletteTestClient(app) as c:
            response = c.get("/")

        assert "Strict-Transport-Security" not in response.headers

    def test_hsts_present_in_production(self):
        app = _build_app("production")
        with StarletteTestClient(app) as c:
            response = c.get("/")

        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=" in hsts
        assert "includeSubDomains" in hsts

    def test_standard_headers_also_present_in_production(self):
        app = _build_app("production")
        with StarletteTestClient(app) as c:
            response = c.get("/")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


def test_real_app_includes_security_headers(client):
    """Smoke test against the actual app/main.py wiring."""
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in response.headers
    assert "Permissions-Policy" in response.headers
