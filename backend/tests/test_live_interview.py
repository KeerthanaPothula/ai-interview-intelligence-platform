"""Tests for live conversational AI interviewer endpoints."""

import uuid

import pytest
import sqlalchemy.exc

from app.models.analysis import RESPONSE_STATUS_UPLOADED, AudioResponse
from app.models.conversation import LiveInterviewSession
from app.models.interview import (
    QUESTION_SOURCE_AI_GENERATED,
    InterviewSession,
    Question,
)
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


def test_mirrored_session_appears_in_sessions_list(client, auth_headers, monkeypatch):
    _start_and_end_live_interview(client, auth_headers, monkeypatch)

    resp = client.get("/api/v1/interviews/", headers=auth_headers)
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "Live Interview – Backend Engineer" in titles
    matching = [
        s for s in resp.json() if s["title"] == "Live Interview – Backend Engineer"
    ]
    assert matching[0]["status"] == "completed"


def test_repeated_mirroring_is_idempotent(client, auth_headers, db, monkeypatch):
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


# ---------------------------------------------------------------------------
# IDOR: audio_response_id ownership (security audit finding)
#
# next_question/end_interview accept an optional audio_response_id and
# write it straight onto the candidate's own ConversationTurn. Without an
# ownership check, a caller could link an arbitrary AudioResponse UUID —
# including one belonging to a different user — since the column's only
# DB-level constraint is the FK (the row must exist), never that the
# caller owns it.
# ---------------------------------------------------------------------------


def _create_foreign_audio_response(client, db) -> uuid.UUID:
    """Register a second user and create an AudioResponse owned by them —
    a resource the test's main candidate must never be able to reference."""
    other = client.post(
        "/api/v1/auth/register",
        json={
            "email": "victim@example.com",
            "password": "securepassword1",
            "full_name": "Victim User",
        },
    )
    assert other.status_code == 201, other.text
    other_user_id = uuid.UUID(other.json()["id"])

    session = InterviewSession(
        user_id=other_user_id,
        title="Victim's session",
        job_role="Engineer",
        job_description="A backend engineering role.",
    )
    db.add(session)
    db.flush()
    question = Question(
        session_id=session.id,
        body="Tell me about yourself.",
        sequence_order=1,
        source=QUESTION_SOURCE_AI_GENERATED,
    )
    db.add(question)
    db.flush()
    response_id = uuid.uuid4()
    response = AudioResponse(
        id=response_id,
        session_id=session.id,
        question_id=question.id,
        user_id=other_user_id,
        file_path=f"{session.id}/{response_id}.webm",
        file_size_bytes=4096,
        mime_type="audio/webm",
        status=RESPONSE_STATUS_UPLOADED,
    )
    db.add(response)
    db.commit()
    return response_id


def test_next_question_rejects_audio_response_id_owned_by_another_user(
    client, auth_headers, db, monkeypatch
):
    foreign_id = _create_foreign_audio_response(client, db)

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
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
        json={"audio_response_id": str(foreign_id)},
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Audio response not found."


def test_next_question_rejects_nonexistent_audio_response_id(
    client, auth_headers, monkeypatch
):
    """A garbage id must produce a clean 404, not an unhandled IntegrityError
    from the foreign key constraint at commit time."""
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

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"audio_response_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


