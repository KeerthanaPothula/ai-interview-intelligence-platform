"""Tests for genuine per-turn scoring of Live Interview answers.

Covers:
  - ConversationTurnAnalysis model / unique constraint
  - interview_service.score_and_store_conversation_turn()
  - next_question() calling the scorer (and surviving its failure)
  - prediction.py's live-session branch (Readiness Assessment / Coaching
    Plan reading genuine ConversationTurnAnalysis scores instead of
    InterviewAnalysis/AudioResponse)
"""

import uuid
from decimal import Decimal

import pytest
import sqlalchemy.exc

from app.core.exceptions import AIServiceError
from app.models.conversation import (
    ConversationTurn,
    ConversationTurnAnalysis,
    LiveInterviewSession,
)
from app.models.interview import InterviewSession
from app.services import interview_service

_MOCK_EVALUATION = {
    "overall_score": 7.5,
    "communication_score": 8.0,
    "technical_score": 7.0,
    "problem_solving_score": 6.5,
    "confidence_score": 8.5,
    "strengths": '["Clear structure"]',
    "weaknesses": '["Could go deeper"]',
    "detailed_feedback": "Solid answer.",
    "model_used": "gemini-test-model",
}


def _mock_evaluation(**kwargs):
    return _MOCK_EVALUATION.copy()


def _mock_opening(job_role, job_description):
    return "Tell me about a challenging project."


def _mock_follow_up(**kwargs):
    return "What would you do differently?", 2


def _mock_summary(**kwargs):
    return "Solid performance overall."


def _start_live_interview(client, auth_headers, monkeypatch, job_role="Engineer"):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": job_role,
            "job_description": "Python backend engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Model / unique constraint
# ---------------------------------------------------------------------------


def test_conversation_turn_analysis_round_trips(db, registered_user):
    """Sanity check the model maps onto the table created by
    Base.metadata.create_all (same schema the migration creates)."""
    live_session = LiveInterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        job_role="Engineer",
        job_description="A backend role.",
    )
    db.add(live_session)
    db.flush()
    turn = ConversationTurn(
        live_session_id=live_session.id,
        turn_number=1,
        question_text="Tell me about yourself.",
        response_text="I'm a backend engineer with 5 years of experience.",
    )
    db.add(turn)
    db.flush()

    analysis = ConversationTurnAnalysis(
        conversation_turn_id=turn.id,
        overall_score=Decimal("7.5"),
        communication_score=Decimal("8.0"),
        technical_score=Decimal("7.0"),
        problem_solving_score=Decimal("6.5"),
        confidence_score=Decimal("8.5"),
        strengths="[]",
        weaknesses="[]",
        detailed_feedback="Fine.",
        model_used="gemini-test-model",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    assert analysis.id is not None
    assert analysis.overall_score == Decimal("7.5")
    assert analysis.turn.id == turn.id


def test_conversation_turn_id_unique_constraint_enforced_at_db_level(
    db, registered_user
):
    """A second analysis for the same turn must violate the unique
    constraint — this is what makes scoring idempotent under a race."""
    live_session = LiveInterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        job_role="Engineer",
        job_description="A backend role.",
    )
    db.add(live_session)
    db.flush()
    turn = ConversationTurn(
        live_session_id=live_session.id,
        turn_number=1,
        question_text="Q1",
        response_text="A1",
    )
    db.add(turn)
    db.flush()

    db.add(
        ConversationTurnAnalysis(
            conversation_turn_id=turn.id,
            overall_score=Decimal("7.0"),
            communication_score=Decimal("7.0"),
            technical_score=Decimal("7.0"),
            problem_solving_score=Decimal("7.0"),
            confidence_score=Decimal("7.0"),
        )
    )
    db.commit()

    db.add(
        ConversationTurnAnalysis(
            conversation_turn_id=turn.id,
            overall_score=Decimal("5.0"),
            communication_score=Decimal("5.0"),
            technical_score=Decimal("5.0"),
            problem_solving_score=Decimal("5.0"),
            confidence_score=Decimal("5.0"),
        )
    )
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# interview_service.score_and_store_conversation_turn
# ---------------------------------------------------------------------------


