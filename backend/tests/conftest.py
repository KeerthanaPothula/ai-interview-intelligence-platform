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

import io
import os
import uuid

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
# UPLOAD_DIR default — tests that write files must use the upload_dir fixture
# to redirect writes to a pytest-managed tmp_path. This value is only used
# by tests that run without that fixture (none should write files).
os.environ.setdefault("UPLOAD_DIR", "uploads")

# ---------------------------------------------------------------------------
# App imports — after env vars are set
# ---------------------------------------------------------------------------
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models.analysis import AudioResponse, RESPONSE_STATUS_UPLOADED
from app.models.interview import (
    InterviewSession,
    Question,
    QUESTION_SOURCE_AI_GENERATED,
)

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


# ---------------------------------------------------------------------------
# Week 2 fixtures — upload directory isolation
# ---------------------------------------------------------------------------


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """Create an isolated upload directory and redirect UPLOAD_DIR to it.

    Every test that requests this fixture gets a unique directory under
    pytest's tmp_path (automatically cleaned up after the session). The
    monkeypatch overrides UPLOAD_DIR in the environment, and the settings
    cache is cleared so the next call to get_settings() re-reads the new
    value.

    Cache clearing order:
      1. Before yield: cache_clear() + monkeypatch.setenv → test reads new path.
      2. After yield (our teardown): cache_clear() while UPLOAD_DIR still has
         test path (monkeypatch teardown hasn't run yet).
      3. monkeypatch teardown: env var restored.
      → Next test's first get_settings() call re-reads the restored env.
    """
    ud = tmp_path / "uploads"
    ud.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(ud))
    get_settings.cache_clear()
    yield ud
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Week 2 fixtures — ORM data helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def interview_session(db, registered_user):
    """Create and return a draft InterviewSession owned by the test user.

    Uses the db fixture directly (bypasses the HTTP layer) so tests can
    pre-populate the database without going through the router. The data
    is committed and visible to the client fixture's sessions because both
    use TestingSessionLocal with StaticPool (same underlying connection).
    """
    session = InterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        title="Test Interview Session",
        job_role="Software Engineer",
        job_description=(
            "Python backend engineering role requiring FastAPI, SQLAlchemy, "
            "and experience with async systems and REST API design."
        ),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@pytest.fixture
def interview_question(db, interview_session):
    """Create and return a Question linked to interview_session (sequence_order=1)."""
    question = Question(
        session_id=interview_session.id,
        body="Tell me about yourself.",
        sequence_order=1,
        category="behavioral",
        source=QUESTION_SOURCE_AI_GENERATED,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@pytest.fixture
def audio_response(db, interview_session, interview_question, registered_user):
    """Create and return an AudioResponse with status='uploaded'.

    file_path uses a realistic relative path matching the save_file() format.
    No file is written to disk — the DB row is created directly.
    """
    response_id = uuid.uuid4()
    response = AudioResponse(
        id=response_id,
        session_id=interview_session.id,
        question_id=interview_question.id,
        user_id=uuid.UUID(registered_user["id"]),
        file_path=f"{interview_session.id}/{response_id}.webm",
        file_size_bytes=4096,
        mime_type="audio/webm",
        status=RESPONSE_STATUS_UPLOADED,
    )
    db.add(response)
    db.commit()
    db.refresh(response)
    return response


# ---------------------------------------------------------------------------
# Week 2 fixtures — upload helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_audio_file():
    """Return a BytesIO of 4096 bytes — above the 1024-byte minimum.

    Use in upload tests as the file body:
        files={"file": ("test.webm", fake_audio_file, "audio/webm")}

    Function-scoped: each test gets a fresh BytesIO with the cursor at 0.
    """
    return io.BytesIO(b"x" * 4096)


# ---------------------------------------------------------------------------
# Week 2 fixtures — Gemini mock
# ---------------------------------------------------------------------------

_MOCK_QUESTIONS = [
    {
        "body": "Tell me about yourself.",
        "category": "behavioral",
        "sequence_order": 1,
    },
    {
        "body": "Describe a challenging technical problem you solved.",
        "category": "technical",
        "sequence_order": 2,
    },
    {
        "body": "How would you handle a disagreement with a teammate?",
        "category": "situational",
        "sequence_order": 3,
    },
    {
        "body": "What is your greatest professional achievement?",
        "category": "behavioral",
        "sequence_order": 4,
    },
    {
        "body": "Explain the difference between REST and GraphQL.",
        "category": "technical",
        "sequence_order": 5,
    },
    {
        "body": "How would you prioritize competing deadlines under pressure?",
        "category": "situational",
        "sequence_order": 6,
    },
]


@pytest.fixture
def mock_gemini_questions(monkeypatch):
    """Prevent real Gemini API calls by patching generate_questions.

    Why patch app.services.question_service.generate_questions (not gemini_service):
        question_service.py does `from app.services.gemini_service import generate_questions`,
        creating a local name binding in question_service's namespace. Patching
        gemini_service.generate_questions after import has no effect on that
        local reference. The correct patch target is the name as it exists in
        question_service's own namespace.

    Returns the list of mock question dicts so tests can assert on content.
    """
    monkeypatch.setattr(
        "app.services.question_service.generate_questions",
        lambda job_role, job_description, count: _MOCK_QUESTIONS[:count],
    )
    return _MOCK_QUESTIONS