def test_next_question_accepts_audio_response_id_owned_by_caller(
    client, auth_headers, registered_user, db, monkeypatch
):
    """Regression: a legitimately-owned audio_response_id must still work —
    the fix must reject only cross-user references, not the field itself."""
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
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

    own_session = InterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        title="My own session",
        job_role="Engineer",
        job_description="A backend engineering role.",
    )
    db.add(own_session)
    db.flush()
    own_question = Question(
        session_id=own_session.id,
        body="Tell me about yourself.",
        sequence_order=1,
        source=QUESTION_SOURCE_AI_GENERATED,
    )
    db.add(own_question)
    db.flush()
    own_response_id = uuid.uuid4()
    db.add(
        AudioResponse(
            id=own_response_id,
            session_id=own_session.id,
            question_id=own_question.id,
            user_id=uuid.UUID(registered_user["id"]),
            file_path=f"{own_session.id}/{own_response_id}.webm",
            file_size_bytes=4096,
            mime_type="audio/webm",
            status=RESPONSE_STATUS_UPLOADED,
        )
    )
    db.commit()

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"audio_response_id": str(own_response_id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


def test_end_interview_rejects_audio_response_id_owned_by_another_user(
    client, auth_headers, db, monkeypatch
):
    foreign_id = _create_foreign_audio_response(client, db)

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

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/end",
        json={"audio_response_id": str(foreign_id)},
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Audio response not found."


# ---------------------------------------------------------------------------
# mirror_completed_live_session — transient DB error retry
# (production reliability audit finding)
#
# Once end_interview sets status=COMPLETED, a second /end call 409s
# immediately and never reaches the mirror step again — there is no other
# path that retries it. Without a retry here, a one-off dropped/stale DB
# connection on the mirror insert permanently and silently hides an
# otherwise-successfully-completed interview from /interviews, the
# dashboard, readiness, and coaching, with no error ever surfaced to
# anyone.
# ---------------------------------------------------------------------------


def _make_completed_live_session(db, registered_user) -> LiveInterviewSession:
    live_session = LiveInterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        job_role="Engineer",
        job_description="A backend role.",
        status="completed",
    )
    db.add(live_session)
    db.commit()
    db.refresh(live_session)
    return live_session


def test_mirror_completed_live_session_retries_transient_db_error(
    db, registered_user, monkeypatch
):
    live_session = _make_completed_live_session(db, registered_user)

    real_commit = db.commit
    call_count = 0

    def _flaky_commit():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise sqlalchemy.exc.OperationalError(
                "INSERT", {}, Exception("server closed the connection unexpectedly")
            )
        real_commit()

    monkeypatch.setattr(db, "commit", _flaky_commit)

    result = interview_service.mirror_completed_live_session(db, live_session)

    assert call_count == 3
    assert result.live_session_id == live_session.id
    assert (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == live_session.id)
        .count()
        == 1
    )


def test_mirror_completed_live_session_gives_up_after_max_attempts(
    db, registered_user, monkeypatch
):
    """The retry is bounded — it must eventually raise, not loop forever —
    and end_interview's existing try/except (see
    test_end_interview_mirror_failure_does_not_fail_the_response) is what
    keeps that raise from breaking a successful interview completion."""
    live_session = _make_completed_live_session(db, registered_user)

    call_count = 0

    def _always_fails():
        nonlocal call_count
        call_count += 1
        raise sqlalchemy.exc.OperationalError(
            "INSERT", {}, Exception("server closed the connection unexpectedly")
        )

    monkeypatch.setattr(db, "commit", _always_fails)

    with pytest.raises(sqlalchemy.exc.OperationalError):
        interview_service.mirror_completed_live_session(db, live_session)

    assert call_count == 3
    assert (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == live_session.id)
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# GET /live-interviews/active — resuming after a refresh / navigation away
# ---------------------------------------------------------------------------

ACTIVE = "/api/v1/live-interviews/active"


