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
import json
import os
import uuid
from decimal import Decimal

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
# Disable the Week 3 pipeline globally. Without this, app.main's module-level
# `settings = get_settings()` (read at `from app.main import app` below) and
# every request-time `get_settings()` call in upload_audio/trigger_processing
# would default ENABLE_AUDIO_PROCESSING=True (config.py default) — every
# response upload in every test would enqueue a real BackgroundTask calling
# process_response(), which loads the real Whisper model and calls the real
# Gemini API. Setting this BEFORE `from app.main import app` ensures the
# first get_settings() call (and therefore the @lru_cache'd value used for
# the lifetime of the test session, absent cache_clear()) sees "false".
# Individual tests opt back in via the processing_enabled fixture.
os.environ.setdefault("ENABLE_AUDIO_PROCESSING", "false")

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
from app.models.analysis import (
    AudioResponse,
    InterviewAnalysis,
    RESPONSE_STATUS_UPLOADED,
    Transcript,
)
from app.models.interview import (
    InterviewSession,
    Question,
    QUESTION_SOURCE_AI_GENERATED,
)
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User

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


@pytest.fixture(scope="function", autouse=True)
def _patch_processing_session_local(monkeypatch):
    """Redirect processing_service's internal SessionLocal() calls to the test DB.

    processing_service.py does `from app.database import SessionLocal` and
    calls `SessionLocal()` directly inside _claim_and_load_context,
    _mark_failed, and Transactions 2/3 — these calls bypass the get_db
    dependency that the `client` fixture overrides. app.database.SessionLocal
    is bound to app.database.engine, a `sqlite://` in-memory database that is
    separate from conftest's TEST_ENGINE (different Engine = different
    in-memory SQLite database) and on which Base.metadata.create_all() is
    never called — every table is missing.

    Patching the name as it exists in processing_service's own namespace
    (the local binding created by `from app.database import SessionLocal`)
    redirects every SessionLocal() call inside processing_service to
    TestingSessionLocal/TEST_ENGINE — the same database the `db` and
    `client` fixtures use, with tables created by reset_database above.

    autouse=True: every test gets this patch, including tests that never
    call processing_service — for those it is a no-op (an unused module
    attribute is swapped and restored by monkeypatch's teardown).
    """
    monkeypatch.setattr(
        "app.services.processing_service.SessionLocal", TestingSessionLocal
    )


@pytest.fixture(scope="function", autouse=True)
def _reset_login_rate_limiter():
    """Clear the in-memory login rate limiter's hit counts between tests.

    login_rate_limiter (app/core/rate_limit.py) is a module-level singleton
    shared by every request in the process. Without resetting it, login
    attempts accumulated by earlier tests (via the auth_token/registered_user
    fixtures used throughout the suite) would count toward later tests'
    RATE_LIMIT_LOGIN_ATTEMPTS budget, eventually causing unrelated tests to
    fail with 429 instead of their expected status code.
    """
    from app.core.rate_limit import login_rate_limiter

    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


@pytest.fixture(scope="function", autouse=True)
def _patch_main_session_local(monkeypatch):
    """Redirect app.main's startup recovery to the test DB.

    app.main.py does `from app.database import SessionLocal` and its
    lifespan handler calls SessionLocal() directly to run
    processing_service.recover_stuck_jobs() once at startup, bypassing
    get_db() entirely — the same pattern processing_service itself uses
    (see _patch_processing_session_local above), and for the same reason:
    app.database.SessionLocal is bound to app.database.engine, a separate,
    tableless in-memory SQLite database from conftest's TEST_ENGINE.

    The lifespan handler runs on every `with TestClient(app) as c:` — i.e.
    every test that requests the `client` fixture, not just tests that
    exercise the processing pipeline. Without this patch,
    recover_stuck_jobs(db) would query app.database.engine's tableless
    database and every such test would fail at TestClient startup with
    OperationalError: no such table: audio_responses.

    Patching the name as it exists in app.main's own namespace redirects
    that call to TestingSessionLocal/TEST_ENGINE, where reset_database has
    already created all tables.

    autouse=True: every test gets this patch, including tests that never
    use the `client` fixture — for those it is a no-op.
    """
    monkeypatch.setattr("app.main.SessionLocal", TestingSessionLocal)


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
# RBAC / multi-tenant fixtures
#
# Every non-candidate role is created the same way real role assignment
# happens in production: register (always CANDIDATE — see
# auth_service.register_user) then promote directly via the `db` fixture,
# never through a public self-service endpoint (none exists for anything
# but CANDIDATE). Logging in afterward mints a token reflecting whatever
# role is in the database *at login time* — get_current_user re-reads the
# DB on every request regardless, so this matches production behavior
# exactly rather than being a testing shortcut.
# ---------------------------------------------------------------------------

OTHER_USER = {
    "email": "bob@example.com",
    "password": "securepassword2",
    "full_name": "Bob Example",
}