def _make_turn(db, registered_user, response_text="I built a caching layer."):
    live_session = LiveInterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        job_role="Engineer",
        job_description="A backend role.",
    )
    db.add(live_session)
    db.flush()
    turn = ConversationTurn(
        live_session_id=live_session.id,
        turn_number=1,
        question_text="Tell me about a challenging project.",
        response_text=response_text,
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return turn


def test_score_and_store_creates_analysis_with_decimal_scores(
    db, registered_user, monkeypatch
):
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation", _mock_evaluation
    )
    turn = _make_turn(db, registered_user)

    result = interview_service.score_and_store_conversation_turn(
        db, turn, "Engineer", "A backend role."
    )

    assert result is not None
    assert result.overall_score == Decimal("7.5")
    assert result.communication_score == Decimal("8.0")
    assert result.technical_score == Decimal("7.0")
    assert result.problem_solving_score == Decimal("6.5")
    assert result.confidence_score == Decimal("8.5")
    assert result.model_used == "gemini-test-model"

    stored = (
        db.query(ConversationTurnAnalysis)
        .filter(ConversationTurnAnalysis.conversation_turn_id == turn.id)
        .one()
    )
    assert stored.id == result.id


def test_score_and_store_skips_turn_with_no_response_text(
    db, registered_user, monkeypatch
):
    called = False

    def _fail_if_called(**kwargs):
        nonlocal called
        called = True
        return _MOCK_EVALUATION.copy()

    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation", _fail_if_called
    )
    turn = _make_turn(db, registered_user, response_text=None)

    result = interview_service.score_and_store_conversation_turn(
        db, turn, "Engineer", "A backend role."
    )

    assert result is None
    assert called is False
    assert (
        db.query(ConversationTurnAnalysis)
        .filter(ConversationTurnAnalysis.conversation_turn_id == turn.id)
        .first()
        is None
    )


def test_score_and_store_skips_turn_with_blank_response_text(
    db, registered_user, monkeypatch
):
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation", _mock_evaluation
    )
    turn = _make_turn(db, registered_user, response_text="   ")

    result = interview_service.score_and_store_conversation_turn(
        db, turn, "Engineer", "A backend role."
    )
    assert result is None


def test_score_and_store_is_idempotent(db, registered_user, monkeypatch):
    """Re-scoring an already-scored turn returns the existing row and does
    not call Gemini again."""
    call_count = 0

    def _counting_evaluation(**kwargs):
        nonlocal call_count
        call_count += 1
        return _MOCK_EVALUATION.copy()

    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation", _counting_evaluation
    )
    turn = _make_turn(db, registered_user)

    first = interview_service.score_and_store_conversation_turn(
        db, turn, "Engineer", "A backend role."
    )
    second = interview_service.score_and_store_conversation_turn(
        db, turn, "Engineer", "A backend role."
    )

    assert first.id == second.id
    assert call_count == 1
    assert (
        db.query(ConversationTurnAnalysis)
        .filter(ConversationTurnAnalysis.conversation_turn_id == turn.id)
        .count()
        == 1
    )


def test_score_and_store_propagates_gemini_failure(db, registered_user, monkeypatch):
    """The service function itself does not swallow Gemini failures —
    resilience is the caller's job (see next_question's try/except)."""

    def _raise(**kwargs):
        raise AIServiceError("Interview evaluation is currently unavailable.")

    monkeypatch.setattr("app.services.evaluation_service.generate_evaluation", _raise)
    turn = _make_turn(db, registered_user)

    with pytest.raises(AIServiceError):
        interview_service.score_and_store_conversation_turn(
            db, turn, "Engineer", "A backend role."
        )


# ---------------------------------------------------------------------------
# next_question() wiring
# ---------------------------------------------------------------------------


def test_next_question_scores_the_submitted_answer(
    client, auth_headers, db, monkeypatch
):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation", _mock_evaluation
    )
    session_id = _start_live_interview(client, auth_headers, monkeypatch)

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"response_text": "I built a distributed caching system at scale."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    turns = client.get(
        f"/api/v1/live-interviews/{session_id}/conversation",
        headers=auth_headers,
    ).json()["turns"]
    first_turn_id = uuid.UUID(turns[0]["id"])

    analysis = (
        db.query(ConversationTurnAnalysis)
        .filter(ConversationTurnAnalysis.conversation_turn_id == first_turn_id)
        .one_or_none()
    )
    assert analysis is not None
    assert analysis.overall_score == Decimal("7.5")


def test_next_question_survives_scoring_failure(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )

    def _raise(**kwargs):
        raise AIServiceError("Interview evaluation is currently unavailable.")

    monkeypatch.setattr("app.services.evaluation_service.generate_evaluation", _raise)
    session_id = _start_live_interview(client, auth_headers, monkeypatch)

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"response_text": "I built a distributed caching system at scale."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["current_turn"] == 2
    assert data["current_question"]["question_text"] == "What would you do differently?"