def test_active_interview_is_null_when_none_in_progress(client, auth_headers):
    resp = client.get(ACTIVE, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() is None


def test_active_interview_restores_turns_without_creating_any(
    client, auth_headers, db, monkeypatch
):
    from app.models.conversation import ConversationTurn, ConversationTurnAnalysis

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation", _mock_evaluation
    )
    sid = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/live-interviews/{sid}/next-question",
        json={"response_text": "My first answer."},
        headers=auth_headers,
    )
    turns_before = db.query(ConversationTurn).count()
    scores_before = db.query(ConversationTurnAnalysis).count()

    for _ in range(2):  # repeated reloads must stay read-only
        data = client.get(ACTIVE, headers=auth_headers).json()
        assert data["id"] == sid
        assert data["status"] == "active"
        assert [t["turn_number"] for t in data["turns"]] == [1, 2]
        assert data["turns"][0]["response_text"] == "My first answer."
        assert data["current_question"]["turn_number"] == 2

    assert db.query(ConversationTurn).count() == turns_before == 2
    assert db.query(ConversationTurnAnalysis).count() == scores_before == 1
    live = db.get(LiveInterviewSession, uuid.UUID(sid))
    db.refresh(live)
    assert live.status == "active"  # resuming never completes the interview


def test_completed_interview_is_not_active(client, auth_headers, monkeypatch):
    _start_and_end_live_interview(client, auth_headers, monkeypatch)
    assert client.get(ACTIVE, headers=auth_headers).json() is None


def test_active_interview_is_latest_and_owner_only(
    client, auth_headers, db, registered_user
):
    from datetime import datetime, timedelta, timezone

    from app.models.conversation import ConversationTurn
    from tests.test_analytics_live import _bob_headers

    now = datetime.now(timezone.utc)
    ids = []
    for age_days in (2, 1):
        live = LiveInterviewSession(
            user_id=uuid.UUID(registered_user["id"]),
            job_role="Engineer",
            job_description="Python backend engineering role.",
            max_turns=3,
            current_turn=1,
            status="active",
            created_at=now - timedelta(days=age_days),
        )
        db.add(live)
        db.flush()
        db.add(
            ConversationTurn(live_session_id=live.id, turn_number=1, question_text="Q1")
        )
        ids.append(str(live.id))
    db.commit()

    assert client.get(ACTIVE, headers=auth_headers).json()["id"] == ids[1]
    assert client.get(ACTIVE, headers=_bob_headers(client)).json() is None


def test_active_interview_requires_auth(client):
    assert client.get(ACTIVE).status_code == 401


# ---------------------------------------------------------------------------
# next-question retry / idempotency (turn_number)
# ---------------------------------------------------------------------------


@pytest.fixture
def live_mocks(monkeypatch):
    """Mock every Gemini call; returns the list of answers sent for scoring."""
    scored: list[str] = []

    def _counting_evaluation(**kwargs):
        scored.append(kwargs["transcript_text"])
        return _MOCK_EVALUATION.copy()

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        lambda **kw: (f"Question {kw['current_turn'] + 1}?", 2),
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation", _counting_evaluation
    )
    return scored


def _start(client, auth_headers, max_turns=3) -> str:
    return client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Engineer",
            "job_description": "Python backend engineering role.",
            "max_turns": max_turns,
        },
        headers=auth_headers,
    ).json()["id"]


def _next(client, auth_headers, sid, **body):
    return client.post(
        f"/api/v1/live-interviews/{sid}/next-question", json=body, headers=auth_headers
    )


def _turns(db, sid):
    from app.models.conversation import ConversationTurn

    db.expire_all()
    return (
        db.query(ConversationTurn)
        .filter(ConversationTurn.live_session_id == uuid.UUID(sid))
        .order_by(ConversationTurn.turn_number)
        .all()
    )


def _score_count(db):
    from app.models.conversation import ConversationTurnAnalysis

    return db.query(ConversationTurnAnalysis).count()


def test_first_submission_creates_exactly_one_turn(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers)
    resp = _next(client, auth_headers, sid, response_text="Answer one.", turn_number=1)

    assert resp.status_code == 200, resp.text
    assert resp.json()["current_turn"] == 2
    assert [(t.turn_number, t.response_text) for t in _turns(db, sid)] == [
        (1, "Answer one."),
        (2, None),
    ]
    assert live_mocks == ["Answer one."]
    assert _score_count(db) == 1