RECRUITER_USER = {
    "email": "recruiter@example.com",
    "password": "securepassword3",
    "full_name": "Rita Recruiter",
}

OTHER_ORG_RECRUITER_USER = {
    "email": "other-org-recruiter@example.com",
    "password": "securepassword3b",
    "full_name": "Rex Recruiter",
}

ADMIN_USER = {
    "email": "admin@example.com",
    "password": "securepassword4",
    "full_name": "Adam Admin",
}

SUPER_ADMIN_USER = {
    "email": "superadmin@example.com",
    "password": "securepassword5",
    "full_name": "Sam SuperAdmin",
}

ORG_CANDIDATE_USER = {
    "email": "org-candidate@example.com",
    "password": "securepassword6",
    "full_name": "Cara Candidate",
}


def _login(client, user_data: dict) -> str:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": user_data["email"], "password": user_data["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _register_with_role(
    client,
    db,
    user_data: dict,
    *,
    role: str = Role.CANDIDATE.value,
    organization_id: uuid.UUID | None = None,
) -> dict:
    response = client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201, response.text
    user_json = response.json()

    if role != Role.CANDIDATE.value or organization_id is not None:
        user = db.get(User, uuid.UUID(user_json["id"]))
        user.role = role
        user.organization_id = organization_id
        db.commit()
        db.refresh(user)

    return user_json


@pytest.fixture
def organization(db):
    """A tenant organization, e.g. for a recruiter/candidate pair."""
    org = Organization(name="Acme Corp")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def other_organization(db):
    """A second, distinct organization — for cross-org isolation tests."""
    org = Organization(name="Globex Corp")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def recruiter_user(client, db, organization):
    """A RECRUITER account belonging to `organization`."""
    return _register_with_role(
        client,
        db,
        RECRUITER_USER,
        role=Role.RECRUITER.value,
        organization_id=organization.id,
    )


@pytest.fixture
def recruiter_token(client, recruiter_user):
    return _login(client, RECRUITER_USER)


@pytest.fixture
def recruiter_headers(recruiter_token):
    return {"Authorization": f"Bearer {recruiter_token}"}


@pytest.fixture
def other_org_recruiter_user(client, db, other_organization):
    """A RECRUITER account belonging to `other_organization` — used to
    prove a recruiter cannot see or act on another organization's
    candidates."""
    return _register_with_role(
        client,
        db,
        OTHER_ORG_RECRUITER_USER,
        role=Role.RECRUITER.value,
        organization_id=other_organization.id,
    )


@pytest.fixture
def other_org_recruiter_headers(client, other_org_recruiter_user):
    token = _login(client, OTHER_ORG_RECRUITER_USER)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def org_candidate(client, db, organization):
    """A CANDIDATE account belonging to `organization` — an "invited"
    candidate, as opposed to VALID_USER/registered_user, who is always
    unaffiliated (organization_id=None)."""
    return _register_with_role(
        client,
        db,
        ORG_CANDIDATE_USER,
        role=Role.CANDIDATE.value,
        organization_id=organization.id,
    )


@pytest.fixture
def admin_user(client, db):
    return _register_with_role(client, db, ADMIN_USER, role=Role.ADMIN.value)


@pytest.fixture
def admin_token(client, admin_user):
    return _login(client, ADMIN_USER)


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def super_admin_user(client, db):
    return _register_with_role(
        client, db, SUPER_ADMIN_USER, role=Role.SUPER_ADMIN.value
    )


@pytest.fixture
def super_admin_token(client, super_admin_user):
    return _login(client, SUPER_ADMIN_USER)