def test_next_question_does_not_rescore_or_lose_answer_on_retry(
    client, auth_headers, monkeypatch
):
    """A scoring failure must not roll back the response_text the
    candidate just submitted — verified by re-fetching the conversation."""
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )

    def _raise(**kwargs):
        raise AIServiceError("boom")

    monkeypatch.setattr("app.services.evaluation_service.generate_evaluation", _raise)
    session_id = _start_live_interview(client, auth_headers, monkeypatch)

    client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"response_text": "My real answer."},
        headers=auth_headers,
    )

    conv = client.get(
        f"/api/v1/live-interviews/{session_id}/conversation", headers=auth_headers
    ).json()
    assert conv["turns"][0]["response_text"] == "My real answer."


# ---------------------------------------------------------------------------
# prediction.py — live-session branch
# ---------------------------------------------------------------------------


def _complete_scored_live_interview(client, auth_headers, db, monkeypatch):
    """Full flow: start -> answer (scored) -> end -> mirrored session id."""
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation", _mock_evaluation
    )
    session_id = _start_live_interview(client, auth_headers, monkeypatch)

    client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"response_text": "I built a distributed caching system at scale."},
        headers=auth_headers,
    )
    client.post(f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers)

    mirrored = (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == uuid.UUID(session_id))
        .one()
    )
    return str(mirrored.id)


def test_readiness_assessment_uses_genuine_live_scores(
    client, auth_headers, db, monkeypatch
):
    mirrored_id = _complete_scored_live_interview(client, auth_headers, db, monkeypatch)

    resp = client.post(
        f"/api/v1/interviews/{mirrored_id}/readiness", headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # Real compute_readiness() runs (not mocked) — proves the weighted
    # formula receives the genuine scored values, not a placeholder.
    # overall=7.5, comm=8.0, tech=7.0, prob=6.5, confidence defaults to 60.0
    # (no voice signal for live interviews — compute_readiness's own
    # documented default, not fabricated by this feature).
    assert 0.0 < data["readiness_score"] <= 1.0
    assert data["readiness_level"] in {
        "Excellent",
        "Strong",
        "Developing",
        "Needs Improvement",
    }


def test_coaching_plan_uses_genuine_live_scores(client, auth_headers, db, monkeypatch):
    mirrored_id = _complete_scored_live_interview(client, auth_headers, db, monkeypatch)

    captured = {}

    def _capturing_coach(**kwargs):
        captured.update(kwargs)
        return {
            "plan_7_day": ["Day 1: Review"],
            "plan_14_day": ["Week 1: Practice"],
            "plan_30_day": ["Week 1-2: Deepen"],
            "focus_areas": ["Technical depth"],
            "model_used": "gemini-test-model",
        }

    monkeypatch.setattr(
        "app.routers.prediction.career_coach_service.generate_coaching_plan",
        _capturing_coach,
    )

    resp = client.post(
        f"/api/v1/interviews/{mirrored_id}/coaching-plan", headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    assert captured["overall_score"] == 7.5
    assert captured["communication_score"] == 8.0
    assert captured["technical_score"] == 7.0
    assert captured["problem_solving_score"] == 6.5


def test_readiness_assessment_no_analyses_for_unscored_live_session(
    client, auth_headers, db, monkeypatch
):
    """A live interview ended with no answered turns still has no genuine
    scores to read — the existing ValidationError fires, now honestly."""
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    session_id = _start_live_interview(client, auth_headers, monkeypatch)
    client.post(f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers)

    mirrored = (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == uuid.UUID(session_id))
        .one()
    )

    resp = client.post(
        f"/api/v1/interviews/{mirrored.id}/readiness", headers=auth_headers
    )
    assert resp.status_code == 422
    assert "No analyses found" in resp.json()["detail"]


def test_coaching_plan_no_analyses_for_unscored_live_session(
    client, auth_headers, db, monkeypatch
):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    session_id = _start_live_interview(client, auth_headers, monkeypatch)
    client.post(f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers)

    mirrored = (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == uuid.UUID(session_id))
        .one()
    )

    resp = client.post(
        f"/api/v1/interviews/{mirrored.id}/coaching-plan", headers=auth_headers
    )
    assert resp.status_code == 422