def test_retry_of_a_submitted_answer_creates_no_turn_and_no_score(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers)
    first = _next(client, auth_headers, sid, response_text="Answer one.", turn_number=1)
    # The response above was "lost": the client retries the identical request.
    retry = _next(client, auth_headers, sid, response_text="Answer one.", turn_number=1)

    assert retry.status_code == 200, retry.text
    assert retry.json()["current_turn"] == 2
    assert retry.json()["current_question"] == first.json()["current_question"]
    assert len(_turns(db, sid)) == 2
    assert live_mocks == ["Answer one."]  # already scored; never scored again
    assert _score_count(db) == 1


def test_retry_never_attaches_the_answer_to_the_next_question(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers)
    _next(client, auth_headers, sid, response_text="Answer one.", turn_number=1)

    for text in ("Answer one.", "An edited answer one."):
        _next(client, auth_headers, sid, response_text=text, turn_number=1)

    turns = _turns(db, sid)
    assert turns[0].response_text == "Answer one."
    assert turns[1].response_text is None
    assert _score_count(db) == 1


def test_retry_with_a_different_answer_is_rejected_not_moved(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers)
    _next(client, auth_headers, sid, response_text="Answer one.", turn_number=1)
    resp = _next(client, auth_headers, sid, response_text="Edited.", turn_number=1)

    assert resp.status_code == 409
    assert "already has a different saved answer" in resp.json()["detail"]


def test_turn_number_ahead_of_the_interview_is_rejected(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers)
    resp = _next(client, auth_headers, sid, response_text="Answer.", turn_number=2)

    assert resp.status_code == 409
    assert [t.response_text for t in _turns(db, sid)] == [None]
    assert live_mocks == []


def test_retry_after_the_final_question_was_created_still_replays(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers, max_turns=3)
    _next(client, auth_headers, sid, response_text="A1.", turn_number=1)
    _next(client, auth_headers, sid, response_text="A2.", turn_number=2)
    retry = _next(client, auth_headers, sid, response_text="A2.", turn_number=2)

    assert retry.status_code == 200, retry.text
    assert retry.json()["current_turn"] == 3
    assert len(_turns(db, sid)) == 3


def _race(client, auth_headers, sid, monkeypatch, racer=None, **body):
    """Run a second request (identical unless `racer` gives its body) to
    completion while the first is mid-flight — after it saved/scored the
    answer, before it inserts the next turn: the window in which both used
    to insert the same turn."""
    racing = []

    def _follow_up(**kwargs):
        if not racing:
            racing.append(None)  # before the call: the racer must not race too
            racing[0] = _next(client, auth_headers, sid, **(racer or body))
        return f"Question {kwargs['current_turn'] + 1}?", 2

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _follow_up,
    )
    first = _next(client, auth_headers, sid, **body)
    return first, racing[0]


def test_concurrent_submissions_for_the_same_turn_create_one_next_turn(
    client, auth_headers, db, live_mocks, monkeypatch
):
    sid = _start(client, auth_headers)
    a, b = _race(
        client, auth_headers, sid, monkeypatch, response_text="Same.", turn_number=1
    )

    assert a.status_code == 200, a.text
    assert b.status_code == 200, b.text
    assert a.json()["current_question"]["id"] == b.json()["current_question"]["id"]
    assert [t.turn_number for t in _turns(db, sid)] == [1, 2]
    assert _turns(db, sid)[0].response_text == "Same."
    assert live_mocks == ["Same."]
    assert _score_count(db) == 1


