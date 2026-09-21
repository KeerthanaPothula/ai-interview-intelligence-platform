"""Application-level request body size limits (app/core/body_limit.py).

Background: Starlette does not bound urlencoded bodies (PYSEC-2026-249) and FastAPI
parses the body before authentication/rate limiting run, so the app enforces its
own caps — small for ordinary requests, the existing per-file caps for the two
upload routes only.
"""

import asyncio
import io
import json

import pytest
from fastapi import params
from fastapi.routing import APIRoute

from app.config import get_settings
from app.core import body_limit
from app.core.body_limit import (
    TOO_LARGE_DETAIL,
    UPLOAD_ROUTES,
    RequestBodyLimitMiddleware,
    body_limit_bytes,
)
from app.main import app
from app.schemas.conversation import StartLiveInterviewRequest
from app.schemas.interview import SessionCreate
from tests.conftest import VALID_USER
from tests.test_uploads import _upload

KB = 1024
MB = 1024 * 1024
LOGIN = "/api/v1/auth/login"
AUDIO_UPLOAD = "/api/v1/interviews/{}/responses"
RESUME_UPLOAD = "/api/v1/documents/resume/upload"
TOO_LARGE = {"detail": TOO_LARGE_DETAIL}


@pytest.fixture
def limits(monkeypatch):
    """Set body-limit env vars for one test (Settings is lru_cached)."""

    def _set(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


def _login_form(password: str, username: str = "nobody@example.com") -> dict:
    return {"username": username, "password": password}


# ---------------------------------------------------------------------------
# Login (urlencoded form) — the endpoint PYSEC-2026-249 is about
# ---------------------------------------------------------------------------


def test_login_below_the_limit_is_processed_normally(client, registered_user, limits):
    limits(MAX_FORM_BODY_KB=1)

    wrong = client.post(LOGIN, data=_login_form("wrong-password-1"))
    right = client.post(
        LOGIN,
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )

    assert wrong.status_code == 401  # reached the handler
    assert right.status_code == 200
    assert "access_token" in right.json()


def test_login_above_the_limit_gets_413(client, limits):
    limits(MAX_FORM_BODY_KB=1)

    response = client.post(LOGIN, data=_login_form("x" * (2 * KB)))

    assert response.status_code == 413
    assert response.json() == TOO_LARGE
    # nothing internal leaks: no paths, no exception text
    assert "Traceback" not in response.text and ".py" not in response.text


def test_many_tiny_fields_are_rejected_before_parsing(client, limits):
    """The PYSEC-2026-249 shape: thousands of fields in a small-looking body."""
    limits(MAX_FORM_BODY_KB=16)
    body = ("a&" * (100 * KB)).encode()  # ~200 KiB, ~100k fields

    response = client.post(
        LOGIN,
        content=body,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 413


def test_urlencoded_limit_is_tighter_than_the_json_limit(client, auth_headers, limits):
    limits(MAX_FORM_BODY_KB=1, MAX_REQUEST_BODY_KB=64)
    payload = "y" * (2 * KB)

    form = client.post(LOGIN, data=_login_form(payload))
    ordinary = client.post(
        "/api/v1/interviews/",
        json={"title": "t", "job_role": "r", "job_description": payload},
        headers=auth_headers,
    )

    assert form.status_code == 413
    assert ordinary.status_code == 201  # same size, JSON tier: allowed


# ---------------------------------------------------------------------------
# Ordinary JSON API requests
# ---------------------------------------------------------------------------


def test_json_request_above_the_limit_gets_413(client, auth_headers, limits):
    limits(MAX_REQUEST_BODY_KB=1)

    response = client.post(
        "/api/v1/interviews/",
        json={"title": "t", "job_role": "r", "job_description": "d" * (2 * KB)},
        headers=auth_headers,
    )

    assert response.status_code == 413
    assert response.json() == TOO_LARGE


def test_json_request_below_the_limit_still_works(client, auth_headers, limits):
    limits(MAX_REQUEST_BODY_KB=1)

    response = client.post(
        "/api/v1/interviews/",
        json={
            "title": "Interview",
            "job_role": "Engineer",
            "job_description": "A job description that is long enough to be valid.",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201


def test_413_is_returned_before_authentication_is_checked(client, limits):
    """The point of a pre-parse limit: an unauthenticated client cannot make the
    server parse a large body just to be told 401."""
    limits(MAX_REQUEST_BODY_KB=1)

    response = client.post("/api/v1/interviews/", json={"x": "y" * (2 * KB)})

    assert response.status_code == 413


def test_default_limits_fit_every_legitimate_body():
    """If a schema cap is raised, this fails and the limit must be raised too."""
    settings = get_settings()

    def max_len(model, field):
        return next(
            m.max_length
            for m in model.model_fields[field].metadata
            if hasattr(m, "max_length")
        )

    # Worst case: every character 4 bytes in UTF-8, as the browser sends JSON.
    session = 4 * sum(
        max_len(SessionCreate, f) for f in ("title", "job_role", "job_description")
    )
    live = 4 * (
        max_len(StartLiveInterviewRequest, "job_role")
        + max_len(StartLiveInterviewRequest, "job_description")
    )

    assert settings.MAX_REQUEST_BODY_KB * KB >= 4 * max(session, live)
    assert settings.MAX_FORM_BODY_KB * KB >= 4 * len(
        b"username=" + b"e" * 254 + b"&password=" + b"p" * 128
    )


# ---------------------------------------------------------------------------
# Uploads keep working, under their own limits
# ---------------------------------------------------------------------------


def test_audio_upload_within_its_limit_works_despite_a_tiny_default(
    client, auth_headers, interview_session, interview_question, upload_dir, limits
):
    limits(MAX_REQUEST_BODY_KB=1, MAX_FORM_BODY_KB=1)  # far below the 4 KiB file

    response = _upload(
        client, auth_headers, interview_session.id, interview_question.id
    )

    assert response.status_code == 201, response.text


def test_resume_upload_within_its_limit_works_despite_a_tiny_default(
    client, auth_headers, upload_dir, limits, monkeypatch
):
    limits(MAX_REQUEST_BODY_KB=1, MAX_FORM_BODY_KB=1)
    monkeypatch.setattr(
        "app.routers.documents.document_extraction_service.extract_text",
        lambda path, mime: "Python FastAPI engineer.",
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.chunk_text", lambda t, **k: [t]
    )
    monkeypatch.setattr("app.routers.documents.rag_service.store_chunks", lambda **k: 1)
    pdf = io.BytesIO(b"%PDF-1.4 " + b"x" * (64 * KB))

    response = client.post(
        RESUME_UPLOAD,
        files={"file": ("resume.pdf", pdf, "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text


def test_audio_file_just_over_its_cap_still_gets_the_endpoints_own_413(
    client, auth_headers, interview_session, interview_question, upload_dir, limits
):
    """Within the multipart-overhead allowance, the endpoint (not the middleware)
    answers, with its precise message — existing behaviour is preserved."""
    limits(MAX_UPLOAD_SIZE_MB=1)
    content = io.BytesIO(b"\x1a\x45\xdf\xa3" + b"x" * (MB + 200 * KB))

    response = _upload(
        client,
        auth_headers,
        interview_session.id,
        interview_question.id,
        file_content=content,
    )

    assert response.status_code == 413
    assert "exceeds the maximum" in response.json()["detail"]


def test_audio_upload_far_over_its_cap_is_rejected_by_the_middleware(
    client, auth_headers, interview_session, interview_question, upload_dir, limits
):
    limits(MAX_UPLOAD_SIZE_MB=1)
    content = io.BytesIO(b"\x1a\x45\xdf\xa3" + b"x" * (3 * MB))

    response = _upload(
        client,
        auth_headers,
        interview_session.id,
        interview_question.id,
        file_content=content,
    )

    assert response.status_code == 413
    assert response.json() == TOO_LARGE


def test_resume_over_its_cap_is_rejected_both_near_and_far(
    client, auth_headers, upload_dir, limits
):
    limits(MAX_RESUME_UPLOAD_SIZE_MB=1)

    def post(size):
        return client.post(
            RESUME_UPLOAD,
            files={
                "file": (
                    "r.pdf",
                    io.BytesIO(b"%PDF-1.4 " + b"x" * size),
                    "application/pdf",
                )
            },
            headers=auth_headers,
        )

    near = post(MB + 200 * KB)
    far = post(3 * MB)

    assert near.status_code == far.status_code == 413
    assert "File too large" in near.json()["detail"]  # the endpoint's own message
    assert far.json() == TOO_LARGE


def test_the_upload_allowance_is_not_available_to_other_endpoints(client, limits):
    """A multipart body to the login route gets the ordinary limit, not the 50 MB
    upload one — and a urlencoded body to an upload route gets the form limit."""
    limits(MAX_REQUEST_BODY_KB=1, MAX_FORM_BODY_KB=1)

    multipart_login = client.post(
        LOGIN,
        files={
            "file": ("f.bin", io.BytesIO(b"x" * (8 * KB)), "application/octet-stream")
        },
    )
    urlencoded_upload = client.post(RESUME_UPLOAD, data={"junk": "j" * (8 * KB)})

    assert multipart_login.status_code == 413
    assert urlencoded_upload.status_code == 413


# ---------------------------------------------------------------------------
# No Content-Length (chunked): counted as it streams
# ---------------------------------------------------------------------------


def _chunks(total_kib: int, prefix: bytes = b"username=a%40b.com&password="):
    yield prefix
    for _ in range(total_kib):
        yield b"x" * KB


def test_chunked_body_without_content_length_is_limited_too(client, limits):
    limits(MAX_FORM_BODY_KB=2)

    response = client.post(
        LOGIN,
        content=_chunks(8),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 413  # not 400: FastAPI must not mask it
    assert response.json() == TOO_LARGE


def test_chunked_body_under_the_limit_is_processed(client, limits):
    limits(MAX_FORM_BODY_KB=8)

    response = client.post(
        LOGIN,
        content=_chunks(1),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 401  # reached the login handler


# ---------------------------------------------------------------------------
# Memory: an oversized body is never read in full (ASGI-level)
# ---------------------------------------------------------------------------


def _run_middleware(headers, chunks, limit_kb=4):
    """Drive the middleware with a fake ASGI server; return (status, chunks_read, app_called)."""
    state = {"read": 0, "app_called": False, "status": None}
    queue = list(chunks)

    async def receive():
        if not queue:
            return {"type": "http.request", "body": b"", "more_body": False}
        state["read"] += 1
        return {"type": "http.request", "body": queue.pop(0), "more_body": bool(queue)}

    async def send(message):
        if message["type"] == "http.response.start":
            state["status"] = message["status"]

    async def inner(scope, receive, send):
        state["app_called"] = True
        try:
            while (await receive()).get("more_body"):
                pass
            await send({"type": "http.response.start", "status": 200, "headers": []})
        except Exception:  # an HTTPException from the limited receive
            await send({"type": "http.response.start", "status": 413, "headers": []})

    scope = {"type": "http", "method": "POST", "path": "/x", "headers": headers}
    settings = get_settings()
    original = settings.MAX_REQUEST_BODY_KB
    object.__setattr__(settings, "MAX_REQUEST_BODY_KB", limit_kb)
    try:
        asyncio.run(RequestBodyLimitMiddleware(inner)(scope, receive, send))
    finally:
        object.__setattr__(settings, "MAX_REQUEST_BODY_KB", original)
    return state["status"], state["read"], state["app_called"]


def test_declared_oversize_is_rejected_without_reading_or_calling_the_app():
    headers = [
        (b"content-length", str(50 * MB).encode()),
        (b"content-type", b"application/json"),
    ]

    status, read, app_called = _run_middleware(headers, [b"x" * KB] * 1000)

    assert (status, read, app_called) == (413, 0, False)


def test_streamed_oversize_stops_reading_shortly_after_the_limit():
    headers = [(b"content-type", b"application/json")]  # no content-length

    status, read, _ = _run_middleware(headers, [b"x" * KB] * 1000, limit_kb=4)

    assert status == 413
    assert (
        read <= 5
    )  # 4 KiB limit / 1 KiB chunks, plus the chunk that crossed it — not 1000


def test_understated_content_length_cannot_bypass_the_limit():
    headers = [(b"content-length", b"10"), (b"content-type", b"application/json")]

    status, read, _ = _run_middleware(headers, [b"x" * KB] * 1000, limit_kb=4)

    assert status == 413 and read <= 5


# ---------------------------------------------------------------------------
# Unchanged behaviour: headers, CORS, health, rate limiting
# ---------------------------------------------------------------------------


def test_413_responses_carry_cors_security_and_request_id_headers(client, limits):
    limits(MAX_FORM_BODY_KB=1)

    response = client.post(
        LOGIN,
        data=_login_form("x" * (2 * KB)),
        headers={"Origin": "http://localhost:5173", "X-Request-ID": "trace-me-123"},
    )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"] == "trace-me-123"


def test_health_and_readiness_are_unaffected_by_tiny_limits(client, limits):
    limits(MAX_REQUEST_BODY_KB=1, MAX_FORM_BODY_KB=1)

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_rate_limiting_still_applies_to_in_limit_login_attempts(client, limits):
    limits(MAX_FORM_BODY_KB=1)

    codes = [
        client.post(LOGIN, data=_login_form("wrong-password")).status_code
        for _ in range(8)
    ]

    assert codes[0] == 401
    assert 429 in codes


def test_settings_defaults_and_validation(monkeypatch):
    settings = get_settings()
    assert (settings.MAX_REQUEST_BODY_KB, settings.MAX_FORM_BODY_KB) == (256, 16)
    monkeypatch.setenv("MAX_FORM_BODY_KB", "0")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError):
            get_settings()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Structural guards
# ---------------------------------------------------------------------------


def _file_routes():
    for route in app.routes:
        if isinstance(route, APIRoute) and any(
            isinstance(p.field_info, params.File) for p in route.dependant.body_params
        ):
            yield route


def test_every_route_that_accepts_a_file_is_registered_as_an_upload_route():
    """A new upload endpoint that is not in UPLOAD_ROUTES would be capped at the
    small default limit (fail-safe), but this test forces the omission to be seen."""
    routes = list(_file_routes())
    assert len(routes) == len(UPLOAD_ROUTES) == 2
    for route in routes:
        concrete = route.path.replace("{session_id}", "abc")
        assert any(
            method in route.methods and pattern.match(concrete)
            for method, pattern, _ in UPLOAD_ROUTES
        ), f"{route.path} accepts a file but is not in body_limit.UPLOAD_ROUTES"


def test_upload_routes_point_at_real_settings_and_routes():
    settings = get_settings()
    for _, _, setting in UPLOAD_ROUTES:
        assert getattr(settings, setting) > 0
    paths = {r.path for r in _file_routes()}
    assert paths == {
        "/api/v1/interviews/{session_id}/responses",
        "/api/v1/documents/resume/upload",
    }


def test_limit_selection_by_content_type_and_route():
    s = get_settings()
    audio = AUDIO_UPLOAD.format("some-id")

    assert (
        body_limit_bytes("POST", audio, "multipart/form-data; boundary=x", s)
        == s.MAX_UPLOAD_SIZE_MB * MB + MB
    )
    assert (
        body_limit_bytes("POST", RESUME_UPLOAD, "multipart/form-data", s)
        == s.MAX_RESUME_UPLOAD_SIZE_MB * MB + MB
    )
    assert (
        body_limit_bytes("POST", audio, "application/json", s)
        == s.MAX_REQUEST_BODY_KB * KB
    )
    assert (
        body_limit_bytes("POST", audio, "application/x-www-form-urlencoded", s)
        == s.MAX_FORM_BODY_KB * KB
    )
    assert (
        body_limit_bytes("POST", LOGIN, "multipart/form-data", s)
        == s.MAX_REQUEST_BODY_KB * KB
    )
    assert (
        body_limit_bytes("GET", audio, "multipart/form-data", s)
        == s.MAX_REQUEST_BODY_KB * KB
    )
    assert body_limit_bytes("POST", "/x", "", s) == s.MAX_REQUEST_BODY_KB * KB
    assert (
        body_limit_bytes(
            "POST", "/x", "Application/X-WWW-Form-Urlencoded; charset=utf-8", s
        )
        == s.MAX_FORM_BODY_KB * KB
    )
    assert json.dumps(TOO_LARGE)  # detail is a plain, static string
    assert body_limit.TOO_LARGE_DETAIL == "Request body too large."
