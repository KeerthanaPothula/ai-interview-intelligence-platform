"""
Test configuration and shared fixtures.

All required environment variables are set at the top of this file,
BEFORE any app modules are imported. This is critical because config.py
uses @lru_cache — the Settings object is built on first import and cached
for the lifetime of the test session. Setting os.environ after that point
has no effect.

The test suite uses an in-memory SQLite database so it runs without Docker
or a running PostgreSQL instance. The trade-off is that PostgreSQL-specific
features (e.g. UUID column type at the DB level, full-text search) are not
exercised. That is acceptable for unit/integration tests of the API layer.
"""

import os

# ---------------------------------------------------------------------------
# Required settings — must be set before any `from app...` import
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite://")  # in-memory, wiped per session
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long"
)
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key-not-real")
os.environ.setdefault("WHISPER_MODEL", "base")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "true")

# ---------------------------------------------------------------------------
# App imports — after env vars are set
# ---------------------------------------------------------------------------
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# Test engine — SQLite in memory, shared across connections within a test
# ---------------------------------------------------------------------------
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    # StaticPool ensures every call to connect() returns the same underlying
    # connection. Without this, SQLite creates a new in-memory database for
    # each connection, so the tables created in setup are invisible to the
    # session used by the route handler.
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=TEST_ENGINE,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest.fixture(scope="function", autouse=True)
def reset_database():
    """
    Create all tables before each test and drop them after.
    scope="function" means every test starts with a clean database.
    autouse=True means this runs for every test without needing to
    explicitly request it.
    """
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture(scope="function")
def db():
    """Yield a SQLAlchemy session connected to the test database."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client():
    """
    Yield a FastAPI TestClient with get_db overridden to use the test DB.

    The override is cleared after each test so tests are fully isolated.
    """

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Reusable helpers
# ---------------------------------------------------------------------------

VALID_USER = {
    "email": "alice@example.com",
    "password": "securepassword1",
    "full_name": "Alice Example",
}


@pytest.fixture
def registered_user(client):
    """Register a user and return the response JSON."""
    response = client.post("/api/v1/auth/register", json=VALID_USER)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def auth_token(client, registered_user):
    """Return a valid Bearer token for the registered test user."""
    response = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """Return Authorization headers dict for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}