def _race_before_claim(client, auth_headers, sid, racer, send=None, **body):
    """Both requests read turn 1 as unanswered: the racer runs to completion
    just as the first is about to execute its answer-claiming UPDATE.
    `send` is the request both make (default: next-question)."""
    send = send or _next
    from sqlalchemy import event

    from tests.conftest import TEST_ENGINE

    racing = []

    def _hook(conn, cursor, statement, params, context, executemany):
        if not racing and statement.lstrip().upper().startswith(
            "UPDATE CONVERSATION_TURNS"
        ):
            racing.append(None)
            racing[0] = send(client, auth_headers, sid, **racer)

    event.listen(TEST_ENGINE, "before_cursor_execute", _hook)
    try:
        first = send(client, auth_headers, sid, **body)
    finally:
        event.remove(TEST_ENGINE, "before_cursor_execute", _hook)
    return first, racing[0]


def _assert_only_accepted_answer_kept(db, sid, live_mocks, accepted, rejected):
    """Exactly one winner; its answer is the one persisted and scored."""
    assert accepted.status_code == 200, accepted.text
    assert rejected.status_code == 409, rejected.text
    assert "already has a different saved answer" in rejected.json()["detail"]
    turns = _turns(db, sid)
    assert [t.turn_number for t in turns] == [1, 2]
    winner = accepted.json()["turns"][0]["response_text"]
    assert turns[0].response_text == winner
    assert live_mocks == [winner]  # the rejected answer was never scored
    assert _score_count(db) == 1


def test_concurrent_different_answer_after_the_first_was_saved_gets_409(
    client, auth_headers, db, live_mocks, monkeypatch
):
    sid = _start(client, auth_headers)
    a, b = _race(
        client,
        auth_headers,
        sid,
        monkeypatch,
        racer={"response_text": "Second.", "turn_number": 1},
        response_text="First.",
        turn_number=1,
    )
    _assert_only_accepted_answer_kept(db, sid, live_mocks, accepted=a, rejected=b)
    assert _turns(db, sid)[0].response_text == "First."


def test_concurrent_different_answers_both_unanswered_first_claim_wins(
    client, auth_headers, db, live_mocks
):
    """The racer claims the turn first, so the original request — which had
    also read the turn as unanswered — must not overwrite it."""
    sid = _start(client, auth_headers)
    a, b = _race_before_claim(
        client,
        auth_headers,
        sid,
        racer={"response_text": "Second.", "turn_number": 1},
        response_text="First.",
        turn_number=1,
    )
    _assert_only_accepted_answer_kept(db, sid, live_mocks, accepted=b, rejected=a)
    assert _turns(db, sid)[0].response_text == "Second."


def test_concurrent_same_answer_both_unanswered_is_one_answer(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers)
    a, b = _race_before_claim(
        client,
        auth_headers,
        sid,
        racer={"response_text": "Same.", "turn_number": 1},
        response_text="Same.",
        turn_number=1,
    )
    assert (a.status_code, b.status_code) == (200, 200), (a.text, b.text)
    assert [t.response_text for t in _turns(db, sid)] == ["Same.", None]
    assert live_mocks == ["Same."]
    assert _score_count(db) == 1


def test_different_answer_for_the_still_current_turn_gets_409(
    client, auth_headers, db, live_mocks, monkeypatch
):
    """After the answer is saved but question generation failed, the turn is
    still current: an edited answer is rejected, the saved one kept."""
    sid = _start(client, auth_headers)

    def _boom(**kwargs):
        raise RuntimeError("Gemini down")

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _boom,
    )
    with pytest.raises(RuntimeError):
        _next(client, auth_headers, sid, response_text="Saved.", turn_number=1)

    resp = _next(client, auth_headers, sid, response_text="Edited.", turn_number=1)

    assert resp.status_code == 409, resp.text
    assert [t.response_text for t in _turns(db, sid)] == ["Saved."]
    assert live_mocks == ["Saved."]


def test_concurrent_submissions_without_turn_number_are_also_safe(
    client, auth_headers, db, live_mocks, monkeypatch
):
    sid = _start(client, auth_headers)
    a, b = _race(client, auth_headers, sid, monkeypatch, response_text="Same.")

    assert (a.status_code, b.status_code) == (200, 200), a.text
    assert [t.turn_number for t in _turns(db, sid)] == [1, 2]
    assert _score_count(db) == 1


