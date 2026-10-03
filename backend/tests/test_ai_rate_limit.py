"""Per-user rate limit on Gemini-backed endpoints (enforce_ai_rate_limit)."""

import uuid

import pytest

from app.config import get_settings
from app.core.rate_limit import enforce_ai_rate_limit
from app.main import app
from tests.conftest import OTHER_USER, VALID_USER, _login

_JOB = {
    "job_role": "Engineer",
    "job_description": "Python backend engineering role.",
    "max_turns": 3,
}

# Every endpoint that calls Gemini in the request path.
AI_ENDPOINTS = [
    ("POST", "/api/v1/live-interviews/"),
    ("POST", "/api/v1/live-interviews/{sid}/next-question"),
    ("POST", "/api/v1/live-interviews/{sid}/end"),
    ("POST", "/api/v1/interviews/{sid}/report/generate"),
    ("POST", "/api/v1/interviews/{sid}/coaching-plan"),
    ("POST", "/api/v1/interviews/{sid}/questions/generate"),
    ("POST", "/api/v1/interviews/{sid}/follow-up-question"),
    ("POST", "/api/v1/documents/interviews/{sid}/generate-rag-questions"),
    ("GET", "/api/v1/documents/resume/analysis"),
]


@pytest.fixture
def ai_limit(monkeypatch):
    """Shrink the AI budget to `n` requests per minute for a test."""

    def _set(n):
        monkeypatch.setenv("RATE_LIMIT_AI_REQUESTS", str(n))
        monkeypatch.setenv("RATE_LIMIT_AI_WINDOW_SECONDS", "60")
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


@pytest.fixture
def opening_calls(monkeypatch):
    """Mock the Gemini opening question; returns how often it ran."""
    calls = []

    def _opening(job_role, job_description):
        calls.append(job_role)
        return "Tell me about yourself."

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _opening,
    )
    return calls


def _start(client, headers):
    return client.post("/api/v1/live-interviews/", json=_JOB, headers=headers)


def _bob_headers(client):
    client.post("/api/v1/auth/register", json=OTHER_USER)
    return {"Authorization": f"Bearer {_login(client, OTHER_USER)}"}


def test_requests_under_the_limit_succeed(
    client, auth_headers, ai_limit, opening_calls
):
    ai_limit(3)
    for _ in range(3):
        assert _start(client, auth_headers).status_code == 201
    assert len(opening_calls) == 3


def test_exceeding_the_limit_returns_429_with_retry_after(
    client, auth_headers, ai_limit, opening_calls
):
    ai_limit(2)
    for _ in range(2):
        _start(client, auth_headers)

    blocked = _start(client, auth_headers)

    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 61
    detail = blocked.json()["detail"]
    assert "too many AI requests" in detail
    assert "gemini" not in blocked.text.lower()
    assert len(opening_calls) == 2  # the blocked request never reached Gemini


def test_users_have_independent_buckets(client, auth_headers, ai_limit, opening_calls):
    ai_limit(1)
    assert _start(client, auth_headers).status_code == 201
    assert _start(client, auth_headers).status_code == 429

    bob = _bob_headers(client)
    assert _start(client, bob).status_code == 201
    assert _start(client, bob).status_code == 429


def test_unauthenticated_requests_cannot_claim_a_users_bucket(
    client, registered_user, auth_headers, ai_limit, opening_calls
):
    """No token, a forged token, or a client-supplied user id: all 401
    before the limiter — none of them spend (or bypass) a real user's budget."""
    ai_limit(1)
    uid = registered_user["id"]
    for headers in (
        {"X-User-Id": uid},
        {"Authorization": "Bearer not-a-real-token", "X-User-Id": uid},
        {"Authorization": f"Bearer {uid}"},
    ):
        resp = client.post(
            f"/api/v1/live-interviews/?user_id={uid}", json=_JOB, headers=headers
        )
        assert resp.status_code == 401, headers

    assert _start(client, auth_headers).status_code == 201  # budget untouched
    assert opening_calls == ["Engineer"]


