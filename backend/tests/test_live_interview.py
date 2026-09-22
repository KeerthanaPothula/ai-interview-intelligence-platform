"""Tests for live conversational AI interviewer endpoints."""

import uuid

import pytest
import sqlalchemy.exc

from app.models.conversation import LiveInterviewSession
from app.models.interview import InterviewSession
from app.services import interview_service

_FIRST_Q = "Tell me about your most challenging project."
_NEXT_Q = "Can you elaborate on the technical decisions you made?"
_SUMMARY = "Strong performance overall with good technical depth."


def _mock_opening(job_role, job_description):
    return _FIRST_Q


def _mock_follow_up(**kwargs):
    return _NEXT_Q, 2


def _mock_summary(**kwargs):
    return _SUMMARY


_MOCK_EVALUATION = {
    "overall_score": 7.5,
    "communication_score": 8.0,
    "technical_score": 7.0,
    "problem_solving_score": 6.5,
    "confidence_score": 8.5,
    "strengths": '["Clear structure"]',
    "weaknesses": '["Could go deeper on trade-offs"]',
    "detailed_feedback": "Solid, well-structured answer.",
    "model_used": "gemini-test-model",
}


def _mock_evaluation(**kwargs):
    return _MOCK_EVALUATION.copy()


# ---------------------------------------------------------------------------
# POST /api/v1/live-interviews/
# ---------------------------------------------------------------------------


def test_start_live_interview_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Software Engineer",
            "job_description": "Python backend role with FastAPI",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "active"
    assert data["current_turn"] == 1
    assert data["max_turns"] == 3
    assert data["current_question"]["question_text"] == _FIRST_Q
    assert data["current_question"]["difficulty_level"] == 1


def test_start_live_interview_requires_auth(client):
    resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "A backend engineering role.",
            "max_turns": 3,
        },
    )
    assert resp.status_code == 401