@pytest.fixture
def super_admin_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}"}


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

    Prefixed with the WebM/Matroska EBML magic bytes (0x1A45DFA3) so the
    Phase 3 magic-byte check in upload_service.validate_upload accepts it
    when declared as audio/webm (the MIME type used by every test that
    relies on this fixture).

    Use in upload tests as the file body:
        files={"file": ("test.webm", fake_audio_file, "audio/webm")}

    Function-scoped: each test gets a fresh BytesIO with the cursor at 0.
    """
    return io.BytesIO(b"\x1a\x45\xdf\xa3" + b"x" * 4092)


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


# ---------------------------------------------------------------------------
# Week 3 fixtures — processing toggle, transcript/analysis data, AI mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def processing_enabled():
    """Temporarily enable the Week 3 pipeline for one test.

    conftest.py sets ENABLE_AUDIO_PROCESSING=false globally (see top of
    file) so that uploads never enqueue real Whisper/Gemini calls. Tests
    that exercise the enqueue path (upload_audio's BackgroundTask, or
    POST /responses/{id}/process returning something other than 503) request
    this fixture to flip the gate to "true" for the duration of the test.

    Saves the current ENABLE_AUDIO_PROCESSING value, sets it to "true", and
    clears the get_settings() cache so the next get_settings() call (made
    per-request by upload_audio/trigger_processing) observes "true". After
    the test, the previous value is restored and the cache is cleared again
    so subsequent tests see the original ("false") value.
    """
    previous = os.environ.get("ENABLE_AUDIO_PROCESSING")
    os.environ["ENABLE_AUDIO_PROCESSING"] = "true"
    get_settings.cache_clear()
    yield
    if previous is None:
        os.environ.pop("ENABLE_AUDIO_PROCESSING", None)
    else:
        os.environ["ENABLE_AUDIO_PROCESSING"] = previous
    get_settings.cache_clear()


@pytest.fixture
def transcript(db, audio_response):
    """Create and return a Transcript row attached to audio_response.

    Pre-generates the row's id (matching the pattern used by
    processing_service, which generates transcript_id before INSERT) and
    uses realistic Whisper-shaped values: English text, a BCP-47 language
    code, and word_count computed the same way transcription_service does
    (len(text.split())) so the row is internally consistent.
    """
    text = (
        "I have about five years of experience building backend services "
        "with Python and FastAPI, focusing on REST API design, database "
        "schema design, and integrating third-party AI services."
    )
    transcript = Transcript(
        id=uuid.uuid4(),
        audio_response_id=audio_response.id,
        text=text,
        language="en",
        duration_seconds=42,
        word_count=len(text.split()),
    )
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    return transcript


@pytest.fixture
def interview_analysis(db, audio_response, transcript):
    """Create and return an InterviewAnalysis row attached to audio_response
    and transcript.

    Pre-generates the row's id (matching the pattern used by
    processing_service, which generates analysis_id before INSERT). Scores
    use Decimal values constructed from string literals — the same pattern
    evaluation_service uses (Decimal(str(rounded_float))) to avoid IEEE 754
    imprecision entering the NUMERIC(4,1) columns. strengths/weaknesses are
    stored as JSON-encoded text, matching generate_evaluation's storage
    format (json.dumps(list[str])).
    """
    analysis = InterviewAnalysis(
        id=uuid.uuid4(),
        audio_response_id=audio_response.id,
        transcript_id=transcript.id,
        overall_score=Decimal("7.5"),
        communication_score=Decimal("8.0"),
        technical_score=Decimal("7.0"),
        problem_solving_score=Decimal("6.5"),
        confidence_score=Decimal("8.5"),
        strengths=json.dumps(["Clear structure", "Relevant technical examples"]),
        weaknesses=json.dumps(["Could elaborate on trade-offs"]),
        detailed_feedback=(
            "The candidate demonstrated solid backend experience with clear "
            "communication and relevant technical examples, though some "
            "answers could go deeper on trade-offs."
        ),
        model_used="gemini-2.0-flash",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@pytest.fixture
def mock_transcription(monkeypatch):
    """Prevent real Whisper calls by patching transcribe_audio.

    processing_service.py does `from app.services import transcription_service`
    and calls `transcription_service.transcribe_audio(file_path)` — a
    module-attribute access at call time, so patching
    app.services.transcription_service.transcribe_audio directly (rather
    than a name imported into processing_service's namespace) is sufficient,
    unlike the gemini_service/question_service case documented on
    mock_gemini_questions.

    Returns the mock result dict so tests can assert against it.
    """
    result = {
        "text": "I have about five years of experience building backend services.",
        "language": "en",
        "duration_seconds": 42,
        "word_count": 120,
    }
    monkeypatch.setattr(
        "app.services.transcription_service.transcribe_audio",
        lambda file_path: result,
    )
    return result


@pytest.fixture
def mock_evaluation(monkeypatch):
    """Prevent real Gemini calls by patching generate_evaluation.

    processing_service.py does `from app.services import evaluation_service`
    and calls `evaluation_service.generate_evaluation(...)` — a
    module-attribute access at call time, so patching
    app.services.evaluation_service.generate_evaluation directly is
    sufficient (same reasoning as mock_transcription above).

    Returns realistic scores matching the shape of
    evaluation_service.generate_evaluation's return value: floats already
    rounded to one decimal place (processing_service converts these to
    Decimal(str(v)) before INSERT), and JSON-encoded strengths/weaknesses.
    """
    result = {
        "overall_score": 7.5,
        "communication_score": 8.0,
        "technical_score": 7.0,
        "problem_solving_score": 6.5,
        "confidence_score": 8.5,
        "strengths": json.dumps(["Clear structure", "Relevant technical examples"]),
        "weaknesses": json.dumps(["Could elaborate on trade-offs"]),
        "detailed_feedback": (
            "The candidate demonstrated solid backend experience with clear "
            "communication and relevant technical examples."
        ),
        "model_used": "gemini-2.0-flash",
    }
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation",
        lambda **kwargs: result,
    )
    return result