def test_ip_login_rate_limit_still_applies_and_is_separate(
    client, registered_user, auth_headers, ai_limit, opening_calls, monkeypatch
):
    ai_limit(1)
    _start(client, auth_headers)
    assert _start(client, auth_headers).status_code == 429

    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "2")
    get_settings.cache_clear()
    bad = {"username": VALID_USER["email"], "password": "wrongpassword"}
    # auth_headers already spent one login attempt from this IP.
    assert client.post("/api/v1/auth/login", data=bad).status_code == 401
    blocked = client.post("/api/v1/auth/login", data=bad)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


@pytest.mark.parametrize(("method", "path"), AI_ENDPOINTS)
def test_every_gemini_endpoint_is_limited(client, auth_headers, ai_limit, method, path):
    ai_limit(1)
    url = path.format(sid=uuid.uuid4())
    # Whatever the first call returns (404 for a random session, etc.), it
    # spends the budget before the handler runs; the second is refused.
    client.request(method, url, json={}, headers=auth_headers)
    resp = client.request(method, url, json={}, headers=auth_headers)
    assert resp.status_code == 429, resp.text


def test_only_gemini_endpoints_carry_the_limiter():
    limited = {
        (method, route.path)
        for route in app.routes
        if any(
            d.dependency is enforce_ai_rate_limit
            for d in getattr(route, "dependencies", [])
        )
        for method in route.methods
    }
    assert limited == {(m, p.replace("{sid}", "{session_id}")) for m, p in AI_ENDPOINTS}


def test_reads_are_not_limited(client, auth_headers, ai_limit, opening_calls):
    ai_limit(1)
    sid = _start(client, auth_headers).json()["id"]
    assert _start(client, auth_headers).status_code == 429

    for path in (
        "/api/v1/live-interviews/active",
        f"/api/v1/live-interviews/{sid}/conversation",
        "/api/v1/interviews/",
        "/api/v1/analytics/overview",
    ):
        assert client.get(path, headers=auth_headers).status_code == 200, path


def test_a_full_interview_workflow_fits_the_default_limit(
    client, auth_headers, opening_calls, monkeypatch
):
    """Default settings: a 10-question live interview (11 AI requests) and
    its report never hit 429."""
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        lambda **kw: (f"Question {kw['current_turn'] + 1}?", 2),
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        lambda **kw: "Good interview.",
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation",
        lambda **kw: {
            "overall_score": 7.0,
            "communication_score": 7.0,
            "technical_score": 7.0,
            "problem_solving_score": 7.0,
            "confidence_score": 7.0,
            "strengths": "[]",
            "weaknesses": "[]",
            "detailed_feedback": "Fine.",
            "model_used": "test",
        },
    )
    statuses = []
    live = client.post(
        "/api/v1/live-interviews/", json={**_JOB, "max_turns": 10}, headers=auth_headers
    )
    statuses.append(live.status_code)
    sid = live.json()["id"]
    for n in range(1, 10):
        statuses.append(
            client.post(
                f"/api/v1/live-interviews/{sid}/next-question",
                json={"response_text": f"Answer {n}.", "turn_number": n},
                headers=auth_headers,
            ).status_code
        )
    statuses.append(
        client.post(
            f"/api/v1/live-interviews/{sid}/end",
            json={"response_text": "Answer 10."},
            headers=auth_headers,
        ).status_code
    )
    mirrored = client.get("/api/v1/interviews/", headers=auth_headers).json()[0]["id"]
    monkeypatch.setattr(
        "app.services.report_service.generate_session_report",
        lambda **kw: {"overall_performance": "Good.", "readiness_level": "Developing"},
    )
    statuses.append(
        client.post(
            f"/api/v1/interviews/{mirrored}/report/generate", headers=auth_headers
        ).status_code
    )

    assert 429 not in statuses, statuses
    assert statuses == [201] + [200] * 10 + [201]