def test_turn_numbers_are_unique_per_session_at_db_level(db, registered_user):
    from app.models.conversation import ConversationTurn

    live = LiveInterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        job_role="Engineer",
        job_description="Python backend engineering role.",
        current_turn=1,
        max_turns=3,
    )
    db.add(live)
    db.flush()
    for _ in range(2):
        db.add(
            ConversationTurn(live_session_id=live.id, turn_number=1, question_text="Q")
        )
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()


def test_each_question_in_an_interview_is_answered_in_turn(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers, max_turns=3)
    for n in (1, 2):
        resp = _next(client, auth_headers, sid, response_text=f"A{n}.", turn_number=n)
        assert resp.status_code == 200, resp.text
        assert resp.json()["current_turn"] == n + 1
    end = client.post(
        f"/api/v1/live-interviews/{sid}/end",
        json={"response_text": "A3."},
        headers=auth_headers,
    )
    assert end.status_code == 200, end.text

    assert [(t.turn_number, t.response_text) for t in _turns(db, sid)] == [
        (1, "A1."),
        (2, "A2."),
        (3, "A3."),
    ]
    assert live_mocks == ["A1.", "A2.", "A3."]
    assert _score_count(db) == 3


def test_retry_after_failed_question_generation_still_advances(
    client, auth_headers, db, live_mocks, monkeypatch
):
    """The answer is saved before generation, so the turn stays current; a
    retry for it must proceed normally, not be treated as already answered."""
    sid = _start(client, auth_headers)

    def _boom(**kwargs):
        raise RuntimeError("Gemini down")

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _boom,
    )
    with pytest.raises(RuntimeError):
        _next(client, auth_headers, sid, response_text="Saved.", turn_number=1)
    assert [t.response_text for t in _turns(db, sid)] == ["Saved."]

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )
    resp = _next(client, auth_headers, sid, response_text="Saved.", turn_number=1)
    assert resp.status_code == 200, resp.text
    assert len(_turns(db, sid)) == 2
    assert live_mocks == ["Saved."]


# ---------------------------------------------------------------------------
# End Interview: first-write-wins for the final answer
# ---------------------------------------------------------------------------


def _end(client, auth_headers, sid, **body):
    return client.post(
        f"/api/v1/live-interviews/{sid}/end", json=body, headers=auth_headers
    )


def _live_session(db, sid):
    db.expire_all()
    return db.get(LiveInterviewSession, uuid.UUID(sid))


def _race_end_during_summary(client, auth_headers, sid, monkeypatch, racer, **body):
    """The racer End runs to completion while the first End is generating
    its summary: after it saved/scored the final answer, before it
    completes the session."""
    racing = []

    def _summary(**kwargs):
        if not racing:
            racing.append(None)
            racing[0] = _end(client, auth_headers, sid, **racer)
        return "Good interview."

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _summary,
    )
    first = _end(client, auth_headers, sid, **body)
    return first, racing[0]


def _assert_one_final_answer(db, sid, live_mocks, accepted, rejected):
    """Exactly one winner; its answer is the one persisted and scored, and
    the interview is completed."""
    assert accepted.status_code == 200, accepted.text
    assert rejected.status_code == 409, rejected.text
    assert "already has a different saved answer" in rejected.json()["detail"]
    winner = accepted.json()["turns"][-1]["response_text"]
    assert [t.response_text for t in _turns(db, sid)] == [winner]
    assert live_mocks == [winner]  # the rejected answer was never scored
    assert _score_count(db) == 1
    assert _live_session(db, sid).status == "completed"


def test_end_saves_scores_and_completes(client, auth_headers, db, live_mocks):
    sid = _start(client, auth_headers)
    resp = _end(client, auth_headers, sid, response_text="Final answer.")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"
    assert resp.json()["turns"][-1]["response_text"] == "Final answer."
    assert [t.response_text for t in _turns(db, sid)] == ["Final answer."]
    assert live_mocks == ["Final answer."]
    assert _live_session(db, sid).completed_at is not None