def test_start_live_interview_validation(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    # job_description too short
    resp = client.post(
        "/api/v1/live-interviews/",
        json={"job_role": "Engineer", "job_description": "short", "max_turns": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/live-interviews/{id}/next-question
# ---------------------------------------------------------------------------


def test_next_question_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )
    # Submitting a response_text now triggers best-effort per-turn scoring
    # (interview_service.score_and_store_conversation_turn) — mocked here,
    # like every other Gemini call site in this file, so the test never
    # makes a real network call.
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation",
        _mock_evaluation,
    )

    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"response_text": "I built a distributed caching system at scale."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["current_turn"] == 2
    assert data["current_question"]["question_text"] == _NEXT_Q
    assert data["current_question"]["difficulty_level"] == 2


def test_next_question_wrong_session(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )
    resp = client.post(
        f"/api/v1/live-interviews/{uuid.uuid4()}/next-question",
        json={"response_text": "answer"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_next_question_requires_auth(client):
    resp = client.post(
        f"/api/v1/live-interviews/{uuid.uuid4()}/next-question",
        json={"response_text": "answer"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/live-interviews/{id}/conversation
# ---------------------------------------------------------------------------


def test_get_conversation_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    resp = client.get(
        f"/api/v1/live-interviews/{session_id}/conversation",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["turns"]) == 1
    assert data["turns"][0]["question_text"] == _FIRST_Q


def test_get_conversation_wrong_session(client, auth_headers):
    resp = client.get(
        f"/api/v1/live-interviews/{uuid.uuid4()}/conversation",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/live-interviews/{id}/end
# ---------------------------------------------------------------------------


def test_end_interview_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/end",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "completed"
    assert data["summary"] == _SUMMARY
    assert data["total_turns"] == 1


def test_end_interview_double_end(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    client.post(f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers)
    resp2 = client.post(
        f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers
    )
    assert resp2.status_code == 409


def test_end_interview_requires_auth(client):
    resp = client.post(f"/api/v1/live-interviews/{uuid.uuid4()}/end")
    assert resp.status_code == 401


def test_end_interview_returns_502_not_500_when_gemini_returns_no_usable_text(
    client, auth_headers, monkeypatch
):
    """Integration-level regression test for the confirmed production bug:
    a Gemini response with text=None (blocked by content/safety filtering)
    for the summary prompt must surface as a clean 502 through the
    AppException handler, never as an unhandled AttributeError reaching the
    global 500 handler."""
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    # Exercise the real generate_interview_summary implementation (not a
    # mock of the whole function) with a fake Gemini client whose response
    # has no usable text — this is what actually broke in production.
    class _FakeResponse:
        text = None

    class _FakeModels:
        def generate_content(self, model, contents):
            return _FakeResponse()

    class _FakeClient:
        models = _FakeModels()

    monkeypatch.setattr(
        "app.services.interview_conversation_service._get_client",
        lambda: _FakeClient(),
    )

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] != "Internal server error."
    assert "Interview summary generation" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Mirroring into InterviewSession (so completed live interviews appear in
# GET /interviews and dashboard analytics)
# ---------------------------------------------------------------------------


def _start_and_end_live_interview(client, auth_headers, monkeypatch) -> str:
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Backend Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]
    end_resp = client.post(
        f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers
    )
    assert end_resp.status_code == 200, end_resp.text
    return session_id


def test_end_interview_creates_exactly_one_mirrored_interview_session(
    client, auth_headers, db, registered_user, monkeypatch
):
    live_session_id = _start_and_end_live_interview(client, auth_headers, monkeypatch)

    mirrored = (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == uuid.UUID(live_session_id))
        .all()
    )
    assert len(mirrored) == 1
    m = mirrored[0]
    assert m.user_id == uuid.UUID(registered_user["id"])
    assert m.job_role == "Backend Engineer"
    assert m.job_description == "Python backend engineering role."
    assert m.status == "completed"
    assert m.title == "Live Interview – Backend Engineer"


def test_mirrored_session_appears_in_sessions_list(
    client, auth_headers, monkeypatch
):
    _start_and_end_live_interview(client, auth_headers, monkeypatch)

    resp = client.get("/api/v1/interviews/", headers=auth_headers)
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "Live Interview – Backend Engineer" in titles
    matching = [s for s in resp.json() if s["title"] == "Live Interview – Backend Engineer"]
    assert matching[0]["status"] == "completed"


def test_repeated_mirroring_is_idempotent(
    client, auth_headers, db, monkeypatch
):
    """Simulates a backfill script re-processing an already-mirrored session."""
    live_session_id = _start_and_end_live_interview(client, auth_headers, monkeypatch)
    live_session = (
        db.query(LiveInterviewSession)
        .filter(LiveInterviewSession.id == uuid.UUID(live_session_id))
        .one()
    )

    first = interview_service.mirror_completed_live_session(db, live_session)
    second = interview_service.mirror_completed_live_session(db, live_session)
    third = interview_service.mirror_completed_live_session(db, live_session)

    assert first.id == second.id == third.id
    count = (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == live_session.id)
        .count()
    )
    assert count == 1


def test_end_interview_mirror_failure_does_not_fail_the_response(
    client, auth_headers, db, monkeypatch
):
    """A broken mirror step must not turn a successful interview completion
    into a failed API response — the candidate already finished the
    interview and must see their summary."""
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )

    def _broken_mirror(*_args, **_kwargs):
        raise RuntimeError("simulated DB failure while mirroring")

    monkeypatch.setattr(
        "app.services.interview_service.mirror_completed_live_session",
        _broken_mirror,
    )

    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "completed"
    assert data["summary"] == _SUMMARY

    # The live interview itself is still marked completed...
    live_session = (
        db.query(LiveInterviewSession)
        .filter(LiveInterviewSession.id == uuid.UUID(session_id))
        .one()
    )
    assert live_session.status == "completed"

    # ...but no mirror was created, since the mirror step failed.
    mirrored_count = (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == live_session.id)
        .count()
    )
    assert mirrored_count == 0


def test_live_session_id_unique_constraint_enforced_at_db_level(
    client, auth_headers, db, registered_user, monkeypatch
):
    """Bypasses interview_service.mirror_completed_live_session entirely to
    prove the uniqueness comes from the migration's DB constraint (model:
    InterviewSession.__table_args__ uq_interview_sessions_live_session_id),
    not merely from the service's own check-first logic."""
    live_session_id = _start_and_end_live_interview(client, auth_headers, monkeypatch)

    # A second InterviewSession inserted directly with the same
    # live_session_id must violate the unique constraint.
    duplicate = InterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        title="Duplicate mirror attempt",
        job_role="Backend Engineer",
        job_description="Python backend engineering role.",
        status="completed",
        live_session_id=uuid.UUID(live_session_id),
    )
    db.add(duplicate)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()