def test_concurrent_ends_with_different_answers_one_gets_409(
    client, auth_headers, db, live_mocks, monkeypatch
):
    sid = _start(client, auth_headers)
    a, b = _race_end_during_summary(
        client,
        auth_headers,
        sid,
        monkeypatch,
        racer={"response_text": "Second."},
        response_text="First.",
    )
    _assert_one_final_answer(db, sid, live_mocks, accepted=a, rejected=b)
    assert _turns(db, sid)[0].response_text == "First."


def test_concurrent_ends_both_unanswered_first_claim_wins(
    client, auth_headers, db, live_mocks
):
    sid = _start(client, auth_headers)
    a, b = _race_before_claim(
        client,
        auth_headers,
        sid,
        racer={"response_text": "Second."},
        send=_end,
        response_text="First.",
    )
    _assert_one_final_answer(db, sid, live_mocks, accepted=b, rejected=a)
    assert _turns(db, sid)[0].response_text == "Second."


def test_concurrent_ends_with_the_same_answer_are_idempotent(
    client, auth_headers, db, live_mocks
):
    """Both succeed; one saved answer, one score, one mirrored session, and
    the first completion (its completed_at) is not rewritten."""
    sid = _start(client, auth_headers)
    completed_at = []

    def _send(client, auth_headers, sid, **body):
        resp = _end(client, auth_headers, sid, **body)
        completed_at.append(_live_session(db, sid).completed_at)
        return resp

    a, b = _race_before_claim(
        client,
        auth_headers,
        sid,
        racer={"response_text": "Same."},
        send=_send,
        response_text="Same.",
    )

    assert (a.status_code, b.status_code) == (200, 200), (a.text, b.text)
    assert [t.response_text for t in _turns(db, sid)] == ["Same."]
    assert live_mocks == ["Same."]
    assert _score_count(db) == 1
    assert completed_at[0] is not None
    assert completed_at[0] == completed_at[1]  # the racer's completion stands
    mirrored = db.query(InterviewSession).filter(
        InterviewSession.live_session_id == uuid.UUID(sid)
    )
    assert mirrored.count() == 1


def test_later_end_with_a_different_final_answer_gets_409(
    client, auth_headers, db, live_mocks, monkeypatch
):
    """The final answer was saved but summary generation failed, so the
    interview is still active: a retry may not replace that answer, while a
    retry with the same answer completes normally."""
    sid = _start(client, auth_headers)

    def _boom(**kwargs):
        raise RuntimeError("Gemini down")

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _boom,
    )
    with pytest.raises(RuntimeError):
        _end(client, auth_headers, sid, response_text="Saved.")
    assert _live_session(db, sid).status == "active"

    different = _end(client, auth_headers, sid, response_text="Edited.")
    assert different.status_code == 409, different.text
    assert [t.response_text for t in _turns(db, sid)] == ["Saved."]

    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    same = _end(client, auth_headers, sid, response_text="Saved.")
    assert same.status_code == 200, same.text
    assert live_mocks == ["Saved."]
    assert _score_count(db) == 1
    assert _live_session(db, sid).status == "completed"


def test_end_after_completion_still_returns_already_completed(
    client, auth_headers, db, live_mocks
):
    """The frontend's lost-End-response recovery keys off this 409."""
    sid = _start(client, auth_headers)
    assert _end(client, auth_headers, sid, response_text="A.").status_code == 200
    for body in ({"response_text": "A."}, {"response_text": "B."}, {}):
        resp = _end(client, auth_headers, sid, **body)
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Interview session is already completed"
    assert [t.response_text for t in _turns(db, sid)] == ["A."]
    assert live_mocks == ["A."]
